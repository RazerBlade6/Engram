"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AdminOnly } from "@/components/admin-only";
import { api } from "@/lib/api";
import type { MaterialSummary } from "@/lib/inspector";

export default function AdminPage() {
  return (
    <AdminOnly>
      <Materials />
    </AdminOnly>
  );
}

function Materials() {
  const [materials, setMaterials] = useState<MaterialSummary[] | null>(null);

  useEffect(() => {
    api<MaterialSummary[]>("/admin/materials").then(setMaterials);
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <Link href="/" className="text-muted underline hover:text-foreground">
        Home
      </Link>
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
    </main>
  );
}

function Status({ status }: { status: MaterialSummary["status"] }) {
  const tone =
    status === "ready" ? "text-success" : status === "failed" ? "text-danger" : "text-muted";
  return <span className={`font-medium ${tone}`}>{status}</span>;
}
