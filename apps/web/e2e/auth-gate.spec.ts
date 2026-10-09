import { test, expect } from "@playwright/test";

/**
 * G4 —— AuthGate 统一未登录守卫 e2e 矩阵（2026-10-10）。
 *
 * 背景：未登录访问受保护页此前六形态并存（白屏 null ×2 / 裸调 API 401 错误壳 ×3 /
 * 跳首页 ×4 / admin loading-guest 不分）；统一为 AuthGate 原地卡片后，本套件
 * 逐页锁定契约：锚点文案「尚未登录或会话已过期」可见 + 登录按钮可见 + URL 不跳转。
 *
 * 豁免页（不在矩阵）：/（首页 guest 引导卡）、/hot（游客可浏览）、/auth/*（SSO 回调）。
 * 口径：MOCK 态产物（NEXT_PUBLIC_API_MOCK=true 烘焙），PORT=3456，
 * 与 trunk.spec 双口径约定一致（见 playwright.config.ts）。
 */

const MOCK_LOGIN_KEY = "bothot_mock_login";

const PROTECTED_PAGES = [
  "/spaces",
  "/subscriptions",
  "/jobs",
  "/public",
  "/engines",
  "/chat",
  "/onboarding",
  "/bots",
  "/admin",
];

test.describe.serial("AuthGate 未登录统一守卫矩阵", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(([k]) => {
      localStorage.removeItem(k as string);
      sessionStorage.clear();
    }, [MOCK_LOGIN_KEY]);
  });

  for (const path of PROTECTED_PAGES) {
    test(`未登录访问 ${path} → AuthGate 统一卡片（原地，不跳转）`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByText("尚未登录或会话已过期")).toBeVisible();
      await expect(page.getByRole("button", { name: /使用主平台账号登录/ })).toBeVisible();
      await expect(page.getByText("返回首页")).toBeVisible();
      // 原地渲染：URL 保留用户意图路径（散装重定向已废除）
      await expect(page).toHaveURL(new RegExp(path.replace(/\//g, "\\/") + "$"));
      // 受保护内容不得渲染
      await expect(page.getByText("AUTH REQUIRED")).toBeVisible();
    });
  }

  test("未登录访问无效地址 → 404 兜底页（非 AuthGate 域，锁定不混淆）", async ({ page }) => {
    await page.goto("/definitely-not-a-page");
    await expect(page.getByText("页面不存在或已被移动")).toBeVisible();
  });
});
