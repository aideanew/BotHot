import type { StepDef } from "./types";

/**
 * 步骤条（R0.6.2 由 app/onboarding/page.tsx 抽出）
 * 已完成的步显示 ✓、当前步高亮描边、未到达步置灰。纯展示。
 */
export default function StepIndicator({
  steps,
  current,
}: {
  steps: readonly StepDef[];
  current: number;
}) {
  return (
    <ol className="mt-6 flex items-center gap-2">
      {steps.map((s) => (
        <li key={s.id} className="flex flex-1 items-center gap-2">
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-base font-medium ${
              s.id < current
                ? "bg-brand-500 text-white"
                : s.id === current
                  ? "border-2 border-brand-500 bg-white text-brand-600"
                  : "border border-neutral-300 bg-white text-neutral-400"
            }`}
          >
            {s.id < current ? "✓" : s.id}
          </span>
          <span
            className={`text-caption ${s.id === current ? "font-medium text-neutral-900" : "text-neutral-400"}`}
          >
            {s.label}
          </span>
        </li>
      ))}
    </ol>
  );
}
