import { supabase } from "./supabase";
import { currentVisit } from "./visit";

const DEFAULT_API_URL = "http://localhost:8000";

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
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else reject(new ApiError(request.status, "The upload didn't go through. Please try again."));
    };
    request.onerror = () =>
      reject(new ApiError(0, "The upload was interrupted. Check your internet connection and try again."));
    request.send(form);
  });
}
