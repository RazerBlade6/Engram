import { cx } from "@/lib/cx";

/** A thin bar showing how far through something is, e.g. a review session. */
export function ProgressBar({
  value,
  max,
  label,
  className,
}: {
  value: number;
  max: number;
  /** What it measures, for screen readers, e.g. "Cards reviewed". */
  label: string;
  className?: string;
}) {
  const share = max > 0 ? Math.min(1, value / max) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cx("h-1.5 overflow-hidden rounded-full bg-foreground/10", className)}
    >
      <div
        className="h-full rounded-full bg-accent transition-[width] duration-300 ease-quiet"
        style={{ width: `${share * 100}%` }}
      />
    </div>
  );
}
