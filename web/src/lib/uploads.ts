/** Limits for student uploads, mirrored from the API (`api/routes/materials.py`) so a wrong
 * file is caught before it is sent. The API checks the content itself regardless. */

export const MAX_UPLOAD_MB = 100;
export const ACCEPT = ".pdf,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation";

/** Why this file can't be uploaded, in words for the student, or null if it can. */
export function uploadProblem(file: { name: string; size: number }): string | null {
  const extension = file.name.toLowerCase().split(".").pop();
  if (extension === "ppt") {
    return "This is an older PowerPoint file. Open it in PowerPoint, save it as .pptx, and add that instead.";
  }
  if (extension !== "pdf" && extension !== "pptx") {
    return "Engram can read PDF and PowerPoint (.pptx) files.";
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `That file is over ${MAX_UPLOAD_MB} MB. Saving the slides as a PDF usually makes them smaller.`;
  }
  return null;
}
