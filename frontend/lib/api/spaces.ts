/**
 * lib/api/spaces —— 知识空间域（C-T3，B-T4 契约 v0.2）
 *
 * 契约：POST/GET /api/v1/spaces、GET /api/v1/spaces/{id}、GET /api/v1/spaces/{id}/docs。
 * 列表类返回统一解包信封 data.items。
 */

import { ERROR_MESSAGES, MOCK_ENABLED, mockRequest, request } from "./http";
import { MOCK_DOCS, MOCK_SPACE_DETAILS, MOCK_SPACES } from "./mock-data";
import {
  ApiError,
  BATCH_DOCS_MAX_IDS,
  CATEGORIES,
  UNCATEGORIZED,
  type BatchDocFailure,
  type DeleteDocResult,
  type DeleteDocsBatchResult,
  type ListSpaceDocsOptions,
  type PatchDocResult,
  type RecategorizeDocsBatchResult,
  type Space,
  type SpaceDetail,
  type SpaceDocsPage,
} from "./types";

/** POST /api/v1/spaces → 201 data（复用详情形状；重名 → 30006/409） */
export interface CreateSpacePayload {
  name: string;
  description?: string;
}

/**
 * POST /api/v1/spaces —— 创建知识空间（T-022 L-09 onboarding 第 1 步）。
 * 契约：后端返回 201 + SpaceDetail；重名 30006/409 由信封 code 上抛。
 * MOCK 态返回本地样例空间，保证引导页无后端时仍可走完 3 步。
 */
