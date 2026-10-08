/**
 * T2.6.2 批量粘贴 Job 化（前端侧）回归单测
 *
 * 覆盖：
 * - `batchProgressPercent`：进度百分比（0/部分/满/越界钳制/total 非法）；
 * - `isBatchJobTerminal` + `BATCH_JOB_TERMINAL_STATUSES`：Job 终态判定（对齐
 *   `models/entities.py` 状态机 QUEUED→RUNNING→SUCCEEDED/PARTIAL_SUCCESS/FAILED，
 *   QUEUED→CANCELLED（R0.4.2）；CANCELLED 必为终态，漏掉则被取消的批量作业无限轮询）；
 * - `read/save/clearBatchJobCheckpoint`：jobId 断点写入/读取/清除/非法降级/无 window 降级。
 *
 * 环境说明：与 t022 同口径——vitest 为 node 环境，用 vi.stubGlobal 注入最小
 * window+sessionStorage polyfill（不引入 jsdom，套件零新增依赖）。
 * 这些纯函数是「刷新不丢」的判定基座，故必须有直接用例，不能只靠 UI 间接覆盖。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

/** 最小 Storage polyfill：仅实现 getItem/setItem/removeItem/clear */
function makeStorage(): Storage {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    clear: () => void m.clear(),
    key: () => null,
    get length() {
      return m.size;
    },
  };
}

function installWindow(): { localStorage: Storage; sessionStorage: Storage } {
  const ls = makeStorage();
  const ss = makeStorage();
  vi.stubGlobal("window", { localStorage: ls, sessionStorage: ss });
  return { localStorage: ls, sessionStorage: ss };
}

const CHECKPOINT_KEY = "bothot_batch_job_checkpoint_v1";

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("T2.6.2 batchProgressPercent（已完成篇数占比）", () => {
  it("total<=0 → 0（未知总量不虚报进度）", async () => {
    const { batchProgressPercent } = await import("@/lib/api");
    expect(batchProgressPercent({ total: 0, succeeded: 0, failed: 0 })).toBe(0);
  });

  it("尚未有终态篇目 → 0", async () => {
    const { batchProgressPercent } = await import("@/lib/api");
    expect(batchProgressPercent({ total: 10, succeeded: 0, failed: 0 })).toBe(0);
  });

  it("部分完结：成功+失败计入分子（失败也算推进）", async () => {
    const { batchProgressPercent } = await import("@/lib/api");
    // 5 成功 + 1 失败 / 10 = 60%（只看停下来的篇目）
    expect(batchProgressPercent({ total: 10, succeeded: 5, failed: 1 })).toBe(60);
  });

  it("全部完结 → 100", async () => {
    const { batchProgressPercent } = await import("@/lib/api");
    expect(batchProgressPercent({ total: 4, succeeded: 3, failed: 1 })).toBe(100);
  });

  it("越界（成功+失败 > total）钳制在 100，不超条宽", async () => {
    const { batchProgressPercent } = await import("@/lib/api");
    expect(batchProgressPercent({ total: 2, succeeded: 5, failed: 3 })).toBe(100);
  });
});

