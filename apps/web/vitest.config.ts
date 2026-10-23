import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

/**
 * Vitest 单测配置（C-T6）
 * - 仅收 tests/ 目录，避免误抓 e2e/（Playwright 套件归 test:e2e）；
 * - resolve alias 对齐 tsconfig 的 @/* 路径别名。
 * - environment: happy-dom — vitest 5.x forks/threads pool 在跨进程序列化
 *   jsdom 30.x 时触发 webidl.util.markAsUncloneable 崩溃；happy-dom 不依赖
 *   webidl，可正常工作。
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  oxc: {
    jsx: {
      runtime: "automatic",
      importSource: "react",
    },
  },
  test: {
    include: ["tests/**/*.spec.ts", "tests/**/*.spec.tsx"],
    environment: "happy-dom",
    // S35.4（P-105 / D-V18-08）：happy-dom 的文档基址默认落在
    // http://localhost:3000——那是主平台专用端口（AGENTS.md 明令 BotHot 不得碰），
    // 未桩的相对路径 fetch 会真的拨过去。钉到 3200（BotHot 前端宿主端口），
    // 让"拨通主平台端口"这件事在结构上不可能；未桩的 fetch 由 setup 直接抛错。
    environmentOptions: {
      happyDOM: {
        url: "http://localhost:3200/",
      },
    },
    setupFiles: ["./tests/setup-fetch-guard.ts"],
    // CI runner 是 UTC，本机多为 UTC+8；断言「今天 10:00」这类本地时区文案时，
    // 只 vi.setSystemTime 钉时刻而不钉时区，同一时刻在 UTC 下会渲染成 02:00 → 仅 CI 红。
    // 统一按产品目标时区 Asia/Shanghai 运行。
    env: {
      TZ: "Asia/Shanghai",
    },
    // 失败时留档，供 CI 以 artifact 上传（此前只有摘要、无原始输出，
    // 导致定位必须靠等价环境复现，取证成本高）。
    reporters: ["default", "junit"],
    outputFile: { junit: "vitest-report/junit.xml" },
  },
});