export async function createSpace(payload: CreateSpacePayload): Promise<SpaceDetail> {
  if (MOCK_ENABLED) {
    const now = new Date().toISOString();
    return {
      id: `sp-mock-${Date.now()}`,
      name: payload.name,
      description: payload.description ?? "",
      docCount: 0,
      updatedAt: now,
      createdAt: now,
      stats: { docs: 0, chunks: null },
    };
  }
  return request<SpaceDetail>("/api/v1/spaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** GET /api/v1/spaces —— 知识空间列表（信封 data.items 解包） */
export async function listSpaces(): Promise<Space[]> {
  if (MOCK_ENABLED) {
    return mockRequest(MOCK_SPACES);
  }
  return request<{ items: Space[] }>("/api/v1/spaces").then((d) => d.items);
}

/**
 * GET /api/v1/spaces/{id} —— 空间详情。
 * 不存在/无权（30101/10102）由调用方渲染 404 语义空态页，不白屏。
 */
export async function getSpace(id: string): Promise<SpaceDetail> {
  if (MOCK_ENABLED) {
    const detail = MOCK_SPACE_DETAILS[id];
    if (!detail) {
      throw new ApiError(30101, ERROR_MESSAGES[30101], `mock-${Date.now()}`);
    }
    return mockRequest(detail);
  }
  return request<SpaceDetail>(`/api/v1/spaces/${encodeURIComponent(id)}`);
}

/**
 * GET /api/v1/spaces/{id}/docs —— 空间内文章列表（T1.5.7 服务端分页 + R0.1.1 分类过滤）。
 *
 * 分页是服务端语义：`total` 与 `items` 走同一过滤谓词，故过滤后的 `total` 不会虚高。
 * `category` 省略或空串 = 全部（不发送该参数）；`UNCATEGORIZED` = 未分类。
 */
export async function listSpaceDocs(
  id: string,
  opts: ListSpaceDocsOptions = {}
): Promise<SpaceDocsPage> {
  if (MOCK_ENABLED) {
    const { items, total, limit, offset } = sliceMockDocs(id, opts);
    return mockRequest({ items, total, limit, offset });
  }
  const q = new URLSearchParams();
  q.set("limit", String(opts.limit ?? 100));
  q.set("offset", String(opts.offset ?? 0));
  if (opts.category) q.set("category", opts.category);
  return request<SpaceDocsPage>(
    `/api/v1/spaces/${encodeURIComponent(id)}/docs?${q.toString()}`
  );
}

/**
 * GET /api/v1/spaces/{id}/docs:categories —— 本空间**实际存在**的分类集合（R0.1.2）。
 *
 * 服务端枚举，替代前端按当前页数据推导（分页后单页推导会漏掉不在本页的分类）。
 * 返回值已按规则版声明序排好、未分类以 `UNCATEGORIZED` 置末，可直接作
 * `listSpaceDocs({ category })` 的入参回传；空空间返回空数组。
 */
export async function listSpaceDocCategories(id: string): Promise<string[]> {
  if (MOCK_ENABLED) {
    return mockRequest(orderMockCategories(id));
  }
  return request<{ items: string[] }>(
    `/api/v1/spaces/${encodeURIComponent(id)}/docs:categories`
  ).then((d) => d.items);
}

/** 入库状态查询返回体；status 为**原始态**（FETCHED|INDEXED|READY），
 *  与列表接口的 pending/ready 归一化不同；FAILED 以 30003 抛出而非返回。 */
export interface DocIngestStatus {
  docId: string;
  status: string;
  langbotFileId: string;
}

/**
 * GET /api/v1/spaces/{id}/docs/{docId}/status —— 以引擎文件状态为准回写本地状态。
 * 入库只写到 INDEXED，推进靠本篇调用驱动回写（后端刻意不做请求内长轮询）。
 */
export async function getDocIngestStatus(
  spaceId: string,
  docId: string
): Promise<DocIngestStatus> {
  if (MOCK_ENABLED) {
    return mockRequest({ docId, status: "READY", langbotFileId: "" });
  }
  return request<DocIngestStatus>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs/${encodeURIComponent(docId)}/status`
  );
}

/** mock 分支：按 category 过滤后切片（口径与后端 `_docs_stmt` 一致）。 */
function sliceMockDocs(id: string, opts: ListSpaceDocsOptions) {
  const all = MOCK_DOCS[id] ?? [];
  const filtered = opts.category
    ? opts.category === UNCATEGORIZED
      ? all.filter((d) => !d.category)
      : all.filter((d) => (d.category ?? "") === opts.category)
    : all;
  const limit = opts.limit ?? 100;
  const offset = opts.offset ?? 0;
  return { items: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset };
}

/** mock 分支：复刻后端 `order_categories`（声明序、未登记取值置后、未分类哨兵置末）。 */
function orderMockCategories(id: string): string[] {
  const all = MOCK_DOCS[id] ?? [];
  const present = new Set(all.map((d) => d.category ?? "").filter((c) => c !== ""));
  const ordered = CATEGORIES.filter((c) => present.has(c));
  ordered.push(...all.map((d) => d.category ?? "").filter((c) => c && !CATEGORIES.includes(c)));
  if (all.some((d) => !d.category)) ordered.push(UNCATEGORIZED);
  return ordered;
}

/**
 * R0.2.1 —— DELETE /api/v1/spaces/{id}/docs/{docId}：删除单篇（引擎先删、失败整体回滚）。
 * 越权/无效空间或 doc → 30004；引擎删除失败 → 错误信封上抛（PG 无残留）。
 * MOCK 态就地改写样例库，使演示模式下删除/改分类可闭环。
 */
export async function deleteSpaceDoc(spaceId: string, docId: string): Promise<DeleteDocResult> {
  if (MOCK_ENABLED) {
    const list = MOCK_DOCS[spaceId];
    if (list) {
      const idx = list.findIndex((d) => d.id === docId);
      if (idx >= 0) list.splice(idx, 1);
    }
    return mockRequest({ ok: true, docId, docs: 1, assets: 0 });
  }
  return request<DeleteDocResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs/${encodeURIComponent(docId)}`,
    { method: "DELETE" }
  );
}

/**
 * R0.2.2 —— PATCH /api/v1/spaces/{id}/docs/{docId}：人工纠偏分类（不改正文）。
 * `category` 取规则版六类或空串（= 清空人工标签，响应回默认「其他」）；越界 → 10005/422。
 */
export async function patchSpaceDocCategory(
  spaceId: string,
  docId: string,
  category: string
): Promise<PatchDocResult> {
  if (MOCK_ENABLED) {
    const doc = (MOCK_DOCS[spaceId] ?? []).find((d) => d.id === docId);
    if (doc) doc.category = category;
    return mockRequest({ docId, category: category || "其他" });
  }
  return request<PatchDocResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs/${encodeURIComponent(docId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category }),
    }
  );
}

