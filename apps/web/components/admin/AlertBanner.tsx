"use client";

/**
 * AlertBanner —— STEP-14b S14b.2.3：管理台顶部的告警状态条，读 `/ready` 的 `alerting` 字段。
 *
 * 这条为什么值得单独占一屏顶部：STEP-16 把 `ALERTING_ENABLED` 做成 `/ready` 上的**可观测事实**
 * （刻意不放进 `checks`，因为"告警没开"不该摘流量），但事实若只活在 JSON 里，界面上
 * "告警关着"与"告警开着"就同形——把探针画成绿色不等于有人会被它叫醒，这正是 R7.7
 * "静默失效 5 天无人察觉"那一族的可见性缺口。
 *
 * 两条取向写在这里，不是为了好看：
 * ① 读取失败一律画**未知**，不画健康：探针不可用时给绿灯是 fail-open。
 * ② 不轮询：`/ready` 每次要并发跑 PG ping + Redis ping + schema 比对，整段只有一个 4s 预算
 *    （STEP-00H 实测黑洞 DSN 下 5.46s 才返），挂在常驻页面上按秒轮询等于把探针做成负载源。
 *    要新读数就点「重读」。
 */

import { useCallback, useEffect, useState } from "react";
import StatusPill, { type PillTone } from "./StatusPill";
import { getReadyProbe, type ReadyProbe } from "@/lib/api/admin-ops";

const CHECK_LABELS: Record<keyof ReadyProbe["checks"], string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  schema: "数据库版本",
};

const TONE_RING: Record<PillTone, string> = {
  ok: "border-emerald-200 bg-emerald-50",
  degraded: "border-amber-200 bg-amber-50",
  bad: "border-red-200 bg-red-50",
  unknown: "border-neutral-200 bg-neutral-50",
};

/** 三态而不是四态：加载/不可读/有读数——后两者共用一套外壳，只差文案与色 */
type Reading = { kind: "loading" } | { kind: "unreadable" } | { kind: "probe"; probe: ReadyProbe };

/** 依赖失败优先于告警关闭：未就绪时该处置是"摘流量"，比"没人盯着"更急 */
function summarize(probe: ReadyProbe): { tone: PillTone; label: string; text: string } {
  const keys = Object.keys(probe.checks) as Array<keyof ReadyProbe["checks"]>;
  const failed = keys.filter((k) => !probe.checks[k].ok).map((k) => `${CHECK_LABELS[k]}（${probe.checks[k].state}）`);
  if (failed.length > 0) {
    return {
      tone: "bad",
      label: "未就绪",
      text: `依赖未就绪：${failed.join("、")}。编排器此刻应摘流量，这不是业务故障而是底座故障。`,
    };
  }
  if (probe.alerting === "disabled") {
    return {
      tone: "degraded",
      label: "告警未启用",
      text: "依赖就绪，但告警探测器未启用（ALERTING_ENABLED=false）：出了故障不会有人收到通知。",
    };
  }
  return {
    tone: "ok",
    label: "告警已启用",
    text: "依赖就绪且告警探测器在跑（读数为点「重读」那一刻，本条不自动刷新）。",
  };
}

export default function AlertBanner() {
  const [reading, setReading] = useState<Reading>({ kind: "loading" });

  const load = useCallback(async () => {
    setReading({ kind: "loading" });
    try {
      setReading({ kind: "probe", probe: await getReadyProbe() });
    } catch {
      // 这里只关心"能不能判定"，不搬运错误文案：探针读不到时的处置动作与原因无关
      setReading({ kind: "unreadable" });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const view =
    reading.kind === "probe"
      ? summarize(reading.probe)
      : reading.kind === "loading"
        ? { tone: "unknown" as PillTone, label: "读取中", text: "正在读取就绪探针…" }
        : {
            tone: "unknown" as PillTone,
            label: "未知",
            text: "就绪探针不可读（后端不可达，或本域在演示态下不打真后端）——按未知处理，不当作健康。",
          };

  return (
    <section
      aria-label="告警状态条"
      role="status"
      className={`mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-input border px-4 py-3 ${TONE_RING[view.tone]}`}
    >
      <StatusPill tone={view.tone} label={view.label} />
      <p className="min-w-0 flex-1 basis-48 text-caption text-neutral-800">{view.text}</p>
      <button
        type="button"
        onClick={() => void load()}
        className="rounded-input border border-neutral-300 bg-white px-3 py-1 text-caption text-neutral-700 hover:bg-neutral-50"
      >
        重读
      </button>
    </section>
  );
}
