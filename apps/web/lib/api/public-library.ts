/**
 * lib/api/public-library —— 公共库域（AB-P004 P1，契约 §六 v0.5 草案）
 *
 * 契约：GET /api/v1/spaces/public（列表）、POST /api/v1/spaces/{id}/links（批量引入）。
 */

import { request } from "./http";
import type { LinkResult, PublicSpace } from "./types";

/**
 * GET /api/v1/spaces/public —— 公共库列表（AB-P004 P1）。
 * 登录保护 10001；返回 PublicSpace[]（已解包 items）。
 * 演示态样例在 `mock-routes.ts`（那里存的是线上 `data` 形状 `{items}`，解包照跑）。
 */
export async function listPublicSpaces(): Promise<PublicSpace[]> {
  return request<{ items: PublicSpace[] }>("/api/v1/spaces/public").then(
    (d) => d.items
  );
}

/**
 * POST /api/v1/spaces/{id}/links —— 批量 copy 公共库 READY 资产进目标用户空间（幂等）。
 * 已 copy 的 doc 跳过；返回 {copied, skipped, total}。
 * 目标空间越权/无效 → ApiError(30004)；公共空间无效 → ApiError(30004)。
 */
export async function linkPublicSpace(
  spaceId: string,
  publicSpaceId: string
): Promise<LinkResult> {
  return request<LinkResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/links`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ public_space_id: publicSpaceId }),
    }
  );
}
