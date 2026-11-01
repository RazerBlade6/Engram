"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { cx } from "@/lib/cx";
import { currentTheme, setTheme, subscribeTheme } from "@/lib/theme";

/** The current theme, light while rendering on the server. */
export function useTheme() {
  return useSyncExternalStore(subscribeTheme, currentTheme, () => "light" as const);
}

/**
 * Switches between the light and dark themes. A small round button in the bottom-left corner
 * on wider screens; on phones it lives in the menu instead (`inline`). Review, a focus screen
 * whose ratings can be pinned to the bottom edge, has no corner button.
 */
export function ThemeToggle({ inline = false }: { inline?: boolean }) {
  const theme = useTheme();
  const pathname = usePathname();
  if (!inline && pathname.startsWith("/review")) return null;
  const next = theme === "dark" ? "light" : "dark";
  const label = `Switch to the ${next} theme`;
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={inline ? undefined : label}
      title={inline ? undefined : label}
      className={cx(
        "flex items-center text-muted transition-colors duration-150 hover:text-foreground",
        inline
          ? "min-h-11 w-full gap-3 rounded-control px-4 font-semibold hover:bg-foreground/5"
          : "fixed bottom-4 left-4 z-30 size-10 justify-center rounded-full border border-border bg-surface shadow-card max-md:hidden",
      )}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
      {inline && (theme === "dark" ? "Light theme" : "Dark theme")}
    </button>
  );
}

function MoonIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11Z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="4" />
      <path
        strokeLinecap="round"
        d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"
      />
    </svg>
  );
}
