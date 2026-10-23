/**
 * usePagedList —— 通用分页状态 hook（W9 D.4）
 *
 * 响应形状（S37.3，P-96 收口）：只有**一种**——D-V3-02 目标壳
 * `{items, total, limit, offset, page, pageSize, hasMore}`，与
 * `apps/api/app/schemas/pagination.py` 的 `Page` 模型逐键对齐。旧两壳联合
 * （page/page_size 与 limit/offset 两种响应）与 `isPageShape` 分支删除；
 * hook 消费 `hasMore`（P-96 原话：此前它自己算 totalPages、目标壳新键零消费）。
 *
 * 入参 shape 决定**请求**参数形状（page+page_size 或 limit+offset——两支请求参数
 * 是后端两类端点的现行入口契约，与响应壳是两回事），
 * 返回统一 page/pageSize/total/items/hasMore 供 Pagination.tsx 消费。
 */

import { useCallback, useEffect, useState } from "react";

export interface PageShape {
  page?: number;
  page_size?: number;
}

export interface OffsetShape {
  limit?: number;
  offset?: number;
}

export type PageTargetUnified<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
};

export type PagedResponse<T> = PageTargetUnified<T>;

export interface UsePagedListOptions<T, P> {
  /** 数据拉取函数，接收分页参数 + 额外过滤参数，返回分页响应 */
  fetcher: (params: P & (PageShape | OffsetShape)) => Promise<PagedResponse<T>>;
  /** 额外过滤参数（每次 fetch 随分页参数一起传） */
  filters?: P;
  /** 每页条数，默认 20 */
  pageSize?: number;
  /** 分页形状：'page' 使用 page/page_size，'offset' 使用 limit/offset */
  shape?: "page" | "offset";
  /** 依赖变更时自动重置到第 1 页并重新拉取 */
  deps?: readonly unknown[];
}

export interface UsePagedListReturn<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  /** 后端目标壳的 hasMore（D-V3-02）：还有下一页。P-96 收口后由 hook 消费。 */
  hasMore: boolean;
  loading: boolean;
  error: string;
  setPage: (p: number) => void;
  refresh: () => void;
}

export function usePagedList<T, P extends Record<string, unknown> = Record<string, never>>(
  opts: UsePagedListOptions<T, P>
): UsePagedListReturn<T> {
  const pageSize = opts.pageSize ?? 20;
  const shape = opts.shape ?? "page";
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const fetchPage = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const pagination =
        shape === "page"
          ? { page, page_size: pageSize }
          : { limit: pageSize, offset: (page - 1) * pageSize };
      const res = await opts.fetcher({ ...opts.filters, ...pagination } as P & (PageShape | OffsetShape));
      setItems(res.items ?? []);
      setTotal(res.total ?? 0);
      // S37.3：hasMore 由响应消费（P-96：目标壳新键此前零消费）。Boolean() 是对
      // 尚未迁移到目标壳的旧端点的运行时兜底，类型层已是必填。
      setHasMore(Boolean(res.hasMore));
      if (res.page !== page && res.page > 0) {
        setPage(res.page);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, shape, opts.fetcher, opts.filters, tick]);

  useEffect(() => {
    fetchPage();
  }, [fetchPage]);

  useEffect(() => {
    setPage(1);
    setTick((t) => t + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, opts.deps ?? []);

  const goToPage = useCallback((p: number) => {
    setPage(Math.max(1, p));
  }, []);

  const refresh = useCallback(() => {
    setTick((t) => t + 1);
  }, []);

  return { items, total, page, pageSize, totalPages, hasMore, loading, error, setPage: goToPage, refresh };
}
