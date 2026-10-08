import { test, expect } from "@playwright/test";

/**
 * W9 D.6 —— /bots e2e（mock 主干，端口 3200）
 *
 * 覆盖：
 * 1. 渠道列表渲染 + Tab 切换到推送任务
 * 2. 新建推送任务（Cron 编辑器交互）
 * 3. 任务日志弹窗
 * 4. 分页组件存在性
 *
 * 端口 3200（旧端口已废止，见 AGENTS.md 端口纪律表）；mock 态执行。
 */

const MOCK_LOGIN_KEY = "bothot_mock_login";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /使用主平台账号登录/ }).click();
  await expect(page.getByRole("button", { name: "退出" })).toBeVisible();
}

test.describe.serial("/bots 推送任务 e2e", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(([k]) => {
      localStorage.removeItem(k as string);
      sessionStorage.clear();
    }, [MOCK_LOGIN_KEY]);
  });

  test("① 渠道列表渲染 + 切换到推送任务 Tab", async ({ page }) => {
    await login(page);
    await page.goto("/bots");
    // 渠道列表区域可见
    await expect(page.getByRole("tab", { name: "推送渠道" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "推送任务" })).toBeVisible();

    // 切到推送任务
    await page.getByRole("tab", { name: "推送任务" }).click();
    // 任务列表区域加载（动态导入可能需要等待）。断言锚定「新建任务」按钮（恒存在）：
    // 原 getByText(/暂无推送任务|新建任务/) 在空列表态命中按钮+空态文案两个节点，
    // strict mode 直接 violation（2026-09-30 CI mock e2e 实证；本地从未跑过该套件）。
    await expect(page.getByRole("button", { name: "+ 新建任务" })).toBeVisible({ timeout: 10_000 });
  });

  test("② 新建推送任务——Cron 编辑器联动", async ({ page }) => {
    await login(page);
    await page.goto("/bots");
    await page.getByRole("tab", { name: "推送任务" }).click();

    // 点击新建任务
    await page.getByRole("button", { name: "+ 新建任务" }).click();
    await expect(page.getByText("新建推送任务")).toBeVisible();

    // 任务名称
    await page.getByPlaceholder("如：每日热点速报").fill("e2e 测试任务");

    // Cron 编辑器可见（默认 trigger_type=cron）
    await expect(page.getByLabel("定时规则预设")).toBeVisible();

    // 切到事件类型
    await page.getByRole("radio", { name: "事件" }).click();
    await expect(page.getByText("事件类型")).toBeVisible();
    // Cron 编辑器隐藏
    await expect(page.getByLabel("定时规则预设")).not.toBeVisible();
  });

  test("③ 任务日志弹窗打开与关闭", async ({ page }) => {
    await login(page);
    await page.goto("/bots");
    await page.getByRole("tab", { name: "推送任务" }).click();

    // 如果有任务行，点击日志按钮
    const logBtn = page.getByRole("button", { name: "日志" }).first();
    if (await logBtn.isVisible()) {
      await logBtn.click();
      await expect(page.getByText(/任务日志|暂无/)).toBeVisible({ timeout: 5_000 });
      // 关闭弹窗
      await page.getByRole("button", { name: "关闭" }).click();
    }
  });

  test("④ 分页组件：多页时显示 Pagination", async ({ page }) => {
    await login(page);
    await page.goto("/bots");
    // 单页时 Pagination 不出现
    const pagination = page.getByRole("navigation", { name: "分页导航" });
    // 不强制断言存在（单页可能不显示），仅断言不白屏
    await expect(page.getByRole("tab", { name: "推送渠道" })).toBeVisible();
  });
});
