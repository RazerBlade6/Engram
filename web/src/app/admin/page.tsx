"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { AdminOnly } from "@/components/admin-only";
import { Toast, type ToastMessage } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { CONTROL, Field, Select } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { RowList } from "@/components/ui/row-list";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api, apiFetch } from "@/lib/api";
import type { CourseSummary } from "@/lib/courses";
import { cx } from "@/lib/cx";
import type { MaterialSummary } from "@/lib/inspector";
import { useProfile } from "@/lib/profile";
import { ORDER_LABEL, type ReviewOrder } from "@/lib/review";

type Person = {
  id: string;
  display_name: string | null;
  role: "student" | "admin";
  review_order: ReviewOrder;
  /** When they agreed to usage logging, as recorded here; null if they haven't. */
  usage_consent_at: string | null;
  events_this_week: number;
};

type Show = (text: string) => void;

const nameOf = (p: Person) => p.display_name ?? "No name";

export default function AdminPage() {
  return (
    <AdminOnly>
      <Admin />
    </AdminOnly>
  );
}

function Admin() {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastId = useRef(0);

  const loadPeople = useCallback(() => api<Person[]>("/admin/people").then(setPeople), []);
  useEffect(() => {
    loadPeople();
  }, [loadPeople]);

  const show = useCallback((text: string) => {
    toastId.current += 1;
    setToast({ id: toastId.current, text });
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-3xl font-bold">Admin</h1>
      <Materials show={show} />
      <People people={people} setPeople={setPeople} reload={loadPeople} show={show} />
      <Courses people={people} show={show} />
      <Toast key={toast?.id} toast={toast} onDone={() => setToast(null)} />
    </main>
  );
}

function Section({
  id,
  title,
  action,
  children,
}: {
  id: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mt-12">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={id} className="text-2xl font-semibold">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** A table on a sheet of paper; wide tables scroll inside it rather than the page. */
function Sheet({ children }: { children: ReactNode }) {
  return <div className="mt-5 overflow-x-auto rounded-card bg-paper shadow-card">{children}</div>;
}

const TH = "px-4 py-3 text-sm font-semibold text-muted";
const TD = "px-4 py-3";

/** Newest first; the rest are a click away. */
const MATERIALS_SHOWN = 5;

function Materials({ show }: { show: Show }) {
  const [materials, setMaterials] = useState<MaterialSummary[] | null>(null);
  const [all, setAll] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    api<MaterialSummary[]>("/admin/materials").then(setMaterials);
  }, []);

  async function deleteMaterial(material: MaterialSummary) {
    setConfirming(null);
    try {
      await apiFetch(`/materials/${material.id}`, { method: "DELETE" });
      setMaterials((ms) => ms && ms.filter((m) => m.id !== material.id));
      show(`${material.title} deleted.`);
    } catch {
      show(`Couldn't delete ${material.title}. Please try again.`);
    }
  }

  const shown = all ? materials : materials?.slice(0, MATERIALS_SHOWN);
  return (
    <Section id="materials-heading" title="Ingested materials">
      <p className="mt-1 text-muted">
        Open a material to check what was extracted from each page before students use it.
      </p>
      {!materials ? (
        <Skeleton className="mt-5 h-64" />
      ) : materials.length === 0 ? (
        <p className="mt-5">Nothing ingested yet. Add a textbook from a course&apos;s page.</p>
      ) : (
        <>
          <Sheet>
            <table className="w-full min-w-[56rem] border-collapse text-left">
              <thead className="border-b-[1.5px] border-card-rule">
                <tr>
                  <th className={TH}>Material</th>
                  <th className={TH}>Uploaded by</th>
                  <th className={TH}>Belongs to</th>
                  <th className={TH}>Status</th>
                  <th className={cx(TH, "text-right")}>Pages</th>
                  <th className={cx(TH, "text-right")}>Sections</th>
                  <th className={cx(TH, "text-right")}>Figures</th>
                  <th className={cx(TH, "text-right")}>Chunks</th>
                  <th className={TH}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/70">
                {shown!.map((m) => (
                  <tr key={m.id} className="align-top">
                    <td className={TD}>
                      <Link
                        href={`/admin/materials/${m.id}`}
                        className="font-semibold text-accent underline-offset-4 hover:underline"
                      >
                        {m.title}
                      </Link>
                      <div className="text-sm text-muted">
                        {m.course} · {m.kind}
                      </div>
                    </td>
                    <td className={TD}>{m.uploaded_by ?? <span className="text-muted">—</span>}</td>
                    <td className={TD}>{m.owner}</td>
                    <td className={TD}>
                      <Status status={m.status} />
                      {m.error && <div className="mt-1 max-w-xs text-sm text-danger">{m.error}</div>}
                    </td>
                    <td className={cx(TD, "text-right tabular-nums")}>{m.page_count ?? "–"}</td>
                    <td className={cx(TD, "text-right tabular-nums")}>{m.sections}</td>
                    <td className={cx(TD, "text-right tabular-nums")}>{m.figures}</td>
                    <td className={cx(TD, "text-right tabular-nums")}>{m.chunks}</td>
                    <td className={cx(TD, "text-right")}>
                      {confirming === m.id ? (
                        <div className="rise-in flex flex-col items-end gap-2 text-sm">
                          <span className="w-44">
                            {m.kind === "textbook" ? "Delete it with its chapters and cards?" : "Delete these slides?"}
                          </span>
                          <div className="flex gap-2">
                            <Button variant="danger" onClick={() => deleteMaterial(m)} className="min-h-9 px-3 py-1">
                              Delete
                            </Button>
                            <Button variant="quiet" onClick={() => setConfirming(null)} className="min-h-9 px-3 py-1">
                              Keep
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <Button variant="danger" onClick={() => setConfirming(m.id)} aria-label={`Delete ${m.title}`}>
                          Delete
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Sheet>
          {materials.length > MATERIALS_SHOWN && (
            <Button variant="secondary" onClick={() => setAll((a) => !a)} className="mt-3">
              {all ? "Show the newest 5" : `See all ${materials.length} materials`}
            </Button>
          )}
        </>
      )}
    </Section>
  );
}

function Status({ status }: { status: MaterialSummary["status"] }) {
  const tone =
    status === "ready"
      ? { color: "var(--rate-3)", background: "var(--rate-3-soft)" }
      : status === "failed"
        ? { color: "var(--danger)", background: "var(--danger-soft)" }
        : { color: "var(--muted)", background: "var(--accent-soft)" };
  return (
    <span className="rounded-full px-2.5 py-0.5 text-sm font-semibold" style={tone}>
      {status}
    </span>
  );
}

const consentDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" });

/**
 * Per-person switches no student sees: the review-order experiment, and whether they agreed to
 * usage logging.
 */
function People({
  people,
  setPeople,
  reload,
  show,
}: {
  people: Person[] | null;
  setPeople: (change: (people: Person[] | null) => Person[] | null) => void;
  reload: () => void;
  show: Show;
}) {
  const me = useProfile();
  const [inviting, setInviting] = useState(false);

  /** Shows the change at once and puts it back if it can't be saved. */
  async function change(person: Person, changed: Partial<Person>, save: () => Promise<unknown>) {
    const set = (values: Partial<Person>) =>
      setPeople((ps) => ps && ps.map((p) => (p.id === person.id ? { ...p, ...values } : p)));
    set(changed);
    try {
      await save();
    } catch {
      set(person);
      show("That change couldn't be saved. Please try again.");
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

  // Not built yet: wire this to the API when removing people exists.
  function removePerson(person: Person) {
    show(`Removing ${nameOf(person)} isn't built yet.`);
  }

  return (
    <Section
      id="people-heading"
      title="People"
      action={<Button onClick={() => setInviting(true)}>Invite people</Button>}
    >
      <p className="mt-1 max-w-prose text-muted">
        <b className="text-foreground">Review order</b> is how each person&apos;s reviews arrange flashcards and
        multiple choice; it takes effect the next time they start a review.{" "}
        <b className="text-foreground">Usage logging</b> records what they do (ratings, flags, pages, timings, never
        their words). Turn it on only after they&apos;ve agreed. Turning it off stops logging.
      </p>
      {!people ? (
        <Skeleton className="mt-5 h-48" />
      ) : (
        <Sheet>
          <table className="w-full min-w-[48rem] border-collapse text-left">
            <thead className="border-b-[1.5px] border-card-rule">
              <tr>
                <th className={TH}>Person</th>
                <th className={TH}>Review order</th>
                <th className={TH}>Usage logging</th>
                <th className={TH}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/70">
              {people.map((p) => {
                const name = p.display_name ?? "this person";
                return (
                  <tr key={p.id}>
                    <td className={TD}>
                      <span className="font-semibold">
                        {p.display_name ?? <span className="font-normal text-muted">No name</span>}
                      </span>
                      {p.role === "admin" && (
                        <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">
                          admin
                        </span>
                      )}
                    </td>
                    <td className={TD}>
                      <select
                        value={p.review_order}
                        onChange={(e) => chooseOrder(p, e.target.value as ReviewOrder)}
                        aria-label={`Review order for ${name}`}
                        className={cx(CONTROL, "w-auto py-2")}
                      >
                        {(Object.keys(ORDER_LABEL) as ReviewOrder[]).map((o) => (
                          <option key={o} value={o}>
                            {ORDER_LABEL[o]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className={TD}>
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
                    <td className={cx(TD, "text-right")}>
                      {/* You can't remove yourself from here. */}
                      {p.id !== me?.id && (
                        <Button variant="danger" onClick={() => removePerson(p)} aria-label={`Remove ${name}`}>
                          Remove
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Sheet>
      )}
      {inviting && (
        <Drawer title="Invite people" onClose={() => setInviting(false)}>
          <InviteForm onInvited={reload} />
        </Drawer>
      )}
    </Section>
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
    <form onSubmit={invite} className="flex flex-col gap-5">
      <p className="text-muted">They get an email with a link to choose a password.</p>
      <Field label="Name" hint="Optional" value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" />
      <Field
        label="Email"
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        autoComplete="off"
      />
      <Button type="submit" size="lg" disabled={sending || !email.trim()}>
        {sending ? "Sending…" : "Send invite"}
      </Button>
      {result && <Notice tone={result.ok ? "success" : "error"}>{result.text}</Notice>}
    </form>
  );
}

/** One person's courses: open, create or delete them. */
function Courses({ people, show }: { people: Person[] | null; show: Show }) {
  const [courses, setCourses] = useState<CourseSummary[] | null>(null);
  const [owner, setOwner] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api<CourseSummary[]>("/courses").then(setCourses);
  }, []);

  // A student first, once people have loaded.
  const chosen = owner || people?.find((p) => p.role === "student")?.id || people?.[0]?.id || "";
  const person = people?.find((p) => p.id === chosen);
  const listed = courses?.filter((c) => c.owner_id === chosen);

  // Not built yet: wire this to the API when deleting courses exists.
  function deleteCourse(course: CourseSummary) {
    show(`Deleting ${course.title} isn't built yet.`);
  }

  return (
    <Section id="courses-heading" title="Courses">
      {!people || !courses ? (
        <Skeleton className="mt-5 h-40" />
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <div className="w-72">
              <Select
                label="Whose courses"
                value={chosen}
                onChange={(e) => {
                  setOwner(e.target.value);
                  setCreating(false);
                }}
              >
                {people.map((p) => (
                  <option key={p.id} value={p.id}>
                    {nameOf(p)}
                    {p.role === "admin" ? " (admin)" : ""}
                  </option>
                ))}
              </Select>
            </div>
            <Button onClick={() => setCreating(true)} disabled={creating} className="mb-0.5">
              Create course
            </Button>
          </div>
          {creating && person && <CourseForm owner={person} onCancel={() => setCreating(false)} />}
          {listed!.length === 0 ? (
            <p className="mt-4 text-muted">{person ? `${nameOf(person)} has no courses yet.` : "No courses yet."}</p>
          ) : (
            <RowList className="mt-4">
              {listed!.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                  <Link
                    href={`/courses/${c.id}`}
                    className="min-w-0 flex-1 font-semibold text-accent underline-offset-4 hover:underline"
                  >
                    {c.title}
                  </Link>
                  <span className="text-sm text-muted tabular-nums">
                    {c.chapters ? `${c.covered} of ${c.chapters} chapters covered` : "No chapters yet"}
                  </span>
                  <Button variant="danger" onClick={() => deleteCourse(c)} aria-label={`Delete ${c.title}`}>
                    Delete course
                  </Button>
                </li>
              ))}
            </RowList>
          )}
        </>
      )}
    </Section>
  );
}

/** A course for someone else, ready for its textbook: it opens once made. */
function CourseForm({ owner, onCancel }: { owner: Person; onCancel: () => void }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      const course = await api<{ id: string }>("/courses", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), owner_id: owner.id }),
      });
      router.push(`/courses/${course.id}`);
    } catch {
      setProblem("The course couldn't be created. Please try again.");
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={create}
      className="rise-in mt-4 max-w-xl rounded-control border border-border bg-surface p-5 shadow-card"
    >
      <Field
        label={`New course for ${nameOf(owner)}`}
        autoFocus
        required
        maxLength={200}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        autoComplete="off"
        placeholder="e.g. Introduction to Psychology"
      />
      <div className="mt-4 flex items-center gap-3">
        <Button type="submit" disabled={busy || !title.trim()}>
          {busy ? "Creating…" : "Create course"}
        </Button>
        <Button variant="quiet" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {problem && (
        <div className="mt-4">
          <Notice tone="error">{problem}</Notice>
        </div>
      )}
    </form>
  );
}
