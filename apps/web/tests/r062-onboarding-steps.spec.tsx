// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * R0.6.2 —— onboarding 拆分后的呈现不变式 + 断点持久化接线
 *
 * 该页拆分前**零测试覆盖**：步骤条、三步面板、断点读取（越界拒绝）都无人管。
 * 本页与 chat 页的零覆盖同因——都是「整页渲染」才能触达的组件，R0.6.1/R0.6.2
 * 的拆分正是让它们首次可单测（行为不变，仅搬家）。
 *
 * 覆盖的不变式：
 * A. StepIndicator：已完成步 ✓、当前步高亮描边、未到达步置灰（文案层级同步）；
 * B. StepPanels 第 1 步：空名禁提交 / 错误行 / 引擎位空回落内置 / 未配置引擎禁用；
 * C. StepPanels 第 2、3 步：进度摘要与两个去向按钮各自回调上抛；
 * D. 页面接线：断点恢复横幅取 STEPS 文案、越界 step 被拒绝回到第 1 步、
 *    建库成功写入 step 2、建库失败留在第 1 步可改名重试。
 */

// —— 页面级 mock（仅 Part D 需要）——
const h = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn() },
  listEngines: vi.fn(),
  createSpace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => h.router,
}));

vi.mock("@/components/AuthContext", () => ({
  useAuth: () => ({
    status: "authed",
    me: null,
    login: () => {},
    logout: async () => {},
    reload: () => {},
  }),
}));

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    code: number;
    requestId: string;
    constructor(code: number, message: string, requestId = "") {
      super(message);
      this.name = "ApiError";
      this.code = code;
      this.requestId = requestId;
    }
  }
  return { ApiError, listEngines: h.listEngines, createSpace: h.createSpace };
});

import { ApiError, type EngineItem } from "@/lib/api";
import { STEPS, type OnboardingProgress } from "@/components/onboarding/types";
import StepIndicator from "@/components/onboarding/StepIndicator";
import StepPanels from "@/components/onboarding/StepPanels";
import OnboardingPage from "@/app/onboarding/page";

const STORAGE_KEY = "bothot_onboarding_v1";

const ENGINES: EngineItem[] = [
  {
    engine: "builtin",
    configured: true,
    available: true,
    allowlisted: true,
    keyEnv: "",
    description: "默认引擎，开箱可用",
  },
  {
    engine: "langbot",
    configured: false,
    available: false,
    allowlisted: false,
    keyEnv: "LANGBOT_BASE_URL",
    description: "外部 LangBot 实例",
  },
];

const PROGRESS: OnboardingProgress = {
  step: 2,
  spaceId: "sp-9",
  spaceName: "产品资料库",
  engine: "builtin",
  savedAt: 1,
};

function panelProps(over: Partial<Parameters<typeof StepPanels>[0]> = {}) {
  return {
    steps: STEPS,
    step: 1,
    progress: null,
    spaceName: "",
    engines: [] as EngineItem[],
    engine: "builtin",
    creating: false,
    error: "",
    onSpaceNameChange: () => {},
    onEngineChange: () => {},
    onCreateSpace: () => {},
    onStep2Next: () => {},
    onRestart: () => {},
    onGoAsk: () => {},
    onHome: () => {},
    ...over,
  };
}

