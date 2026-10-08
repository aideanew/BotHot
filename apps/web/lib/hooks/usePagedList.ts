/**
 * usePagedList —— 通用分页状态 hook（W9 D.4）
 *
 * 兼容双形状：
 * - bot/hot 域：{ items, total, page, page_size }（PageResult，page 从 1 起）
 * - 知识库/任务域：{ items, total, limit, offset }（SpaceDocsPage/JobsPage，offset 从 0 起）
 *
 * 入参 shape 决定请求参数形状（page+page_size 或 limit+offset），
 * 返回统一 page/pageSize/total/items 供 Pagination.tsx 消费。
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

export type PagedResponse<T> =
  | { items: T[]; total: number; page: number; page_size: number }
  | { items: T[]; total: number; limit: number; offset: number };

function isPageShape<T>(res: PagedResponse<T>): res is { items: T[]; total: number; page: number; page_size: number } {
  return "page" in res && "page_size" in res;
}

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
      if (isPageShape(res) && res.page !== page && res.page > 0) {
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

  return { items, total, page, pageSize, totalPages, loading, error, setPage: goToPage, refresh };
}
