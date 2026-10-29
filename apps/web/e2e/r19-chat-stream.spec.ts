import fs from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { CHAT_COPY } from "@/lib/chat/copy";

/**
 * STEP-60（V0.24.0 重写 / V0.25.0 订正）：`/chat` 契约**五态**的真后端验收通道。
 *
 * 五态不是八态：冻结稿 `x-core-views[/chat 流式问答].states` 只有
 * loading / success / error / unauthenticated / degraded 五键（STEP-68 已把逐视图键集
 * 投影进 `UX_VIEW_STATES`）。原卡「八态」里的 initial / forbidden 在该视图没有 DOM 出口，
 * 判据已按增量 §1.2 作废。
 *
 * 供给（由 `bash scripts/e2e/run_real_backend.sh --with-fake-llm --with-fake-langbot` 起）：
 *   ① 真 uvicorn:3300 + MOCK=false 的 next:3200；
 *   ② 假 LLM :3290（`scripts/e2e/fake_llm.py`，三段固定正文）；
 *   ③ 假 LangBot :3291（`scripts/e2e/fake_langbot.py`，检索命中 `fake-doc-1`）；
 *   ④ 种子空间「R24 流式验收空间」（`scripts/e2e/seed_chat_space.py`，admin 名下）。
 * 两个开关都在才执行；缺任一 ⇒ 本套件不执行（`--project=real` 本身也只在 `E2E_REAL_BACKEND=1` 时存在）。
 *
 * 三处**测试侧手段**（不是 mock：请求仍打到真后端，只是改「什么时候让它过去 / 在哪儿截断」）：
 *   ① loading 窗口用 `page.route` 把本次请求推迟 2s。真链路首 delta 只要几十毫秒，
 *      不加这一下，「思考中…」在 Playwright 的轮询间隙里就闪过去了。
 *   ② error 用 `page.route` 读走真后端的完整响应、再**截断在首个 delta 帧之后**：请求与帧字节
 *      全部来自真后端（`route.fetch()`），丢掉的只有 done 及其后的帧 ⇒ 前端读到「干净 EOF、
 *      无 done 帧」⇒ `lib/api/ask.ts` 的 interruptedPartial 分支。
 *      不用 CDP 限速 + 断网：探针实测限速下整段流会在渲染进程侧**一次性**到达，等「首段可见」时
 *      早已缓冲完毕，断网只能换来干净收尾（S60.0 读数见证据）。
 *   ③ degraded 用 `context.setOffline(true)` 让 fetch 当场失败：`lib/api/ask.ts` 把它
 *      归一成 50002，而 50002 正在 `useSseAsk` 的 DEGRADED_CODES 里 ⇒ 走契约的 degraded 文案。
 *
 * 三条**不按卡面原字取供给**的读数（S60.0 探针，见 `EVD-V24-60/s60_0_probe_readings.md`）：
 *   ① 卡面 error 行的供给写 `FAKE_LLM_MODE=abort`，但 abort 在本仓 httpx 眼里是**干净 EOF**
 *      （normal 8 行 / abort 2 行，两次 `exception=None`）⇒ 后端 `_event_stream` 不进 error 分支，
 *      照发 `done` 帧，前端拿到的是一条「内容较短的成功」，证明不了 error 态。
 *   ② 卡面 degraded 行的供给写 `FAKE_LLM_MODE=slow`，但模式是**进程级**的（`--with-fake-llm` 只起
 *      一个 :3290），slow 与 success 在同一 job 里互斥；且 slow 的 16s 首帧与后端
 *      `LLM_FIRST_TOKEN_TIMEOUT=15s` 同点竞争，读数不确定。
 *   ③ 卡面 error 行还有半句「断流后**已渲染正文仍在**」——现读代码只有一种走法兑现得了：
 *      `lib/api/ask.ts` 的 `!streamError && !doneReceived && content !== ""`（流干净结束、无 done 帧）
 *      ⇒ `CHAT_COPY.interruptedPartial`，正文保留；而 `useSseAsk` 的 catch（fetch/reader 硬失败，
 *      如真断网）入口第一件事就是 `content: ""`。两个分支的取舍见证据里的读数表——
 *      故手段② 选「截断」而不是「断网」：后者走的是清空分支，兑现不了这半句。
 *      本 spec 断言 `interruptedPartial` + 假 LLM 首段仍在 + 重试按钮。
 *
 * 跑法（人工，前提齐备时）：
 *   bash scripts/e2e/run_real_backend.sh --with-fake-llm --with-fake-langbot
 *   cd apps/web && PORT=3200 E2E_REAL_BACKEND=1 E2E_CHAT_LLM=1 pnpm exec playwright test \
 *     --project=real e2e/r19-chat-stream.spec.ts
 */

