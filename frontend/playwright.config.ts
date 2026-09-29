import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e 配置（C-T5；C-T7R 返工：双态执行口径文档化，杜绝 A-T17.1 运行态错配）
 *
 * 双口径约定（验收/CI 统一按此执行）：
 * ① MOCK 态（默认回归）：`NEXT_PUBLIC_API_MOCK=true` 烘焙构建产物，`PORT=3456` 隔离跑
 *    `NEXT_PUBLIC_API_MOCK=true PORT=3456 pnpm test:e2e` → 期望 9/9 绿。
 *    3456 是 e2e 专用隔离口，与业务铁律端口（3000/3333）无冲突。
 * ② 真实态（活体链路）：复用 `http://localhost:3200` 常驻容器（烘焙 MOCK=false），
 *    `PORT=3200` 直接对容器执行（webServer reuseExistingServer 复用，不起新服务）。
 *    严禁把 mock 用例跑在 MOCK=false 容器上（A-T17.1 八红根因：SSO 502 假红非回归）。
 *
 * baseURL 走 PORT 环境变量（默认 3333），禁止硬编码 3000；
 * webServer 自动起服（复用已构建产物），测试结束自动回收进程。
 */
const PORT = Number(process.env.PORT || 3333);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // 会话态依赖 localStorage，串行执行避免互相污染
  workers: 1,
  retries: 0,
  reporter: [["list"]],
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
});
