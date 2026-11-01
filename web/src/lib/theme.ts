/**
 * Light or dark, chosen with the toggle and kept per browser in localStorage (not per account:
 * it's a preference of the screen as much as of the person). Light is the default (D23).
 */

export type Theme = "light" | "dark";

const KEY = "engram-theme";
const CHANGED = "engram-theme-change";

/** Runs in <head> before the page paints, so a dark page never flashes light first. */
export const THEME_SCRIPT = `try{if(localStorage.getItem("${KEY}")==="dark")document.documentElement.dataset.theme="dark"}catch(e){}`;

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function apply(theme: Theme) {
  if (theme === "dark") document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
  window.dispatchEvent(new Event(CHANGED));
}

export function setTheme(theme: Theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Private browsing can refuse storage; the theme still changes for this page.
  }
  apply(theme);
}

/** For useSyncExternalStore: hears this tab's changes and other tabs' (the storage event). */
export function subscribeTheme(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === KEY) apply(event.newValue === "dark" ? "dark" : "light");
  };
  window.addEventListener(CHANGED, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener("storage", onStorage);
  };
}