const REAL_BACKEND = process.env.E2E_REAL_BACKEND === "1";
const REAL_LLM = process.env.E2E_CHAT_LLM === "1";

/** `scripts/e2e/seed_chat_space.py` 的 `SPACE_NAME` 逐字同名（跨文件契约：改名要两边一起改）。 */
const SEEDED_SPACE_NAME = "R24 流式验收空间";

/** `scripts/e2e/fake_llm.py` 的 `SEGMENTS[0]`；换掉假上游时这条锚要跟着换。 */
const FAKE_LLM_MARKER = /假 LLM 首段/;

/**
 * 归一规则与 `packages/contracts/src/ux/states.ts`、`apps/api/tests/test_ux_states_contract.py`
 * 同一套：首段 → 去前导 `/` → 小写 → 去非 `[a-z0-9]`（`/chat 流式问答` → `chat`）。
 * 刻意不设别名表——别名表就是第二个真源。
 */
function viewKey(view: string): string {
  const first = view.trim().split(/\s+/)[0] ?? "";
  return first.replace(/^\//, "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * 运行时读冻结稿取 `/chat` 的键集。
 * 为什么读文件而不 import：`@bothot/contracts` 是 `emitDeclarationOnly`，运行时没有值可导；
 * 手抄一份数组正是增量 §1.2 点名要删掉的那个第二真源。
 */
function readChatStates(): string[] {
  const draft = path.resolve(process.cwd(), "../../docs/任务规划V0.12.0/contracts/ux_states.schema.json");
  if (!fs.existsSync(draft)) {
    throw new Error(`冻结稿读不到：${draft}（cwd=${process.cwd()}）——本 spec 必须在 apps/web 下执行`);
  }
  const doc = JSON.parse(fs.readFileSync(draft, "utf8")) as {
    "x-core-views"?: { view?: unknown; states?: unknown }[];
  };
  const views = doc["x-core-views"] ?? [];
  const hit = views.filter((v) => typeof v.view === "string" && viewKey(v.view) === "chat");
  if (hit.length !== 1) {
    throw new Error(`冻结稿 x-core-views 里归一成 "chat" 的视图应恰好一条，实读 ${hit.length} 条`);
  }
  const states = hit[0]?.states;
  if (states === null || typeof states !== "object" || Array.isArray(states)) {
    throw new Error(`/chat 视图的 states 应为「态名 → 说明」的对象，实读 ${JSON.stringify(states)}`);
  }
  return Object.keys(states as Record<string, unknown>);
}

const CHAT_STATES = readChatStates();

if (CHAT_STATES.length !== 5) {
  throw new Error(
    `/chat 契约应为 5 态，实读 ${CHAT_STATES.length} 条：${CHAT_STATES.join(", ")} ⇒ 契约变了就要回来改用例，` +
      "不许让用例悄悄少一条或多出一条",
  );
}

/** 用例表：每一态一条用例，顺序与契约无关（beforeAll 只判集合相等，不判顺序）。 */
const CASES = ["loading", "success", "error", "unauthenticated", "degraded"] as const;

test.skip(
  !REAL_BACKEND || !REAL_LLM,
  "需要 E2E_REAL_BACKEND=1 与 E2E_CHAT_LLM=1（真后端 + LLM 上游，CI 由 fake_llm/fake_langbot 供给）；缺任一个本套件不执行",
);

test.beforeAll(() => {
  expect(
    [...CHAT_STATES].sort(),
    `/chat 的契约键集与用例表不再一一对应（契约 ${CHAT_STATES.join(",")} / 用例 ${CASES.join(",")}）`,
  ).toEqual([...CASES].sort());
});

/** 打开 /chat 并确保选中的是种子空间（`listSpaces()` 的第一个空间不保证是它）。 */
async function openSeededChat(page: Page): Promise<void> {
  await page.goto("/chat");
  await expect(page.getByRole("textbox").first()).toBeVisible({ timeout: 15_000 });
  const select = page.locator("#space-select");
  await expect(select).toBeEnabled({ timeout: 15_000 });
  const option = page.locator("#space-select option", { hasText: SEEDED_SPACE_NAME }).first();
  await expect(option, `空间列表里没有「${SEEDED_SPACE_NAME}」——种子（seed_chat_space.py）没跑或属于别的用户`).toHaveCount(1);
  const value = await option.getAttribute("value");
  expect(value, "种子空间的 option 没有 value").toBeTruthy();
  if ((await select.inputValue()) !== value) {
    await select.selectOption(value as string);
    await page.getByRole("button", { name: "确认切换" }).click();
  }
  await expect(select).toHaveValue(value as string);
}

/** 填问题并回车（与用户操作同一入口，不走路由直达）。 */
async function ask(page: Page, question: string): Promise<void> {
  const input = page.getByRole("textbox").first();
  await input.fill(question);
  await input.press("Enter");
}

test("① loading：首 delta 前「思考中…」可见，且此刻「停止」可点", async ({ page }) => {
  await openSeededChat(page);
  // 把本次请求压住 2s：真链路首 delta 只要几十毫秒，不压这一下这个态抓不稳（见头注手段①）。
  await page.route("**/api/v1/chat/ask", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2_000));
    await route.continue().catch(() => {
      // 「停止」把请求 abort 掉后 continue() 会拒绝，这里不是失败
    });
  });
  try {
    await ask(page, "R19 loading：先别急着回答，我要看「思考中…」这一态");
    await expect(page.getByText(CHAT_COPY.thinking)).toBeVisible({ timeout: 5_000 });
    const stop = page.getByRole("button", { name: CHAT_COPY.stop });
    await expect(stop).toBeVisible();
    await stop.click();
    // 「停止」不能把用户的主动操作渲染成失败态（STEP-69 / S69.3）：中性灰的「已停止」+ 重试
    await expect(page.getByText(CHAT_COPY.stopped)).toBeVisible({ timeout: 10_000 });
  } finally {
    await page.unroute("**/api/v1/chat/ask");
  }
});

