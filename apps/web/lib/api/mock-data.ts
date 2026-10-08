/**
 * lib/api/mock-data —— 跨域共享的 mock 样例（T1.2.5 分域拆分）
 *
 * 只放**被多个域模块复用**的样例（知识空间三件套：spaces 域与 ask 域都要用空间名）。
 * 域内独占的样例（公共库/解析入库等）留在各自域模块，避免本文件膨胀为杂物间。
 */

import type { Space, SpaceDetail, SpaceDoc } from "./types";

export const MOCK_SPACES: Space[] = [
  {
    id: "sp-001",
    name: "产品资料库",
    description: "产品手册、FAQ 与功能说明文档",
    docCount: 12,
    updatedAt: "2026-09-05T10:00:00+08:00",
  },
  {
    id: "sp-002",
    name: "竞品动态",
    description: "竞品公众号文章与行业动态追踪",
    docCount: 5,
    updatedAt: "2026-09-06T14:30:00+08:00",
  },
];

export const MOCK_SPACE_DETAILS: Record<string, SpaceDetail> = {
  "sp-001": {
    ...MOCK_SPACES[0],
    createdAt: "2026-09-01T10:00:00+08:00",
    stats: { docs: 12, chunks: null },
  },
  "sp-002": {
    ...MOCK_SPACES[1],
    createdAt: "2026-09-03T14:30:00+08:00",
    stats: { docs: 5, chunks: null },
  },
};

export const MOCK_DOCS: Record<string, SpaceDoc[]> = {
  "sp-001": [
    { id: "doc-001", title: "用户手册 v2.3", source: "公众号：产品团队", status: "ready", updatedAt: "2026-09-05T10:00:00+08:00" },
    { id: "doc-002", title: "常见问题解答（第 4 期）", source: "公众号：产品团队", status: "ready", updatedAt: "2026-09-04T16:20:00+08:00" },
    { id: "doc-003", title: "新功能预告：批量入库", source: "公众号：产品团队", status: "pending", updatedAt: "2026-09-06T09:15:00+08:00" },
    { id: "doc-004", title: "旧版迁移指南（已归档）", source: "公众号：产品团队", status: "failed", updatedAt: "2026-09-02T11:40:00+08:00" },
  ],
  "sp-002": [
    { id: "doc-101", title: "行业周报：AI 应用趋势", source: "公众号：行业观察", status: "ready", updatedAt: "2026-09-06T14:30:00+08:00" },
    { id: "doc-102", title: "竞品 X 发布新版本", source: "公众号：行业观察", status: "ready", updatedAt: "2026-09-05T18:00:00+08:00" },
  ],
};