describe("T2.6.2 isBatchJobTerminal（Job 终态判定）", () => {
  it("非终态：QUEUED / RUNNING 不得判为终态（否则会提前停轮询）", async () => {
    const { isBatchJobTerminal } = await import("@/lib/api");
    expect(isBatchJobTerminal("QUEUED")).toBe(false);
    expect(isBatchJobTerminal("RUNNING")).toBe(false);
  });

  it("终态四值：SUCCEEDED / PARTIAL_SUCCESS / FAILED / CANCELLED（R0.4.2）", async () => {
    const { isBatchJobTerminal, BATCH_JOB_TERMINAL_STATUSES } = await import("@/lib/api");
    for (const s of ["SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"]) {
      expect(isBatchJobTerminal(s)).toBe(true);
    }
    expect([...BATCH_JOB_TERMINAL_STATUSES]).toEqual([
      "SUCCEEDED",
      "PARTIAL_SUCCESS",
      "FAILED",
      "CANCELLED",
    ]);
  });

  it("CANCELLED 漏进终态集合会让已取消作业被判为「进行中」——回归锁", async () => {
    // 取消的批量作业 counts.failed 恒为 0（篇目是 PENDING 不是 FAILED），
    // 若被判为非终态，BatchProgressList 会一直显示「同步中…」且轮询永不停。
    const { isBatchJobTerminal } = await import("@/lib/api");
    expect(isBatchJobTerminal("CANCELLED")).toBe(true);
    expect(isBatchJobTerminal("QUEUED")).toBe(false);
    expect(isBatchJobTerminal("RUNNING")).toBe(false);
  });

  it("未知/空状态保守判为「非终态」（继续轮询优于误停）", async () => {
    const { isBatchJobTerminal } = await import("@/lib/api");
    expect(isBatchJobTerminal("")).toBe(false);
    expect(isBatchJobTerminal("WEIRD")).toBe(false);
  });
});

describe("T2.6.2 批量 Job 断点（刷新不丢的凭据）", () => {
  it("写入后可原样读回（spaceId/jobId/urlCount/时间戳）", async () => {
    const { sessionStorage } = installWindow();
    const { saveBatchJobCheckpoint, readBatchJobCheckpoint } = await import("@/lib/api");
    saveBatchJobCheckpoint({ spaceId: "sp-1", jobId: "job-abc", urlCount: 50 });
    const cp = readBatchJobCheckpoint();
    expect(cp).not.toBeNull();
    expect(cp!.spaceId).toBe("sp-1");
    expect(cp!.jobId).toBe("job-abc");
    expect(cp!.urlCount).toBe(50);
    expect(cp!.savedAt).toBeGreaterThan(0);
    // 落在 sessionStorage（同标签页刷新可存活），非 localStorage
    expect(sessionStorage.getItem(CHECKPOINT_KEY)).toBeTruthy();
  });

  it("清除后读回 null（终态被用户处理后不再恢复面板）", async () => {
    const { sessionStorage } = installWindow();
    const { saveBatchJobCheckpoint, readBatchJobCheckpoint, clearBatchJobCheckpoint } =
      await import("@/lib/api");
    saveBatchJobCheckpoint({ spaceId: "sp-1", jobId: "job-abc", urlCount: 3 });
    clearBatchJobCheckpoint();
    expect(readBatchJobCheckpoint()).toBeNull();
    expect(sessionStorage.getItem(CHECKPOINT_KEY)).toBeNull();
  });

  it("非法 JSON / 缺 jobId → 降级 null，不抛异常打断面板", async () => {
    const { sessionStorage } = installWindow();
    const { readBatchJobCheckpoint } = await import("@/lib/api");
    sessionStorage.setItem(CHECKPOINT_KEY, "{ 不是 json");
    expect(readBatchJobCheckpoint()).toBeNull();
    sessionStorage.setItem(CHECKPOINT_KEY, JSON.stringify({ spaceId: "sp-1" }));
    expect(readBatchJobCheckpoint()).toBeNull();
    sessionStorage.setItem(CHECKPOINT_KEY, JSON.stringify({ spaceId: 1, jobId: null }));
    expect(readBatchJobCheckpoint()).toBeNull();
  });

  it("无 window（SSR/未挂载）→ 读 null、写与清空均静默 no-op", async () => {
    const { readBatchJobCheckpoint, saveBatchJobCheckpoint, clearBatchJobCheckpoint } =
      await import("@/lib/api");
    expect(readBatchJobCheckpoint()).toBeNull();
    expect(() =>
      saveBatchJobCheckpoint({ spaceId: "sp-1", jobId: "job-1", urlCount: 1 })
    ).not.toThrow();
    expect(() => clearBatchJobCheckpoint()).not.toThrow();
  });
});
