import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

const TONE = {
  info: "border-accent/30 bg-accent-soft text-foreground",
  success: "border-success/30 bg-success-soft text-success",
  error: "border-danger/30 bg-danger-soft text-danger",
};

/** A short message in the flow of the page: what happened, and what to do about it. */
export function Notice({
  tone = "info",
  action,
  children,
}: {
  tone?: keyof typeof TONE;
  /** A button or link to fix it, e.g. "Try again". */
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cx(
        "flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-control border px-4 py-3",
        TONE[tone],
      )}
    >
      <div className="min-w-0">{children}</div>
      {action}
    </div>
  );
}
