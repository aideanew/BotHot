/**
 * lib/api/engines —— 引擎可插拔域（AB-P004 P4，v0.5 契约，ADR-0004）
 *
 * 契约：GET /api/v1/engines（引擎位 + Key 可用性）、PATCH /api/v1/spaces/{id}/engine（切换）。
 * 该域无 mock 分支：引擎可插拔为后端真实能力，未配 Key 时后端显式报错（不造数）。
 */

import { request } from "./http";

/** GET /api/v1/engines → data.items（引擎位 + Key 可用性） */
export interface EngineItem {
  engine: string;
  configured: boolean;
  available: boolean;
  allowlisted: boolean;
  keyEnv: string;
  /** 生效来源（T5.4）：登记覆盖 env 时显式回报，未配置为 null。旧后端不返回，故可选。 */
  activeSource?: "env" | "registered" | null;
  /** 是否已实接（六方法均实现）。仅 builtin 为真；骨架位为假。旧后端不返回，故可选。 */
  implemented?: boolean;
  /** 已登记 Key 不可解（密文损坏或主密钥已轮换）——标注而非丢弃，避免误读成「未配置」。 */
  decryptFailed?: boolean;
  description: string;
}

/** PATCH /api/v1/spaces/{id}/engine → data */
export interface PatchEngineResult {
  engine: string;
  engineKbId: string;
  spaceId: string;
}

/**
 * 引擎位 → 用户可见标签（T1.1.4 引用来源标注取此口径）。
 *
 * - builtin（或缺省/空串）→「内置」（与 EngineSwitcher/PublicLibraryPicker 既有口径一致）；
 * - 其余引擎位（主平台/coze/dify/fastgpt…）→ 原样透出 token，不臆造中文名。
 * 纯函数，无副作用，便于单测锁定映射。
 */
export function engineLabel(engine?: string | null): string {
  return !engine || engine === "builtin" ? "内置" : engine;
}

/** GET /api/v1/engines —— 5 引擎位 + Key 可用性（builtin 恒 available）。 */
export async function listEngines(): Promise<{
  items: EngineItem[];
  defaultEngine: string;
}> {
  return request<{ items: EngineItem[]; defaultEngine: string }>("/api/v1/engines");
}

/**
 * PATCH /api/v1/spaces/{id}/engine —— 切换空间引擎（双写 engine/engineKbId）。
 * 未配 Key 切非 builtin → ApiError(10004/403) 提示找管理员；越权空间 → 30004。
 */
export async function patchSpaceEngine(
  spaceId: string,
  engine: string
): Promise<PatchEngineResult> {
  return request<PatchEngineResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/engine`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine }),
    }
  );
}
