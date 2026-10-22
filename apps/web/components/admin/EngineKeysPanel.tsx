"use client";

/**
 * EngineKeysPanel —— STEP-14b S14b.3.4 + S14b.1.3：引擎 Key 登记 / 轮换 / 停用。
 *
 * 三条来自后端 T5.4 的纪律：
 * 1. **明文不进任何展示面**：后端从不回显 key，只回 keyId 作轮换句柄；本屏的输入框是
 *    `type="password"`、提交后立即清空，且不写进 URL（URL 会进访问日志）。
 * 2. **registered ≠ configured ≠ envConfigured**：登记覆盖 env 是**可见的**，
 *    三个布尔并列显示，合并成一个就会把"env 里已经有 Key"伪装成"登记成功了"。
 * 3. `masterKeyConfigured=false` 时登记接口会 50002 拒绝——**先禁用按钮并说明原因**，
 *    而不是让人点了才知道。`decryptFailed=true` 是主密钥换过，旧登记行解不开，
 *    必须显式标出来（否则看起来像"没配"，运维会去配一个其实已经存在的 Key）。
 */

import { useCallback, useEffect, useState } from "react";
import ConfirmModal from "@/components/ConfirmModal";
import LoadingErrorShell from "@/components/LoadingErrorShell";
import { useAuth } from "@/components/AuthContext";
import StatusPill from "./StatusPill";
import {
  listEngineKeys,
  registerEngineKey,
  revokeEngineKey,
  type EngineKeyList,
  type EngineKeyRow,
} from "@/lib/api/admin-ops";
import { ApiError } from "@/lib/api/types";

function maskKeyId(id: string): string {
  if (!id) return "—";
  return id.length <= 8 ? `${id.slice(0, 2)}****` : `${id.slice(0, 4)}…${id.slice(-4)}`;
}

