import Skeleton from "@/components/Skeleton";

export default function LoadingOnboarding() {
  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 h-8 w-48 animate-pulse rounded bg-neutral-100" />
      <Skeleton count={4} height="h-14" />
    </div>
  );
}
