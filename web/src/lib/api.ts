import { supabase } from "./supabase";
import { currentVisit } from "./visit";

const DEFAULT_API_URL = "http://localhost:8000";
/** Where a request that finds the session over sends the user. */
export const SIGNED_OUT_URL = "/sign-in?signed-out=1";

/** Absolute URL for an Engram API path, based on NEXT_PUBLIC_API_URL. */
export function apiUrl(path: string, base = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_URL): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Calls the Engram API as the signed-in user; throws ApiError unless the response is OK. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await supabase().auth.getSession();
  const headers = new Headers(init.headers);
  if (data.session) headers.set("Authorization", `Bearer ${data.session.access_token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  // So "due today" means the student's today.
  headers.set("X-Timezone", Intl.DateTimeFormat().resolvedOptions().timeZone);
  // Groups usage events into visits; logged only for people who agreed.
  headers.set("X-Session", currentVisit());

  const response = await fetch(apiUrl(path), { ...init, headers });
  if (response.status === 401 && typeof window !== "undefined") {
    // The session ended (signed out elsewhere, or expired past refreshing): every page says
    // the same thing, on the sign-in page, rather than each failing in its own way.
    await supabase()
      .auth.signOut({ scope: "local" })
      .catch(() => {});
    // A full load, so nothing from the ended session stays on screen.
    window.location.assign(new URL(SIGNED_OUT_URL, window.location.origin));
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }
  return response;
}

/** Calls the Engram API as the signed-in user and returns the parsed JSON body. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  return response.json() as Promise<T>;
}

/**
 * Uploads a file straight to Storage with a token from the API (Cloud Run caps request bodies
 * at 32 MiB, well under a textbook), reporting progress from 0 to 1.
 */
export async function storageUpload(path: string, token: string, file: File, onProgress: (fraction: number) => void) {
  const base = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://127.0.0.1:54321").replace(/\/+$/, "");
  const form = new FormData();
  form.append("cacheControl", "3600");
  form.append("", file);

  // fetch() can't report upload progress; XMLHttpRequest can.
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", `${base}/storage/v1/object/upload/sign/materials/${path}?token=${encodeURIComponent(token)}`);
    request.setRequestHeader("apikey", process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "");

    // A connection that drops without an error (weak Wi-Fi, a laptop going to sleep) would
    // otherwise leave the progress bar standing still for good.
    let lastHeard = Date.now();
    let sent = false;
    const watch = setInterval(() => {
      if (Date.now() - lastHeard > (sent ? STORED_WITHIN_MS : UPLOAD_STALL_MS)) {
        clearInterval(watch);
        request.abort();
        reject(new ApiError(0, "The upload stopped making progress. Check your internet connection and try again."));
      }
    }, 5000);
    const settle = (finish: () => void) => {
      clearInterval(watch);
      finish();
    };

    request.upload.onprogress = (event) => {
      lastHeard = Date.now();
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    // Every byte is sent; Storage still has to save the file before it answers.
    request.upload.onload = () => {
      lastHeard = Date.now();
      sent = true;
    };
    request.onload = () =>
      settle(() => {
        if (request.status >= 200 && request.status < 300) resolve();
        else reject(new ApiError(request.status, "The upload didn't go through. Please try again."));
      });
    request.onerror = () =>
      settle(() =>
        reject(new ApiError(0, "The upload was interrupted. Check your internet connection and try again.")),
      );
    request.send(form);
  });
}

/** How long an upload may go without sending anything before it counts as stalled. */
const UPLOAD_STALL_MS = 60_000;
/** How long Storage may take to answer once the whole file is sent. */
const STORED_WITHIN_MS = 120_000;