/**
 * R0.2.6 —— POST /api/v1/spaces/{id}/docs:delete：批量删除（单次上限 50，篇级部分成功）。
 *
 * `failed` 为空即全成功；引擎侧失败篇的 PG 行完整保留（可原样重试）。全批失败、
 * 越权/无效空间、任一篇 doc 缺失或不属于本空间、空批或超单次上限 → 错误信封上抛，
 * 不返回 200 的空结果（避免「200 但一篇都没删」被误读为成功）。
 */
export async function deleteSpaceDocsBatch(
  spaceId: string,
  ids: string[]
): Promise<DeleteDocsBatchResult> {
  if (MOCK_ENABLED) {
    const list = MOCK_DOCS[spaceId];
    const failed: BatchDocFailure[] = [];
    if (list) {
      for (const id of ids) {
        const idx = list.findIndex((d) => d.id === id);
        if (idx < 0) failed.push({ docId: id, code: 30004, error: "RESOURCE_NOT_FOUND" });
        else list.splice(idx, 1);
      }
    }
    return mockRequest({
      ok: true,
      requested: ids.length,
      docs: Math.max(0, ids.length - failed.length),
      assets: 0,
      failed,
    });
  }
  return request<DeleteDocsBatchResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs:delete`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    }
  );
}

/**
 * R0.2.6 —— POST /api/v1/spaces/{id}/docs:recategorize：批量人工纠偏分类（单次上限 50）。
 *
 * **整批原子**：全批成功或全批不生效，无「改了一半」中间态。`category` 取规则版六类
 * 或空串（= 清空人工标签，响应回默认「其他」）；越界 → 10005/422。
 * 语义与单篇 PATCH 同：category 是资产级属性，改写对本资产在其他空间的呈现一并生效。
 */
export async function recategorizeSpaceDocsBatch(
  spaceId: string,
  ids: string[],
  category: string
): Promise<RecategorizeDocsBatchResult> {
  if (MOCK_ENABLED) {
    const list = MOCK_DOCS[spaceId];
    const normalized = category || "其他";
    (list ?? []).forEach((d) => {
      if (ids.includes(d.id)) d.category = normalized;
    });
    return mockRequest({ ok: true, requested: ids.length, docs: ids.length, category: normalized });
  }
  return request<RecategorizeDocsBatchResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs:recategorize`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, category }),
    }
  );
}

/**
 * 按单次上限切片 ids（`batch_docs_max_ids` = 50；单次超出即 10005/422）。
 * 纯函数、保序、不产生空尾批；size 退化（0/负数）时按 1 切片，防死循环。
 */
export function chunkDocIds(ids: string[], size = BATCH_DOCS_MAX_IDS): string[][] {
  const step = Math.max(1, size);
  const out: string[][] = [];
  for (let i = 0; i < ids.length; i += step) out.push(ids.slice(i, i + step));
  return out;
}

/**
 * DELETE /api/v1/spaces/{id} —— 删除知识空间（R5.4.3）。
 * 后端已强制本人归属（space.user_id == actor.id），无跨用户误删风险。
 * 引擎删库先行 → 文档表 CASCADE，失败整体回滚，前端只需传空间 id。
 */
export async function deleteSpace(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/spaces/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
