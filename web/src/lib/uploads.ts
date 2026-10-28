/** Adding materials to a course. The limits mirror the API (`api/routes/materials.py`) so a
 * wrong file is caught before it is sent; the API checks the file itself regardless. */

import { ApiError, api, apiFetch, storageUpload } from "./api";
import type { Material } from "./courses";

export type MaterialKind = Material["kind"];

export const MAX_UPLOAD_MB: Record<MaterialKind, number> = { slides: 100, textbook: 500 };
export const ACCEPT = ".pdf,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation";

/** Why this file can't be uploaded, in words for the student, or null if it can. */
export function uploadProblem(file: { name: string; size: number }, kind: MaterialKind = "slides"): string | null {
  const extension = file.name.toLowerCase().split(".").pop();
  if (extension === "ppt") {
    return "This is an older PowerPoint file. Open it in PowerPoint, save it as .pptx, and add that instead.";
  }
  if (extension !== "pdf" && extension !== "pptx") {
    return "Engram can read PDF and PowerPoint (.pptx) files.";
  }
  if (file.size > MAX_UPLOAD_MB[kind] * 1024 * 1024) {
    return kind === "slides"
      ? `That file is over ${MAX_UPLOAD_MB.slides} MB. Saving the slides as a PDF usually makes them smaller.`
      : `That file is over ${MAX_UPLOAD_MB.textbook} MB.`;
  }
  return null;
}

type PendingMaterial = { material: Material; upload: { path: string; token: string } };

/**
 * Adds a file to a course: the API records it, the browser uploads it straight to storage,
 * then the API queues it to be read. A failed upload is removed rather than left half-added.
 */
export async function addMaterial(
  courseId: string,
  file: File,
  kind: MaterialKind,
  onProgress: (fraction: number) => void,
): Promise<Material> {
  const { material, upload } = await api<PendingMaterial>(`/courses/${courseId}/materials`, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, size: file.size, kind }),
  });
  try {
    await storageUpload(upload.path, upload.token, file, onProgress);
    return await api<Material>(`/materials/${material.id}/queue`, { method: "POST" });
  } catch (error) {
    // A file that isn't what it says (415) has already been removed by the API.
    if (!(error instanceof ApiError && error.status === 415)) {
      await apiFetch(`/materials/${material.id}`, { method: "DELETE" }).catch(() => {});
    }
    throw error;
  }
}
