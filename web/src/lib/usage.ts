/**
 * Usage events only the browser sees (see backend `api/usage.py`). The server logs them only
 * for people who agreed; for everyone else it says so, and nothing more is sent that visit.
 */

import { api } from "./api";
import { currentVisit } from "./visit";

export type BrowserEvent =
  | { name: "session_start"; width: number }
  | { name: "page_view"; page: string }
  | { name: "source_opened"; origin: "chat" | "review"; page_image: boolean }
  | {
      name: "chat_question";
      course_id: string;
      first_text_ms: number | null;
      total_ms: number;
      grounded: boolean;
      outside: boolean;
      sources: number;
      follow_up: boolean;
      failed: boolean;
    };

const OFF_KEY = "engram.usage.off";

/** Sends an event in the background. Never throws, and never holds up the page. */
export function track(event: BrowserEvent): void {
  const visit = currentVisit();
  try {
    if (sessionStorage.getItem(OFF_KEY) === visit) return;
  } catch {}
  api<{ logged: boolean }>("/events", { method: "POST", body: JSON.stringify(event), keepalive: true })
    .then(({ logged }) => {
      if (logged) return;
      try {
        sessionStorage.setItem(OFF_KEY, visit);
      } catch {}
    })
    .catch(() => {});
}

const STARTED_KEY = "engram.usage.started";

/** A page view, preceded by `session_start` when it's the first of a visit. */
export function trackPage(pathname: string): void {
  const visit = currentVisit();
  let started: string | null = null;
  try {
    started = sessionStorage.getItem(STARTED_KEY);
    sessionStorage.setItem(STARTED_KEY, visit);
  } catch {}
  if (started !== visit) track({ name: "session_start", width: window.innerWidth });
  track({ name: "page_view", page: pageOf(pathname) });
}

const ID = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)$/i;

/** "/courses/4f1c…/x" → "/courses/[id]/x": which page, not which course. */
export function pageOf(pathname: string): string {
  const page = pathname
    .split("/")
    .map((part) => (ID.test(part) ? "[id]" : part.toLowerCase()))
    .join("/");
  return page.replace(/[^a-z0-9/_[\]-]/g, "").slice(0, 100) || "/";
}

/** Milliseconds since `start` (from `performance.now()`), whole and capped at an hour. */
export function msSince(start: number): number {
  return Math.min(Math.round(performance.now() - start), 3_600_000);
}
