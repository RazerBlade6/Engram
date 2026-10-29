"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, ButtonLink } from "@/components/ui/button";
import { CONTROL } from "@/components/ui/field";
import { api, apiFetch } from "@/lib/api";
import { cx } from "@/lib/cx";
import {
  boxStyle,
  emptyPages,
  pageRanges,
  sectionsOnPage,
  type ChunkBox,
  type FigureBox,
  type Inspection,
  type Page,
} from "@/lib/inspector";

type Layer = "text" | "table" | "figure";
type Selection = { type: "chunk"; box: ChunkBox } | { type: "figure"; box: FigureBox };

const LAYERS: { layer: Layer; label: string; color: string }[] = [
  { layer: "text", label: "Text", color: "var(--box-text)" },
  { layer: "table", label: "Tables", color: "var(--box-table)" },
  { layer: "figure", label: "Figures", color: "var(--box-figure)" },
];

const layerOf = (box: ChunkBox): Layer => (box.kind === "table" ? "table" : "text");

export function Inspector() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const pageNumber = Math.max(1, Number(search.get("page")) || 1);

  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<Layer>>(new Set());
  const contents = useRef<HTMLElement>(null);

  useEffect(() => {
    api<Inspection>(`/admin/materials/${id}`)
      .then(setInspection)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  const pageCount = inspection?.material.page_count ?? 0;
  const goTo = useCallback(
    (page: number) => {
      if (page < 1 || page > pageCount) return;
      router.replace(`/admin/materials/${id}?page=${page}`, { scroll: false });
    },
    [id, pageCount, router],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement) return;
      if (event.key === "ArrowLeft") goTo(pageNumber - 1);
      if (event.key === "ArrowRight") goTo(pageNumber + 1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goTo, pageNumber]);

  // Keep the innermost section on this page in view in the contents list.
  useEffect(() => {
    // Scrolls the list only: scrollIntoView would scroll the whole window too.
    const nav = contents.current;
    const current = nav?.querySelectorAll('[aria-current="true"]');
    const item = current?.[current.length - 1];
    if (nav && item) {
      const offset = item.getBoundingClientRect().top - nav.getBoundingClientRect().top;
      nav.scrollTop += offset - nav.clientHeight / 3;
    }
  }, [inspection, pageNumber]);

  if (error) return <p className="px-6 py-12 text-danger">{error}</p>;
  if (!inspection) return null;

  const { material, sections } = inspection;
  const current = sectionsOnPage(sections, pageNumber).map((s) => s.ordinal);
  const empty = pageRanges(emptyPages(pageCount, inspection.pages));

  return (
    <main className="px-6 py-8">
      <ButtonLink href="/admin" variant="secondary">
        ← All materials
      </ButtonLink>
      <h1 className="mt-5 text-2xl font-bold">{material.title}</h1>
      <p className="mt-1 text-muted">
        {material.course} · {material.status} · {pageCount} pages · {material.sections} sections · {material.figures}{" "}
        figures · {material.chunks} chunks
      </p>
      {empty.length > 0 && (
        <p className="mt-2 text-sm text-muted">
          Nothing extracted on pages{" "}
          {empty.map((r, i) => (
            <span key={r.start}>
              {i > 0 && ", "}
              <button
                onClick={() => goTo(r.start)}
                className="font-semibold text-accent underline-offset-4 hover:underline"
              >
                {r.start === r.end ? r.start : `${r.start}–${r.end}`}
              </button>
            </span>
          ))}
        </p>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)_18rem]">
        <nav
          ref={contents}
          aria-label="Table of contents"
          className="lg:sticky lg:top-4 lg:max-h-[90vh] lg:overflow-y-auto"
        >
          <h2 className="font-semibold">Contents</h2>
          {sections.length === 0 && <p className="mt-2 text-sm text-muted">No sections detected.</p>}
          <ol className="mt-2 space-y-1 text-sm">
            {sections.map((s) => (
              <li key={s.id} style={{ paddingLeft: `${(s.level - 1) * 0.875}rem` }}>
                <button
                  onClick={() => s.page_start && goTo(s.page_start)}
                  aria-current={current.includes(s.ordinal)}
                  className={cx(
                    "w-full rounded-md px-1.5 py-0.5 text-left hover:bg-foreground/5",
                    current.includes(s.ordinal) && "bg-accent-soft font-semibold text-accent",
                  )}
                >
                  {s.title}
                  <span className="ml-1 text-muted tabular-nums">
                    {s.page_start === s.page_end ? s.page_start : `${s.page_start}–${s.page_end}`}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <PageView
          key={pageNumber}
          materialId={id}
          pageNumber={pageNumber}
          pageCount={pageCount}
          preview={inspection.preview}
          goTo={goTo}
          hidden={hidden}
          setHidden={setHidden}
        />
      </div>
    </main>
  );
}

function PageView({
  materialId,
  pageNumber,
  pageCount,
  preview,
  goTo,
  hidden,
  setHidden,
}: {
  materialId: string;
  pageNumber: number;
  pageCount: number;
  preview: boolean;
  goTo: (page: number) => void;
  hidden: Set<Layer>;
  setHidden: (update: (hidden: Set<Layer>) => Set<Layer>) => void;
}) {
  const [page, setPage] = useState<Page | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [selected, setSelected] = useState<Selection | null>(null);

  useEffect(() => {
    const base = `/admin/materials/${materialId}/pages/${pageNumber}`;
    let url: string | null = null;
    let cancelled = false;
    api<Page>(base).then((p) => !cancelled && setPage(p));
    if (preview) {
      apiFetch(`${base}/image`)
        .then((r) => r.blob())
        .then((blob) => {
          if (cancelled) return;
          url = URL.createObjectURL(blob);
          setImage(url);
        });
    }
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [materialId, pageNumber, preview]);

  function toggle(layer: Layer) {
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }

  const chunks = page?.chunks.filter((c) => !hidden.has(layerOf(c))) ?? [];
  const figures = hidden.has("figure") ? [] : (page?.figures ?? []);

  return (
    <>
      <section aria-label={`Page ${pageNumber}`}>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" onClick={() => goTo(pageNumber - 1)} disabled={pageNumber <= 1}>
            ← Previous
          </Button>
          <label className="flex items-center gap-2 whitespace-nowrap">
            Page
            <input
              type="number"
              min={1}
              max={pageCount}
              defaultValue={pageNumber}
              onKeyDown={(e) => e.key === "Enter" && goTo(Number(e.currentTarget.value))}
              className={cx(CONTROL, "w-20 px-2 py-1.5 tabular-nums")}
            />
            of {pageCount}
          </label>
          <Button variant="secondary" onClick={() => goTo(pageNumber + 1)} disabled={pageNumber >= pageCount}>
            Next →
          </Button>
          <div className="ml-auto flex gap-3 text-sm">
            {LAYERS.map(({ layer, label, color }) => (
              <label key={layer} className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={!hidden.has(layer)}
                  onChange={() => toggle(layer)}
                  className="size-4 accent-accent"
                />
                <span className="inline-block size-3 rounded-sm border-2" style={{ borderColor: color }} />
                {label}
              </label>
            ))}
          </div>
        </div>

        {preview && page?.width && page.height ? (
          <div
            className="relative mt-4 rounded-card bg-paper shadow-card"
            style={{ aspectRatio: `${page.width} / ${page.height}` }}
          >
            {image && (
              // A blob URL from an authenticated fetch: next/image has nothing to optimize.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={image} alt={`Page ${pageNumber}`} className="absolute inset-0 size-full" />
            )}
            {chunks.map((c) => (
              <Box
                key={`${c.chunk_id}-${c.part}`}
                style={boxStyle(c.bbox, page.width!, page.height!)}
                color={LAYERS.find((l) => l.layer === layerOf(c))!.color}
                label={c.parts > 1 ? `#${c.ordinal} (${c.part}/${c.parts})` : `#${c.ordinal}`}
                active={selected?.type === "chunk" && selected.box.chunk_id === c.chunk_id}
                onClick={() => setSelected({ type: "chunk", box: c })}
              />
            ))}
            {figures.map((f) => (
              <Box
                key={f.id}
                style={boxStyle(f.bbox, page.width!, page.height!)}
                color="var(--box-figure)"
                label={`Figure ${f.ordinal}`}
                active={selected?.type === "figure" && selected.box.id === f.id}
                onClick={() => setSelected({ type: "figure", box: f })}
              />
            ))}
          </div>
        ) : (
          page && <p className="mt-4 text-muted">No page preview for PowerPoint files.</p>
        )}
      </section>

      <aside
        aria-label="Details"
        className="rounded-card bg-paper p-4 shadow-card lg:sticky lg:top-4 lg:max-h-[90vh] lg:overflow-y-auto"
      >
        {selected ? (
          <Details selection={selected} onClose={() => setSelected(null)} />
        ) : (
          <PageSummary page={page} onSelect={setSelected} />
        )}
      </aside>
    </>
  );
}

function Box({
  style,
  color,
  label,
  active,
  onClick,
}: {
  style: React.CSSProperties;
  color: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={`absolute border-2 ${active ? "bg-accent/15" : "hover:bg-accent/5"}`}
      style={{ ...style, borderColor: color, borderWidth: active ? 3 : 2 }}
    >
      <span
        className="absolute -top-5 left-0 rounded-sm px-1 text-xs whitespace-nowrap text-white"
        style={{ background: color }}
      >
        {label}
      </span>
    </button>
  );
}

function PageSummary({ page, onSelect }: { page: Page | null; onSelect: (selection: Selection) => void }) {
  if (!page) return null;
  // A chunk can have several boxes on one page (two columns); list it once.
  const parts = page.chunks.filter((c, i) => page.chunks.findIndex((o) => o.chunk_id === c.chunk_id) === i);
  return (
    <div>
      <h2 className="font-semibold">On this page</h2>
      <p className="mt-1 text-sm text-muted">Select a box to see exactly what was extracted.</p>
      {parts.length === 0 && page.figures.length === 0 && <p className="mt-4">Nothing extracted.</p>}
      <ul className="mt-4 space-y-3">
        {parts.map((c) => (
          <li key={c.chunk_id}>
            <button onClick={() => onSelect({ type: "chunk", box: c })} className="w-full text-left hover:underline">
              <span className="text-sm text-muted">
                #{c.ordinal} {c.kind}
              </span>
              <p className="line-clamp-2">{stripHeading(c)}</p>
            </button>
          </li>
        ))}
        {page.figures.map((f) => (
          <li key={f.id}>
            <button onClick={() => onSelect({ type: "figure", box: f })} className="w-full text-left hover:underline">
              <span className="text-sm text-muted">Figure {f.ordinal}</span>
              <p className="line-clamp-2">{f.caption ?? f.description ?? "No caption"}</p>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Details({ selection, onClose }: { selection: Selection; onClose: () => void }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-semibold">
          {selection.type === "chunk"
            ? `Chunk #${selection.box.ordinal} · ${selection.box.kind}`
            : `Figure ${selection.box.ordinal}`}
        </h2>
        <Button variant="quiet" onClick={onClose} className="-mr-2 min-h-9 px-2 py-1">
          Close
        </Button>
      </div>
      {selection.type === "chunk" ? (
        <>
          <p className="mt-2 text-sm text-muted">{selection.box.heading_path.join(" › ") || "No section"}</p>
          {selection.box.parts > 1 && <p className="mt-1 text-sm text-muted">Spans {selection.box.parts} regions.</p>}
          <pre className="mt-4 font-sans whitespace-pre-wrap">{stripHeading(selection.box)}</pre>
        </>
      ) : (
        <dl className="mt-4 space-y-4">
          <Field term="Caption">{selection.box.caption ?? <em className="text-muted">None found</em>}</Field>
          <Field term="Description">{selection.box.description ?? <em className="text-muted">Not described</em>}</Field>
          <Field term="Labels">
            {selection.box.labels.length ? selection.box.labels.join(", ") : <em className="text-muted">None</em>}
          </Field>
          {selection.box.described_by && <Field term="Described by">{selection.box.described_by}</Field>}
        </dl>
      )}
    </div>
  );
}

function Field({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-sm font-medium text-muted">{term}</dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}

/** Chunk content starts with its heading path (it is embedded that way); the panel shows it separately. */
function stripHeading(chunk: ChunkBox): string {
  const prefix = chunk.heading_path.join(" > ");
  return prefix && chunk.content.startsWith(prefix) ? chunk.content.slice(prefix.length).trimStart() : chunk.content;
}
