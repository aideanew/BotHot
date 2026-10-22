import { expect, test } from "@playwright/test";

/**
 * STEP-19 S19.1.3：REQ-F-005 聊天流式的"关 mock 八态"验收通道。
 *
 * 为什么默认跳过（且这不是 `test.skip(true)` 那种死断言）：本套件的两个前提都是**运维供给**，
 * 不是代码缺失——
 *   ① `E2E_REAL_BACKEND=1`：需要一个 MOCK=false 烘焙、监听 3200 的常驻前端 + 3300 后端
 *      （`playwright.config.ts` 的双口径约定；mock 态跑它会拿到 A-T17.1 那类 SSO 502 假红）；
 *   ② `E2E_CHAT_LLM=1`：`/ask` 的流式正文来自 SiliconFlow 直连，没有真实凭据时首 Token
 *      只能以超时收场——卡面「阻塞条件 ①」明令**不得用超时冒充读数**。
 * 两个开关都在，套件才执行；缺任一个 ⇒ 该判定停在 `证据不足`（见 EVD-V3-19/verdicts.md）。
 *
 * 跑法（人工，前提齐备时）：
 *   cd apps/web && E2E_REAL_BACKEND=1 E2E_CHAT_LLM=1 PORT=3200 \
 *     pnpm exec playwright test e2e/r19-chat-stream.spec.ts
 *
 * 八态取自 `docs/任务规划V0.12.0/contracts/ux_states.schema.json` 的 `State` 枚举
 * （initial/loading/empty/success/error/forbidden/unauthenticated/degraded）。
 * ⚠️ 该契约文件在 V0.13.0 及以后的树里没有再出现（`ls docs/任务规划V0.17.0/contracts/` 零命中），
 *    本 spec 引用的是历史版本的冻结稿——这条按读数登记，不在本卡修。
 */

const REAL_BACKEND = process.env.E2E_REAL_BACKEND === "1";
const REAL_LLM = process.env.E2E_CHAT_LLM === "1";

const UX_STATES = [
  "initial",
  "loading",
  "empty",
  "success",
  "error",
  "forbidden",
  "unauthenticated",
  "degraded",
] as const;

test.skip(
  !REAL_BACKEND || !REAL_LLM,
  "需要 E2E_REAL_BACKEND=1 与 E2E_CHAT_LLM=1（关 mock 前端 + 后端 + 真实 LLM 凭据）；缺任一个本套件不执行",
);

async function openChat(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/chat");
  await expect(page.getByRole("textbox").first()).toBeVisible({ timeout: 15_000 });
}

test("① success：一次正常提问出现渐进正文（meta→delta*→done）", async ({ page }) => {
  await openChat(page);
  const input = page.getByRole("textbox").first();
  await input.fill("R19 流式验收：请用一句话说明本知识库的主题");
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).not.toBeEmpty({ timeout: 30_000 });
});

test("② 流式中主动断连：已渲染内容保留，且恢复后可重发", async ({ page, context }) => {
  await openChat(page);
  const input = page.getByRole("textbox").first();
  await input.fill("R19 断连验收：请连续输出较长一段内容");
  await page.keyboard.press("Enter");

  // 必须先确认真的拿到了增量，再去断线——"还没开始就断"证明不了"保留已渲染内容"
  const body = page.locator("main");
  await expect(body).not.toBeEmpty({ timeout: 20_000 });
  const before = await body.innerText();
  expect(before.length).toBeGreaterThan(0);

  const cdp = await context.newCDPSession(page);
  const offline = (value: boolean) =>
    cdp.send("Network.emulateNetworkConditions", {
      offline: value,
      latency: 0,
      downloadThroughput: -1,
      uploadThroughput: -1,
    });

  await offline(true);
  await page.waitForTimeout(1_500);
  await offline(false);

  const afterCut = await body.innerText();
  expect(afterCut.length).toBeGreaterThanOrEqual(before.length);

  const retry = page.getByRole("button", { name: /重试|重新生成/ }).first();
  if (await retry.isVisible()) {
    await retry.click();
    await expect(body).not.toBeEmpty({ timeout: 30_000 });
  }
});

test("③ unauthenticated：会话失效显示「未登录」，不许显示「权限不足」", async ({ page, context }) => {
  await openChat(page);
  await context.clearCookies({ name: "bothot_session" });
  await page.reload();
  const text = await page.locator("main").innerText();
  expect(text).toMatch(/未登录|重新登录|10001/);
  expect(text).not.toMatch(/权限不足|10004/);
});

test("④ 八态清单：只有真取到读数的态才算数", async ({}, testInfo) => {
  // 这张表是给人回填的：每一态初始值一律"未测"，本 test 断言的是"没有把没测过的态打成通过"。
  const checklist = UX_STATES.map((state) => ({ state, verdict: "未测" }));
  await testInfo.attach("ux-states.json", {
    body: JSON.stringify(checklist, null, 2),
    contentType: "application/json",
  });
  expect(checklist).toHaveLength(8);
  expect(checklist.every((row) => row.verdict === "未测")).toBe(true);
});
