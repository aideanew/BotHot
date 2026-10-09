"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";import {
  ApiError,
  listEngines,
  createSpace,
  type EngineItem,
} from "@/lib/api";
import { useAuth } from "@/components/AuthContext";
import { usePageTitle } from "@/components/usePageTitle";
import AuthGate from "@/components/AuthGate";
import StepIndicator from "@/components/onboarding/StepIndicator";
import StepPanels from "@/components/onboarding/StepPanels";
import { STEPS, type OnboardingProgress } from "@/components/onboarding/types";

/**
 * OnboardingPage —— T-022 L-09 / D-01（P1）引导页 + 断点续做（/onboarding）
 * R0.6.2 拆分：StepIndicator 步骤条 + StepPanels 三步面板（纯展示），
 * 本页只留断点持久化、建库请求与路由跳转。
 *
 * SPEC §六 6.2「/onboarding 引导页」+ J5「做到第 2 步刷新页面→回到引导页显示
 * 『上次做到第 N 步，继续』」。
 *
 * 实现口径（关键取舍，如实登记）：后端 GET /api/v1/onboarding/steps 已在 BE-02
 * 提供但为**静态快照桩**（恒返回默认值，无按用户持久化，见 app/api/v1/onboarding.py），
 * 本组件按 ux-walkthrough 建议走**纯前端本地断点**（localStorage 记录步骤进度）；
 * 大纲 5.2.4「onboarding 进度后端化」落地按用户进度存储后，可无痛替换为远端权威进度。
 *
 * 三步：① 起名 + 选引擎（建库）→ ② 选来源（单篇/整号）→ ③ 提问（跳问答）。
 * 刷新/回入：读取本地 step，横幅「上次做到第 N 步，继续」。
 */

const STORAGE_KEY = "bothot_onboarding_v1";

function readProgress(): OnboardingProgress | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as Partial<OnboardingProgress> | null;
    if (!o || typeof o.step !== "number" || o.step < 1 || o.step > STEPS.length) {
      return null;
    }
    return {
      step: o.step,
      spaceId: typeof o.spaceId === "string" ? o.spaceId : "",
      spaceName: typeof o.spaceName === "string" ? o.spaceName : "",
      engine: typeof o.engine === "string" ? o.engine : "builtin",
      savedAt: typeof o.savedAt === "number" ? o.savedAt : 0,
    };
  } catch {
    return null;
  }
}

function writeProgress(p: OnboardingProgress): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...p, savedAt: Date.now() }));
  } catch {
    // 存储不可用：断点能力降级为无，不阻断引导流程
  }
}

function clearProgress(): void {
  if (typeof window !== "undefined") window.localStorage.removeItem(STORAGE_KEY);
}

export default function OnboardingPage() {
  const router = useRouter();
  const { status } = useAuth();
  usePageTitle("新手引导");
  const [progress, setProgress] = useState<OnboardingProgress | null>(null);
  const [resumed, setResumed] = useState(false); // 是否为「断点续做」回入态
  const [spaceName, setSpaceName] = useState("");
  const [engines, setEngines] = useState<EngineItem[]>([]);
  const [engine, setEngine] = useState("builtin");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  // 断点恢复：仅恢复本浏览器本地进度（不跨会话）
  useEffect(() => {
    const p = readProgress();
    if (!p) return;
    setProgress(p);
    setSpaceName(p.spaceName);
    setEngine(p.engine);
    setResumed(true);
  }, []);

  // 引擎位列表（失败回落内置引擎单选项，不阻断第 1 步）；G2.3：guest 态不发请求
  useEffect(() => {
    if (status !== "authed") return;
    listEngines()
      .then((d) => setEngines(d.items))
      .catch(() => {});
  }, [status]);

  function save(next: OnboardingProgress) {
    setProgress(next);
    writeProgress(next);
  }

  async function handleCreateSpace() {
    const name = spaceName.trim();
    if (!name) {
      setError("请先给知识库起个名字");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const detail = await createSpace({ name });
      save({ step: 2, spaceId: detail.id, spaceName: detail.name, engine, savedAt: Date.now() });
    } catch (e) {
      // 重名 30006 / 409 或网络异常：原步骤保留，允许改名重试
      setError(e instanceof ApiError ? e.message : "创建失败，请稍后重试");
    } finally {
      setCreating(false);
    }
  }

  function handleStep2Next() {
    if (!progress) return;
    save({ ...progress, step: 3, savedAt: Date.now() });
  }

  function handleRestart() {
    setProgress(null);
    setSpaceName("");
    clearProgress();
  }

  function finish() {
    // 完成即清断点（下次进入从第 1 步开始，可重复走引导）
    clearProgress();
    router.push(progress ? `/chat?q=${encodeURIComponent("这个知识库里有哪些内容？")}` : "/chat");
  }

  const step = progress?.step ?? 1;

  return (
    <AuthGate>
    <main className="mx-auto max-w-3xl px-4 py-10">
      <p className="eyebrow">GET STARTED</p>
      <h1 className="mt-1 text-title-lg font-semibold text-neutral-900">
        三步建好你的知识库
      </h1>

      {/* 断点续做横幅（刷新/回入后提示「上次做到第 N 步，继续」） */}
      {resumed && progress && (
        <div className="mt-4 rounded-card border border-blue-200 bg-blue-50 p-4">
          <p className="text-base text-blue-700">
            上次做到第 {progress.step} 步（{STEPS[progress.step - 1].label}），继续完成。
          </p>
        </div>
      )}

      <StepIndicator steps={STEPS} current={step} />

      <StepPanels
        steps={STEPS}
        step={step}
        progress={progress}
        spaceName={spaceName}
        engines={engines}
        engine={engine}
        creating={creating}
        error={error}
        onSpaceNameChange={setSpaceName}
        onEngineChange={setEngine}
        onCreateSpace={() => void handleCreateSpace()}
        onStep2Next={handleStep2Next}
        onRestart={handleRestart}
        onGoAsk={finish}
        onHome={() => router.push("/")}
      />

      {/* 进度存储口径如实登记：本地断点为当前方案，服务端按用户同步待 5.2.4 */}
      <p className="mt-6 text-caption text-neutral-400">
        断点记录保存在本浏览器本地；GET /api/v1/onboarding/steps 现为静态快照，按用户进度同步待后端化（大纲 5.2.4）。
      </p>
    </main>
    </AuthGate>
  );
}
