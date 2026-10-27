import { supabase } from "./supabase";

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

/** Uploads a file to the Engram API as the signed-in user, reporting progress from 0 to 1. */
export async function apiUpload<T>(path: string, file: File, onProgress: (fraction: number) => void): Promise<T> {
  const { data } = await supabase().auth.getSession();
  const form = new FormData();
  form.append("file", file);

  // fetch() can't report upload progress; XMLHttpRequest can.
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", apiUrl(path));
    if (data.session) request.setRequestHeader("Authorization", `Bearer ${data.session.access_token}`);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    request.onload = () => {
      let body: { detail?: string } | null = null;
      try {
        body = JSON.parse(request.responseText);
      } catch {}
      if (request.status >= 200 && request.status < 300) resolve(body as T);
      else reject(new ApiError(request.status, body?.detail ?? request.statusText));
    };
    request.onerror = () =>
      reject(new ApiError(0, "The upload was interrupted. Check your internet connection and try again."));
    request.send(form);
  });
}
