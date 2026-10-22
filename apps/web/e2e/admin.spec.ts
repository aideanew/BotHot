import { test, expect, type Page } from "@playwright/test";

/**
 * STEP-14b S14b.4.1 / S14b.4.2 —— 管理端 e2e。
 *
 * 两档口径与 `playwright.config.ts` 的双口径一致，先说清本文件**能证明什么**：
 *
 * ① 演示态（CI 阻塞门禁，`NEXT_PUBLIC_API_MOCK=true` + :3456）——下面①～④条无条件执行。
 *    这一档覆盖的是权限分层与版式：mock 会话的 `is_admin` 恒为 `false`，而
 *    `/api/v1/admin/*` 与 `/api/v1/system/ready` 都在演示态豁免清单里（STEP-15b 的口径：
 *    后台跨用户读面与部署事实不造样例）。所以**四屏面板与告警状态条在这一档结构上不可达**，
 *    这不是漏写用例，是演示态刻意没有后台数据；四屏的渲染契约（含错误态与"读不到 ⇒ 未知"）
 *    由 `tests/admin-ops-panels.spec.tsx` 无条件执行地锁住。
 * ② 真后端档（`E2E_REAL_BACKEND=1`，CI 非阻塞）——⑤～⑦条。本档在本机与 CI **均未执行过**
 *    （前置三条见 `e2e/real-backend.spec.ts` 头部）；里面的选择器是逐个从组件源码读出来的，
 *    解除闸门时需先复核再采信。
 */

const MOCK_LOGIN_KEY = "bothot_mock_login";
const REAL_BACKEND_ENABLED = process.env.E2E_REAL_BACKEND === "1";

async function mockLogin(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /使用主平台账号登录/ }).click();
  await expect(page.getByRole("button", { name: "退出" })).toBeVisible();
}

/**
 * 内容区（`<main>`）在 375px 下是否横向溢出。
 * 只判 main 内元素：顶栏与侧边 chrome 不归 STEP-14b 所有，把它们的版式问题算进本卡的
 * 判据会让这张卡去改别人的文件。
 */
async function mainOverflow(page: Page): Promise<{ vw: number; offenders: string[] } | null> {
  return page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return null;
    const vw = window.innerWidth;
    const offenders: string[] = [];
    for (const el of Array.from(main.querySelectorAll("*"))) {
      const rect = el.getBoundingClientRect();
      if (Math.round(rect.right) > vw || Math.round(rect.left) < 0) {
        offenders.push(`${el.tagName}.${el.getAttribute("class") ?? ""}`.slice(0, 80));
      }
    }
    return { vw, offenders };
  });
}

