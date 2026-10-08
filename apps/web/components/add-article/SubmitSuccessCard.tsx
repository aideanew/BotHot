"use client";

/**
 * SubmitSuccessCard —— T1.2.4 入库确认子组件（原 AddArticlePanel 成功提示段）。
 * 含 P0 缓存命中「秒入库」强调分支；纯展示。
 */
interface Props {
  hitCache: boolean;
  hitCount: number;
  title: string;
  onDone: () => void;
}

export default function SubmitSuccessCard({ hitCache, hitCount, title, onDone }: Props) {
  return (
    <div className="mt-4 rounded-card border border-green-200 bg-green-50 p-5">
      <p className="font-medium text-green-700">文章已入库</p>
      {hitCache ? (
        <p className="mt-1 text-base font-medium text-emerald-700">
          ⚡ 命中缓存，秒入库（该文章已被其他空间采集过 {hitCount} 次，本次 0 网络请求）
        </p>
      ) : (
        <p className="mt-1 text-base text-green-600">
          《{title}》已完成入库，文档列表已刷新。
        </p>
      )}
      <button
        onClick={onDone}
        className="mt-3 rounded-input border border-green-300 px-4 py-1.5 text-base text-green-700 hover:bg-green-100"
      >
        完成
      </button>
    </div>
  );
}
