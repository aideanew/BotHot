/**
 * lib/api/spaces —— 知识空间域（C-T3，B-T4 契约 v0.2）
 *
 * 契约：POST/GET /api/v1/spaces、GET /api/v1/spaces/{id}、GET /api/v1/spaces/{id}/docs。
 * 列表类返回统一解包信封 data.items。
 */

import { request } from "./http";
import {
  BATCH_DOCS_MAX_IDS,
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
  return request<SpaceDetail>("/api/v1/spaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** GET /api/v1/spaces —— 知识空间列表（信封 data.items 解包） */
export async function listSpaces(): Promise<Space[]> {
  return request<{ items: Space[] }>("/api/v1/spaces").then((d) => d.items);
}

/**
 * GET /api/v1/spaces/{id} —— 空间详情。
 * 不存在/无权（30004）由调用方渲染 404 语义空态页，不白屏。
 * （STEP-55 S55.3 纠真：这行原来写的是"30101/10102"，而后端全仓不产 30101，
 * 未命中的线上码是 30004——`apps/api/tests/test_spaces_api.py:244` 把码位钉在断言里。
 * 文案表里的 30101 仍在（D-V21-14：发版前不删码），但它不是这条端点的返回值。）
 */
export async function getSpace(id: string): Promise<SpaceDetail> {
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
  return request<DocIngestStatus>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/docs/${encodeURIComponent(docId)}/status`
  );
}


/**
 * R0.2.1 —— DELETE /api/v1/spaces/{id}/docs/{docId}：删除单篇（引擎先删、失败整体回滚）。
 * 越权/无效空间或 doc → 30004；引擎删除失败 → 错误信封上抛（PG 无残留）。
 * MOCK 态就地改写样例库，使演示模式下删除/改分类可闭环。
 */
export async function deleteSpaceDoc(spaceId: string, docId: string): Promise<DeleteDocResult> {
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
