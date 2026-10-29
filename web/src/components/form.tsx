import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { IndexCard } from "@/components/ui/index-card";
import { Notice } from "@/components/ui/notice";

export { Field } from "@/components/ui/field";

export function PrimaryButton({ children, busy }: { children: ReactNode; busy?: boolean }) {
  return (
    <Button type="submit" size="lg" disabled={busy} className="w-full">
      {children}
    </Button>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return <Notice tone="error">{message}</Notice>;
}

/** Signed-out pages: the name, one line on what it is, and the form on a card on the desk. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <p className="text-2xl font-bold text-accent">Engram</p>
      <p className="mt-1 text-muted">Your course materials, turned into practice.</p>
      <div className="rise-in mt-8">
        {/* The title is written by hand above the red line; the heading is for screen readers. */}
        <IndexCard label={<span aria-hidden>{title}</span>}>
          <h1 className="sr-only">{title}</h1>
          {children}
        </IndexCard>
      </div>
    </main>
  );
}
