"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AdminOnly } from "@/components/admin-only";
import { Toast, type ToastMessage } from "@/components/toast";
import { api, apiFetch } from "@/lib/api";
import type { MaterialSummary } from "@/lib/inspector";
import { ORDER_LABEL, type ReviewOrder } from "@/lib/review";

export default function AdminPage() {
  return (
    <AdminOnly>
      <main className="mx-auto max-w-5xl px-6 py-12">
        <Link href="/" className="text-muted underline hover:text-foreground">
          Home
        </Link>
        <Materials />
        <People />
      </main>
    </AdminOnly>
  );
}

function Materials() {
  const [materials, setMaterials] = useState<MaterialSummary[] | null>(null);

  useEffect(() => {
    api<MaterialSummary[]>("/admin/materials").then(setMaterials);
  }, []);

  return (
    <section>
      <h1 className="mt-4 text-3xl font-semibold">Ingested materials</h1>
      <p className="mt-2 text-muted">
        Open a material to check what was extracted from each page before students use it.
      </p>
      {materials && materials.length === 0 && (
        <p className="mt-8">
          Nothing ingested yet. Upload with <code>engram-admin ingest FILE --course ID</code>.
        </p>
      )}
      {materials && materials.length > 0 && (
        <table className="mt-8 w-full border-collapse text-left">
          <thead className="border-b border-border text-muted">
            <tr>
              <th className="py-2 pr-4 font-medium">Material</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 pr-4 text-right font-medium">Pages</th>
              <th className="py-2 pr-4 text-right font-medium">Sections</th>
              <th className="py-2 pr-4 text-right font-medium">Figures</th>
              <th className="py-2 text-right font-medium">Chunks</th>
            </tr>
          </thead>
          <tbody>
            {materials.map((m) => (
              <tr key={m.id} className="border-b border-border align-top">
                <td className="py-3 pr-4">
                  <Link href={`/admin/materials/${m.id}`} className="font-medium text-accent underline">
                    {m.title}
                  </Link>
                  <div className="text-muted">
                    {m.course} · {m.kind}
                  </div>
                </td>
                <td className="py-3 pr-4">
                  <Status status={m.status} />
                  {m.error && <div className="mt-1 max-w-xs text-sm text-danger">{m.error}</div>}
                </td>
                <td className="py-3 pr-4 text-right tabular-nums">{m.page_count ?? "–"}</td>
                <td className="py-3 pr-4 text-right tabular-nums">{m.sections}</td>
                <td className="py-3 pr-4 text-right tabular-nums">{m.figures}</td>
                <td className="py-3 text-right tabular-nums">{m.chunks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

type Person = { id: string; display_name: string | null; role: "student" | "admin"; review_order: ReviewOrder };

/** The review-order experiment: which ordering each person is trying (never a student setting). */
function People() {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastId = useRef(0);

  useEffect(() => {
    api<Person[]>("/admin/people").then(setPeople);
  }, []);

  async function choose(person: Person, order: ReviewOrder) {
    const previous = person.review_order;
    const set = (o: ReviewOrder) =>
      setPeople((ps) => ps && ps.map((p) => (p.id === person.id ? { ...p, review_order: o } : p)));
    set(order);
    try {
      await apiFetch(`/admin/people/${person.id}/review-order`, {
        method: "PUT",
        body: JSON.stringify({ order }),
      });
    } catch {
      set(previous);
      toastId.current += 1;
      setToast({ id: toastId.current, text: "That change couldn't be saved. Please try again." });
    }
  }

  if (!people) return null;
  return (
    <section className="mt-14" aria-labelledby="people-heading">
      <h2 id="people-heading" className="text-2xl font-semibold">
        Review order
      </h2>
      <p className="mt-2 text-muted">
        How each person&apos;s reviews arrange flashcards and multiple choice. It takes effect the next time they
        start a review.
      </p>
      <table className="mt-6 w-full border-collapse text-left">
        <thead className="border-b border-border text-muted">
          <tr>
            <th className="py-2 pr-4 font-medium">Person</th>
            <th className="py-2 font-medium">Order</th>
          </tr>
        </thead>
        <tbody>
          {people.map((p) => (
            <tr key={p.id} className="border-b border-border">
              <td className="py-3 pr-4">
                {p.display_name ?? <span className="text-muted">No name</span>}
                {p.role === "admin" && <span className="ml-2 text-muted">admin</span>}
              </td>
              <td className="py-3">
                <select
                  value={p.review_order}
                  onChange={(e) => choose(p, e.target.value as ReviewOrder)}
                  aria-label={`Review order for ${p.display_name ?? "this person"}`}
                  className="rounded-lg border border-border bg-white px-3 py-2"
                >
                  {(Object.keys(ORDER_LABEL) as ReviewOrder[]).map((o) => (
                    <option key={o} value={o}>
                      {ORDER_LABEL[o]}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Toast key={toast?.id} toast={toast} onDone={() => setToast(null)} />
    </section>
  );
}

function Status({ status }: { status: MaterialSummary["status"] }) {
  const tone =
    status === "ready" ? "text-success" : status === "failed" ? "text-danger" : "text-muted";
  return <span className={`font-medium ${tone}`}>{status}</span>;
}
