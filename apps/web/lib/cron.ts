/**
 * lib/cron —— 推送任务 cron_expr 的前端侧纯函数（W4 4.2）
 *
 * 与后端 `app/services/cron_expr.py` 的四类合法格式口径对齐：
 * - "HH:MM" → 每天 HH:MM
 * - 星号斜杠 N（每 N 小时）
 * - 纯数字 N → 每 N 分钟
 * - 标准 5 段 → 原样交给 croniter
 *
 * 本模块只做**人类可读预览**与**失焦轻量结构检查**；最终以服务端校验为准
 * （非法值后端返回 400，message 经 http.ts 信封链路展示）。
 */

const pad2 = (n: number): string => String(n).padStart(2, "0");

/** 解析四类合法格式；返回描述串，无法识别返回 null。 */
export function describeCron(expr: string): string {
  const trimmed = (expr ?? "").trim();
  if (!trimmed) return "";

  // HH:MM（含 ":" 无 "/"，与后端 _translate_shorthand 同判定）
  if (trimmed.includes(":") && !trimmed.includes("/")) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(trimmed);
    if (m) {
      const hh = Number(m[1]);
      const mm = Number(m[2]);
      if (hh <= 23 && mm <= 59) return `每天 ${pad2(hh)}:${pad2(mm)}`;
    }
    return trimmed;
  }

  // 星号斜杠 N（每 N 小时）
  const hourly = /^\*\/(\d+)$/.exec(trimmed);
  if (hourly) {
    const n = Number(hourly[1]);
    return n > 0 ? `每 ${n} 小时` : trimmed;
  }

  // 纯数字 N（每 N 分钟）
  if (/^\d+$/.test(trimmed)) {
    const n = Number(trimmed);
    return n > 0 ? `每 ${n} 分钟` : trimmed;
  }

  // 标准 5 段：逐段常见模式给简式描述，其余原样回显
  const fields = trimmed.split(/\s+/);
  if (fields.length === 5) {
    const [mm, hh, dom, mon, dow] = fields;
    const everyMinutes = /^\*\/(\d+)$/.exec(mm);
    const exactMinute = /^\d+$/.test(mm);
    if (dom === "*" && mon === "*" && dow === "*") {
      if (hh === "*" && everyMinutes) return `每 ${everyMinutes[1]} 分钟`;
      if (exactMinute && hh.startsWith("*/")) return `每 ${hh.slice(2)} 小时的第 ${mm} 分钟`;
      if (exactMinute && /^\d+$/.test(hh)) return `每天 ${pad2(Number(hh))}:${pad2(Number(mm))}`;
    }
    return `Cron：${trimmed}`;
  }

  return trimmed;
}

/**
 * 失焦轻量结构检查：明确不合法的形态返回中文错误串，疑似合法返回 null。
 * 只做结构级判断（段数/正则/数值范围），段内高级语法（列表、区间等）
 * 交由服务端 croniter 裁决，前端不冒充完整校验器。
 */
export function checkCronShape(expr: string): string | null {
  const trimmed = (expr ?? "").trim();
  if (!trimmed) return "定时规则不能为空";

  if (trimmed.includes(":") && !trimmed.includes("/")) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(trimmed);
    if (!m) return "时间格式应为 HH:MM，如 10:00";
    const hh = Number(m[1]);
    const mm = Number(m[2]);
    if (hh > 23) return "小时应在 0~23 之间";
    if (mm > 59) return "分钟应在 0~59 之间";
    return null;
  }

  if (trimmed.startsWith("*/")) {
    const m = /^\*\/(\d+)$/.exec(trimmed);
    if (!m || Number(m[1]) <= 0) return "每 N 小时的写法不正确：应为 */N，N 为正整数";
    return null;
  }

  if (/^\d+$/.test(trimmed)) {
    return Number(trimmed) > 0 ? null : "分钟数应为正整数";
  }

  const fields = trimmed.split(/\s+/);
  if (fields.length !== 5) {
    return "格式不识别：支持 HH:MM、每 N 小时、分钟数字或标准 5 段式";
  }
  return null;
}

/** 预设模式（4.2 下拉）：daily=HH:MM，hourly=星号斜杠 N，minutely=纯数字，custom=5 段式。 */
export type CronPresetMode = "daily" | "hourly" | "minutely" | "custom";

export const CRON_PRESET_LABELS: Record<CronPresetMode, string> = {
  daily: "每天 HH:MM",
  hourly: "每 N 小时",
  minutely: "每 N 分钟",
  custom: "自定义 5 段式",
};

/** 由预设模式 + 数值拼出 cron_expr 写入值（custom 模式直接用原文）。 */
export function buildCronExpr(mode: CronPresetMode, time: string, interval: string): string {
  if (mode === "daily") return time.trim();
  if (mode === "hourly") return interval.trim() ? `*/${interval.trim()}` : "";
  if (mode === "minutely") return interval.trim();
  return time.trim();
}

/** 从既有 cron_expr 反推预设模式（编辑器打开时回填用）。 */
export function detectCronMode(expr: string): CronPresetMode {
  const trimmed = (expr ?? "").trim();
  if (/^\d{1,2}:\d{2}$/.test(trimmed)) return "daily";
  if (/^\*\/\d+$/.test(trimmed)) return "hourly";
  if (/^\d+$/.test(trimmed)) return "minutely";
  return "custom";
}
