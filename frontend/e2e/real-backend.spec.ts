import { test, expect } from "@playwright/test";

/**
 * R5.2.5 —— 真实后端 e2e 骨架（Compose 栈 + PG + Redis + LangBot 运行时）
 *
 * 运行前提：
 *   docker compose -p bothot up -d postgres redis langbot langbot_plugin_runtime migrate backend scheduler worker frontend
 *   且 backend 健康检查通过（curl http://localhost:3300/api/v1/system/health → {"code":0}）
 *
 * 验收（文件存在且结构完整）：
 *   npx playwright test --config=playwright.config.ts e2e/real-backend.spec.ts
 *
 * 注意：本套件与 trunk.spec.ts 不可同时运行——trunk.spec.ts 用 MOCK=true（3456），
 * 本套件用 MOCK=false（3200）。两套 base URL 不同，CI 需分 job 执行。
 *
 * 登录路径：SSO OIDC code flow（主平台 aidean_issuer），非 mock 本地登录。
 * 需主平台 OIDC 白名单已配置 bothot redirect_uri，否则 SSO 回调失败。
 */

/** 环境闸：三项前置齐备时才真实执行（默认跳过，保证 CI/本地默认态全绿）。 */
const REAL_BACKEND_ENABLED = process.env.E2E_REAL_BACKEND === "1";

/** 步骤③用的真实文章 URL（须为可公开访问的公众号文章）；可用 E2E_ARTICLE_URL 覆盖。 */
const ARTICLE_URL =
  process.env.E2E_ARTICLE_URL ?? "https://mp.weixin.qq.com/s/example";

test.describe.serial("真实后端 e2e", () => {
  // WD（2026-09-30）复核：本套件**不能**无条件启用——三项前置 CI/本地均不具备：
  //   ① Compose 栈全起（PG + Redis + LangBot，且 backend `/health` 已就绪）；
  //   ② 主平台 OIDC 白名单已登记 bothot redirect_uri（否则 SSO 回调失败）；
  //   ③ 一篇可公开访问的真实公众号文章 URL（步骤③的入库链路）。
  // 原实现是 `test.skip(true, "...")` —— **无条件恒跳过**，套件永远不可能被执行（死断言）。
  // 现改为**环境闸**：设 E2E_REAL_BACKEND=1 即真实执行，未设则跳过。
  // 效果：默认态仍全绿（不阻塞 CI），但前置落地后**能真正跑起来**，而非永久死代码。
  test.skip(
    !REAL_BACKEND_ENABLED,
    "需三项前置：Compose 栈运行 + 主平台 OIDC 白名单 + 真实文章 URL；设 E2E_REAL_BACKEND=1 启用"
  );

  test("① SSO 登录 → 进入已登录态", async ({ page }) => {
    await page.goto("/");
    // 点击登录按钮后跳转主平台 OIDC authorize，回调后回到 /auth/aidean/callback
    await page.getByRole("button", { name: /使用主平台账号登录/ }).click();
    // 回调成功后应看到顶栏用户信息（非 mock 登录键）
    await expect(page.getByRole("button", { name: "退出" })).toBeVisible();
  });

  test("② 创建知识空间", async ({ page }) => {
    await page.goto("/onboarding");
    await page.getByRole("textbox", { name: /空间名称/ }).fill("e2e-test-space");
    await page.getByRole("textbox", { name: /简介/ }).fill("e2e 测试空间");
    await page.getByRole("button", { name: /创建/ }).click();
    await expect(page).toHaveURL(/\/spaces\/[a-z0-9]+/);
  });

  test("③ 粘贴公众号文章链接并入库", async ({ page }) => {
    // 需先有空间（步骤②的结果）
    // 粘贴 mp.weixin.qq.com 链接，提交后等待入库完成
    await page.getByRole("textbox", { name: /粘贴文章链接/ }).fill(ARTICLE_URL);
    await page.getByRole("button", { name: /提交入库/ }).click();
    // 入库异步 → 等待文档出现在列表中
    await expect(page.getByRole("listitem")).toBeVisible({ timeout: 30_000 });
  });

  test("④ 查看文章列表并显示状态", async ({ page }) => {
    // 文章入库后应显示 READY 状态徽章
    await expect(
      page.getByRole("listitem").locator("text=READY").first()
    ).toBeVisible();
  });
});