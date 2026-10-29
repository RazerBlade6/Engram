import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

import { cx } from "@/lib/cx";

export const CONTROL =
  "w-full rounded-control border border-border-strong bg-surface px-4 py-3 outline-none transition-[border-color,box-shadow] duration-150 ease-quiet placeholder:text-muted/70 focus:border-accent focus:ring-3 focus:ring-accent/25";

function Label({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="block font-semibold">{label}</span>
      {hint && <span className="block text-sm text-muted">{hint}</span>}
      <span className="mt-2 block">{children}</span>
    </label>
  );
}

export function Field({
  label,
  hint,
  className,
  ...input
}: { label: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Label label={label} hint={hint}>
      <input {...input} className={cx(CONTROL, className)} />
    </Label>
  );
}

export function Select({
  label,
  hint,
  className,
  children,
  ...select
}: { label: string; hint?: string } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <Label label={label} hint={hint}>
      <select {...select} className={cx(CONTROL, "appearance-auto", className)}>
        {children}
      </select>
    </Label>
  );
}
