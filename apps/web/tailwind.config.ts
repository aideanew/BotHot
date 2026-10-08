import type { Config } from "tailwindcss";

/**
 * BotHot 设计 token（C-T1）
 * 原则：浅色主题、克制留白、圆角卡片风；不引入暗色模式。
 * 页面内禁止散写裸色值，一律引用本文件的语义 token。
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // 浅色色板：品牌主色 + 中性灰阶（覆盖默认，收敛用色范围）
      colors: {
        brand: {
          50: "#eef6ff",
          100: "#d9eaff",
          200: "#bcdaff",
          300: "#8ec2ff",
          400: "#59a1ff",
          500: "#2f80ed", // 主操作色（按钮/链接）
          600: "#1f6ad4", // hover
          700: "#1a55ab",
          800: "#17467f",
          900: "#153a66",
        },
        neutral: {
          0: "#ffffff",
          50: "#fafafa",
          100: "#f5f5f5",
          200: "#e5e5e5", // 分割线
          300: "#d4d4d4", // 输入框描边
          400: "#a3a3a3", // 占位文字
          500: "#737373", // 次要文字
          700: "#404040", // 正文
          900: "#171717", // 标题
        },
        success: "#16a34a",
        warning: "#d97706",
        danger: "#dc2626",
      },
      // 中文字体栈：优先系统 UI 字体，避免加载网络字体
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
      },
      // 圆角卡片风
      borderRadius: {
        card: "12px",
        input: "10px",
      },
      fontSize: {
        // 收敛字号：正文基准 14px，标题层级少量档位
        base: ["14px", { lineHeight: "22px" }],
        "title-lg": ["20px", { lineHeight: "28px" }],
        "title-sm": ["16px", { lineHeight: "24px" }],
        caption: ["12px", { lineHeight: "18px" }],
      },
      boxShadow: {
        card: "0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)",
        popover: "0 4px 16px rgba(0, 0, 0, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
