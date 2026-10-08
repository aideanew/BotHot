import Skeleton from "@/components/Skeleton";

export default function LoadingHotDaily() {
  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-6 h-8 w-48 animate-pulse rounded bg-neutral-100" />
      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-1">
          <Skeleton count={5} height="h-16" />
        </div>
        <div className="md:col-span-2">
          <Skeleton count={3} height="h-20" />
        </div>
      </div>
    </div>
  );
}
