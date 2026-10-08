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

import { ApiError } from "./types";
import { MOCK_ENABLED, mockRequest, request } from "./http";

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

/** mock 样例：builtin 恒可用；其余引擎位未配 Key（置灰 + 提示找管理员），与真实后端「零 Key 部署」形态一致。 */
const MOCK_ENGINES: EngineItem[] = [
  {
    engine: "builtin",
    configured: true,
    available: true,
    allowlisted: true,
    implemented: true,
    keyEnv: "",
    activeSource: "env",
    description: "内置关键词检索引擎（演示数据）",
  },
  {
    engine: "main-platform",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "MAIN_PLATFORM_API_KEY",
    description: "主平台知识引擎",
  },
  {
    engine: "coze",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "COZE_API_KEY",
    description: "Coze 知识引擎",
  },
  {
    engine: "dify",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "DIFY_API_KEY",
    description: "Dify 知识引擎",
  },
  {
    engine: "fastgpt",
    configured: false,
    available: false,
    allowlisted: true,
    implemented: false,
    keyEnv: "FASTGPT_API_KEY",
    description: "FastGPT 知识引擎",
  },
];

/** GET /api/v1/engines —— 5 引擎位 + Key 可用性（builtin 恒 available）。 */
export async function listEngines(): Promise<{
  items: EngineItem[];
  defaultEngine: string;
}> {
  if (MOCK_ENABLED) {
    return mockRequest({ items: MOCK_ENGINES, defaultEngine: "builtin" });
  }
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
  if (MOCK_ENABLED) {
    // 演示态：builtin 与样例中 available 的引擎放行，其余按未配 Key 拒（10004 语义）。
    const target = MOCK_ENGINES.find((e) => e.engine === engine);
    if (!target || !target.available) {
      throw new ApiError(
        10004,
        "引擎未开放 / 未配置 Key / 尚未实接，请联系管理员"
      );
    }
    return mockRequest<PatchEngineResult>({
      engine,
      engineKbId: `mock-kb-${engine}`,
      spaceId,
    });
  }
  return request<PatchEngineResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/engine`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine }),
    }
  );
}
