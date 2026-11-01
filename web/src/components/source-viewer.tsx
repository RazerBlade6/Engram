"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Highlight } from "@/components/ui/source-box";
import { api } from "@/lib/api";
import { findQuote } from "@/lib/chat";
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
 * The passage a citation points to, as text, with the quoted words marked and scrolled into
 * view (D65). A passage from a PDF also links to its page in the file, for anyone who wants
 * the page itself; PowerPoint uploads have no page to open.
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
  const [failed, setFailed] = useState(false);
  const [pdfFailed, setPdfFailed] = useState(false);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    api<SourcePage>(`/chunks/${chunkId}/source`)
      .then((s) => {
        if (cancelled) return;
        setSource(s);
        track({ name: "source_opened", origin, page_image: false });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [chunkId, origin]);

  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const where =
    source && [source.heading_path.at(-1), source.page !== null && `page ${source.page}`].filter(Boolean).join(" · ");
  // Only PDFs are drawn as pages, so a page size means there's a PDF page to open.
  const pdfPage = source && source.page !== null && source.width !== null ? source.page : null;

  async function openPdf(materialId: string, page: number) {
    setPdfFailed(false);
    // Opened now, while the click still counts, so a pop-up blocker doesn't stop it.
    const tab = window.open("", "_blank");
    try {
      const { url } = await api<{ url: string }>(`/materials/${materialId}/file`);
      const atPage = new URL(url);
      atPage.hash = `page=${page}`;
      track({ name: "pdf_opened", origin: "chat" });
      if (tab) {
        tab.opener = null;
        tab.location.href = atPage.href;
      } else {
        window.location.assign(atPage);
      }
    } catch {
      tab?.close();
      setPdfFailed(true);
    }
  }

  return (
    <div className="fade-in fixed inset-0 z-40 flex justify-center bg-scrim/40 p-4 sm:p-8" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-title"
        className="rise-in flex max-h-full w-full max-w-2xl flex-col self-center overflow-hidden rounded-control bg-paper shadow-lifted"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div className="min-w-0">
            <p id="source-title" className="font-semibold">
              {source?.book ?? "Source"}
            </p>
            {where && <p className="text-sm text-muted">{where}</p>}
          </div>
          <Button ref={close} variant="secondary" hint="Esc" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="overflow-y-auto">
          {failed && (
            <div className="p-6">
              <Notice tone="error">This passage couldn&apos;t be opened. Close it and try again.</Notice>
            </div>
          )}
          {!source && !failed && (
            <div className="flex flex-col gap-3 p-6 sm:px-8">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
          {source && <Passage passage={source.passage} quote={quote} />}
        </div>
        {source && pdfPage !== null && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border px-6 py-3 text-sm">
            <button
              type="button"
              onClick={() => openPdf(source.material_id, pdfPage)}
              className="font-semibold text-accent underline-offset-4 hover:underline"
            >
              Open page {pdfPage} in the PDF
            </button>
            {pdfFailed && <span className="text-muted">Couldn&apos;t open the PDF. Please try again.</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function Passage({ passage, quote }: { passage: string; quote: string | null }) {
  const marked = useRef<HTMLElement>(null);
  const span = quote ? findQuote(passage, quote) : null;

  useEffect(() => {
    marked.current?.scrollIntoView({ block: "center" });
  }, [passage, quote]);

  const text = "p-6 font-read text-lg leading-relaxed whitespace-pre-line sm:px-8";
  if (!span) return <p className={text}>{passage}</p>;
  const [start, end] = span;
  return (
    <p className={text}>
      {passage.slice(0, start)}
      <Highlight ref={marked}>{passage.slice(start, end)}</Highlight>
      {passage.slice(end)}
    </p>
  );
}
