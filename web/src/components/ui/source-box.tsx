import type { ComponentProps, ReactNode } from "react";

import { cx } from "@/lib/cx";

/**
 * Where something came from: set apart from the card by a line down its left edge rather
 * than another box. Put the quoted passage in `children`.
 */
export function SourceBox({
  title,
  where,
  action,
  className,
  children,
}: {
  /** The book or file, e.g. "From Introduction to Psychology". */
  title: ReactNode;
  /** Section and page, e.g. "8.2 Parts of the Brain Involved in Memory · page 274". */
  where?: ReactNode;
  /** A link at the bottom, e.g. "Open the page". */
  action?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <aside className={cx("rounded-r-control border-l-[3px] border-accent bg-paper px-6 py-5 shadow-card", className)}>
      <p className="font-semibold">{title}</p>
      {where && <p className="text-sm text-muted">{where}</p>}
      {children && <div className="mt-3 font-read text-lg leading-relaxed">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </aside>
  );
}

/** The quoted words inside a passage, marked like a highlighter would. */
export function Highlight({ children, ...props }: ComponentProps<"mark">) {
  return (
    <mark className="rounded-sm bg-highlight px-0.5 text-foreground" {...props}>
      {children}
    </mark>
  );
}
