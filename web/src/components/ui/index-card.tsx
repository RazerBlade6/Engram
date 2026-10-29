import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

/**
 * A ruled index card resting on the desk, with the next card in the pile peeking out from
 * underneath. Only the things a student studies are drawn as cards.
 */
export function IndexCard({
  tab,
  tabColor,
  corner,
  pile = true,
  ruled = true,
  className,
  children,
}: {
  /** A short label on the card's colored tab, e.g. the course or "Due today". */
  tab?: ReactNode;
  /** The tab's color, usually the course's; the accent if not given. */
  tabColor?: string;
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
        <IndexCardHeader tab={tab} tabColor={tabColor} corner={corner} />
        <div className="px-6 pt-5 pb-6 sm:px-8">{children}</div>
      </div>
    </div>
  );
}

/** The band above the red line: the tab on the left, the corner control on the right. */
export function IndexCardHeader({ tab, tabColor, corner }: { tab?: ReactNode; tabColor?: string; corner?: ReactNode }) {
  return (
    <div className="flex h-11 items-end justify-between gap-4 px-6 sm:px-8">
      {tab ? (
        <span
          className="truncate rounded-t-[3px] px-2.5 py-0.5 text-sm font-semibold text-on-accent"
          style={{ background: tabColor ?? "var(--accent)" }}
        >
          {tab}
        </span>
      ) : (
        <span />
      )}
      {corner && <div className="self-center">{corner}</div>}
    </div>
  );
}
