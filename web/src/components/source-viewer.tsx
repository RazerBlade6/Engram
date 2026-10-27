"use client";

import { useEffect, useRef, useState } from "react";

import { apiFetch, api } from "@/lib/api";
import { findQuote } from "@/lib/chat";
import { boxStyle } from "@/lib/inspector";
import { track } from "@/lib/usage";

type SourcePage = {
  chunk_id: string;
  material_id: string;
  book: string;
  heading_path: string[];
  passage: string;
  page: number | null;
  width: number | null;
  height: number | null;
  boxes: { page: number; bbox: [number, number, number, number] }[];
};

/**
 * The page a citation points to, with the cited passage boxed and scrolled into view. Materials
 * without page images (PowerPoint uploads) show the passage text with the quoted words marked.
 */
export function SourceViewer({
  chunkId,
  quote,
  origin,
  onClose,
}: {
  chunkId: string;
  quote: string | null;
  origin: "chat" | "review";
  onClose: () => void;
}) {
  const [source, setSource] = useState<SourcePage | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const close = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    api<SourcePage>(`/chunks/${chunkId}/source`)
      .then(async (s) => {
        if (cancelled) return;
        setSource(s);
        const pageImage = s.page !== null && s.width !== null;
        track({ name: "source_opened", origin, page_image: pageImage });
        if (!pageImage) return;
        const blob = await apiFetch(`/materials/${s.material_id}/pages/${s.page}/image`).then((r) => r.blob());
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setImage(url);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [chunkId, origin]);

  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const where = source && [source.heading_path.at(-1), source.page !== null && `page ${source.page}`].filter(Boolean).join(" · ");
  const boxes = source?.boxes.filter((b) => b.page === source.page) ?? [];

  return (
    <div className="fixed inset-0 z-40 flex justify-center bg-black/40 p-4 sm:p-8" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-title"
        className="flex max-h-full w-full max-w-3xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 border-b border-border px-6 py-4">
          <div>
            <p id="source-title" className="font-semibold">
              {source?.book ?? "Source"}
            </p>
            {where && <p className="text-sm text-muted">{where}</p>}
          </div>
          <button ref={close} type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-muted underline hover:text-foreground">
            Close
          </button>
        </div>
        <div className="overflow-y-auto">
          {failed && <p className="p-6">This page couldn&apos;t be opened. Please try again.</p>}
          {source && image && source.width && source.height ? (
            <div className="relative" style={{ aspectRatio: `${source.width} / ${source.height}` }}>
              {/* A blob URL from an authenticated fetch: next/image has nothing to optimize. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={image}
                alt={`Page ${source.page} of ${source.book}`}
                className="absolute inset-0 size-full"
                onLoad={() => box.current?.scrollIntoView({ block: "center" })}
              />
              {boxes.map((b, i) => (
                <div
                  key={i}
                  ref={i === 0 ? box : undefined}
                  className="absolute rounded bg-accent/15 ring-2 ring-accent"
                  style={boxStyle(b.bbox, source.width!, source.height!)}
                />
              ))}
            </div>
          ) : (
            source && <Passage passage={source.passage} quote={quote} />
          )}
        </div>
      </div>
    </div>
  );
}

function Passage({ passage, quote }: { passage: string; quote: string | null }) {
  const span = quote ? findQuote(passage, quote) : null;
  if (!span) return <p className="p-6 text-lg leading-relaxed whitespace-pre-line">{passage}</p>;
  const [start, end] = span;
  return (
    <p className="p-6 text-lg leading-relaxed whitespace-pre-line">
      {passage.slice(0, start)}
      <mark className="rounded bg-accent/15 px-0.5 text-foreground">{passage.slice(start, end)}</mark>
      {passage.slice(end)}
    </p>
  );
}
