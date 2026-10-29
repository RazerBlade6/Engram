import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { cx } from "@/lib/cx";

import { Kbd } from "./kbd";

type Variant = "primary" | "secondary" | "quiet";
type Size = "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-2.5 rounded-control font-semibold transition-[background-color,border-color,color,box-shadow,translate] duration-150 ease-quiet disabled:pointer-events-none disabled:opacity-60";

const VARIANT: Record<Variant, string> = {
  // The one obvious action: it sits slightly raised, and presses down when clicked.
  primary: "bg-accent text-on-accent shadow-press hover:bg-accent-strong active:translate-y-0.5 active:shadow-none",
  secondary: "border border-border-strong bg-surface text-foreground hover:border-accent hover:text-accent",
  quiet: "text-muted hover:bg-foreground/5 hover:text-foreground",
};

const SIZE: Record<Size, string> = {
  md: "min-h-11 px-4 py-2",
  lg: "min-h-13 px-6 py-3 text-lg",
};

export function buttonClass({ variant = "primary", size = "md" }: { variant?: Variant; size?: Size } = {}): string {
  return cx(BASE, VARIANT[variant], SIZE[size]);
}

type Style = {
  variant?: Variant;
  size?: Size;
  /** A keyboard shortcut shown inside the button. */ hint?: string;
};

function Content({ children, hint, variant }: { children: ReactNode; hint?: string; variant: Variant }) {
  return (
    <>
      {children}
      {hint && <Kbd tone={variant === "primary" ? "inverse" : "default"}>{hint}</Kbd>}
    </>
  );
}

export function Button({
  variant = "primary",
  size = "md",
  hint,
  className,
  children,
  type = "button",
  ...props
}: Style & ComponentProps<"button">) {
  return (
    <button type={type} className={cx(buttonClass({ variant, size }), className)} {...props}>
      <Content hint={hint} variant={variant}>
        {children}
      </Content>
    </button>
  );
}

/** A link that looks like a button, for actions that go to another page. */
export function ButtonLink({
  variant = "primary",
  size = "md",
  hint,
  className,
  children,
  ...props
}: Style & ComponentProps<typeof Link>) {
  return (
    <Link className={cx(buttonClass({ variant, size }), className)} {...props}>
      <Content hint={hint} variant={variant}>
        {children}
      </Content>
    </Link>
  );
}
