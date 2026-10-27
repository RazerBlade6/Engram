"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { trackPage } from "@/lib/usage";

/** Not signed in yet on these, so there's no one to log for. */
const SIGNED_OUT = ["/sign-in", "/auth"];

/** Logs each page a signed-in user opens (only for people who agreed; see `lib/usage`). */
export function UsageTracker() {
  const pathname = usePathname();
  // Once per page, even when effects run twice (React's development mode).
  const tracked = useRef<string | null>(null);
  useEffect(() => {
    if (tracked.current === pathname || SIGNED_OUT.some((p) => pathname.startsWith(p))) return;
    tracked.current = pathname;
    trackPage(pathname);
  }, [pathname]);
  return null;
}