test("② success：正常提问 → 增量正文 + 来源文章 + 来源引擎", async ({ page }) => {
  await openSeededChat(page);
  await ask(page, "R19 success：请用一句话说明这篇假文章的主题");
  // 增量正文来自假 LLM 的三段固定正文（SEGMENTS），落到气泡里是拼接后的一整段
  await expect(page.getByText(FAKE_LLM_MARKER)).toBeVisible({ timeout: 30_000 });
  // 引用区来自 meta 帧：假 LangBot 的检索命中必须过 `_filter_by_allowed` 才会画出这两行
  await expect(page.getByText("来源文章")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/来源引擎：/)).toBeVisible({ timeout: 10_000 });
});

/**
 * 把本次 `/api/v1/chat/ask` 的**真响应**截断在首个 delta 帧之后（传输层故障注入）。
 * `route.fetch()` 把请求原样发到真后端并读完整个响应；`fulfill` 只回放 meta + 首个 delta，
 * done 帧被丢掉 ⇒ 浏览器看到的是「干净 EOF、无 done」，与运营商/代理半路掐断同形。
 * 若真后端没吐 delta（供给坏了/检索空），这里直接抛错——不许静默退化成「没断流」的假绿。
 */
async function truncateAfterFirstDelta(page: Page): Promise<void> {
  await page.route("**/api/v1/chat/ask", async (route) => {
    const response = await route.fetch();
    const body = await response.text();
    const frames = body.split("\n\n").filter((frame) => frame.trim() !== "");
    const firstDelta = frames.findIndex((frame) => {
      try {
        const evt = JSON.parse(frame.trim().slice("data:".length)) as { type?: string };
        return evt.type === "delta";
      } catch {
        return false;
      }
    });
    if (firstDelta < 0) {
      throw new Error(`真后端响应里没有 delta 帧，无法截断：${body.slice(0, 200)}`);
    }
    // 不能只写 `{ response, body }`：`fulfill` 会原样复用 `response.headers()`，而 `route.fetch()`
    // 交出的是**已解压**的正文、头里却留着 `content-encoding: gzip`（`/api/v1/*` 是 next 的
    // rewrite 代理，对 SSE 也套了压缩）。明文配 gzip 头 ⇒ 浏览器解码失败 ⇒ fetch 当场拒绝 ⇒
    // 走 `useSseAsk` 的 catch（清空正文 + degraded），永远等不到 interruptedPartial。
    // 三处长度/编码头一律删掉，content-type 显式钉回 SSE（否则会命中「非流式回退」分支）。
    const headers = { ...response.headers() };
    for (const key of ["content-encoding", "content-length", "transfer-encoding"]) {
      delete headers[key];
    }
    headers["content-type"] = "text/event-stream";
    await route.fulfill({
      status: response.status(),
      headers,
      body: `${frames.slice(0, firstDelta + 1).join("\n\n")}\n\n`,
    });
  });
}

