import Skeleton from "@/components/Skeleton";

export default function LoadingAdminOps() {
  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 h-8 w-40 animate-pulse rounded bg-neutral-100" />
      <Skeleton count={3} height="h-16" />
    </div>
  );
}
