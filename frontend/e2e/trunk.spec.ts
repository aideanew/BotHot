import { test, expect, type Page } from "@playwright/test";

/**
 * C-T5 前端 e2e 回归（mock 主干 8 条路径）
 * 定位策略：role/placeholder/label 优先，不锁死 mock 数据文案；
 * 仅两类内容字符串允许硬编码——
 *  1. 组件 UI 标签（如"来源文章""重试"），属界面契约；
 *  2. 错误注入触发词"触发错误"，属 lib/api.ts mock 钩子契约。
 */

const FAIL_TRIGGER = "触发错误";
const MOCK_LOGIN_KEY = "bothot_mock_login";

/** 顶栏搜索框提交（回车） */
async function topbarSearch(page: Page, keyword: string) {
  const box = page.getByRole("searchbox", { name: "全局搜索" });
  await box.fill(keyword);
  await box.press("Enter");
}

/** 从引导卡完成 mock 登录 */
async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /使用主平台账号登录/ }).click();
  await expect(page.getByRole("button", { name: "退出" })).toBeVisible();
}

test.describe.serial("mock 主干回归", () => {
  let consoleErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      // 未登录游客态访问 /spaces /chat 触发 /api/v1/auth/me 401 为预期行为，浏览器会以 console error 形式报告 Failed to load resource 401，无需视为用例失败
      if (text.includes("401") && text.includes("Unauthorized")) return;
      if (text.includes("Failed to load resource") && text.includes("401")) return;
      consoleErrors.push(text);
    });
    // 统一清会话：串行执行下每个用例从游客态起步
    await page.goto("/");
    await page.evaluate(([k]) => {
      localStorage.removeItem(k as string);
      sessionStorage.clear();
    }, [MOCK_LOGIN_KEY]);
  });

  test.afterEach(async () => {
    expect(consoleErrors, "console 不应出现 error").toEqual([]);
  });

  test("① 未登录访问受保护页跳回首页引导卡", async ({ page }) => {
    await page.goto("/spaces");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("button", { name: /使用主平台账号登录/ })).toBeVisible();

    await page.goto("/chat");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("button", { name: /使用主平台账号登录/ })).toBeVisible();
  });

  test("② 登录 → 首页已登录（昵称 + 退出）", async ({ page }) => {
    await login(page);
    await expect(page.getByRole("button", { name: "退出" })).toBeVisible();
    // 首页出现空间卡入口（不锁死卡片文案，断言卡片链接存在）
    await expect(page.locator('a[href^="/spaces/"]').first()).toBeVisible();
  });

  test("③ 首页搜索 → /chat 自动首问（流式 + 引用）", async ({ page }) => {
    await login(page);
    await topbarSearch(page, "测试问题");
    await expect(page).toHaveURL(/\/chat/);
    // 用户气泡出现
    await expect(page.getByText("测试问题").first()).toBeVisible();
    // 流式完成标志：引用块渲染（伪流式 1.2~2.5s + 页面加载余量）
    await expect(page.getByText("来源文章").first()).toBeVisible({ timeout: 20_000 });
    // 引用列表为 2 条（li 元素计数，不锁死文章标题）
    const citationList = page.getByText("来源文章").locator("xpath=following-sibling::ul/li");
    await expect(citationList).toHaveCount(2);
    // 生成结束：无 loading 态残留
    await expect(page.getByText("正在思考…")).toHaveCount(0);
    await expect(page.getByText("回答中…")).toHaveCount(0);
  });

  test("④ 第二轮追问（多轮并存）", async ({ page }) => {
    await login(page);
    await topbarSearch(page, "测试问题");
    await expect(page.getByText("来源文章").first()).toBeVisible({ timeout: 20_000 });

    const input = page.getByPlaceholder(/输入问题/);
    await input.fill("如何批量导入文章？");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    // 第二个引用块出现即第二轮完成
    await expect(page.getByText("来源文章")).toHaveCount(2, { timeout: 20_000 });
    // 两轮问答并存（用户气泡用精确匹配，避免命中回答正文）
    await expect(page.getByText("测试问题", { exact: true })).toBeVisible();
    await expect(page.getByText("如何批量导入文章？", { exact: true })).toBeVisible();
  });

  test("⑤ 切换空间：确认模态 + 清空会话", async ({ page }) => {
    await login(page);
    await topbarSearch(page, "测试问题");
    await expect(page.getByText("来源文章").first()).toBeVisible({ timeout: 20_000 });

    // 触发切换 → 页内模态
    const selector = page.getByLabel("当前空间");
    const secondValue = await selector.locator("option").nth(1).getAttribute("value");
    await selector.selectOption(secondValue!);
    await expect(page.getByText("切换空间将开启新会话")).toBeVisible();
    await page.getByRole("button", { name: "确认切换" }).click();

    // 消息流清空，回空会话引导
    await expect(page.getByText("开始向机器人提问")).toBeVisible();
    await expect(page.getByText("来源文章")).toHaveCount(0);
    await expect(page.getByLabel("当前空间")).toHaveValue(secondValue!);
  });

  test("⑥ 错误态 + 重试", async ({ page }) => {
    await login(page);
    await topbarSearch(page, "测试问题");
    await expect(page.getByText("来源文章").first()).toBeVisible({ timeout: 20_000 });

    // 触发词提问 → 首轮 30002 错误气泡
    const input = page.getByPlaceholder(/输入问题/);
    await input.fill(`${FAIL_TRIGGER}的提问`);
    await page.getByRole("button", { name: "发送", exact: true }).click();
    await expect(page.getByText("机器人服务异常，请稍后重试")).toBeVisible({ timeout: 10_000 });

    // 重试放行 → 回答 + 引用，错误消失
    await page.getByRole("button", { name: "重试" }).click();
    await expect(page.getByText("机器人服务异常，请稍后重试")).toHaveCount(0, { timeout: 20_000 });
    await expect(page.getByText("来源文章")).toHaveCount(2, { timeout: 20_000 });
    await expect(page.getByRole("button", { name: "重试" })).toHaveCount(0);
  });

  test("⑦ 空间列表 / 详情 / 无效 id 空态", async ({ page }) => {
    await login(page);

    // 列表页：卡片 ≥ 2（不锁死名称）
    await page.goto("/spaces");
    await expect(page.locator('a[href^="/spaces/"]')).toHaveCount(2);
    await expect(page.getByText("篇文章").first()).toBeVisible();

    // 详情页：信息头 + 文章列表 + 三态徽标
    await page.locator('a[href^="/spaces/"]').first().click();
    await expect(page.getByText("返回空间列表")).toBeVisible();
    await expect(page.getByRole("heading", { name: "文章列表" })).toBeVisible();
    await expect(page.getByText("已就绪").first()).toBeVisible();
    await expect(page.getByText("采集中").first()).toBeVisible();
    await expect(page.getByText("失败").first()).toBeVisible();

    // 无效 id → 404 语义空态（不白屏）
    await page.goto("/spaces/nonexistent-id");
    await expect(page.getByText("未找到该知识空间")).toBeVisible();
    await page.getByText("返回空间列表").click();
    await expect(page).toHaveURL(/\/spaces$/);
  });

  test("⑧ 登出 → 回未登录态", async ({ page }) => {
    await login(page);
    await page.getByRole("button", { name: "退出" }).click();
    await expect(page.getByRole("button", { name: /使用主平台账号登录/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "退出" })).toHaveCount(0);
  });

  test("⑨ 链接入库主链路：粘贴 → 解析预览 → 确认入库 → 轮询收敛（mock 即 READY）", async ({ page }) => {
    await login(page);

    // 进入第一个空间详情
    await page.goto("/spaces");
    await page.locator('a[href^="/spaces/"]').first().click();
    await expect(page.getByRole("heading", { name: "文章列表" })).toBeVisible();

    // 展开面板并粘贴链接解析
    await page.getByRole("button", { name: "添加文章" }).click();
    await page.getByLabel("文章链接").fill("https://mp.weixin.qq.com/s/e2e-001");
    await page.getByRole("button", { name: "解析", exact: true }).click();

    // 预览卡：质量徽标（mock 高分）+ 确认入库可用
    await expect(page.getByText(/质量分 \d+/)).toBeVisible({ timeout: 10_000 });
    // 幂等覆盖提示（C-FRONTEND-HARDENING：SPEC §3.3 / D3(a) 覆盖语义明示）
    await expect(page.getByText("同一链接重复提交将覆盖并重新入库。")).toBeVisible();
    const submitBtn = page.getByRole("button", { name: "确认入库" });
    await expect(submitBtn).toBeEnabled();

    // 入库提交 + 轮询收敛：成功提示（C-T7R 接真后为 202 提交 + 轮询至 READY，mock 态即 READY）
    await submitBtn.click();
    await expect(page.getByText("文章已入库")).toBeVisible({ timeout: 10_000 });
    // 成功后文档列表刷新（onSubmitted → reloadTick）
    await expect(page.getByRole("heading", { name: "文章列表" })).toBeVisible();
  });
});
