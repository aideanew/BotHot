import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

/**
 * Vitest 单测配置（C-T6）
 * - 仅收 tests/ 目录，避免误抓 e2e/（Playwright 套件归 test:e2e）；
 * - resolve alias 对齐 tsconfig 的 @/* 路径别名。
 * - environment: happy-dom
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  esbuild: {
    jsx: "automatic",
    jsxImportSource: "react",
  },
  test: {
    include: ["tests/**/*.spec.ts", "tests/**/*.spec.tsx"],
    environment: "happy-dom",
    env: {
      TZ: "Asia/Shanghai",
    },
    reporters: ["default", "junit"],
    outputFile: { junit: "vitest-report/junit.xml" },
  },
});
