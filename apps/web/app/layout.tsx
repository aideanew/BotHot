import type { Metadata } from "next";
import TopBar from "@/components/TopBar";
import { AuthProvider } from "@/components/AuthContext";
import "./globals.css";

export const metadata: Metadata = {
  // template 与各页 usePageTitle 的 `<页名> · BotHot` 保持同序：
  // SSR 阶段的页签标题与水合后客户端设置的标题一致，不会出现两种格式。
  title: { default: "BotHot", template: "%s · BotHot" },
  description: "公众号链接 → 知识库 → 机器人问答 闭环",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">
        <AuthProvider>
          <TopBar />
          <div className="min-h-[calc(100vh-3.5rem)]">{children}</div>
        </AuthProvider>
      </body>
    </html>
  );
}
