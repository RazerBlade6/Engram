import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
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

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-16">
      <p className="text-lg font-bold text-accent">Engram</p>
      <h1 className="mt-2 text-3xl font-bold">{title}</h1>
      <div className="mt-8">{children}</div>
    </main>
  );
}
