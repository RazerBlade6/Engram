import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

/**
 * A ruled index card resting on the desk, with the next card in the pile peeking out from
 * underneath. Only the things a student studies are drawn as cards.
 */
export function IndexCard({
  label,
  labelColor,
  corner,
  pile = true,
  ruled = true,
  className,
  children,
}: {
  /** A short note handwritten above the red line, e.g. the course or "Due today". */
  label?: ReactNode;
  /** The ink it's written in, usually the course's color; muted if not given. */
  labelColor?: string;
  /** Something small in the top-right corner, e.g. the report control. */
  corner?: ReactNode;
  /** Whether another card peeks out from underneath. */
  pile?: boolean;
  /** Ruled lines; turn off for long or dense content. */
  ruled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className="relative isolate">
      {pile && <div aria-hidden className="index-card-under -z-10" />}
      <div className={cx("index-card", className)} data-ruled={ruled || undefined}>
        <IndexCardHeader label={label} labelColor={labelColor} corner={corner} />
        <div className="px-6 pt-5 pb-6 sm:px-8">{children}</div>
      </div>
    </div>
  );
}

/**
 * The band above the red line: a handwritten note on the left, the corner control on the
 * right. The note is written on the paper in a quiet ink, so it never outranks the card's text.
 */
export function IndexCardHeader({
  label,
  labelColor,
  corner,
}: {
  label?: ReactNode;
  labelColor?: string;
  corner?: ReactNode;
}) {
  return (
    <div className="flex h-11 items-end justify-between gap-4 px-6 sm:px-8">
      {label ? (
        <span
          className="truncate pb-0.5 font-hand text-xl leading-none font-medium opacity-85"
          style={{ color: labelColor ?? "var(--muted)" }}
        >
          {label}
        </span>
      ) : (
        <span />
      )}
      {corner && <div className="self-center">{corner}</div>}
    </div>
  );
}
