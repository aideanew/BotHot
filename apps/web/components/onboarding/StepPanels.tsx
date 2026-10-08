import type { EngineItem } from "@/lib/api";
import type { OnboardingProgress, StepDef } from "./types";

/**
 * 三步面板（R0.6.2 由 app/onboarding/page.tsx 抽出）
 * 按 `step` 渲染对应面板；状态与副作用全留在页面（断点持久化 / 建库请求 /
 * 路由跳转），本组件只做呈现与回调上抛。
 */
export default function StepPanels({
  steps,
  step,
  progress,
  spaceName,
  engines,
  engine,
  creating,
  error,
  onSpaceNameChange,
  onEngineChange,
  onCreateSpace,
  onStep2Next,
  onRestart,
  onGoAsk,
  onHome,
}: {
  steps: readonly StepDef[];
  step: number;
  progress: OnboardingProgress | null;
  spaceName: string;
  engines: EngineItem[];
  engine: string;
  creating: boolean;
  error: string;
  onSpaceNameChange: (value: string) => void;
  onEngineChange: (engine: string) => void;
  onCreateSpace: () => void;
  onStep2Next: () => void;
  onRestart: () => void;
  onGoAsk: () => void;
  onHome: () => void;
}) {
  return (
    <>
      {step === 1 && (
        <section className="card mt-6 p-6">
          <h2 className="text-title-sm font-semibold text-neutral-900">
            第 1 步：起名并选择引擎
          </h2>
          <p className="mt-1 text-caption text-neutral-400">{steps[0].desc}</p>
          <label className="mt-4 mb-1 block text-caption text-neutral-500">
            知识库名称
          </label>
          <input
            value={spaceName}
            onChange={(e) => onSpaceNameChange(e.target.value)}
            placeholder="例如：产品资料库"
            aria-label="知识库名称"
            className="w-full rounded-input border border-neutral-300 bg-neutral-50 px-4 py-2 text-base outline-none focus:border-brand-500 focus:bg-white"
          />
          <p className="mt-4 mb-1 text-caption text-neutral-500">引擎</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {engines.length === 0 && (
              <button
                type="button"
                onClick={() => onEngineChange("builtin")}
                className={`rounded-input border px-4 py-2 text-base text-left ${
                  engine === "builtin"
                    ? "border-brand-500 bg-brand-50"
                    : "border-neutral-300 bg-white"
                }`}
              >
                内置引擎（默认）
              </button>
            )}
            {engines.map((e) => (
              <button
                key={e.engine}
                type="button"
                disabled={!e.available}
                onClick={() => onEngineChange(e.engine)}
                title={e.description}
                className={`rounded-input border px-4 py-2 text-base text-left ${
                  engine === e.engine
                    ? "border-brand-500 bg-brand-50"
                    : "border-neutral-300 bg-white"
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {e.engine}
                {e.available ? "" : "（未配置）"}
              </button>
            ))}
          </div>
          {error && <p className="mt-3 text-caption text-red-600">{error}</p>}
          <button
            onClick={onCreateSpace}
            disabled={creating || !spaceName.trim()}
            className="mt-5 rounded-input bg-brand-500 px-6 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {creating ? "创建中…" : "创建知识库并继续"}
          </button>
        </section>
      )}

      {step === 2 && progress && (
        <section className="card mt-6 p-6">
          <h2 className="text-title-sm font-semibold text-neutral-900">
            第 2 步：选择来源
          </h2>
          <p className="mt-1 text-base text-neutral-500">
            已创建「{progress.spaceName}」（引擎：{progress.engine}）。接下来选一种方式填充内容。
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <a
              href={`/spaces/${progress.spaceId}`}
              className="card block p-4 transition hover:border-brand-200 hover:shadow-popover"
            >
              <p className="text-base font-medium text-neutral-900">粘贴文章链接</p>
              <p className="mt-1 text-caption text-neutral-500">
                单篇或换行批量粘贴公众号文章，逐篇解析入库。
              </p>
            </a>
            <a
              href="/subscriptions"
              className="card block p-4 transition hover:border-brand-200 hover:shadow-popover"
            >
              <p className="text-base font-medium text-neutral-900">订阅整号公众号</p>
              <p className="mt-1 text-caption text-neutral-500">
                填 biz 或 profile URL，按同步策略自动入库。
              </p>
            </a>
          </div>
          <div className="mt-5 flex gap-3">
            <button
              onClick={onRestart}
              className="rounded-input border border-neutral-300 px-4 py-2 text-base text-neutral-600 hover:bg-neutral-50"
            >
              重新开始
            </button>
            <button
              onClick={onStep2Next}
              className="rounded-input bg-brand-500 px-6 py-2 font-medium text-white hover:bg-brand-600"
            >
              已添加内容，进入提问 →
            </button>
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="card mt-6 p-6">
          <h2 className="text-title-sm font-semibold text-neutral-900">
            第 3 步：开始提问
          </h2>
          <p className="mt-1 text-base text-neutral-500">
            {progress ? `「${progress.spaceName}」已就绪。` : "知识库已就绪。"}
            每一次回答都会附带来源引用，可追溯到具体文章。
          </p>
          <div className="mt-5 flex gap-3">
            <button
              onClick={onHome}
              className="rounded-input border border-neutral-300 px-4 py-2 text-base text-neutral-600 hover:bg-neutral-50"
            >
              去工作台
            </button>
            <button
              onClick={onGoAsk}
              className="rounded-input bg-brand-500 px-6 py-2 font-medium text-white hover:bg-brand-600"
            >
              去提问 →
            </button>
          </div>
        </section>
      )}
    </>
  );
}
