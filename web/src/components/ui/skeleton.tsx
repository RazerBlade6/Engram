import { cx } from "@/lib/cx";

/** A placeholder in the shape of content that's still loading. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("rounded-control bg-foreground/8 motion-safe:animate-pulse", className)} />;
}

/** Stands in for a page's content while it loads, announced once to screen readers. */
export function Loading({ label = "Loading", lines = 3 }: { label?: string; lines?: number }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3">
      <Skeleton className="h-9 w-2/3" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cx("h-5", i === lines - 1 ? "w-1/2" : "w-full")} />
      ))}
    </div>
  );
}
