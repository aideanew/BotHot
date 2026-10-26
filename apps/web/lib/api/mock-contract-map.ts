/**
 * mock-contract-map —— mock 路由 ↔ 契约类型名的**唯一对照表**（STEP-52，P-82 收口）。
 *
 * 为什么需要一张独立的表：`mock-routes.ts` 的路由 pattern 是 RegExp，编译期类型系统
 * 看不见"哪条路由该长成哪个契约形状"——没有这张表，"漏登记"会表现为"这个页面拿到
 * 一份结构正确但键缺失的样例"，只在运行时离奇地炸。表把对照变成数据，
 * `s52-mock-contract-coverage.spec.ts` 就能用它逐条比对 `MOCK_ROUTES` 的注册面。
 *
 * **来源（只读镜像）**：`apps/api/app/contracts/shapes.py` 的 `MOCK_ROUTE_CONTRACTS`
 * ——后端是权威源（22 条，STEP-47 落地）；本表是它在前端的数据镜像，类型名从
 * `@bothot/contracts` 导入做编译期核对（名字写错 tsc 红）。
 *
 * pattern 源串采用后端权威串的写法（`/api/v1/spaces/{id}/docs` 形）；覆盖测试
 * 负责把它与 `MOCK_ROUTES` 里实际注册的 RegExp 归一后对上（`{seg}` ↔ `([^/]+)`）。
 */

import type {
  DocCategoryList,
  DocCategoryPatch,
  DocDeleteResult,
  DocIngestState,
  DocsBatchDeleteResult,
  DocsRecategorizeResult,
  EngineList,
  ExtractedArticleView,
  IngestAccepted,
  LinkResult,
  LogoutResult,
  MeView,
  NotificationHistoryPage,
  NotificationReadResult,
  PublicSpacePage,
  ResolvedArticleView,
  SpaceDeleteResult,
  SpaceDetail,
  SpaceDocPage,
  SpaceEngineBinding,
  SpacePage,
} from "@bothot/contracts";

/** 路由 pattern 源串 → 契约类型名（与 shapes.py 的 MOCK_ROUTE_CONTRACTS 一一对应） */
export const MOCK_CONTRACT_MAP = {
  "GET /api/v1/engines": "EngineList",
  "PATCH /api/v1/spaces/{id}/engine": "SpaceEngineBinding",
  "GET /api/v1/auth/me": "MeView",
  "POST /api/v1/auth/logout": "LogoutResult",
  "GET /api/v1/spaces/public": "PublicSpacePage",
  "POST /api/v1/spaces/{id}/links": "LinkResult",
  "POST /api/v1/resolve": "ResolvedArticleView",
  "POST /api/v1/extract": "ExtractedArticleView",
  "POST /api/v1/spaces/{id}/docs": "IngestAccepted",
  "GET /api/v1/spaces/{id}/docs/{docId}/status": "DocIngestState",
  "GET /api/v1/system/notifications/history": "NotificationHistoryPage",
  "PUT /api/v1/system/notifications/read": "NotificationReadResult",
  "POST /api/v1/spaces": "SpaceDetail",
  "GET /api/v1/spaces": "SpacePage",
  "GET /api/v1/spaces/{id}/docs": "SpaceDocPage",
  "GET /api/v1/spaces/{id}/docs:categories": "DocCategoryList",
  "DELETE /api/v1/spaces/{id}/docs/{docId}": "DocDeleteResult",
  "PATCH /api/v1/spaces/{id}/docs/{docId}": "DocCategoryPatch",
  "POST /api/v1/spaces/{id}/docs:delete": "DocsBatchDeleteResult",
  "POST /api/v1/spaces/{id}/docs:recategorize": "DocsRecategorizeResult",
  "GET /api/v1/spaces/{id}": "SpaceDetail",
  "DELETE /api/v1/spaces/{id}": "SpaceDeleteResult",
} as const;

/** 表里声明的每个类型名都真实存在于契约包（编译期核对，名字漂移 tsc 红） */
export type _AssertTypesExist = [
  EngineList,
  SpaceEngineBinding,
  MeView,
  LogoutResult,
  PublicSpacePage,
  LinkResult,
  ResolvedArticleView,
  ExtractedArticleView,
  IngestAccepted,
  DocIngestState,
  NotificationHistoryPage,
  NotificationReadResult,
  SpaceDetail,
  SpacePage,
  SpaceDocPage,
  DocCategoryList,
  DocDeleteResult,
  DocCategoryPatch,
  DocsBatchDeleteResult,
  DocsRecategorizeResult,
  SpaceDeleteResult,
];

/**
 * 两侧归一到同一形态：RegExp 源串 `^\/api\/v1\/spaces\/([^/]+)$` ↔ 权威串 `/api/v1/spaces/{id}`。
 *
 * 三步的**顺序是判据的一部分**：先按字面量把匿名段换成 `{seg}`，再剥首尾锚。
 * 反过来先全局删 `^` 会连字符类 `[^/]` 里的插入符一起删掉（变成 `[/]`），
 * 于是匿名段替换永不命中、两侧永不相等——覆盖测试会变成"永远列全 22 条缺失"的假红。
 */
export function normalizeRouteKey(method: string, pattern: string): string {
  const path = pattern
    .replace(/\\/g, "") // RegExp 源串里的 \/ 只是转义，比对不需要反斜杠
    .replaceAll("([^/]+)", "{seg}") // 位置捕获组形
    .replaceAll("[^/]+", "{seg}") // 裸字符类形（同一张表里两种都存在）
    .replace(/^\^/, "")
    .replace(/\$$/, "");
  return `${method} ${path}`;
}
