"use client";

/**
 * CollectionConfigPanel —— STEP-14b 余项「采集配置页」（V0.17 增量句点名的那一半）。
 *
 * 两块配置放同一屏，因为它们是同一次运营动作的两面：从哪些渠道采（发现渠道屏）、
 * 采回来按什么分（本屏左）、分不到时花不花钱兜底（本屏右）。
 *
 * 三处"不能画错"的地方都来自后端已经写死的约束，不是这里的偏好：
 * 1. 分类清单必须留着「其他」——缺它后端直接 10005，所以那一行不给停用也不给删；
 * 2. 兜底的 `providers` 从 `null`（不限制）变成显式名单是**不可逆的一步**：此后新配好凭据的
 *    供应商不会自动进名单。所以保存前必须把这句话摆在人眼前，而不是保存后写进日志；
 * 3. 空名单 = "开着但一家都不打"，开启又必须带日预算（D-V12-20 拒绝无上限付费调用）——
 *    这两条在前端拦住，不让人拿一次 422 才知道自己点了什么。
 *
 * 写权限也不对称：分类 operator 可写，付费兜底只有 admin 可写（读侧都是 operator）。
 */

import { useCallback, useEffect, useState } from "react";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import StatusPill from "./StatusPill";
import { useAuth } from "@/components/AuthContext";
import {
  getArticleFallback,
  getCategories,
  putArticleFallback,
  putCategories,
  type ArticleFallbackView,
  type CategoryItem,
} from "@/lib/api/admin-ops";
import { ApiError } from "@/lib/api/types";

