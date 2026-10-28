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
 * ② 真后端档（`E2E_REAL_BACKEND=1`，CI 非阻塞 job `e2e-real`，STEP-59）——⑤～⑦ 条由 `real`
 *    project 注入 admin 会话；①③ 在同一档里分别换成**游客态**与 **user 会话**复跑（越权负例，
 *    只换 storageState，断言一条不加）。② 在真后端档**不可达**：回车触发的是整页跳
 *    `/api/v1/auth/login`（`lib/api/auth.ts:23-31` 的真实分支，后端 302 去主平台），落点不是
 *    "权限不足卡"；④ 的前半（游客卡）可达、后半（权限不足卡）要另一种会话，而 `test.use` 的作用域
 *    是 describe 不是断言段 ⇒ 同一条用例里两种会话不能各管半段。两处都显式 skip 并写明原因，
 *    不删断言、也不改成"看起来能过"的样子（判据冲突本体见台账 P-131）。
 *    首次执行读数见 `EVD-V22-59/`。
 *
 * ① 在两种构建下**落点不同**，这是已登记的构建差异而不是断言放宽（D-V23-15 / 台账 P-150）：
 *    mock 档 `middleware.ts:24-29` 的 `MOCK_BUILD` 短路不查 cookie ⇒ 原地渲染统一 AuthGate；
 *    real 档 `middleware.ts:38-46` 无 `bothot_session` 一律 307 到 `/` ⇒ 落点是首页。
 *    共同判据是四条不变量（不渲染受保护内容 / 唯一登录入口 / 不出现 10004·权限不足 / 不白屏），
 *    落点本身不进判据；real 分支另附 landing 物证（`guest-landing-*.txt`）以自证 307 确实发生。
 *    这个差异就是 `e2e-real` 红了五轮才被看清的根因——同一句断言在两档下含义不同。
 */

const MOCK_LOGIN_KEY = "bothot_mock_login";
const REAL_BACKEND_ENABLED = process.env.E2E_REAL_BACKEND === "1";

/**
 * 三块 `test.use` 载荷：演示态一律给**空对象**（不注册任何覆盖项），真后端档才换会话。
 * mock 档因此不改变"跑哪些用例、每条断什么"；要说清一处可见差异：③ 为了按 describe 作用域
 * 换 `user.json` 被单独包了一层 describe，它在报告里的**完整标题多了一段父级名**（用例数不变）。
 *
 * 真后端档里"游客态"必须**显式清空** project 默认会话（`playwright.config.ts` 的 real project
 * 给了 `storageState: e2e/.auth/admin.json`）。这里用的是文档化的清空形式 `{cookies: [], origins: []}`，
 * **不是** `undefined`——`CI run 40638671189`/`40643109335` 上 ① 一直红，页面快照（artifact
 * `e2e-real-diagnostics`，`error-context.md`）里画的是 `QA管理员` + `退出` + `ADMIN CONSOLE`，
 * 也就是浏览器**带着 admin 会话**进了 `/admin`。本机探针把两种写法并排测了一遍（同一份 Playwright 1.63、
 * 同一个 chromium，判据是测试服务器实际收到的 `Cookie` 头）：`{storageState: undefined}` ⇒ 服务器仍收到
 * `probe_session=admin-token`（没清掉）；`{storageState: {cookies: [], origins: []}}` ⇒ `Cookie` 头为空。
 * 早期注释里"已在 1.63 源码核对过生效路径"那句是被否证的旧判断，别再按它写。
 * 文件名里的会话由 `e2e/real.setup.ts` 从 Redis 种子生成，不在这里手抄 cookie。
 */
// `StorageState` 不是 `@playwright/test` 的具名导出（1.63 实测 tsc 报 TS2614），所以这里用结构型：
// 空数组的元素类型写成 `never[]`，它对 Playwright 的 `Cookie[]`/`Origin[]` 天然可赋值。
type UseOverride = { storageState?: string | { cookies: never[]; origins: never[] } };

const REAL_GUEST_STATE: UseOverride = REAL_BACKEND_ENABLED
  ? { storageState: { cookies: [], origins: [] } }
  : {};
const REAL_USER_STATE: UseOverride = REAL_BACKEND_ENABLED
  ? { storageState: "e2e/.auth/user.json" }
  : {};
