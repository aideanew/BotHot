import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  deleteAdminSpace,
  deleteAdminSpaceDoc,
  isAuthError,
  listAdminSpaceDocs,
  listAdminSpaces,
  patchAdminSpaceDescription,
  type AdminSpace,
  type SpaceDoc,
} from "@/lib/api";
import { useAuth } from "@/components/AuthContext";

const PAGE_SIZE = 50;

export function useAdminData() {
  const router = useRouter();
  const { status, me } = useAuth();
  const [spaces, setSpaces] = useState<AdminSpace[] | null>(null);
  const [activeSpaceId, setActiveSpaceId] = useState("");
  const [docs, setDocs] = useState<SpaceDoc[] | null>(null);
  const [total, setTotal] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loadingMore, setLoadingMore] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [reloadTick, setReloadTick] = useState(0);
  const [editDescSpaceId, setEditDescSpaceId] = useState("");
  const [editDescValue, setEditDescValue] = useState("");
  const [savingDesc, setSavingDesc] = useState(false);
  const [confirmingDocDelete, setConfirmingDocDelete] = useState("");
  const [deletingDoc, setDeletingDoc] = useState("");
  const [confirmingSpaceDelete, setConfirmingSpaceDelete] = useState("");
  const [deletingSpace, setDeletingSpace] = useState("");

  const isAdmin = status === "authed" && me?.is_admin === true;

  useEffect(() => {
    if (status === "guest") router.replace("/");
  }, [status, router]);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    setSpaces(null);
    listAdminSpaces()
      .then((items) => {
        if (!cancelled) setSpaces(items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && isAuthError(err.code)) {
          router.replace("/");
          return;
        }
        setErrorMsg(err instanceof Error ? err.message : "加载失败");
      });
    return () => { cancelled = true; };
  }, [isAdmin, reloadTick, router]);

  const openSpace = useCallback((spaceId: string) => {
    setActiveSpaceId(spaceId);
    setDocs(null);
    setTotal(0);
    setCategoryFilter("");
    setSelected(new Set());
    setLoadingMore(false);
    setErrorMsg("");
    listAdminSpaceDocs(spaceId, { limit: PAGE_SIZE, offset: 0 })
      .then((res) => {
        setDocs(res.items);
        setTotal(res.total);
      })
      .catch((err: unknown) => {
        setErrorMsg(err instanceof Error ? err.message : "加载失败");
      });
  }, []);

  const refreshDocs = useCallback((category: string) => {
    if (!activeSpaceId) return;
    listAdminSpaceDocs(activeSpaceId, { limit: PAGE_SIZE, offset: 0, category })
      .then((res) => {
        setDocs(res.items);
        setTotal(res.total);
      })
      .catch(() => {});
  }, [activeSpaceId]);

  const loadMore = useCallback(() => {
    if (!activeSpaceId || loadingMore || !docs || docs.length >= total) return;
    setLoadingMore(true);
    listAdminSpaceDocs(activeSpaceId, {
      limit: PAGE_SIZE,
      offset: docs.length,
      category: categoryFilter,
    })
      .then((res) => {
        setDocs((prev) => (prev ? [...prev, ...res.items] : res.items));
        setTotal(res.total);
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }, [activeSpaceId, loadingMore, docs, total, categoryFilter]);

  const handleSaveDescription = useCallback(
    async (spaceId: string) => {
      setSavingDesc(true);
      try {
        await patchAdminSpaceDescription(spaceId, editDescValue);
        setEditDescSpaceId("");
        setReloadTick((t) => t + 1);
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : "保存失败");
      } finally {
        setSavingDesc(false);
      }
    },
    [editDescValue]
  );

  const handleDeleteDoc = useCallback(
    async (docId: string) => {
      if (!activeSpaceId) return;
      setConfirmingDocDelete("");
      setDeletingDoc(docId);
      try {
        await deleteAdminSpaceDoc(activeSpaceId, docId);
        refreshDocs(categoryFilter);
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : "删除失败");
      } finally {
        setDeletingDoc("");
      }
    },
    [activeSpaceId, categoryFilter, refreshDocs]
  );

  const handleDeleteSpace = useCallback(
    async (spaceId: string) => {
      setConfirmingSpaceDelete("");
      setDeletingSpace(spaceId);
      try {
        await deleteAdminSpace(spaceId);
        if (activeSpaceId === spaceId) {
          setActiveSpaceId("");
          setDocs(null);
          setTotal(0);
        }
        setReloadTick((t) => t + 1);
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : "删除空间失败");
      } finally {
        setDeletingSpace("");
      }
    },
    [activeSpaceId]
  );

  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0 || docs === null) return prev;
      const loaded = new Set(docs.map((d) => d.id));
      const next = new Set(Array.from(prev).filter((id) => loaded.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [docs]);

  return {
    status, isAdmin,
    spaces, activeSpaceId, setActiveSpaceId,
    docs, total, categoryFilter, setCategoryFilter,
    selected, setSelected,
    loadingMore, errorMsg, setReloadTick,
    editDescSpaceId, setEditDescSpaceId, editDescValue, setEditDescValue,
    savingDesc, setSavingDesc,
    confirmingDocDelete, setConfirmingDocDelete, deletingDoc,
    confirmingSpaceDelete, setConfirmingSpaceDelete, deletingSpace,
    openSpace, refreshDocs, loadMore,
    handleSaveDescription, handleDeleteDoc, handleDeleteSpace,
  };
}
