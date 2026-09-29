"use client";

import { useEffect, useState } from "react";

/**
 * ConfirmModal —— T1.2.2 统一确认模态（大纲 v1.1 组件化批次）。
 * 合并 EngineSwitcher/chat 等各写一份的手写模态：遮罩 + 标题 + 描述 + 取消/确认。
 *
 * R0.2.4 增补：可选 `options` 下拉。删除/退订只需确认，改分类/改间隔需要先选一个值
 * 再确认——与其另写一个输入型模态（又制造一份手写模态），在本件上补一个可选下拉，
 * `onConfirm` 回传所选值（未提供 options 时回 undefined，既有调用方零改动）。
 */
export interface ConfirmOption {
  value: string;
  label: string;
}

interface Props {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  busy?: boolean;
  /** 提供则为「先选值再确认」；省略则为纯确认 */
  options?: ConfirmOption[];
  initialValue?: string;
  onConfirm: (value?: string) => void;
  onCancel: () => void;
}

export default function ConfirmModal({
  open,
  title,
  description = "",
  confirmText = "确认",
  cancelText = "取消",
  busy = false,
  options,
  initialValue = "",
  onConfirm,
  onCancel,
}: Props) {
  const [value, setValue] = useState(initialValue);

  // 每次打开按 initialValue 重置（关闭后组件卸载渲染，但 state 保留在实例里）
  useEffect(() => {
    if (open) setValue(initialValue);
  }, [open, initialValue]);

  if (!open) return null;
  const hasOptions = options && options.length > 0;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog">
      <div className="card w-full max-w-md p-6">
        <h3 className="text-title-sm font-semibold text-neutral-900">{title}</h3>
        {description && <p className="mt-2 text-base text-neutral-600">{description}</p>}
        {hasOptions && (
          <label className="mt-4 block">
            <span className="mb-1 block text-caption text-neutral-500">选择</span>
            <select
              value={value}
              onChange={(e) => setValue(e.target.value)}
              disabled={busy}
              className="w-full rounded-input border border-neutral-300 px-3 py-2 text-base outline-none focus:border-brand-500"
            >
              {options!.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-neutral-300 px-4 py-1.5 text-base text-neutral-700 hover:bg-neutral-50 disabled:opacity-50"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={() => onConfirm(hasOptions ? value : undefined)}
            disabled={busy}
            className="rounded bg-brand-600 px-4 py-1.5 text-base font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {busy ? "处理中…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
