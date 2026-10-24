/**
 * lib/api/engines —— 引擎可插拔域（AB-P004 P4，v0.5 契约，ADR-0004）
 *
 * 契约：GET /api/v1/engines（引擎位 + Key 可用性）、PATCH /api/v1/spaces/{id}/engine（切换）。
 * ⚠️ mock 裁定变更（2026-10-08 CI 实证推翻原「无 mock 分支」决定）：原裁定"引擎为
 * 后端真实能力，不造数"，但 EngineSwitcher 在空间详情页**无条件挂载**并于 useEffect
 * 拉取列表——mock 产物（演示模式 / e2e）里该请求绕过 MOCK 网关真打 /api/v1/engines，
 * 被 rewrite 代理到不存在的后端（ECONNREFUSED :3300 → HTTP 500 → console error），
 * trunk.spec ⑦ 的 console 门禁即红（CI run 37749239965）。mock 态改为返回静态样例
 * （builtin 可用、其余未配 Key），与 notifications.ts 的 MOCK 门同一动机。
 */

import type { EngineCapability, EngineList, SpaceEngineBinding } from "@bothot/contracts";

import { request } from "./http";

/**
 * 引擎位不可用的**首要**原因（STEP-13；`packages/contracts/schemas/engine.schema.json` 的 `EngineReason`）。
 * 排序按"谁能解决"：开放名单 → 登记 Key → 开发排期。`available === (reason === "ok")` 是契约不变量，
 * 由后端 `_engine_reason()` 单点产出，列表与切换拒绝读同一个函数。
 *
 * 联合以外不取值，也**不再由前端从三个布尔自己推顺序**：`app/engines/page.tsx` 原先先判
 * `configured` 再判 `allowlisted`，于是一个"既没开名单也没配 Key"的引擎会提示"未配置 Key"，
 * 把管理员指到一个解决不了的处置上。顺序只有一份，就在后端。
 */
export type EngineReason = "ok" | "not_allowlisted" | "key_missing" | "not_implemented";

/** reason → 完整可读原因（S15.V17.1 口径：说清"谁能解决"，不复述内部字段名） */
export const ENGINE_REASON_TEXT: Record<EngineReason, string> = {
  ok: "",
  not_allowlisted: "未开放，请联系管理员",
  key_missing: "未登记 API Key",
  not_implemented: "暂未接入",
};

/** reason → 短标签（卡片/列表里放不下一整句时用这个） */
export const ENGINE_REASON_LABEL: Record<EngineReason, string> = {
  ok: "可用",
  not_allowlisted: "未开放",
  key_missing: "未登记 Key",
  not_implemented: "暂未接入",
};

/**
 * GET /api/v1/engines → data.items（引擎位 + Key 可用性）。
 *
 * S48（P-119/D-V21-02）：`activeSource`/`decryptFailed` 在契约里是 **required**（后端
 * `_engine_status` 恒返回），本接口旧写法把两键放宽成可选 ⇒ 演示态样例缺键也无机器察觉。
 * 现在直接别名契约生成类型（`packages/contracts/src/engine/dto.ts`，STEP-46 生成），
 * 生成侧一变这里跟着变，写错一个字段 tsc 红。
 */
export type EngineItem = EngineCapability;

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

/** GET /api/v1/engines —— 5 引擎位 + Key 可用性（演示态样例见 `mock-routes.ts` 的 engines 段）。 */
export async function listEngines(): Promise<EngineList> {
  return request<EngineList>("/api/v1/engines");
}

/**
 * PATCH /api/v1/spaces/{id}/engine —— 切换空间引擎（双写 engine/engineKbId）。
 * 未配 Key 切非 builtin → ApiError(10004/403) 提示找管理员；越权空间 → 30004。
 */
export async function patchSpaceEngine(
  spaceId: string,
  engine: string
): Promise<SpaceEngineBinding> {
  return request<SpaceEngineBinding>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/engine`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine }),
    }
  );
}
