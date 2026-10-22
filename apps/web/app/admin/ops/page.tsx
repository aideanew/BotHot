"use client";

/**
 * /admin/ops —— STEP-14b：管理端运维四屏（推送 / 进程存活 / 发现渠道 / 引擎密钥）。
 *
 * D-V3-06 已签口径：这 5 组端点此前"有 API 无 UI"，判为**未做**；本屏补最小可用界面，
 * 沿用现有 admin 角色，不新增 RBAC、不接新权限模型。
 *
 * 四屏走 `?screen=` 参数而不是四个路由文件：运维修一次要看四张脸，深链需求是
 * "把这屏发给同事"——query 足够，且省掉四个只有 12 行的 page.tsx。
 * 这是本卡的**显式偏离**，理由记在卡里，不当作已完成 5 入口侧栏 IA。
 */

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import AuthGate from "@/components/AuthGate";
import { useAuth } from "@/components/AuthContext";
import { usePageTitle } from "@/components/usePageTitle";
import DiscoveryChannelsPanel from "@/components/admin/DiscoveryChannelsPanel";
import AlertBanner from "@/components/admin/AlertBanner";
import EngineKeysPanel from "@/components/admin/EngineKeysPanel";
import LivenessPanel from "@/components/admin/LivenessPanel";
import PushConsolePanel from "@/components/admin/PushConsolePanel";

const SCREENS = [
  { key: "push", label: "推送终态", render: () => <PushConsolePanel /> },
  { key: "liveness", label: "进程存活", render: () => <LivenessPanel /> },
  { key: "channels", label: "发现渠道", render: () => <DiscoveryChannelsPanel /> },
  { key: "keys", label: "引擎密钥", render: () => <EngineKeysPanel /> },
] as const;

function OpsConsole() {
  const params = useSearchParams();
  const fromUrl = params.get("screen") ?? "";
  const initial = SCREENS.findIndex((s) => s.key === fromUrl);
  const [active, setActive] = useState<number>(initial >= 0 ? initial : 0);
  // 每个屏各自带 load()/LoadingErrorShell：切屏时重新挂载，才能重取"此刻"的心跳
  const [epoch, setEpoch] = useState(0);
  const refresh = useCallback(() => setEpoch((n) => n + 1), []);

  const current = SCREENS[active];
  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-title-lg font-semibold text-neutral-900">运维台</h1>
          <p className="mt-1 text-caption text-neutral-600">
            后台健康与采集能力面。数据来源为 <code className="font-mono">/api/v1/admin/*</code> 与{" "}
            <code className="font-mono">/api/v1/system/ready</code> 真实端点，本域无演示数据。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            className="rounded-input border border-neutral-300 px-3 py-1.5 text-caption hover:bg-neutral-50"
          >
            重新取数
          </button>
          <Link href="/admin" className="rounded-input border border-neutral-300 px-3 py-1.5 text-caption hover:bg-neutral-50">
            返回管理台
          </Link>
        </div>
      </header>

      <AlertBanner />

      <nav aria-label="运维屏切换" className="mb-4 flex flex-wrap gap-2">
        {SCREENS.map((s, i) => (
          <button
            key={s.key}
            type="button"
            aria-current={i === active ? "page" : undefined}
            onClick={() => setActive(i)}
            className={`rounded-input px-3 py-1.5 text-caption font-medium ${
              i === active
                ? "bg-neutral-900 text-white"
                : "border border-neutral-300 text-neutral-700 hover:bg-neutral-50"
            }`}
          >
            {s.label}
          </button>
        ))}
      </nav>

      {/* key 里带 epoch：切屏与"重新取数"都会重挂载子树，避免沿用上一次的进程心跳 */}
      <div key={`${current.key}-${epoch}`}>{current.render()}</div>
    </main>
  );
}

export default function AdminOpsPage() {
  const { status, me } = useAuth();
  usePageTitle("运维台");

  // 与 /admin 同口径的分层：判定中/未登录先交给 AuthGate，
  // 否则 guest 的 is_admin 恒 false，会把游客误导进"权限不足"卡。
  if (status !== "authed") return <AuthGate>{null}</AuthGate>;

  if (me?.is_admin !== true) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-16">
        <div className="card mx-auto max-w-md p-10 text-center">
          <p className="text-title-lg font-semibold text-neutral-900">权限不足</p>
          <p className="mt-3 text-neutral-500">
            运维台需要 operator 以上角色（后端 <code className="font-mono">require_roles(&quot;operator&quot;)</code>）。
            当前账号未登记该角色，或尚未刷新过 <code className="font-mono">/auth/me</code>。
          </p>
          <Link href="/" className="mt-6 inline-block rounded-input bg-neutral-900 px-4 py-2 text-sm text-white">
            回到首页
          </Link>
        </div>
      </main>
    );
  }

  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-16 text-center text-neutral-500">载入运维台…</div>}>
      <OpsConsole />
    </Suspense>
  );
}
