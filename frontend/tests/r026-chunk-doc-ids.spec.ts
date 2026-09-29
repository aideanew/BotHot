import { describe, expect, it } from "vitest";
import { BATCH_DOCS_MAX_IDS, chunkDocIds } from "@/lib/api";

/**
 * R0.2.6 —— ids 按单次上限切片（批量删除 / 批量改分类共用）
 *
 * 后端 `batch_docs_max_ids` = 50 是业务闸（超出即 10005/422，整批被拒且零副作用）。
 * 前端必须在发请求前切片，否则用户勾了 60 篇会得到一个「全部没执行」的错误信封。
 */
describe("chunkDocIds 切片语义", () => {
  it("空选择 → 空数组；不足上限 → 单批", () => {
    expect(chunkDocIds([])).toEqual([]);
    expect(chunkDocIds(["d-1", "d-2"])).toEqual([["d-1", "d-2"]]);
  });

  it("正好 50 篇 → 单批，不产生空尾批", () => {
    const ids = Array.from({ length: BATCH_DOCS_MAX_IDS }, (_, i) => `d-${i}`);
    expect(chunkDocIds(ids)).toEqual([ids]);
  });

  it("超出上限 → 顺序切片、保序、总篇数守恒", () => {
    const ids = Array.from({ length: BATCH_DOCS_MAX_IDS + 1 }, (_, i) => `d-${i}`);
    const out = chunkDocIds(ids);
    expect(out.map((c) => c.length)).toEqual([BATCH_DOCS_MAX_IDS, 1]);
    expect(out.reduce((all, c) => all.concat(c), [] as string[])).toEqual(ids);
  });

  it("100 篇 → 两批各 50；上限可显式覆盖", () => {
    const ids = Array.from({ length: 100 }, (_, i) => `d-${i}`);
    expect(chunkDocIds(ids).map((c) => c.length)).toEqual([50, 50]);
    expect(chunkDocIds(ids, 30).map((c) => c.length)).toEqual([30, 30, 30, 10]);
  });

  it("size 退化（0 / 负数）按 1 切片，不产生空批或死循环", () => {
    expect(chunkDocIds(["d-1", "d-2"], 0).map((c) => c.length)).toEqual([1, 1]);
    expect(chunkDocIds(["d-1"], -5)).toEqual([["d-1"]]);
  });
});
