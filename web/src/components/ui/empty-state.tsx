import type { ReactNode } from "react";

/** What a page shows before there's anything on it: what will appear, and how to start. */
export function EmptyState({ title, action, children }: { title: string; action?: ReactNode; children?: ReactNode }) {
  return (
    <div className="rounded-control border border-dashed border-border-strong px-6 py-8 text-center">
      <p className="text-xl font-semibold text-balance">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-prose text-muted">{children}</div>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}
