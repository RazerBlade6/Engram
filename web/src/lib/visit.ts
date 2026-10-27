/**
 * The visit id sent with every API request, so usage events can be grouped into sessions:
 * one per browser tab, renewed after half an hour without activity.
 */

const KEY = "engram.visit";
export const IDLE_MS = 30 * 60 * 1000;

type Visit = { id: string; last: number };

/** The current visit's id, renewed if it has been idle too long. Each call counts as activity. */
export function currentVisit(now = Date.now()): string {
  let saved: Visit | null = null;
  try {
    saved = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
  } catch {}
  const visit = { id: saved && now - saved.last <= IDLE_MS ? saved.id : crypto.randomUUID(), last: now };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(visit));
  } catch {}
  return visit.id;
}
