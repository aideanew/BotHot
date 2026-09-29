"use client";

import { useState } from "react";
import ConfirmModal from "@/components/ConfirmModal";
import { CATEGORY_OPTIONS } from "@/components/DocLifecycleActions";
import {
  BATCH_DOCS_MAX_IDS,
  BATCH_FAILURE_MESSAGES,
  chunkDocIds,
  deleteSpaceDocsBatch,
  recategorizeSpaceDocsBatch,
  type BatchDocFailure,
  type DeleteDocsBatchResult,
  type RecategorizeDocsBatchResult,
  type SpaceDoc,
} from "@/lib/api";

/** 批量端点注入点：admin 面传跨用户变体，用户面用缺省值 */
type DeleteBatchFn = (
  spaceId: string,
  ids: string[]
) => Promise<DeleteDocsBatchResult>;
type RecategorizeBatchFn = (
  spaceId: string,
  ids: string[],
  category: string
) => Promise<RecategorizeDocsBatchResult>;

/**
 * DocBatchActions —— R0.2.6 批量入口（列表多选 + 批量删除 / 批量改分类）
 *
 * 接 R0.2.5 两条端点，按各自的失败语义呈现（两者刻意不同，因副作用性质不同）：
 * - 批量删除 = **篇级部分成功**：逐篇生效并提交，失败篇的记录完整保留、逐篇列出失败原因，
 *   且保留在选中态——再点一次「批量删除」即只重试失败篇。
 * - 批量改分类 = **整批原子**：单批全成功或全批不生效，无「改了一半」中间态。
 *
 * ids 按 `batch_docs_max_ids`（50）切片。切片对删除是语义安全的叠加（逐篇提交不变）；
 * 对改分类会削弱「整批原子」——跨批时各批独立生效，故选择数超出上限时在弹窗内明确提示，
 * 结果面板也逐批列出差错批次，不静默把「整批原子」说成「跨批原子」。
 *
 * 选中态由父级（详情页）持有：勾选须跨「加载更多」保留，而父级在每次拉页后按**已加载**行
 * 修剪选中集，使切过滤后不再可见的行自动退出选中——避免批量删除命中用户看不见的文章。
 */
interface BatchReport {
  kind: "delete" | "recategorize";
  /** 本次目标篇数（= 点击时已选篇数） */
  requested: number;
  /** 实际生效篇数 */
  docs: number;
  /** 删除连带清理的孤儿资产数 */
  assets: number;
  /** 改分类的目标分类（服务端归一化后，空串回「其他」） */
  category: string;
  /** 篇级失败明细（仅删除） */
  failed: BatchDocFailure[];
  /** 被整体拒绝的子批（空批/超上限/越权等，发生在任何生效之前） */
  rejected: { index: number; count: number; message: string }[];
  /** 实际发出的请求批数 */
  chunks: number;
}

interface Props {
  spaceId: string;
  /** 当前过滤下已加载的行（跨页累积）——「全选已加载」与勾选的作用域 */
  docs: SpaceDoc[];
  /** 当前过滤下的总数；与 docs.length 的差额即「还需加载更多才能勾选」的篇数 */
  total: number;
  selected: Set<string>;
  onSelectChange: (next: Set<string>) => void;
  onDocsChanged: () => void;
  /** 批量删除端点（缺省 = 用户本人空间端点） */
  deleteBatch?: DeleteBatchFn;
  /** 批量改分类端点（缺省 = 用户本人空间端点） */
  recategorizeBatch?: RecategorizeBatchFn;
}

function failureText(f: BatchDocFailure): string {
  return BATCH_FAILURE_MESSAGES[f.code] ?? `该篇未能处理（错误码 ${f.code}）`;
}

