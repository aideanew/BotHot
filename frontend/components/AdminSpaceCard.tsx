import type { AdminSpace } from "@/lib/api";

interface AdminSpaceCardProps {
  space: AdminSpace;
  isEditingDesc: boolean;
  editDescValue: string;
  savingDesc: boolean;
  confirmingDelete: boolean;
  deleting: boolean;
  onEditDescStart: (spaceId: string, desc: string) => void;
  onEditDescCancel: () => void;
  onDescValueChange: (v: string) => void;
  onSaveDesc: (spaceId: string) => void;
  onOpen: (spaceId: string) => void;
  onDeleteConfirm: (spaceId: string) => void;
  onDeleteCancel: () => void;
  onDeleteRequest: (spaceId: string) => void;
}

export default function AdminSpaceCard({
  space: s,
  isEditingDesc,
  editDescValue,
  savingDesc,
  confirmingDelete,
  deleting,
  onEditDescStart,
  onEditDescCancel,
  onDescValueChange,
  onSaveDesc,
  onOpen,
  onDeleteConfirm,
  onDeleteCancel,
  onDeleteRequest,
}: AdminSpaceCardProps) {
  return (
    <li className="relative">
      <button
        type="button"
        onClick={() => onOpen(s.id)}
        className="card w-full p-4 text-left transition hover:border-brand-300"
      >
        <p className="truncate text-base font-medium text-neutral-900">
          {s.name}
          {s.isPublic ? " · 公共库" : ""}
        </p>
        <p className="mt-1 truncate text-caption text-neutral-400">
          {s.description || "（未填写简介）"}
        </p>
        <p className="mt-2 text-caption text-neutral-500">
          {s.docCount} 篇 · 归属{" "}
          {s.ownerNickname || s.ownerSub || "（归属账号已不存在）"}
          · {s.engine || "builtin"}
        </p>
      </button>
      {isEditingDesc ? (
        <div className="card mt-2 space-y-2 p-3">
          <textarea
            value={editDescValue}
            onChange={(e) => onDescValueChange(e.target.value)}
            maxLength={200}
            rows={2}
            placeholder="空间简介（留空则清空）"
            className="w-full resize-none rounded-input border border-neutral-300 p-2 text-caption outline-none focus:border-brand-500"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={savingDesc}
              onClick={() => onSaveDesc(s.id)}
              className="rounded-input bg-brand-600 px-3 py-1 text-caption text-white disabled:opacity-60"
            >
              {savingDesc ? "保存中…" : "保存"}
            </button>
            <button
              type="button"
              onClick={onEditDescCancel}
              className="rounded-input border border-neutral-300 px-3 py-1 text-caption text-neutral-600 hover:bg-neutral-50"
            >
              取消
            </button>
          </div>
        </div>
      ) : confirmingDelete ? (
        <div className="card mt-2 space-y-2 p-3">
          <p className="text-caption text-red-600">
            确定删除空间「{s.name}」？此操作不可撤销，将级联删除所有文档与资产。
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={deleting}
              onClick={() => onDeleteConfirm(s.id)}
              className="rounded-input bg-red-600 px-3 py-1 text-caption text-white disabled:opacity-60"
            >
              {deleting ? "删除中…" : "确认删除"}
            </button>
            <button
              type="button"
              onClick={onDeleteCancel}
              className="rounded-input border border-neutral-300 px-3 py-1 text-caption text-neutral-600 hover:bg-neutral-50"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <div className="absolute right-2 top-2 flex gap-1">
          <button
            type="button"
            title="编辑简介"
            onClick={(e) => {
              e.stopPropagation();
              onEditDescStart(s.id, s.description ?? "");
            }}
            className="rounded p-1 text-caption text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
          >
            编辑
          </button>
          <button
            type="button"
            title="删除空间"
            onClick={(e) => {
              e.stopPropagation();
              onDeleteRequest(s.id);
            }}
            className="rounded p-1 text-caption text-neutral-400 hover:bg-red-50 hover:text-red-600"
          >
            删除
          </button>
        </div>
      )}
    </li>
  );
}