function splitKeywords(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export default function CollectionConfigPanel() {
  const { me } = useAuth();
  const canWriteFallback = me?.is_admin === true;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [cats, setCats] = useState<CategoryItem[]>([]);
  const [catSource, setCatSource] = useState("");
  const [defaultCategory, setDefaultCategory] = useState("其他");
  const [catKeywordDraft, setCatKeywordDraft] = useState<Record<string, string>>({});
  const [catNote, setCatNote] = useState("");
  const [catError, setCatError] = useState("");
  const [catSaving, setCatSaving] = useState(false);

  const [fb, setFb] = useState<ArticleFallbackView | null>(null);
  const [fbEnabled, setFbEnabled] = useState(false);
  const [fbTriggers, setFbTriggers] = useState<string[]>([]);
  const [fbProviders, setFbProviders] = useState<string[]>([]);
  const [fbBudget, setFbBudget] = useState<string>("");
  const [fbNote, setFbNote] = useState("");
  const [fbError, setFbError] = useState("");
  const [fbSaving, setFbSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [c, f] = await Promise.all([getCategories(), getArticleFallback()]);
      setCats(c.categories);
      setCatSource(c.source);
      setDefaultCategory(c.defaultCategory);
      setCatKeywordDraft(
        Object.fromEntries(c.categories.map((item) => [item.name, item.keywords.join(", ")]))
      );
      setFb(f);
      setFbEnabled(f.effective.enabled);
      setFbTriggers(f.effective.trigger);
      setFbProviders(f.effective.providers ?? []);
      setFbBudget(f.effective.dailyBudget === null ? "" : String(f.effective.dailyBudget));
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 10004
          ? "权限不足：采集配置读取需要 operator 以上角色"
          : "采集配置读取失败，请稍后重试"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const patchCat = (index: number, patch: Partial<CategoryItem>) => {
    setCatNote("");
    setCatError("");
    setCats((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  const moveCat = (index: number, delta: -1 | 1) => {
    setCatNote("");
    setCats((rows) => {
      const target = index + delta;
      if (target < 0 || target >= rows.length) return rows;
      const next = [...rows];
      const a = next[index];
      next[index] = next[target];
      next[target] = a;
      return next;
    });
  };

  const saveCats = async () => {
    setCatSaving(true);
    setCatError("");
    setCatNote("");
    const payload = cats.map((row, i) => ({
      name: row.name.trim() || `未命名-${i + 1}`,
      keywords: splitKeywords(catKeywordDraft[row.name] ?? row.keywords.join(", ")),
      enabled: row.enabled,
    }));
    try {
      const got = await putCategories(payload);
      setCats(got.categories);
      setCatSource(got.source);
      setCatNote(`分类清单已保存（${got.categories.length} 项，顺序即优先级），下一轮入库生效。`);
    } catch (e) {
      setCatError(
        e instanceof ApiError ? `分类未保存：${e.message}` : "分类未保存：写入失败，请稍后重试"
      );
    } finally {
      setCatSaving(false);
    }
  };

  /** 开启付费兜底的两条硬约束在前端先拦：预算缺失、名单为空（空名单=开着但一家都不打） */
  const fbBlocker = !fbEnabled
    ? ""
    : fbBudget.trim() === ""
      ? "开启付费兜底必须同时给日预算——后端会拒绝「可无上限开启付费调用」。"
      : fbProviders.length === 0
        ? "一家供应商都没选：这样保存等于「开着但永远不打」，既不花钱也不生效。"
        : "";

  const saveFb = async () => {
    if (fbBlocker) return;
    setFbSaving(true);
    setFbError("");
    setFbNote("");
    try {
      const got = await putArticleFallback({
        enabled: fbEnabled,
        trigger: fbTriggers,
        providers: fbProviders,
        dailyBudget: fbBudget.trim() === "" ? null : Number(fbBudget),
      });
      setFbNote(
        `兜底配置已保存：${got.effective.enabled ? `开，日预算 ${got.effective.dailyBudget ?? "—"} 次` : "关"}，` +
          `生效名单 ${got.effective.providers === null ? "不限制" : `${got.effective.providers.length} 家`}。`
      );
      await load();
    } catch (e) {
      setFbError(e instanceof ApiError ? `兜底未保存：${e.message}` : "兜底未保存：写入失败，请稍后重试");
    } finally {
      setFbSaving(false);
    }
  };

  const toggleIn = (list: string[], v: string, on: boolean) =>
    on ? [...list, v] : list.filter((x) => x !== v);

  return (
    <LoadingErrorShell loading={loading} error={error} onRetry={load} loadingText="读取采集配置…">
      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-100 px-4 py-3">
          <p className="text-title-md font-semibold text-neutral-900">分类清单</p>
          <p className="text-caption text-neutral-600">
            来源：
            <strong>
              {catSource === "db" ? "运营配置（db）" : "代码默认清单（env，还没配过）"}
            </strong>
            {" · 顺序即自动分类的优先级与筛选项顺序"}
          </p>
        </div>
        <ul className="divide-y divide-neutral-100">
          {cats.map((row, i) => {
            const locked = row.name === defaultCategory;
            return (
              <li key={`${row.name}-${i}`} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    value={row.name}
                    onChange={(e) => patchCat(i, { name: e.target.value })}
                    aria-label={`第 ${i + 1} 个分类名`}
                    className="w-40 rounded-input border border-neutral-300 px-2 py-1 text-caption"
                  />
                  <input
                    value={catKeywordDraft[row.name] ?? row.keywords.join(", ")}
                    onChange={(e) =>
                      setCatKeywordDraft((d) => ({ ...d, [row.name]: e.target.value }))
                    }
                    aria-label={`${row.name} 的关键词`}
                    placeholder="关键词，逗号分隔"
                    className="min-w-0 flex-1 basis-52 rounded-input border border-neutral-300 px-2 py-1 text-caption"
                  />
                  <label className="flex items-center gap-1 text-caption text-neutral-700">
                    <input
                      type="checkbox"
                      checked={row.enabled}
                      disabled={locked}
                      onChange={(e) => patchCat(i, { enabled: e.target.checked })}
                      aria-label={`启用分类 ${row.name}`}
                    />
                    启用
                  </label>
                  <span className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => moveCat(i, -1)}
                      disabled={i === 0}
                      aria-label={`上移 ${row.name}`}
                      className="rounded-input border border-neutral-300 px-2 py-0.5 text-caption disabled:opacity-40"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => moveCat(i, 1)}
                      disabled={i === cats.length - 1}
                      aria-label={`下移 ${row.name}`}
                      className="rounded-input border border-neutral-300 px-2 py-0.5 text-caption disabled:opacity-40"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => setCats((rows) => rows.filter((_, k) => k !== i))}
                      disabled={locked}
                      title={locked ? `兜底分类「${defaultCategory}」不可移除（缺它后端 10005）` : "从清单移除（仍被引用的分类会被后端拒绝，改成停用即可）"}
                      aria-label={`移除 ${row.name}`}
                      className="rounded-input border border-neutral-300 px-2 py-0.5 text-caption text-neutral-700 disabled:opacity-40"
                    >
                      移除
                    </button>
                  </span>
                  {locked ? <StatusPill tone="unknown" label="兜底分类" /> : null}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="flex flex-wrap items-center gap-3 border-t border-neutral-100 px-4 py-3">
          <button
            type="button"
            onClick={() =>
              setCats((rows) => [...rows, { name: `新分类-${rows.length + 1}`, keywords: [], enabled: true }])
            }
            className="rounded-input border border-neutral-300 px-3 py-1.5 text-caption hover:bg-neutral-50"
          >
            新增分类
          </button>
          <button
            type="button"
            onClick={() => void saveCats()}
            disabled={catSaving}
            className="rounded-input bg-neutral-900 px-4 py-1.5 text-caption text-white hover:bg-neutral-800 disabled:opacity-50"
          >
            {catSaving ? "保存中…" : "保存分类清单"}
          </button>
          {catError ? <p className="text-caption text-red-800">{catError}</p> : null}
          {catNote ? <p className="text-caption text-emerald-800">{catNote}</p> : null}
        </div>
      </div>

      <div className="card mt-4 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-100 px-4 py-3">
          <p className="text-title-md font-semibold text-neutral-900">付费详情兜底</p>
          <p className="text-caption text-neutral-600">
            来源：
            <strong>{fb?.source === "db" ? "运营配置（db）" : "环境变量/默认（env）"}</strong>
            {fb?.effective.providers === null ? " · 供应商名单：不限制" : ""}
          </p>
        </div>
        <div className="px-4 py-3">
          <label className="flex items-center gap-2 text-sm text-neutral-900">
            <input
              type="checkbox"
              checked={fbEnabled}
              onChange={(e) => {
                setFbEnabled(e.target.checked);
                setFbNote("");
              }}
              aria-label="开启付费详情兜底"
            />
            开启付费兜底
          </label>
          <p className="mt-2 text-caption text-neutral-600">
            触发条件（只有这里列出的值真的接进了代码——照卡面猜一个没有检测面的值会被拒）：
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            {(fb?.wiredTriggers ?? []).map((t) => (
              <label key={t} className="flex items-center gap-1 text-caption text-neutral-700">
                <input
                  type="checkbox"
                  checked={fbTriggers.includes(t)}
                  onChange={(e) => {
                    setFbTriggers((prev) => toggleIn(prev, t, e.target.checked));
                    setFbNote("");
                  }}
                  aria-label={`触发条件 ${t}`}
                />
                {t}
              </label>
            ))}
          </div>
          <p className="mt-3 text-caption text-neutral-600">
            供应商（勾了就等于把「不限制」改成显式名单，此后新配好凭据的供应商不会自动进来）：
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            {(fb?.platforms ?? []).map((p) => (
              <label key={p.name} className="flex items-center gap-1 text-caption text-neutral-700">
                <input
                  type="checkbox"
                  checked={fbProviders.includes(p.name)}
                  onChange={(e) => {
                    setFbProviders((prev) => toggleIn(prev, p.name, e.target.checked));
                    setFbNote("");
                  }}
                  aria-label={`供应商 ${p.name}`}
                />
                {p.name}
                <StatusPill tone={p.ready ? "ok" : "unknown"} label={p.ready ? "凭据就绪" : "未配凭据"} />
              </label>
            ))}
          </div>
          <label className="mt-3 flex flex-wrap items-center gap-2 text-caption text-neutral-600">
            日预算（次）
            <input
              type="number"
              min={1}
              value={fbBudget}
              onChange={(e) => {
                setFbBudget(e.target.value);
                setFbNote("");
              }}
              aria-label="每日付费调用上限"
              className="w-28 rounded-input border border-neutral-300 px-2 py-1 text-caption"
            />
          </label>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {canWriteFallback ? (
              <button
                type="button"
                onClick={() => void saveFb()}
                disabled={fbSaving || fbBlocker !== ""}
                className="rounded-input bg-neutral-900 px-4 py-1.5 text-caption text-white hover:bg-neutral-800 disabled:opacity-50"
              >
                {fbSaving ? "保存中…" : "保存兜底配置"}
              </button>
            ) : (
              <p className="text-caption text-neutral-700">
                本屏对 operator <strong>只读</strong>：付费兜底的写入是 admin 权限（D-V12-20，涉及花钱）。
              </p>
            )}
            {fbBlocker ? <p className="text-caption text-amber-900">{fbBlocker}</p> : null}
            {fbError ? <p className="text-caption text-red-800">{fbError}</p> : null}
            {fbNote ? <p className="text-caption text-emerald-800">{fbNote}</p> : null}
          </div>
        </div>
      </div>
    </LoadingErrorShell>
  );
}