export default function DocBatchActions({
  spaceId,
  docs,
  total,
  selected,
  onSelectChange,
  onDocsChanged,
  deleteBatch,
  recategorizeBatch,
}: Props) {
  const [modal, setModal] = useState<"delete" | "recategorize" | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<BatchReport | null>(null);

  const count = selected.size;
  /** 超出单批上限时按批次提示；count 为 0 时按 1 批取词，避免「分 0 批」 */
  const batchCount = Math.ceil(count / BATCH_DOCS_MAX_IDS) || 1;
  const willChunk = count > BATCH_DOCS_MAX_IDS;
  const allLoaded = docs.length > 0 && docs.every((d) => selected.has(d.id));
  const someLoaded = docs.some((d) => selected.has(d.id));
  const remaining = total - docs.length;

  /** 「全选已加载」：全选当前已加载行，再次点击全取消。未加载的行不受影响 */
  const toggleAllLoaded = () => {
    const next = new Set(selected);
    if (allLoaded) docs.forEach((d) => next.delete(d.id));
    else docs.forEach((d) => next.add(d.id));
    setReport(null);
    onSelectChange(next);
  };

  /** 批量删除：跨子批合并篇级结果；失败篇留在选中态供原样重试。
   *  注入端点的缺省值在**调用时**取用（非渲染期）：渲染期解引用会让未声明该导出
   *  的测试替身直接抛错。runRecategorize 同款。 */
  const runDelete = async (ids: string[]) => {
    const deleteFn = deleteBatch ?? deleteSpaceDocsBatch;
    setBusy(true);
    setReport(null);
    const chunks = chunkDocIds(ids);
    let done = 0;
    let assets = 0;
    const failed: BatchDocFailure[] = [];
    const rejected: BatchReport["rejected"] = [];
    for (let i = 0; i < chunks.length; i++) {
      try {
        const r = await deleteFn(spaceId, chunks[i]);
        done += r.docs;
        assets += r.assets;
        failed.push(...r.failed);
      } catch (e) {
        rejected.push({
          index: i + 1,
          count: chunks[i].length,
          message: e instanceof Error ? e.message : "操作失败，请稍后重试",
        });
      }
    }
    onSelectChange(new Set(failed.map((f) => f.docId)));
    setReport({
      kind: "delete",
      requested: ids.length,
      docs: done,
      assets,
      category: "",
      failed,
      rejected,
      chunks: chunks.length,
    });
    onDocsChanged();
    setBusy(false);
    setModal(null);
  };

  /** 批量改分类：单批原子；跨批时逐批记录被拒批次（前面的批已生效、不回滚） */
  const runRecategorize = async (ids: string[], category: string) => {
    const recatFn = recategorizeBatch ?? recategorizeSpaceDocsBatch;
    setBusy(true);
    setReport(null);
    const chunks = chunkDocIds(ids);
    let done = 0;
    let returned = "";
    const rejected: BatchReport["rejected"] = [];
    for (let i = 0; i < chunks.length; i++) {
      try {
        const r = await recatFn(spaceId, chunks[i], category);
        done += r.docs;
        returned = r.category;
      } catch (e) {
        rejected.push({
          index: i + 1,
          count: chunks[i].length,
          message: e instanceof Error ? e.message : "操作失败，请稍后重试",
        });
      }
    }
    onSelectChange(new Set());
    setReport({
      kind: "recategorize",
      requested: ids.length,
      docs: done,
      assets: 0,
      category: returned,
      failed: [],
      rejected,
      chunks: chunks.length,
    });
    onDocsChanged();
    setBusy(false);
    setModal(null);
  };

  const problemCount = report
    ? report.failed.length + report.rejected.length
    : 0;

  return (
    <>
      {docs.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <label className="flex cursor-pointer select-none items-center gap-1.5 text-caption text-neutral-600">
            <input
              type="checkbox"
              checked={allLoaded}
              aria-label="全选已加载"
              disabled={busy}
              onChange={toggleAllLoaded}
              ref={(el) => {
                if (el) el.indeterminate = someLoaded && !allLoaded;
              }}
              className="h-4 w-4 accent-brand-500"
            />
            全选已加载（{docs.length}）
          </label>
          <span className="text-caption text-neutral-400">已选 {count} 篇</span>
          <button
            type="button"
            disabled={count === 0 || busy}
            onClick={() => {
              setReport(null);
              setModal("delete");
            }}
            className="rounded border border-red-300 px-3 py-1 text-caption text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            批量删除{willChunk ? `（分 ${batchCount} 批）` : ""}
          </button>
          <button
            type="button"
            disabled={count === 0 || busy}
            onClick={() => {
              setReport(null);
              setModal("recategorize");
            }}
            className="rounded border border-neutral-300 px-3 py-1 text-caption text-neutral-600 hover:bg-neutral-50 disabled:opacity-50"
          >
            批量改分类{willChunk ? `（分 ${batchCount} 批）` : ""}
          </button>
          <button
            type="button"
            disabled={count === 0 || busy}
            onClick={() => {
              setReport(null);
              onSelectChange(new Set());
            }}
            className="rounded px-2 py-1 text-caption text-neutral-500 hover:bg-neutral-50 disabled:opacity-50"
          >
            取消选择
          </button>
          {remaining > 0 && (
            <span className="text-caption text-neutral-400">
              还有 {remaining} 篇未加载，需先「加载更多」才能勾选
            </span>
          )}
        </div>
      )}

      {report && (
        <div className="card mt-3 p-4" role="status" aria-live="polite">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 text-caption">
              {report.kind === "delete" ? (
                <p className="text-base font-medium text-neutral-900">
                  批量删除：已生效 {report.docs} 篇 / 共 {report.requested} 篇
                  {report.assets > 0
                    ? `，连带清理 ${report.assets} 个孤儿资产`
                    : ""}
                </p>
              ) : (
                <p className="text-base font-medium text-neutral-900">
                  批量改分类：已改 {report.docs} 篇 → {report.category || "其他"}
                </p>
              )}
              {report.chunks > 1 && (
                <p className="mt-1 text-neutral-400">
                  超出单批 {BATCH_DOCS_MAX_IDS} 篇上限，已分 {report.chunks} 批执行，各批独立生效
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setReport(null)}
              className="shrink-0 rounded px-2 py-1 text-caption text-neutral-500 hover:bg-neutral-50"
            >
              关闭
            </button>
          </div>
          {problemCount > 0 && (
            <ul className="mt-3 space-y-1 text-caption">
              {report.failed.map((f) => (
                <li key={f.docId} className="text-red-600">
                  {docs.find((d) => d.id === f.docId)?.title ?? f.docId}：{failureText(f)}
                </li>
              ))}
              {report.rejected.map((r) => (
                <li key={r.index} className="text-red-600">
                  第 {r.index} 批（{r.count} 篇）：{r.message}
                </li>
              ))}
            </ul>
          )}
          {report.kind === "delete" && report.failed.length > 0 && (
            <p className="mt-3 text-caption text-neutral-400">
              未生效的篇仍保持选中，再点「批量删除」即只重试这些篇。
            </p>
          )}
        </div>
      )}

      <ConfirmModal
        open={modal === "recategorize"}
        title={`批量改分类：已选 ${count} 篇`}
        description={`同一批（≤${BATCH_DOCS_MAX_IDS} 篇）整体生效，不会出现「改了一半」。${
          willChunk
            ? `已选 ${count} 篇超出单批上限，将分 ${batchCount} 批执行，各批独立生效、非整体原子。`
            : ""
        }分类是资产级属性，改动对本篇在其他知识空间的呈现一并生效；号主改文会使分类按新内容重算覆盖。`}
        confirmText="批量改分类"
        options={CATEGORY_OPTIONS}
        initialValue={CATEGORY_OPTIONS[0].value}
        busy={busy}
        onConfirm={(v) => void runRecategorize(Array.from(selected), v ?? "")}
        onCancel={() => setModal(null)}
      />
      <ConfirmModal
        open={modal === "delete"}
        title={`批量删除：已选 ${count} 篇`}
        description={`逐篇删除并逐篇提交：引擎侧失败的文章不会被删除、可原样重试；已成功删除的不可撤销。不再被任何其他空间引用的资产会连带清理（跨空间共享的资产保留）。${
          willChunk ? `已选 ${count} 篇超出单批上限，将分 ${batchCount} 批执行。` : ""
        }`}
        confirmText="确认批量删除"
        busy={busy}
        onConfirm={() => void runDelete(Array.from(selected))}
        onCancel={() => setModal(null)}
      />
    </>
  );
}