const REAL_ADMIN_STATE: UseOverride = REAL_BACKEND_ENABLED
  ? { storageState: "e2e/.auth/admin.json" }
  : {};

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
  // 真后端档里，直接放在本 describe 的 ①②④ 一律按**游客**跑（project 默认是 admin 会话）
  test.use(REAL_GUEST_STATE);

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

  // ① 的"未登录访问受保护页"落点**按档不同**，这是已登记的构建差异（D-V23-15 / P-150），不是断言放宽：
  //   mock 档 `middleware.ts:24-29` 的 MOCK_BUILD 短路不查 cookie ⇒ 原地渲染统一 AuthGate（下面 mock 分支一字未改）；
  //   real 档 `middleware.ts:38-46` 无 bothot_session 一律 307 → `/` ⇒ 落点是首页。
  // 两档共同的判据是四条不变量（D-V23-15）：不渲染受保护内容 / 有唯一登录入口 / 不出现 10004·权限不足 / 不白屏。
  // real 分支**必须附 landing 物证**（URL + 顶栏文本），否则"绿"无法与"断言写松了凑巧通过"区分开。
  async function expectGuestLanding(page: Page, path: string): Promise<void> {
    await page.goto(path);
    if (!REAL_BACKEND_ENABLED) {
      await expect(page.getByText("尚未登录或会话已过期")).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
      return;
    }
    // 落点：被 307 到首页（`/`，可能带 query）
    await expect(page).toHaveURL(/\/(\?|$)/);
    // 不变量②：唯一登录入口（首页引导卡的按钮，`page.tsx:77`；顶栏那个是 `登录`，不同名）
    await expect(page.getByRole("button", { name: "使用主平台账号登录" })).toHaveCount(1);
    // 不变量①：不渲染任何受保护内容
    const body = await page.locator("body").innerText();
    expect(body).not.toContain("ADMIN CONSOLE");
    // 不变量③：不许把"未登录"说成"权限不足"
    expect(body).not.toMatch(/10004|权限不足/);
    // 物证：这一发的 URL 与顶栏文本，进 artifact（run 成功后 artifact 仍由 if: always() 步上传）
    // 断言在上面的 expect(...) 里已经钉死（顶栏出现"未登录"、首页出现引导卡），这里再留一份人读快照。
    await test.info().attach(`guest-landing-${path.slice(1)}.txt`, {
      body: `URL=${page.url()}\nBODY_HEAD=${body.slice(0, 400)}\n`,
      contentType: "text/plain",
    });
  }

  test("① 游客访问 /admin 与 /admin/ops：未登录守卫给出可判定的落点（两档按不变量，D-V23-15）", async ({ page }) => {
    await expectGuestLanding(page, "/admin");
    await expectGuestLanding(page, "/admin/ops");
  });

  test("② 键盘可达：Tab 到登录按钮、回车登录，落点是权限分层而不是白屏", async ({ page }) => {
    test.skip(
      REAL_BACKEND_ENABLED,
      "真后端档不可达：回车触发的是 /api/v1/auth/login → 外部主平台跳转，不是演示态那种写本地标记后刷新；" +
        "落点断言（权限不足卡）在真后端档没有对应流程。08 §2 59.4 的前提冲突已登 P 号交回规划方"
    );
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

  // ③ 需要"已登录但不是 admin"这一态：演示态用 mockLogin，真后端档换成 user.json 会话。
  // test.use 只能按 describe 作用域生效，所以这一条单独包一层——断言与选择器一条没动。
  test.describe("③ 非 admin 会话", () => {
    test.use(REAL_USER_STATE);

    test("③ 非 admin 的处置：两屏都给出出口链接", async ({ page }) => {
      if (!REAL_BACKEND_ENABLED) {
        await mockLogin(page);
      }

      await page.goto("/admin");
      await expect(page.getByText("权限不足")).toBeVisible();
      await expect(page.getByRole("link", { name: "返回空间列表" })).toBeVisible();

      await page.goto("/admin/ops");
      await expect(page.getByText("权限不足")).toBeVisible();
      await expect(page.getByRole("link", { name: "回到首页" })).toBeVisible();
    });
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

    // 后半段"权限不足卡"这一档取不到，原因不是"没有那种会话"而是作用域不够细：
    // 整条用例挂在游客态（①～④ 直接在本 describe 里，见上面 REAL_GUEST_STATE），
    // 而 `test.use` 只能按 describe 生效、不能只换后半段；把整条换成 user.json 的话，
    // 前半段就再也画不出游客卡（`AuthGate.tsx:45-73` 那张卡只在 status==="guest" 渲染），
    // 于是"两卡都不溢出"降级成"一卡不溢出"。⇒ real 档这一条只证游客卡，
    //   读数口径按"半段"记（下面的 else 分支把这件事写进 stdout，报告里看得见），
    //   冲突本体与两种可两全的出路都登在台账 P-131，不由本卡自取。
    if (!REAL_BACKEND_ENABLED) {
      await mockLogin(page);
      await page.goto("/admin");
      const denied = await mainOverflow(page);
      expect(denied).not.toBeNull();
      expect(denied!.offenders, `越界元素：${denied!.offenders.join(" | ")}`).toEqual([]);
    } else {
      // 一条"没执行的半段"必须留下可见痕迹，否则报告里 ④ 只是 passed，谁看不出少了一半。
      // 这不是断言，是把 skip 的成因写进这份用例的 stdout（P-131 记的就是这条判据的粒度问题）。
      console.log("④ real 档只证游客卡；权限不足卡那一半未执行（原因：test.use 作用域是 describe，见 P-131）");
    }
  });

  test.describe("四屏主路径（真后端 + operator 会话）", () => {
    // 标题里的 operator 是 STEP-14b 留下的说法，实际门槛是 admin（/admin/ops 要 is_admin，
    // 08 §2 59.4 也让本组挂 admin.json）；本卡只接开关与会话，不改标题——改名会动到既有
    // 用例标识，这条已登台账 P-133 交回规划方。
    test.use(REAL_ADMIN_STATE);

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
