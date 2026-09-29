/**
 * EngineSwitcher —— AB-P004 P4 空间设置页引擎切换器（ADR-0004）。
 *
 * 5 引擎卡片（内置✓/主平台/Coze/Dify/FastGPT）：
 * - 三态不可用（与后端 assert_engine_switchable 同序）：未开放 → 未配置 API Key → 尚未实接；
 *   卡片置灰 + tooltip 给出对应原因，可切换才亮 hover；
 * - 切换确认模态「切换后新入库走新引擎，旧文档不动」；
 * - 切换后显示 engineKbId 与状态。
 * 默认 builtin；SaaS 按 Key 到位逐个开（notion 不出现——按 CMS 对待，ADR-0004 §二）。
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import ConfirmModal from "@/components/ConfirmModal";
import {
  ApiError,
  listEngines,
  patchSpaceEngine,
  type EngineItem,
  type Space,
} from "@/lib/api";

interface Props {
  space: Space;
  /** 切换成功回调（刷新空间详情） */
  onChanged?: () => void;
}

/**
 * 引擎不可用原因（三态）——判定顺序与后端 assert_engine_switchable 同序
 * （未开放 → 未配 Key → 未实接），否则原因提示会让管理员按错误指引行动。
 */
/**
 * 第三态「未实接」判据——新后端在 GET /engines 显式回报 implemented；
 * 旧后端未回报时以 available 反推（available = configured ∧ allowlisted ∧
 * implemented，调用点已排除前两态，故 !available ⟺ 未实接，语义等价）。
 */
function notImplemented(e: EngineItem): boolean {
  return e.implemented === false || (e.implemented === undefined && !e.available);
}

/**
 * 引擎不可用原因（三态）——判定顺序与后端 assert_engine_switchable 同序
 * （未开放 → 未配 Key → 未实接），否则原因提示会让管理员按错误指引行动。
 */
function blockReason(e: EngineItem): string | null {
  if (!e.allowlisted) return "该引擎未开放（allowlist），需管理员在服务端开放名单配置";
  if (!e.configured) return "未配置 API Key，需管理员在引擎 Key 登记页配置";
  if (notImplemented(e)) return "该引擎尚未实接（仅骨架），需开发者完成适配器代码";
  return null;
}

/** 卡片状态标签（三态），与 blockReason 同序。 */
function statusLabel(e: EngineItem): string {
  if (!e.allowlisted) return "未开放";
  if (!e.configured) return "未配置 Key";
  if (notImplemented(e)) return "未实接";
  return "可用";
}

export default function EngineSwitcher({ space, onChanged }: Props) {
  const [engines, setEngines] = useState<EngineItem[]>([]);
  const [defaultEngine, setDefaultEngine] = useState("builtin");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState("");

  const currentEngine = space.engine ?? "builtin";

  const load = useCallback(async () => {
    try {
      const d = await listEngines();
      setEngines(d.items);
      setDefaultEngine(d.defaultEngine);
    } catch {
      // 引擎列表加载失败不阻塞空间设置页
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const doSwitch = async (engine: string) => {
    setSwitching(true);
    setError("");
    try {
      await patchSpaceEngine(space.id, engine);
      setConfirming(null);
      onChanged?.();
    } catch (e) {
      if (e instanceof ApiError && e.code === 10004) {
        setError("引擎未开放 / 未配置 Key / 尚未实接，请联系管理员（详见卡片提示）");
      } else if (e instanceof ApiError && e.code === 30004) {
        setError("空间不存在或无权限");
      } else {
        setError("切换失败，请稍后重试");
      }
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="card p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="eyebrow">知识引擎（ADR-0004）</p>
        <p className="text-caption text-neutral-400">
          当前：{engines.find((e) => e.engine === currentEngine)?.description ?? currentEngine}
          {space.engineKbId ? ` · KB ${space.engineKbId}` : ""}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {engines.length === 0 && (
          <p className="col-span-full text-caption text-neutral-400">引擎列表加载中…</p>
        )}
        {engines.map((e) => {
          const isCurrent = e.engine === currentEngine;
          const reason = blockReason(e);
          const canSelect = e.available && !isCurrent;
          return (
            <button
              key={e.engine}
              type="button"
              disabled={!canSelect}
              onClick={() => canSelect && setConfirming(e.engine)}
              title={isCurrent ? `当前：${e.description}` : (reason ?? `切换到${e.description}`)}
              className={`rounded border p-3 text-left text-caption transition ${
                isCurrent
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : canSelect
                    ? "border-neutral-200 hover:border-brand-400"
                    : "border-neutral-200 bg-neutral-50 text-neutral-400"
              }`}
            >
              <p className="text-base font-medium">
                {isCurrent ? "✓ " : ""}
                {e.engine === "builtin" ? "内置" : e.engine}
              </p>
              <p className="mt-1 text-neutral-400">{statusLabel(e)}</p>
            </button>
          );
        })}
      </div>

      {error && <p className="mt-2 text-caption text-red-600">{error}</p>}

      {/* 切换确认模态（SPEC §6.2；T1.2.2 起复用 ConfirmModal 基础件） */}
      <ConfirmModal
        open={confirming !== null}
        title="确认切换引擎"
        description={`切换后新入库走新引擎（${confirming ?? ""}），旧文档不动。`}
        confirmText="确认切换"
        busy={switching}
        onConfirm={() => confirming && void doSwitch(confirming)}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}
