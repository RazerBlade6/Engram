const DEFAULT_API_URL = "http://localhost:8000";

/** Absolute URL for an Engram API path, based on NEXT_PUBLIC_API_URL. */
export function apiUrl(path: string, base = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}
