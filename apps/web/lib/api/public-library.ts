/**
 * lib/api/public-library —— 公共库域（AB-P004 P1，契约 §六 v0.5 草案）
 *
 * 契约：GET /api/v1/spaces/public（列表）、POST /api/v1/spaces/{id}/links（批量引入）。
 */

import { MOCK_ENABLED, mockRequest, request } from "./http";
import type { LinkResult, PublicSpace } from "./types";

/** mock 公共库样例（MOCK_ENABLED 时使用） */
const MOCK_PUBLIC_SPACES: PublicSpace[] = [
  {
    id: "mock-public-ai-001",
    name: "AI前沿库",
    description: "AI前沿库（采自公众号，系统空间）",
    docCount: 50,
    engine: "builtin",
    isPublic: true,
    updatedAt: "2026-09-14T00:00:00",
  },
];

const MOCK_LINK_RESULT: LinkResult = { copied: 50, skipped: 0, total: 50 };

/**
 * GET /api/v1/spaces/public —— 公共库列表（AB-P004 P1）。
 * 登录保护 10001；返回 PublicSpace[]（已解包 items）。
 */
export async function listPublicSpaces(): Promise<PublicSpace[]> {
  if (MOCK_ENABLED) {
    return mockRequest(MOCK_PUBLIC_SPACES);
  }
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
  if (MOCK_ENABLED) {
    return mockRequest(MOCK_LINK_RESULT);
  }
  return request<LinkResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/links`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ public_space_id: publicSpaceId }),
    }
  );
}
