import type { InputHTMLAttributes, ReactNode } from "react";

export function Field({ label, ...input }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="block font-medium">{label}</span>
      <input
        {...input}
        className="mt-2 w-full rounded-lg border border-border bg-white px-4 py-3 outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
      />
    </label>
  );
}

export function PrimaryButton({ children, busy }: { children: ReactNode; busy?: boolean }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="w-full rounded-lg bg-accent px-4 py-3 font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
    >
      {children}
    </button>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-lg bg-danger-soft px-4 py-3 text-danger">
      {message}
    </p>
  );
}

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <p className="text-lg font-semibold text-accent">Engram</p>
      <h1 className="mt-2 text-3xl font-semibold">{title}</h1>
      <div className="mt-8">{children}</div>
    </main>
  );
}
