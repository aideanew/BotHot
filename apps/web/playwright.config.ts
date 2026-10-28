import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e 配置（C-T5；C-T7R 返工：双态执行口径文档化，杜绝 A-T17.1 运行态错配）
 *
 * 双口径约定（验收/CI 统一按此执行）：
 * ① MOCK 态（默认回归）：`NEXT_PUBLIC_API_MOCK=true` 烘焙构建产物，`PORT=3456` 隔离跑
 *    `NEXT_PUBLIC_API_MOCK=true PORT=3456 pnpm test:e2e` → 期望 9/9 绿。
 *    3456 是 e2e 专用隔离口，与业务铁律端口（3000/3200）无冲突。
 * ② 真实态（活体链路）：复用 `http://localhost:3200` 常驻容器（烘焙 MOCK=false），
 *    `PORT=3200` 直接对容器执行（webServer reuseExistingServer 复用，不起新服务）。
 *    严禁把 mock 用例跑在 MOCK=false 容器上（A-T17.1 八红根因：SSO 502 假红非回归）。
 * ③ STEP-59 的 `real` project（`E2E_REAL_BACKEND=1` 才存在）：只收 ②类真后端套件
 *    （`admin.spec.ts` 与 `r19-chat-stream.spec.ts`），会话由 `e2e/real.setup.ts` 从
 *    Redis 种子生成。**没有这个开关时本文件不产生 `projects` 键**——因为 Playwright 一旦
 *    见到非空 `projects` 就只跑里面列出的项目，默认（演示态）那 42 条用例会凭空消失，
 *    表现为"e2e 门禁变绿了"的假绿。故这里用条件展开而不是无条件加项目。
 *
 * baseURL 走 PORT 环境变量（默认 3200），禁止硬编码 3000；
 * webServer 自动起服（复用已构建产物），测试结束自动回收进程。
 */
const PORT = Number(process.env.PORT || 3200);
const REAL_BACKEND = process.env.E2E_REAL_BACKEND === "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // 会话态依赖 localStorage，串行执行避免互相污染
  workers: 1,
  retries: 0,
  // 演示档仍只有 list（CI 的 mock e2e 步骤按这份输出取数，加 reporter 会改它的产物面）。
  // 真后端档加一份 html：08 §2 59.5 的判据写着"失败时上传 playwright-report"，
  // 而只有 list 时 `playwright-report/` 根本不存在 ⇒ 那条上传步会"绿着上传空目录"，
  // 判据看着满足、实际是死的。html 默认落在 apps/web/playwright-report/，与 artifact 路径同。
  reporter: REAL_BACKEND ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: "corepack pnpm start",
    url: `http://localhost:${PORT}`,
    reuseExistingServer: true, // A 手动起服复跑时直接复用
    env: { PORT: String(PORT) },
    timeout: 30_000,
  },
  ...(REAL_BACKEND
    ? {
        // globalSetup 只能挂在 config 顶层：`Project` 类型里没有这个键
        // （playwright/types/test.d.ts 的 globalSetup 声明在 TestConfig 区，1.63 实测 tsc 报错）。
        // 真后端档本来就只有一个 project，挂顶层与挂 project 等价，且少一层"可能被忽略"的歧义。
        globalSetup: "./e2e/real.setup.ts",
        projects: [
          {
            name: "real",
            testMatch: /(admin|r19-chat-stream)\.spec\.ts/,
            // 真后端档默认带 admin 会话；①③ 这类游客/越权负例在自己的 describe 里换掉它。
            // `screenshot: "on"` 是给 04 §1.1.5「四屏截图」留的落点：演示档不开（它会改
            // mock job 的产物体积与口径），真后端档每条用例留一张终态帧，
            // 由 e2e-real job 的 `if: always()` artifact 步骤上传。
            use: { storageState: "e2e/.auth/admin.json", screenshot: "on" },
          },
        ],
      }
    : {}),
});
