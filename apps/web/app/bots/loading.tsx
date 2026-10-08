import Skeleton from "@/components/Skeleton";

export default function BotsLoading() {
  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 h-8 w-48 animate-pulse rounded bg-neutral-100" />
      <div className="mb-6 flex gap-2">
        <div className="h-8 w-20 animate-pulse rounded bg-neutral-100" />
        <div className="h-8 w-20 animate-pulse rounded bg-neutral-100" />
      </div>
      <Skeleton count={5} height="h-14" />
    </div>
  );
}
