"use client";

import { useState, type DragEvent } from "react";

import { Button, buttonClass } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { ProgressBar } from "@/components/ui/progress";
import { RowList } from "@/components/ui/row-list";
import { ApiError, apiFetch } from "@/lib/api";
import { cx } from "@/lib/cx";
import type { Material } from "@/lib/courses";
import { ACCEPT, addMaterial, uploadProblem, type MaterialKind } from "@/lib/uploads";

type Upload = { name: string; progress: number };

const UPLOAD_FAILED = "Something went wrong. Please try again.";

export function MaterialsPanel({
  courseId,
  materials,
  onChange,
  show,
  canAddTextbook,
}: {
  courseId: string;
  materials: Material[];
  onChange: () => void;
  show: (text: string) => void;
  /** Admins add textbooks; students add slides. */
  canAddTextbook: boolean;
}) {
  const [upload, setUpload] = useState<Upload | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  async function add(files: File[], kind: MaterialKind = "slides") {
    setProblem(null);
    for (const file of files) {
      const issue = uploadProblem(file, kind);
      if (issue) {
        setProblem(`${file.name}: ${issue}`);
        continue;
      }
      setUpload({ name: file.name, progress: 0 });
      try {
        await addMaterial(courseId, file, kind, (progress) => setUpload({ name: file.name, progress }));
        onChange();
      } catch (e) {
        const reason = e instanceof ApiError && e.status !== 500 ? e.message : UPLOAD_FAILED;
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
      {materials.length > 0 && (
        <RowList className="mt-3">
          {materials.map((m) => (
            <li key={m.id} className="py-3">
              <div className="font-semibold break-words">{m.title}</div>
              <div
                className={cx(
                  "text-sm",
                  m.status === "failed" || m.status === "uploading" ? "text-danger" : "text-muted",
                )}
              >
                {materialStatus(m)}
              </div>
              {(m.kind === "slides" || canAddTextbook) &&
                (confirming === m.id ? (
                  <div className="rise-in mt-2 flex flex-wrap items-center gap-2 text-sm">
                    <span>Remove {m.kind === "slides" ? "these slides" : "this textbook"}?</span>
                    <Button variant="danger" onClick={() => remove(m)} className="min-h-9 px-3 py-1">
                      Remove
                    </Button>
                    <Button variant="quiet" onClick={() => setConfirming(null)} className="min-h-9 px-3 py-1">
                      Keep
                    </Button>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setConfirming(m.id);
                      setProblem(null);
                    }}
                    className="mt-1 text-sm text-muted underline-offset-4 hover:text-foreground hover:underline"
                    aria-label={`Remove ${m.title}`}
                  >
                    Remove
                  </button>
                ))}
            </li>
          ))}
        </RowList>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cx(
          "mt-5 rounded-control border-2 border-dashed px-5 py-7 text-center transition-colors duration-150",
          dragging ? "border-accent bg-accent-soft" : "border-border-strong bg-surface/60 hover:border-accent",
        )}
      >
        {upload ? (
          <div role="status" aria-live="polite">
            <p className="font-semibold break-words">Uploading {upload.name}</p>
            <ProgressBar
              value={Math.round(upload.progress * 100)}
              max={100}
              label="Uploaded"
              className="mx-auto mt-3 max-w-56"
            />
            <p className="mt-2 text-sm text-muted tabular-nums">{Math.round(upload.progress * 100)}%</p>
          </div>
        ) : (
          <label className="block cursor-pointer rounded-control focus-within:ring-3 focus-within:ring-accent/25">
            <UploadIcon />
            <span className="mt-3 block text-lg font-semibold">Add slides</span>
            <span className="mt-1 block text-muted">Drop a file here, or click to choose one. PDF or PowerPoint.</span>
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
      {canAddTextbook && !upload && (
        <label
          className={cx(
            buttonClass({ variant: "secondary" }),
            "mt-3 w-full cursor-pointer focus-within:ring-3 focus-within:ring-accent/25",
          )}
        >
          Add textbook (admin)
          <input
            type="file"
            accept={ACCEPT}
            className="sr-only"
            onChange={(e) => {
              add(Array.from(e.currentTarget.files ?? []), "textbook");
              e.currentTarget.value = "";
            }}
          />
        </label>
      )}
      {problem && (
        <div className="mt-3">
          <Notice tone="error">{problem}</Notice>
        </div>
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
    case "uploading":
      // Left behind when a page is closed mid-upload.
      return "This upload didn't finish. Remove it and add the file again.";
    default:
      return "Reading it now. You can leave this page.";
  }
}

function UploadIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="mx-auto size-10 text-accent"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"
      />
    </svg>
  );
}
