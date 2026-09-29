"use client";

import { useState } from "react";
import ConfirmModal, { type ConfirmOption } from "@/components/ConfirmModal";
import {
  CATEGORIES,
  deleteSpaceDoc,
  patchSpaceDocCategory,
  type DeleteDocResult,
  type SpaceDoc,
} from "@/lib/api";

/**
 * DocLifecycleActions —— R0.2.4 文档行生命周期入口（改分类 / 删除），复用 ConfirmModal。
 *
 * F-2 背景：此前文档零删除/编辑入口，与 F-1（单页 100 条上限）组合成「删不掉 + 看不全」死锁。
 * 后端已具备 `DELETE`/`PATCH /spaces/{id}/docs/{docId}`（R0.2.1/R0.2.2），本件只补入口。
 *
 * 两个已知语义（前端须知，已写进弹窗描述）：
 * - 分类是**资产级**属性（跨空间共享），改写对本资产在其他空间的呈现一并生效；
 * - 删除会连带清理「不再被任何其他空间引用」的孤儿资产（跨空间共享则保留）。
 */
interface Props {
  spaceId: string;
  doc: SpaceDoc;
  onDeleted: (docId: string, result: DeleteDocResult) => void;
  onRecategorized: (docId: string, category: string) => void;
}

/** 改分类下拉：规则版六类 + 「清空标签」（空串 = 回默认口径）。单篇与批量共用同一份选项 */
export const CATEGORY_OPTIONS: ConfirmOption[] = [
  ...CATEGORIES.map((c) => ({ value: c, label: c })),
  { value: "", label: "清空人工标签（回默认「其他」）" },
];

export default function DocLifecycleActions({
  spaceId,
  doc,
  onDeleted,
  onRecategorized,
}: Props) {
  const [modal, setModal] = useState<"recategorize" | "delete" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleConfirm = async (value?: string) => {
    setBusy(true);
    setError("");
    try {
      if (modal === "delete") {
        const r = await deleteSpaceDoc(spaceId, doc.id);
        setModal(null);
        onDeleted(doc.id, r);
      } else if (modal === "recategorize") {
        const r = await patchSpaceDocCategory(spaceId, doc.id, value ?? "");
        setModal(null);
        onRecategorized(doc.id, r.category);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setError("");
              setModal("recategorize");
            }}
            className="rounded border border-neutral-300 px-3 py-1 text-caption text-neutral-600 hover:bg-neutral-50"
          >
            改分类
          </button>
          <button
            type="button"
            onClick={() => {
              setError("");
              setModal("delete");
            }}
            className="rounded border border-red-300 px-3 py-1 text-caption text-red-600 hover:bg-red-50"
          >
            删除
          </button>
        </div>
        {error && <p className="text-caption text-red-600">{error}</p>}
      </div>

      <ConfirmModal
        open={modal === "recategorize"}
        title={`改分类：${doc.title}`}
        description="分类用于站内筛选。注意：分类是资产级属性，改动对本篇在其他知识空间的呈现一并生效；号主改文会使分类按新内容重算覆盖。"
        confirmText="保存分类"
        options={CATEGORY_OPTIONS}
        initialValue={doc.category ?? ""}
        busy={busy}
        onConfirm={(v) => void handleConfirm(v)}
        onCancel={() => setModal(null)}
      />
      <ConfirmModal
        open={modal === "delete"}
        title={`删除：${doc.title}`}
        description="将从引擎与数据库一并删除；不再被任何其他空间引用的资产会连带清理（跨空间共享的资产保留）。该操作不可撤销。"
        confirmText="确认删除"
        busy={busy}
        onConfirm={() => void handleConfirm()}
        onCancel={() => setModal(null)}
      />
    </>
  );
}