beforeEach(() => {
  h.router.push.mockReset();
  h.router.replace.mockReset();
  h.listEngines.mockReset();
  h.listEngines.mockResolvedValue({ items: ENGINES });
  h.createSpace.mockReset();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("R0.6.2 StepIndicator：已完成 / 当前 / 未到达 三态", () => {
  it("渲染全部步骤；已完成步显示 ✓，当前步高亮描边", () => {
    render(createElement(StepIndicator, { steps: STEPS, current: 2 }));

    // 已完成
    expect(screen.getByText("✓")).toBeTruthy();
    expect((screen.getByText("✓") as HTMLElement).className).toContain("bg-brand-500");

    // 当前：数字编号 + 品牌色描边
    const current = screen.getByText("2") as HTMLElement;
    expect(current.className).toContain("border-brand-500");

    // 未到达：中性描边置灰
    const upcoming = screen.getByText("3") as HTMLElement;
    expect(upcoming.className).toContain("border-neutral-300");
    expect(upcoming.className).not.toContain("bg-brand-500");
  });

  it("文案层级：当前步加粗深色，其余置灰", () => {
    render(createElement(StepIndicator, { steps: STEPS, current: 1 }));

    expect((screen.getByText(STEPS[0].label) as HTMLElement).className).toContain(
      "font-medium"
    );
    expect((screen.getByText(STEPS[1].label) as HTMLElement).className).toContain(
      "text-neutral-400"
    );
  });

  it("第一步时没有任何 ✓（无已完成步）", () => {
    render(createElement(StepIndicator, { steps: STEPS, current: 1 }));
    expect(screen.queryByText("✓")).toBeNull();
  });
});

describe("R0.6.2 StepPanels 第 1 步：起名与选引擎", () => {
  it("空名禁止提交", () => {
    const onCreate = vi.fn();
    render(createElement(StepPanels, panelProps({ spaceName: "  ", onCreateSpace: onCreate })));

    const btn = screen.getByText("创建知识库并继续") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("填名后可提交并上抛回调", () => {
    const onCreate = vi.fn();
    render(
      createElement(StepPanels, panelProps({ spaceName: "产品资料库", onCreateSpace: onCreate }))
    );
    fireEvent.click(screen.getByText("创建知识库并继续"));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it("error 文案渲染到第 1 步卡片内", () => {
    render(createElement(StepPanels, panelProps({ error: "名称已被占用" })));
    expect(screen.getByText("名称已被占用")).toBeTruthy();
  });

  it("creating 态按钮文案切换且禁用", () => {
    render(createElement(StepPanels, panelProps({ spaceName: "a", creating: true })));
    expect((screen.getByText("创建中…") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText("创建知识库并继续")).toBeNull();
  });

  it("引擎位为空 → 回落「内置引擎（默认）」，且不被真实引擎列表挤出", () => {
    render(createElement(StepPanels, panelProps({ engines: [], engine: "builtin" })));
    const fallback = screen.getByText("内置引擎（默认）");
    expect((fallback as HTMLElement).className).toContain("border-brand-500");
  });

  it("未配置引擎禁用并标注（未配置）；已配置引擎可选且不带标注", () => {
    const onEngine = vi.fn();
    render(
      createElement(
        StepPanels,
        panelProps({ engines: ENGINES, engine: "builtin", onEngineChange: onEngine })
      )
    );

    const unavailable = screen.getByText(/langbot（未配置）/).closest("button")!;
    expect(unavailable.disabled).toBe(true);

    fireEvent.click(screen.getByText("builtin"));
    expect(onEngine).toHaveBeenCalledWith("builtin");

    // 有真实引擎时不再渲染回落按钮，避免重复入口
    expect(screen.queryByText("内置引擎（默认）")).toBeNull();
  });
});

describe("R0.6.2 StepPanels 第 2 步：来源选择", () => {
  it("展示已创建摘要（空间名 + 引擎），两个去向各自回调", () => {
    const onNext = vi.fn();
    const onRestart = vi.fn();
    render(
      createElement(
        StepPanels,
        panelProps({
          step: 2,
          progress: PROGRESS,
          onStep2Next: onNext,
          onRestart: onRestart,
        })
      )
    );

    expect(screen.getByText(/已创建「产品资料库」（引擎：builtin）。/)).toBeTruthy();

    fireEvent.click(screen.getByText("重新开始"));
    fireEvent.click(screen.getByText("已添加内容，进入提问 →"));
    expect(onRestart).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);

    // 两个来源卡片仍在
    expect(screen.getByText("粘贴文章链接")).toBeTruthy();
    expect(screen.getByText("订阅整号公众号")).toBeTruthy();
  });

  it("第 2 步缺 progress 时不渲染（不可凭空编造空间）", () => {
    render(createElement(StepPanels, panelProps({ step: 2, progress: null })));
    expect(screen.queryByText(/已创建「/)).toBeNull();
    expect(screen.queryByText("已添加内容，进入提问 →")).toBeNull();
  });
});

describe("R0.6.2 StepPanels 第 3 步：收尾", () => {
  it("有 progress 时点名空间；两个去向各自回调", () => {
    const onHome = vi.fn();
    const onAsk = vi.fn();
    render(
      createElement(
        StepPanels,
        panelProps({ step: 3, progress: PROGRESS, onHome, onGoAsk: onAsk })
      )
    );

    expect(screen.getByText(/「产品资料库」已就绪。/)).toBeTruthy();
    fireEvent.click(screen.getByText("去工作台"));
    fireEvent.click(screen.getByText("去提问 →"));
    expect(onHome).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledTimes(1);
  });

  it("无 progress 时回落中性文案，不显示未创建的空间名", () => {
    render(createElement(StepPanels, panelProps({ step: 3, progress: null })));
    expect(screen.getByText(/知识库已就绪。/)).toBeTruthy();
    expect(screen.queryByText(/产品资料库/)).toBeNull();
  });
});

describe("R0.6.2 页面接线：断点持久化", () => {
  function seed(step: number) {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        step,
        spaceId: "sp-9",
        spaceName: "产品资料库",
        engine: "langbot",
        savedAt: 1,
      })
    );
  }

  it("断点恢复（第 1 步）：横幅取 STEPS 文案，并回填空间名与引擎", async () => {
    seed(1);
    render(createElement(OnboardingPage));

    expect(await screen.findByText(`上次做到第 1 步（${STEPS[0].label}），继续完成。`)).toBeTruthy();
    // 表单态被回填（不只是读 progress 展示，而是可直接续填）
    expect(
      (screen.getByLabelText("知识库名称") as HTMLInputElement).value
    ).toBe("产品资料库");
    const langbotBtn = screen.getByText(/langbot（未配置）/).closest("button")!;
    expect(langbotBtn.className).toContain("border-brand-500");
  });

  it("断点恢复（第 2 步）：直接回到选来源面板，展示已建库摘要", async () => {
    seed(2);
    render(createElement(OnboardingPage));

    expect(await screen.findByText(`上次做到第 2 步（${STEPS[1].label}），继续完成。`)).toBeTruthy();
    expect(screen.getByText(/已创建「产品资料库」（引擎：langbot）。/)).toBeTruthy();
    // 第 1 步表单不再出现
    expect(screen.queryByLabelText("知识库名称")).toBeNull();
  });

  it("越界 step 被拒绝：不显示横幅，回到第 1 步", async () => {
    seed(99);
    render(createElement(OnboardingPage));

    expect(await screen.findByText("创建知识库并继续")).toBeTruthy();
    expect(screen.queryByText(/上次做到第/)).toBeNull();
  });

  it("建库成功 → 写入 step 2 并进入第 2 步面板", async () => {
    h.createSpace.mockResolvedValue({
      id: "sp-9",
      name: "产品资料库",
      description: "",
      docCount: 0,
      engine: "builtin",
      engineKbId: "lb-1",
      createdAt: "2026-09-23T00:00:00+00:00",
      updatedAt: "2026-09-23T00:00:00+00:00",
      stats: { docs: 0, chunks: null },
    });
    render(createElement(OnboardingPage));

    fireEvent.change(screen.getByLabelText("知识库名称"), {
      target: { value: "产品资料库" },
    });
    fireEvent.click(await screen.findByText("创建知识库并继续"));

    expect(await screen.findByText(/已创建「产品资料库」（引擎：builtin）。/)).toBeTruthy();
    expect(h.createSpace).toHaveBeenCalledWith({ name: "产品资料库" });
    await waitFor(() => {
      expect(window.localStorage.getItem(STORAGE_KEY)).toBeTruthy();
    });
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY)!) as OnboardingProgress;
    expect(saved).toMatchObject({ step: 2, spaceId: "sp-9", spaceName: "产品资料库" });
    expect(saved.savedAt).toBeGreaterThan(0);
  });

  it("建库失败 → 留在第 1 步，错误文案就地呈现，可改名重试", async () => {
    h.createSpace.mockRejectedValue(new ApiError(30006, "空间名已存在"));
    render(createElement(OnboardingPage));

    fireEvent.change(screen.getByLabelText("知识库名称"), {
      target: { value: "已占用" },
    });
    fireEvent.click(await screen.findByText("创建知识库并继续"));

    expect(await screen.findByText("空间名已存在")).toBeTruthy();
    // 仍在第 1 步，未写断点
    expect(screen.getByText("创建知识库并继续")).toBeTruthy();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
