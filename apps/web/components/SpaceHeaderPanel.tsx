import { formatTime } from "@/components/DocStatusBadge";
import AddArticlePanel from "@/components/AddArticlePanel";
import SubscribeShortcut from "@/components/SubscribeShortcut";
import PublicLibraryPicker from "@/components/PublicLibraryPicker";
import EngineSwitcher from "@/components/EngineSwitcher";
import type { SpaceDetail } from "@/lib/api";

interface SpaceHeaderPanelProps {
  space: SpaceDetail;
  onSubmitted: () => void;
  onDocsChanged: () => void;
}

export default function SpaceHeaderPanel({
  space,
  onSubmitted,
  onDocsChanged,
}: SpaceHeaderPanelProps) {
  return (
    <>
      <a
        href="/spaces"
        className="inline-flex items-center gap-1 text-caption text-neutral-400 hover:text-neutral-600"
      >
        ← 返回空间列表
      </a>

      <section className="card mt-4 p-6">
        <p className="eyebrow">KNOWLEDGE SPACE</p>
        <h1 className="mt-2 text-title-lg font-semibold tracking-tight text-neutral-900">
          {space.name}
        </h1>
        <p className="mt-2 muted-copy">
          {space.description || "（未填写简介）"}
        </p>
        <p className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-caption text-neutral-400">
          <span>{space.stats.docs} 篇文档</span>
          {space.stats.chunks !== null && (
            <span>{space.stats.chunks} 个知识分块</span>
          )}
          <span>创建于 {formatTime(space.createdAt)}</span>
          <span>更新于 {formatTime(space.updatedAt)}</span>
        </p>
        <AddArticlePanel spaceId={space.id} onSubmitted={onSubmitted} />
      </section>

      <section className="mt-6">
        <SubscribeShortcut spaceId={space.id} />
      </section>

      <section className="mt-6">
        <PublicLibraryPicker
          targetSpaceId={space.id}
          onLinked={onDocsChanged}
        />
      </section>

      <section className="mt-6">
        <EngineSwitcher space={space} onChanged={onDocsChanged} />
      </section>
    </>
  );
}