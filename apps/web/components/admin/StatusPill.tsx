"use client";

/**
 * StatusPill —— STEP-14b S14b.2.2：三色状态丸（健康 / 降级 / 故障）。
 *
 * 刻意带**文本**而不只靠颜色：约 8% 男性有红绿色觉缺陷，纯色丸在"降级/故障"之间不可分辨；
 * 同时对比度按 WCAG AA 取深色文字配浅底（不是彩色底配白字）。
 * `tone="unknown"` 是给"数据缺失"用的第四态——它不等于"故障"，
 * 把未知画成故障会让人去查一个本来就没人启动的进程。
 */

export type PillTone = "ok" | "degraded" | "bad" | "unknown";

const STYLES: Record<PillTone, string> = {
  ok: "border-emerald-300 bg-emerald-50 text-emerald-800",
  degraded: "border-amber-300 bg-amber-50 text-amber-900",
  bad: "border-red-300 bg-red-50 text-red-800",
  unknown: "border-neutral-300 bg-neutral-50 text-neutral-700",
};

const LABELS: Record<PillTone, string> = {
  ok: "健康",
  degraded: "降级",
  bad: "故障",
  unknown: "未知",
};

interface Props {
  tone: PillTone;
  /** 覆盖默认文本（例如"从未启动"比"未知"更能指出处置动作） */
  label?: string;
}

export default function StatusPill({ tone, label }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-caption font-medium ${STYLES[tone]}`}
      data-tone={tone}
    >
      {label ?? LABELS[tone]}
    </span>
  );
}

/** 心跳三态：从未启动(null) / 卡死(stale) / 正常 —— 前两者处置动作不同，不得合并 */
export function livenessTone(row: {
  lastHeartbeatAt: string | null;
  stale: boolean;
}): { tone: PillTone; label: string } {
  if (row.lastHeartbeatAt === null) return { tone: "unknown", label: "从未启动" };
  if (row.stale) return { tone: "bad", label: "心跳卡死" };
  return { tone: "ok", label: "存活" };
}
