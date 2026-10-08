"use client";

/**
 * T1.1.3：根布局级错误兜底（global-error.tsx）——error.tsx 自身渲染失败时的最后防线。
 * 须自带 <html>/<body>（根布局不参与渲染）。
 */
export default function GlobalErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-CN">
      <body
        style={{
          margin: 0,
          minHeight: "60vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui, sans-serif",
          color: "#171717",
        }}
      >
        <h1 style={{ fontSize: "1.25rem", fontWeight: 600 }}>应用出现严重错误</h1>
        <p style={{ color: "#525252", marginTop: "0.5rem" }}>
          请重试；若持续出现请联系管理员。
        </p>
        <button
          type="button"
          onClick={reset}
          style={{
            marginTop: "1.5rem",
            padding: "0.5rem 1rem",
            borderRadius: "0.5rem",
            background: "#2f80ed",
            color: "#fff",
            border: "none",
            cursor: "pointer",
          }}
        >
          重试
        </button>
      </body>
    </html>
  );
}
