/**
 * QualityBadge —— T1.2.4 从 AddArticlePanel 抽出（原文件内私有函数升级为组件）。
 * 质量徽标：≥30 绿 / <30 红（阈值对齐后端 QUALITY_PASS_THRESHOLD=30）。
 */
export default function QualityBadge({ score }: { score: number }) {
  const passed = score >= 30;
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-0.5 text-caption ${
        passed ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
      }`}
      title={`质量分 ${score}（阈值 30）`}
    >
      质量分 {score}
    </span>
  );
}
