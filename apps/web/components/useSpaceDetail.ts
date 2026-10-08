import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getDocIngestStatus,
  getSpace,
  listSpaceDocCategories,
  listSpaceDocs,
  isAuthError,
  type SpaceDetail,
  type SpaceDoc,
} from "@/lib/api";
import { useAuth } from "@/components/AuthContext";

const PAGE_SIZE = 50;
const INGEST_POLL_MS = 4000;

export function useSpaceDetail(spaceId: string) {
  const router = useRouter();
  const { status } = useAuth();
  const [space, setSpace] = useState<SpaceDetail | null>(null);
  const [docs, setDocs] = useState<SpaceDoc[] | null>(null);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<string[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [reloadTick, setReloadTick] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const loadFirstPage = useCallback(
    async (category: string) => {
      try {
        const [res, cats] = await Promise.all([
          listSpaceDocs(spaceId, { limit: PAGE_SIZE, offset: 0, category }),
          listSpaceDocCategories(spaceId),
        ]);
        setDocs(res.items);
        setTotal(res.total);
        setCategories(cats);
      } catch {
        // 失败保留旧列表，不打断当前成功态
      }
    },
    [spaceId]
  );

  const refreshDocs = useCallback(() => {
    void loadFirstPage(categoryFilter);
    getSpace(spaceId)
      .then((detail) => setSpace(detail))
      .catch(() => {});
  }, [loadFirstPage, categoryFilter, spaceId]);

  const handleCategoryChanged = useCallback(
    (value: string) => {
      setCategoryFilter(value);
      void loadFirstPage(value);
    },
    [loadFirstPage]
  );

  const handleDocChanged = useCallback(() => void refreshDocs(), [refreshDocs]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !docs || docs.length >= total) return;
    setLoadingMore(true);
    try {
      const res = await listSpaceDocs(spaceId, {
        limit: PAGE_SIZE,
        offset: docs.length,
        category: categoryFilter,
      });
      setDocs((prev) => (prev ? [...prev, ...res.items] : res.items));
      setTotal(res.total);
    } catch {
      // 追加失败保留已有列表
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, docs, total, categoryFilter, spaceId]);

  const toggleSelected = useCallback((docId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  }, []);

  // 入库是拉模式：提交只写到 pending（引擎侧 INDEXED），状态推进靠按篇调
  // GET /docs/{id}/status 回写——不驱动这条链，文章会永远停在「采集中」。
  // 依赖 pending 的 id 集合而非 docs 引用，避免每次刷新列表都重启定时器。
  const pendingIngestKey = useMemo(
    () =>
      (docs ?? [])
        .filter((d) => d.status === "pending")
        .map((d) => d.id)
        .join(","),
    [docs]
  );

  useEffect(() => {
    if (pendingIngestKey === "") return;
    const ids = pendingIngestKey.split(",");
    let stopped = false;

    const tick = async () => {
      // 单篇失败（30003 等）不中断整轮：其余篇目照常刷新
      await Promise.allSettled(
        ids.map((id) => getDocIngestStatus(spaceId, id))
      );
      if (!stopped) void loadFirstPage(categoryFilter);
    };

    void tick();
    const timer = setInterval(() => void tick(), INGEST_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [pendingIngestKey, spaceId, categoryFilter, loadFirstPage]);

  // 选中态只覆盖当前过滤下已加载的行；切过滤时不可见行退出选中
  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0 || docs === null) return prev;
      const loaded = new Set(docs.map((d) => d.id));
      const next = new Set(Array.from(prev).filter((id) => loaded.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [docs]);

  useEffect(() => {
    if (status === "guest") router.replace("/");
  }, [status, router]);

  useEffect(() => {
    if (status !== "authed") return;
    let cancelled = false;
    setSpace(null);
    setDocs(null);
    setTotal(0);
    setCategories([]);
    setLoadingMore(false);
    setNotFound(false);
    setErrorMsg("");
    setCategoryFilter("");
    setSelected(new Set());
    getSpace(spaceId)
      .then((detail) => {
        if (cancelled) return;
        setSpace(detail);
        return Promise.all([
          listSpaceDocs(spaceId, { limit: PAGE_SIZE, offset: 0 }),
          listSpaceDocCategories(spaceId),
        ]).then(([res, cats]) => {
          if (cancelled) return;
          setDocs(res.items);
          setTotal(res.total);
          setCategories(cats);
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && isAuthError(err.code)) {
          router.replace("/");
          return;
        }
        if (err instanceof ApiError && (err.code === 30101 || err.code === 10102)) {
          setNotFound(true);
          return;
        }
        setErrorMsg(err instanceof Error ? err.message : "加载失败");
      });
    return () => { cancelled = true; };
  }, [status, spaceId, reloadTick, router]);

  return {
    space, docs, total, categories,
    loadingMore, notFound, errorMsg,
    setReloadTick, categoryFilter, selected, setSelected,
    refreshDocs, handleCategoryChanged, handleDocChanged,
    loadMore, toggleSelected,
  };
}