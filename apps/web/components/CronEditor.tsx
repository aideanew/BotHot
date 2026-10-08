"use client";

/**
 * CronEditor —— 推送任务定时规则编辑器（W4 4.2）。
 *
 * 预设下拉（每天 HH:MM / 每 N 小时 / 每 N 分钟 / 自定义 5 段式）+ 人类可读预览。
 * 自定义输入失焦时做轻量结构校验（checkCronShape），最终以服务端 400 为准；
 * 本件只负责「产出 cron_expr 字符串 + 预览 + 轻量提示」，不冒充完整校验器。
 *
 * 受控组件：值与变更经 value/onChange 与父表单同步，内部只管编辑态拆解。
 */

import { useEffect, useMemo, useState } from "react";
import {
  buildCronExpr,
  checkCronShape,
  CRON_PRESET_LABELS,
  describeCron,
  detectCronMode,
  type CronPresetMode,
} from "@/lib/cron";

interface Props {
  /** 当前 cron_expr 写入值（可能为空串） */
  value: string;
  onChange: (expr: string) => void;
}

export default function CronEditor({ value, onChange }: Props) {
  const [mode, setMode] = useState<CronPresetMode>(() => detectCronMode(value));
  const [hhmm, setHhmm] = useState(() => (/^\d{1,2}:\d{2}$/.test(value.trim()) ? value.trim() : "10:00"));
  const [interval, setInterval_] = useState(() => {
    const t = value.trim();
    const hourly = /^\*\/(\d+)$/.exec(t);
    if (hourly) return hourly[1];
    if (/^\d+$/.test(t)) return t;
    return "30";
  });
  const [customText, setCustomText] = useState(() => (detectCronMode(value) === "custom" ? value.trim() : ""));
  const [shapeError, setShapeError] = useState("");

  // 依据编辑态拼出当前表达式，向父级同步
  const expr = useMemo(
    () => buildCronExpr(mode, mode === "custom" ? customText : hhmm, interval),
    [mode, hhmm, interval, customText],
  );

  useEffect(() => {
    onChange(expr);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expr]);

  const preview = describeCron(expr);

  const handleModeChange = (next: CronPresetMode) => {
    setMode(next);
    if (next !== "custom") setShapeError("");
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <select
          value={mode}
          onChange={(e) => handleModeChange(e.target.value as CronPresetMode)}
          className="w-full rounded border px-3 py-2 text-sm"
          aria-label="定时规则预设"
        >
          {(Object.keys(CRON_PRESET_LABELS) as CronPresetMode[]).map((m) => (
            <option key={m} value={m}>
              {CRON_PRESET_LABELS[m]}
            </option>
          ))}
        </select>

        {mode === "daily" && (
          <input
            type="time"
            value={hhmm}
            onChange={(e) => setHhmm(e.target.value)}
            className="w-full rounded border px-3 py-2 text-sm"
            aria-label="每天时间"
          />
        )}
        {(mode === "hourly" || mode === "minutely") && (
          <div className="flex items-center gap-1">
            <span className="text-sm text-gray-600">每</span>
            <input
              type="number"
              min={1}
              value={interval}
              onChange={(e) => setInterval_(e.target.value)}
              className="w-24 rounded border px-3 py-2 text-sm"
              aria-label="间隔数值"
            />
            <span className="text-sm text-gray-600">{mode === "hourly" ? "小时" : "分钟"}</span>
          </div>
        )}
      </div>

      {mode === "custom" && (
        <div>
          <input
            type="text"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            onBlur={() => setShapeError(customText.trim() ? checkCronShape(customText) ?? "" : "")}
            className="w-full rounded border px-3 py-2 text-sm"
            placeholder="分 时 日 月 周，如：0 10 * * 1-5"
            aria-label="自定义 cron 表达式"
          />
          {shapeError && (
            <p className="mt-1 text-xs text-amber-600">{shapeError}（最终以服务端校验为准）</p>
          )}
        </div>
      )}

      {preview && (
        <p className="text-xs text-gray-500">
          预览：<span className="font-medium text-gray-700">{preview}</span>
          <span className="ml-2 text-gray-400">（{expr}）</span>
        </p>
      )}
    </div>
  );
}
