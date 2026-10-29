import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

/**
 * Plain rows separated by thin lines, for lists on the desk (dates, courses). Keeps a page
 * from turning into a stack of boxes; cards are kept for the things a student studies.
 */
export function RowList({ children, className }: { children: ReactNode; className?: string }) {
  return <ul className={cx("divide-y divide-border border-y border-border", className)}>{children}</ul>;
}

export function Row({ children, className }: { children: ReactNode; className?: string }) {
  return <li className={cx("py-3.5", className)}>{children}</li>;
}
