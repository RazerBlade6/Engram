"use client";

import { useState, type DragEvent } from "react";

import { ApiError, apiFetch, apiUpload } from "@/lib/api";
import type { Material } from "@/lib/courses";
import { ACCEPT, uploadProblem } from "@/lib/uploads";

type Upload = { name: string; progress: number };

export function MaterialsPanel({
  courseId,
  materials,
  onChange,
  show,
}: {
  courseId: string;
  materials: Material[];
  onChange: () => void;
  show: (text: string) => void;
}) {
  const [upload, setUpload] = useState<Upload | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  async function add(files: File[]) {
    setProblem(null);
    for (const file of files) {
      const issue = uploadProblem(file);
      if (issue) {
        setProblem(`${file.name}: ${issue}`);
        continue;
      }
      setUpload({ name: file.name, progress: 0 });
      try {
        await apiUpload<Material>(`/courses/${courseId}/materials`, file, (progress) =>
          setUpload({ name: file.name, progress }),
        );
        onChange();
      } catch (e) {
        const reason = e instanceof ApiError && e.status !== 500 ? e.message : "Something went wrong. Please try again.";
        setProblem(`${file.name}: ${reason}`);
      }
    }
    setUpload(null);
  }

  async function remove(material: Material) {
    setConfirming(null);
    setProblem(null);
    try {
      await apiFetch(`/materials/${material.id}`, { method: "DELETE" });
      show(`${material.title} removed.`);
      onChange();
    } catch {
      show(`Couldn't remove ${material.title}. Please try again.`);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (!upload) add(Array.from(event.dataTransfer.files));
  }

  return (
    <section aria-labelledby="materials-heading">
      <h2 id="materials-heading" className="text-xl font-semibold">
        Materials
      </h2>
      <ul className="mt-3 space-y-3">
        {materials.map((m) => (
          <li key={m.id} className="rounded-lg border border-border bg-white px-4 py-3">
            <div className="font-medium break-words">{m.title}</div>
            <div className="text-sm text-muted">{materialStatus(m)}</div>
            {m.kind === "slides" &&
              (confirming === m.id ? (
                <div className="mt-2 flex items-center gap-3 text-sm">
                  <span>Remove these slides?</span>
                  <button onClick={() => remove(m)} className="font-semibold text-danger underline">
                    Remove
                  </button>
                  <button onClick={() => setConfirming(null)} className="text-muted underline">
                    Keep
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => {
                    setConfirming(m.id);
                    setProblem(null);
                  }}
                  className="mt-1 text-sm text-muted underline hover:text-foreground"
                  aria-label={`Remove ${m.title}`}
                >
                  Remove
                </button>
              ))}
          </li>
        ))}
      </ul>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mt-6 rounded-xl border-2 border-dashed px-5 py-8 text-center transition-colors ${
          dragging ? "border-accent bg-accent/10" : "border-border bg-white"
        }`}
      >
        {upload ? (
          <div role="status" aria-live="polite">
            <p className="font-medium break-words">Uploading {upload.name}</p>
            <div className="mx-auto mt-3 h-2 max-w-56 overflow-hidden rounded-full bg-border">
              <div className="h-full bg-accent transition-[width]" style={{ width: `${Math.round(upload.progress * 100)}%` }} />
            </div>
            <p className="mt-2 text-sm text-muted tabular-nums">{Math.round(upload.progress * 100)}%</p>
          </div>
        ) : (
          <label className="block cursor-pointer rounded-lg focus-within:ring-2 focus-within:ring-accent/40">
            <UploadIcon />
            <span className="mt-3 block text-lg font-semibold">Add slides</span>
            <span className="mt-1 block text-muted">
              Drop a file here, or click to choose one. PDF or PowerPoint.
            </span>
            <input
              type="file"
              accept={ACCEPT}
              multiple
              className="sr-only"
              onChange={(e) => {
                add(Array.from(e.currentTarget.files ?? []));
                e.currentTarget.value = "";
              }}
            />
          </label>
        )}
      </div>
      {problem && (
        <p role="alert" className="mt-3 rounded-lg bg-danger-soft px-4 py-3 text-danger">
          {problem}
        </p>
      )}
    </section>
  );
}

function materialStatus(m: Material): string {
  const kind = m.kind === "textbook" ? "Textbook" : "Slides";
  switch (m.status) {
    case "ready":
      return kind;
    case "failed":
      return "This file couldn't be read. Remove it and try a PDF version.";
    default:
      return "Reading it now. You can leave this page.";
  }
}

function UploadIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="mx-auto size-10 text-accent" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}
