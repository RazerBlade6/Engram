import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

/** A keyboard key, shown beside the action it triggers. */
export function Kbd({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "inverse" }) {
  return (
    <kbd
      className={cx(
        "inline-grid min-w-6 place-items-center rounded-md border px-1.5 font-sans text-xs leading-5 font-medium",
        tone === "inverse" ? "border-on-accent/40 text-on-accent/90" : "border-current/30 text-current opacity-80",
      )}
    >
      {children}
    </kbd>
  );
}