test("③ error：流在首段后被截断 → 「连接中断，可重试」+ 正文保留 + 重试按钮", async ({ page }) => {
  await openSeededChat(page);
  await truncateAfterFirstDelta(page);
  try {
    await ask(page, "R19 error：首段之后连接会被切断");
    await expect(page.getByText(CHAT_COPY.interruptedPartial)).toBeVisible({ timeout: 30_000 });
    // 卡面那句「断流后已渲染正文仍在」：干净截断不清 content，所以这一条在本用例里是可读的读数，
    // 不是 UNKNOWN（硬网络错误走 catch 清空分支，那条另有读数，见证据 §1.2）。
    await expect(page.getByText(FAKE_LLM_MARKER)).toBeVisible();
    await expect(page.getByRole("button", { name: "重试" })).toBeVisible();
  } finally {
    await page.unroute("**/api/v1/chat/ask");
  }
});

test("④ unauthenticated：会话失效 → 离开 /chat，且不出现 10004/权限不足", async ({ page, context }) => {
  await openSeededChat(page);
  await context.clearCookies();
  await page.goto("/chat");
  // D-V23-14：断言落点而不只断言文案——middleware 在 cookie 缺席时 307 回首页
  await expect.poll(() => new URL(page.url()).pathname, { timeout: 15_000 }).toBe("/");
  const text = await page.locator("body").innerText();
  expect(text).not.toMatch(/权限不足|10004/);
});

test("⑤ degraded：引擎不可达 → 「引擎暂不可用，请稍后重试或换个空间」", async ({ page, context }) => {
  await openSeededChat(page);
  await context.setOffline(true);
  try {
    await ask(page, "R19 degraded：断网时的引擎不可用提示");
    await expect(page.getByText(CHAT_COPY.degraded)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: "重试" })).toBeVisible();
  } finally {
    await context.setOffline(false);
  }
});
