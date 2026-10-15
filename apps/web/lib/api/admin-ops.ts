/**
 * lib/api/admin-ops —— 管理端「运维能力面」（STEP-15 S15.2.3 / STEP-14b 的消费面）
 *
 * 覆盖 D-V3-06 点名的 5 组「有 API 无 UI」端点：
 *   引擎 Key 登记      GET/POST/DELETE /api/v1/admin/engines/keys[/{engine}]   （T5.4）
 *   推送通道就绪度      GET /api/v1/admin/push/channels                        （T6.2）
 *   发现渠道就绪度      GET /api/v1/admin/discovery/channels                   （R7.6）
 *   常驻进程存活        GET /api/v1/admin/ops/liveness                         （R7.7）
 *   推送终态回执        POST /api/v1/admin/push                                （T6.2 + R7.5.4）
 * 另补 Job 详情 GET /api/v1/admin/jobs/{id}（列表已有，操作性排查缺读侧）。
 *
 * 三条口径写在这里而不是散落到组件里：
 * 1. **三布尔不合并**：`implemented`（代码实接）/`enabled`（在白名单）/`available`（凭据就位）
 *    是三种不同故障，合成一个布尔就把「功能没做」和「功能没配」混成一谈（后端 registry 同纪律）。
 * 2. **null 不是 0**：`lastHeartbeatAt=null` 是「进程从未启动」，有值但 stale 是「启动后卡死」，
 *    处置动作不同，所以类型上是 `string | null` 而不是可选字段——渲染层必须显式分支。
 * 3. **本域无 mock 分支**：admin 能力只能来自后端 admin 端点（`require_roles("operator")`），
 *    演示模式伪造跨用户运维数据等于伪造授权面（沿用 `admin.ts` 纪律）。
 *    未登录 → 10001；非 operator/admin → 10004，由调用方按门禁分支处理。
 */

import { request } from "./http";

// ---------- 引擎 Key 登记 ----------

/** 一个可登记引擎位的回报（后端 GET /admin/engines/keys 的 items 元素） */
export interface EngineKeyRow {
  engine: string;
  /** 登记表里是否有这一行（≠ 可用：env 也能供 Key） */
  registered: boolean;
  /** 登记表 + env 合并后是否可用 */
  configured: boolean;
  /** 当前生效来源：registered 覆盖 env，故两者可比、覆盖不是静默的 */
  activeSource: string;
  /** 仅凭 env 是否已配置 */
  envConfigured: boolean;
  /** 登记行存在但解密失败（主密钥换过）——必须显式回报，否则看起来像"没配" */
  decryptFailed: boolean;
  keyEnv: string;
  keyId: string;
  registeredBy: string;
  updatedAt: string;
}

export interface EngineKeyList {
  /** false = ENGINE_KEY_MASTER_KEY 未配置：登记接口会 50002 拒绝，本列表仍可用 */
  masterKeyConfigured: boolean;
  items: EngineKeyRow[];
}

export function listEngineKeys(): Promise<EngineKeyList> {
  return request<EngineKeyList>("/api/v1/admin/engines/keys");
}

/** 登记/覆盖引擎 Key。明文只在请求体里过一手，响应不回显（只给 keyId 作轮换句柄）。 */
export function registerEngineKey(engine: string, key: string): Promise<{ ok: boolean; keyId?: string }> {
  return request(`/api/v1/admin/engines/keys/${encodeURIComponent(engine)}`, {
    method: "POST",
    body: JSON.stringify({ key }),
  });
}

/** 撤销登记（回落 env；env 亦空则该引擎位不可用）。无登记行 → 30004，不谎报"已撤销"。 */
export function revokeEngineKey(engine: string): Promise<{ ok: boolean }> {
  return request(`/api/v1/admin/engines/keys/${encodeURIComponent(engine)}`, { method: "DELETE" });
}

// ---------- 渠道就绪度 ----------

export interface PushChannelRow {
  channel: string;
  implemented: boolean;
  description: string;
}

export function listPushChannels(): Promise<PushChannelRow[]> {
  return request<{ channels: PushChannelRow[] }>("/api/v1/admin/push/channels").then(
    (d) => d.channels ?? []
  );
}

export interface DiscoveryChannelRow {
  name: string;
  description: string;
  implemented: boolean;
  enabled: boolean;
  available: boolean;
  /** 当前不可用的具体原因（可用时为空串） */
  reason: string;
  contractVerifiedAt: string | null;
  verifiedScope: string;
}

export interface DiscoveryChannelView {
  channels: DiscoveryChannelRow[];
  /** null = 本轮调度不做发现、仅按既有清单 diff（与调度器的跳过日志同源） */
  defaultChannel: string | null;
  selectionReason: string;
  configuredChannels: string[];
}

export function listDiscoveryChannels(): Promise<DiscoveryChannelView> {
  return request<DiscoveryChannelView>("/api/v1/admin/discovery/channels");
}

// ---------- 常驻进程存活 ----------

export interface ProcessLivenessRow {
  processKey: string;
  purpose: string;
  /** null = 进程从未启动（≠ 卡死）；两者处置不同，故显式可空 */
  lastHeartbeatAt: string | null;
  ageSeconds: number | null;
  stale: boolean;
  lastDetail: string;
}

export interface OpsLiveness {
  /** 按 EXPECTED_PROCESSES 全景回报，缺失也占位——只回报"已有行"会把缺进程藏起来 */
  processes: ProcessLivenessRow[];
  maxAgeSeconds: number;
  allHealthy: boolean;
}

export function getOpsLiveness(maxAgeSeconds?: number): Promise<OpsLiveness> {
  const q = maxAgeSeconds ? `?max_age_seconds=${encodeURIComponent(String(maxAgeSeconds))}` : "";
  return request<OpsLiveness>(`/api/v1/admin/ops/liveness${q}`);
}

// ---------- 推送触发与终态回执 ----------

export interface AdminPushPayload {
  channel: string;
  externalUserId: string;
  spaceId?: string;
  docId?: string;
  message?: string;
}

/**
 * POST /api/v1/admin/push —— 通道未就绪时后端回 **200 + delivered=false + reason**（R7.5.4），
 * 不是 503。所以调用方必须读 `delivered` 而不是"没抛异常就算成功"。
 */
export function adminPush(payload: AdminPushPayload): Promise<AdminPushReceipt> {
  return request<AdminPushReceipt>("/api/v1/admin/push", {
    method: "POST",
    body: JSON.stringify({
      channel: payload.channel,
      external_user_id: payload.externalUserId,
      space_id: payload.spaceId ?? "",
      doc_id: payload.docId ?? "",
      message: payload.message ?? "",
    }),
  });
}

export interface AdminPushReceipt {
  ok: boolean;
  channel: string;
  delivered: boolean;
  /** 未投递时的可读原因（delivered=true 时后端不带该字段） */
  reason?: string;
}