test.describe.serial("管理端 e2e（演示态无条件执行 + 真后端档闸门）", () => {
  let consoleErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      // 游客态的 /auth/me 401 是预期读数；⑤～⑦档里 /ready 的 503 也是预期读数
      // （依赖未就绪时后端回 503 + 标准信封，AlertBanner 要拿这份明细而不是撞异常）
      if (text.includes("401")) return;
      if (text.includes("503")) return;
      consoleErrors.push(text);
    });
    await page.goto("/");
    await page.evaluate(([k]) => {
      localStorage.removeItem(k as string);
      sessionStorage.clear();
    }, [MOCK_LOGIN_KEY]);
  });

  test.afterEach(async () => {
    expect(consoleErrors, "console 不应出现 error").toEqual([]);
  });

  test("① 游客访问 /admin 与 /admin/ops：原地渲染统一 AuthGate，不重定向", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.getByText("尚未登录或会话已过期")).toBeVisible();
    await expect(page).toHaveURL(/\/admin$/);

    await page.goto("/admin/ops");
    await expect(page.getByText("尚未登录或会话已过期")).toBeVisible();
    await expect(page).toHaveURL(/\/admin\/ops$/);
  });

  test("② 键盘可达：Tab 到登录按钮、回车登录，落点是权限分层而不是白屏", async ({ page }) => {
    await page.goto("/admin");
    // 先等游客卡定型再走 Tab：mock 的 /auth/me 要过 delay()，判定中态与游客态是两个 DOM
    await expect(page.getByText("尚未登录或会话已过期")).toBeVisible();
    let label = "";
    for (let i = 0; i < 30; i++) {
      await page.keyboard.press("Tab");
      label = (await page.evaluate(() => document.activeElement?.textContent ?? "")).trim();
      if (/使用主平台账号登录/.test(label)) break;
    }
    expect(label, "30 次 Tab 内必须能键盘到达登录按钮").toMatch(/使用主平台账号登录/);
    await page.keyboard.press("Enter");
    // mock 登录写本地标记后整页刷新，回到同一 URL：游客卡 → 权限不足卡，不发生跳转
    await expect(page.getByText("权限不足")).toBeVisible();
    await expect(page).toHaveURL(/\/admin$/);
  });

  test("③ 非 admin 的处置：两屏都给出出口链接", async ({ page }) => {
    await mockLogin(page);

    await page.goto("/admin");
    await expect(page.getByText("权限不足")).toBeVisible();
    await expect(page.getByRole("link", { name: "返回空间列表" })).toBeVisible();

    await page.goto("/admin/ops");
    await expect(page.getByText("权限不足")).toBeVisible();
    await expect(page.getByRole("link", { name: "回到首页" })).toBeVisible();
  });

  test("④ 375px：游客卡与权限不足卡的内容区不横向溢出", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    await page.goto("/admin");
    const guest = await mainOverflow(page);
    expect(guest, "AuthGate 必须有 <main> 内容区").not.toBeNull();
    // 视口确实缩了（headless 滚动条会占位，故只断"窄于 375 且明显小于默认 1280"）
    expect(guest!.vw).toBeLessThanOrEqual(375);
    expect(guest!.vw).toBeGreaterThan(320);
    expect(guest!.offenders, `越界元素：${guest!.offenders.join(" | ")}`).toEqual([]);

    await mockLogin(page);
    await page.goto("/admin");
    const denied = await mainOverflow(page);
    expect(denied).not.toBeNull();
    expect(denied!.offenders, `越界元素：${denied!.offenders.join(" | ")}`).toEqual([]);
  });

  test.describe("四屏主路径（真后端 + operator 会话）", () => {
    test.skip(
      !REAL_BACKEND_ENABLED,
      "需 E2E_REAL_BACKEND=1：演示态里 /api/v1/admin/* 与 /ready 都不造样例，且 mock 会话 is_admin 恒 false"
    );

    test("⑤ 五屏切换：各屏渲染自己的标题，切屏重挂载取当下读数", async ({ page }) => {
      await page.goto("/admin/ops?screen=push");
      await expect(page.getByText("触发一次推送")).toBeVisible();

      await page.getByRole("button", { name: "进程存活" }).click();
      await expect(page.getByText("常驻进程心跳")).toBeVisible();
      await expect(page.getByRole("button", { name: "进程存活" })).toHaveAttribute(
        "aria-current",
        "page"
      );

      await page.getByRole("button", { name: "发现渠道" }).click();
      await expect(page.getByText("推送通道")).toBeVisible();

      await page.getByRole("button", { name: "引擎密钥" }).click();
      await expect(page.getByRole("button", { name: "登记" })).toBeVisible();

      // 采集配置屏（STEP-14b 余项）：兜底默认关 ⇒ 保存按钮可用且没有拦截文案
      await page.getByRole("button", { name: "采集配置" }).click();
      await expect(page.getByText("分类清单")).toBeVisible();
      await expect(page.getByText("付费详情兜底")).toBeVisible();
      await expect(page.getByRole("button", { name: "保存分类清单" })).toBeVisible();
    });

    test("⑥ 告警状态条：/ready 的 alerting 读数必须被画出来", async ({ page }) => {
      await page.goto("/admin/ops");
      const bar = page.getByRole("status");
      await expect(bar).toBeVisible();
      await expect(bar.getByText(/告警未启用|告警已启用|依赖未就绪|未知/)).toBeVisible();
      // 点「重读」再取一次：本条不轮询，新读数必须是显式动作
      await bar.getByRole("button", { name: "重读" }).click();
      await expect(bar.getByText(/告警|依赖未就绪|未知/)).toBeVisible();
    });

    test("⑦ 375px 下密钥表横向滚动而不是挤压", async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto("/admin/ops?screen=keys");
      const wrap = page.locator(".card.overflow-x-auto");
      await expect(wrap).toBeVisible();
      const box = await wrap.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
      expect(box.scroll, "min-w-[720px] 的表应让容器出现横向滚动").toBeGreaterThan(box.client);
    });
  });
});
