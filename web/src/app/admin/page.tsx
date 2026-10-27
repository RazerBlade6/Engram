"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { AdminOnly } from "@/components/admin-only";
import { Toast, type ToastMessage } from "@/components/toast";
import { ApiError, api, apiFetch } from "@/lib/api";
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

type Person = {
  id: string;
  display_name: string | null;
  role: "student" | "admin";
  review_order: ReviewOrder;
  /** When they agreed to usage logging, as recorded here; null if they haven't. */
  usage_consent_at: string | null;
  events_this_week: number;
};

const consentDate = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "long", year: "numeric" });

/**
 * Per-person switches no student sees: the review-order experiment, and whether they agreed to
 * usage logging.
 */
function People() {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastId = useRef(0);

  const load = () => api<Person[]>("/admin/people").then(setPeople);
  useEffect(() => {
    load();
  }, []);

  /** Shows the change at once and puts it back if it can't be saved. */
  async function change(person: Person, changed: Partial<Person>, save: () => Promise<unknown>) {
    const set = (values: Partial<Person>) =>
      setPeople((ps) => ps && ps.map((p) => (p.id === person.id ? { ...p, ...values } : p)));
    set(changed);
    try {
      await save();
    } catch {
      set(person);
      toastId.current += 1;
      setToast({ id: toastId.current, text: "That change couldn't be saved. Please try again." });
    }
  }

  const chooseOrder = (person: Person, order: ReviewOrder) =>
    change(person, { review_order: order }, () =>
      apiFetch(`/admin/people/${person.id}/review-order`, { method: "PUT", body: JSON.stringify({ order }) }),
    );

  const recordConsent = (person: Person, consented: boolean) =>
    change(person, { usage_consent_at: consented ? (person.usage_consent_at ?? new Date().toISOString()) : null }, () =>
      apiFetch(`/admin/people/${person.id}/usage-consent`, { method: "PUT", body: JSON.stringify({ consented }) }),
    );

  if (!people) return null;
  return (
    <section className="mt-14" aria-labelledby="people-heading">
      <h2 id="people-heading" className="text-2xl font-semibold">
        People
      </h2>
      <p className="mt-2 text-muted">
        <b className="text-foreground">Review order</b> is how each person&apos;s reviews arrange flashcards and
        multiple choice; it takes effect the next time they start a review.{" "}
        <b className="text-foreground">Usage logging</b> records what they do (ratings, flags, pages, timings, never
        their words). Turn it on only after they&apos;ve agreed. Turning it off stops logging.
      </p>
      <InviteForm onInvited={load} />
      <table className="mt-6 w-full border-collapse text-left">
        <thead className="border-b border-border text-muted">
          <tr>
            <th className="py-2 pr-4 font-medium">Person</th>
            <th className="py-2 pr-4 font-medium">Review order</th>
            <th className="py-2 font-medium">Usage logging</th>
          </tr>
        </thead>
        <tbody>
          {people.map((p) => {
            const name = p.display_name ?? "this person";
            return (
              <tr key={p.id} className="border-b border-border">
                <td className="py-3 pr-4">
                  {p.display_name ?? <span className="text-muted">No name</span>}
                  {p.role === "admin" && <span className="ml-2 text-muted">admin</span>}
                </td>
                <td className="py-3 pr-4">
                  <select
                    value={p.review_order}
                    onChange={(e) => chooseOrder(p, e.target.value as ReviewOrder)}
                    aria-label={`Review order for ${name}`}
                    className="rounded-lg border border-border bg-white px-3 py-2"
                  >
                    {(Object.keys(ORDER_LABEL) as ReviewOrder[]).map((o) => (
                      <option key={o} value={o}>
                        {ORDER_LABEL[o]}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="py-3">
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={p.usage_consent_at !== null}
                      onChange={(e) => recordConsent(p, e.target.checked)}
                      aria-label={`${name} agreed to usage logging`}
                      className="size-5 accent-accent"
                    />
                    <span className="text-muted">
                      {p.usage_consent_at
                        ? `Agreed ${consentDate.format(new Date(p.usage_consent_at))} · ${p.events_this_week} ${
                            p.events_this_week === 1 ? "event" : "events"
                          } this week`
                        : "Not agreed"}
                    </span>
                  </label>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Toast key={toast?.id} toast={toast} onDone={() => setToast(null)} />
    </section>
  );
}

/** Accounts are invite-only: the email's link opens the page where they choose a password. */
function InviteForm({ onInvited }: { onInvited: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function invite(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setResult(null);
    try {
      await apiFetch("/admin/invites", {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), display_name: name.trim() || null }),
      });
      setResult({ ok: true, text: `Invite sent to ${email.trim()}.` });
      setName("");
      setEmail("");
      onInvited();
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 0;
      const text =
        status === 409
          ? "That email already has an account."
          : status === 422
            ? "That doesn't look like an email address. Check it and try again."
            : "The invite couldn't be sent. Please try again.";
      setResult({ ok: false, text });
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={invite} className="mt-6 flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1">
        <span className="font-medium">Name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoComplete="off"
          className="rounded-lg border border-border bg-white px-3 py-2"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="font-medium">Email</span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="off"
          className="w-72 rounded-lg border border-border bg-white px-3 py-2"
        />
      </label>
      <button
        type="submit"
        disabled={sending}
        className="rounded-lg bg-accent px-6 py-2 font-medium text-white hover:bg-accent-strong disabled:opacity-50"
      >
        {sending ? "Sending…" : "Send invite"}
      </button>
      {result && (
        <p role="status" className={`w-full ${result.ok ? "text-muted" : "text-danger"}`}>
          {result.text}
        </p>
      )}
    </form>
  );
}

function Status({ status }: { status: MaterialSummary["status"] }) {
  const tone =
    status === "ready" ? "text-success" : status === "failed" ? "text-danger" : "text-muted";
  return <span className={`font-medium ${tone}`}>{status}</span>;
}
