"use client";

/**
 * ParsePreviewCard —— T1.2.4 解析预览子组件（原 AddArticlePanel 预览卡片段）。
 * 展示标题/质量徽标/元信息/摘要 + 确认入库按钮与重试；纯展示，状态机留在父面板。
 */
import QualityBadge from "@/components/add-article/QualityBadge";
import { formatTime } from "@/components/DocStatusBadge";
import type { ExtractedArticle } from "@/lib/api";

interface Props {
  data: ExtractedArticle;
  submitting: boolean;
  polling: boolean;
  pollSeconds: number;
  submitError: string;
  onSubmit: () => void;
}

export default function ParsePreviewCard({
  data,
  submitting,
  polling,
  pollSeconds,
  submitError,
  onSubmit,
}: Props) {
  return (
    <div className="mt-4 rounded-card border border-neutral-200 p-5">
      <div className="flex items-start justify-between gap-4">
        <h3 className="text-title-sm font-medium text-neutral-900">{data.title}</h3>
        <QualityBadge score={data.qualityScore} />
      </div>
      <p className="mt-2 text-caption text-neutral-400">
        {data.author}
        {data.publishTime ? ` · ${formatTime(data.publishTime)}` : ""}
        {" · "}
        {data.wordCount} 字 · {data.images.length} 张配图
      </p>
      {/* 正文摘要：取前 3 段 */}
      <div className="mt-3 space-y-1.5 text-base text-neutral-500">
        {data.paragraphs.slice(0, 3).map((p, i) => (
          <p key={i} className="line-clamp-2">
            {p}
          </p>
        ))}
      </div>
      {data.qualityReasons.length > 0 && (
        <ul className="mt-3 list-inside list-disc text-caption text-amber-600">
          {data.qualityReasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
      <button
        onClick={onSubmit}
        disabled={!data.qualityPassed || submitting || polling}
        className="mt-4 rounded-input bg-brand-500 px-5 py-2 text-white hover:bg-brand-600 disabled:opacity-50"
      >
        {submitting ? "提交中…" : polling ? `入库处理中…（已等待 ${pollSeconds} 秒）` : "确认入库"}
      </button>
      {!data.qualityPassed && (
        <p className="mt-2 text-caption text-neutral-400">
          质量分未达阈值（30），无法入库。
        </p>
      )}
      {/* 幂等覆盖提示（SPEC §3.3 / D3(a)）：同 URL 重复提交覆盖重走 ingest，202 不报错 */}
      {data.qualityPassed && (
        <p className="mt-2 text-caption text-neutral-400">
          同一链接重复提交将覆盖并重新入库。
        </p>
      )}
      {submitError && (
        <div className="mt-3 rounded-input border border-red-200 bg-red-50 p-3">
          <p className="text-danger">{submitError}</p>
          <button
            onClick={onSubmit}
            className="mt-2 rounded-input border border-brand-500 px-3 py-1 text-base text-brand-500 hover:bg-brand-50"
          >
            重试
          </button>
        </div>
      )}
    </div>
  );
}
