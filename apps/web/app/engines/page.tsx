"use client";

/**
 * EnginesPage —— T1.1.2 引擎设置页真实现（替换 36 行壳页；大纲 v1.1）。
 *
 * - 引擎全景卡：GET /engines 五引擎位（状态点：可用/未开放/未配置 Key）；
 * - 切换流程：选择目标空间 → 复用 EngineSwitcher（含切换确认模态）；
 * - 验收锚（大纲 T1.1.2）：引擎列表可点切换。
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import EngineSwitcher from "@/components/EngineSwitcher";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import { usePageTitle } from "@/components/usePageTitle";
import { ApiError, listEngines, listSpaces, type EngineItem, type Space } from "@/lib/api";

function statusDot(e: EngineItem): { cls: string; label: string } {
  if (e.available) return { cls: "bg-green-500", label: "可用" };
  if (!e.configured) return { cls: "bg-neutral-300", label: "未配置 Key" };
  if (!e.allowlisted) return { cls: "bg-amber-400", label: "未开放" };
  return { cls: "bg-neutral-300", label: "未实接" };
}

export default function EnginesPage() {
  usePageTitle("知识引擎");
  const [engines, setEngines] = useState<EngineItem[]>([]);
  const [defaultEngine, setDefaultEngine] = useState("builtin");
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [selectedSpaceId, setSelectedSpaceId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [d, mine] = await Promise.all([listEngines(), listSpaces()]);
      setEngines(d.items);
      setDefaultEngine(d.defaultEngine);
      setSpaces(mine);
      setSelectedSpaceId((prev) => prev || (mine[0]?.id ?? ""));
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 10001
          ? "未登录，请重新登录后查看引擎"
          : "引擎列表加载失败，请重试"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedSpace = spaces.find((s) => s.id === selectedSpaceId) ?? null;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="eyebrow">ENGINES</p>
        <h1 className="text-title-lg font-semibold text-neutral-900">知识引擎</h1>
        <p className="mt-2 text-base text-neutral-500">
          默认引擎 <span className="font-medium text-neutral-700">{defaultEngine}</span>
          ；未配置 Key 的引擎由管理员在服务端配置（env）后开放。
        </p>
      </div>

      <LoadingErrorShell
        loading={loading}
        error={error}
        onRetry={() => void load()}
        skeletonRows={2}
      >
        <>
          {/* 引擎全景卡片（Key 状态点） */}
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {engines.map((e) => {
              const dot = statusDot(e);
              return (
                <li key={e.engine} className="card p-4">
                  <div className="flex items-center justify-between">
                    <p className="text-base font-medium text-neutral-900">
                      {e.engine === "builtin" ? "内置引擎" : e.engine}
                      {e.engine === defaultEngine && (
                        <span className="ml-2 rounded-full bg-brand-50 px-2 py-0.5 text-caption text-brand-700">
                          默认
                        </span>
                      )}
                    </p>
                    <span className="flex items-center gap-1.5 text-caption text-neutral-500">
                      <span className={`inline-block h-2 w-2 rounded-full ${dot.cls}`} aria-hidden />
                      {dot.label}
                    </span>
                  </div>
                  <p className="mt-2 text-caption text-neutral-500">{e.description}</p>
                  <p className="mt-1 text-caption text-neutral-400">Key 配置项：{e.keyEnv}</p>
                </li>
              );
            })}
          </ul>

          {/* 切换流程：选目标空间 → EngineSwitcher */}
          <section className="mt-8">
            <h2 className="mb-3 text-title-sm font-semibold text-neutral-900">按空间切换引擎</h2>
            {spaces.length === 0 ? (
              <div className="card p-6 text-center text-neutral-500">
                你还没有自己的空间——先到 <Link className="text-brand-600 underline" href="/spaces">空间页</Link> 创建，
                再回来为空间选择引擎。
              </div>
            ) : (
              <>
                <label className="mb-1 block text-caption text-neutral-500" htmlFor="engine-space">
                  目标空间
                </label>
                <select
                  id="engine-space"
                  value={selectedSpaceId}
                  onChange={(e) => setSelectedSpaceId(e.target.value)}
                  className="mb-4 w-full rounded-input border border-neutral-300 px-3 py-2 text-base outline-none focus:border-brand-500"
                >
                  {spaces.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}（当前 {s.engine ?? "builtin"}）
                    </option>
                  ))}
                </select>
                {selectedSpace && (
                  <EngineSwitcher space={selectedSpace} onChanged={() => void load()} />
                )}
              </>
            )}
          </section>
        </>
      </LoadingErrorShell>
    </main>
  );
}