export default function EngineKeysPanel() {
  const [data, setData] = useState<EngineKeyList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draftEngine, setDraftEngine] = useState("");
  const [draftKey, setDraftKey] = useState("");
  const [confirmRegister, setConfirmRegister] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState<EngineKeyRow | null>(null);
  const [busy, setBusy] = useState("");
  // P-47：登记/停用是 admin 权限（后端 POST/DELETE 走 require_roles("admin")），
  // 而本面板的读面 operator 就能进。按钮按角色收，不是等点了才拿 10004。
  // 今天 /admin/ops 的页面门本身就是 admin，所以这条是**纵深防御**而不是用户可见的修复：
  // 面板一旦被嵌进别的门（或页面门按后端放宽到 operator），写面不会跟着漏。
  const { me } = useAuth();
  const canWrite = me?.is_admin === true;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await listEngineKeys());
    } catch (e) {
      setData(null);
      setError(
        e instanceof ApiError && e.code === 10004
          ? "权限不足：引擎 Key 登记需要 operator 以上角色"
          : "引擎 Key 清单读取失败，请稍后重试"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function doRegister() {
    setConfirmRegister(false);
    const engine = draftEngine.trim();
    if (!engine || !draftKey) return;
    setBusy(engine);
    try {
      await registerEngineKey(engine, draftKey);
      setNotice(`已登记 ${engine}（明文不落库、不回显）`);
    } catch (e) {
      setNotice(e instanceof ApiError ? `登记失败：${e.message}` : "登记失败，请稍后重试");
    } finally {
      setBusy("");
      setDraftKey("");
      await load();
    }
  }

  async function doRevoke(row: EngineKeyRow) {
    setConfirmRevoke(null);
    setBusy(row.engine);
    try {
      await revokeEngineKey(row.engine);
      setNotice(`已撤销 ${row.engine} 的登记${row.envConfigured ? "（回落 env 仍可用）" : "（该引擎位现在不可用）"}`);
    } catch (e) {
      setNotice(e instanceof ApiError ? `撤销失败：${e.message}` : "撤销失败，请稍后重试");
    } finally {
      setBusy("");
      await load();
    }
  }

  return (
    <LoadingErrorShell loading={loading} error={error} onRetry={load} loadingText="读取引擎 Key 登记状态…">
      {data && !data.masterKeyConfigured ? (
        <div className="card mb-4 border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-medium">ENGINE_KEY_MASTER_KEY 未配置</p>
          <p className="mt-1">
            登记接口此时会以 50002 拒绝写入（不会回落成明文存储）。下方按钮已禁用——
            先配置主密钥并重启 backend，再回来登记。
          </p>
        </div>
      ) : null}
      {data && !canWrite ? (
        <p className="mb-3 rounded-input border border-neutral-200 bg-neutral-50 px-3 py-2 text-caption text-neutral-700">
          本屏对 operator <strong>只读</strong>：登记与停用是 admin 权限（后端
          <code className="font-mono"> require_roles(&quot;admin&quot;) </code>
          ），状态列照常可读。需要开某个引擎位请联系管理员。
        </p>
      ) : null}
      {notice ? (
        <p className="mb-3 rounded-input border border-neutral-200 bg-neutral-50 px-3 py-2 text-caption text-neutral-700">
          {notice}
        </p>
      ) : null}
      {data ? (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-neutral-50 text-left text-caption text-neutral-500">
              <tr>
                <th className="px-4 py-2 font-medium">引擎位</th>
                <th className="px-4 py-2 font-medium">已登记</th>
                <th className="px-4 py-2 font-medium">可用</th>
                <th className="px-4 py-2 font-medium">生效来源</th>
                <th className="px-4 py-2 font-medium">env</th>
                <th className="px-4 py-2 font-medium">Key 句柄</th>
                <th className="px-4 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.engine} className="border-t border-neutral-100">
                  <td className="px-4 py-2 font-medium text-neutral-900">
                    {row.engine}
                    <span className="ml-2 font-mono text-caption text-neutral-500">{row.keyEnv}</span>
                  </td>
                  <td className="px-4 py-2">
                    <StatusPill
                      tone={row.registered ? "ok" : "unknown"}
                      label={row.registered ? "有登记行" : "无登记行"}
                    />
                  </td>
                  <td className="px-4 py-2">
                    {row.decryptFailed ? (
                      <StatusPill tone="bad" label="解密失败" />
                    ) : (
                      <StatusPill tone={row.configured ? "ok" : "bad"} label={row.configured ? "可用" : "不可用"} />
                    )}
                  </td>
                  <td className="px-4 py-2 text-caption text-neutral-600">{row.activeSource || "—"}</td>
                  <td className="px-4 py-2">
                    <StatusPill
                      tone={row.envConfigured ? "ok" : "unknown"}
                      label={row.envConfigured ? "env 有值" : "env 空"}
                    />
                  </td>
                  <td className="px-4 py-2 font-mono text-caption text-neutral-600">{maskKeyId(row.keyId)}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      {canWrite ? (
                        <>
                          <button
                            type="button"
                            disabled={!data.masterKeyConfigured || busy === row.engine}
                            onClick={() => {
                              setDraftEngine(row.engine);
                              setDraftKey("");
                              setConfirmRegister(true);
                            }}
                            className="rounded-input border border-neutral-300 px-2 py-1 text-caption hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {row.registered ? "轮换" : "登记"}
                          </button>
                          {row.registered ? (
                            <button
                              type="button"
                              disabled={busy === row.engine}
                              onClick={() => setConfirmRevoke(row)}
                              className="rounded-input border border-red-300 px-2 py-1 text-caption text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              停用
                            </button>
                          ) : null}
                        </>
                      ) : (
                        <span className="text-caption text-neutral-400">只读</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* 登记明文不能进 ConfirmModal：那个组件只支持"选择"不支持自由文本，
          硬塞一个 input 进去会让明文出现在被复用的确认弹窗里（它的文案是给破坏性操作用的）。
          所以登记用这一块独立的表单：password 输入、提交后立刻清空、不进 URL。 */}
      {confirmRegister ? (
        <div className="card mb-4 border border-neutral-200 p-4">
          <p className="text-title-sm font-semibold text-neutral-900">
            为 <span className="font-mono">{draftEngine}</span> 登记 API Key
          </p>
          <p className="mt-1 text-caption text-neutral-600">
            明文只用于加密落库，不保存、不回显；重复登记同一引擎位 = 覆盖（keyId 换新）。
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              type="password"
              value={draftKey}
              onChange={(e) => setDraftKey(e.target.value)}
              placeholder="粘贴引擎 API Key"
              autoComplete="off"
              aria-label={`${draftEngine} 的 API Key`}
              className="min-w-[240px] flex-1 rounded-input border border-neutral-300 px-3 py-2 text-sm"
            />
            <button
              type="button"
              disabled={!draftKey || busy !== ""}
              onClick={() => void doRegister()}
              className="rounded-input bg-neutral-900 px-3 py-2 text-caption font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              确认登记
            </button>
            <button
              type="button"
              onClick={() => setConfirmRegister(false)}
              className="rounded-input border border-neutral-300 px-3 py-2 text-caption hover:bg-neutral-50"
            >
              取消
            </button>
          </div>
        </div>
      ) : null}

      <ConfirmModal
        open={confirmRevoke !== null}
        title={confirmRevoke ? `停用 ${confirmRevoke.engine} 的登记` : "停用登记"}
        description={
          confirmRevoke?.envConfigured
            ? "撤销后该引擎位回落到环境变量里的 Key（当前 env 有值，仍可正常调用）。"
            : "撤销后该引擎位将不可用（env 也没有值），依赖它的功能会拒绝服务——确认这是你要的。"
        }
        confirmText="确认停用"
        busy={busy !== ""}
        onCancel={() => setConfirmRevoke(null)}
        onConfirm={() => confirmRevoke && void doRevoke(confirmRevoke)}
      />
    </LoadingErrorShell>
  );
}
