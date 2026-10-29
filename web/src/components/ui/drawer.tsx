"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "./button";

/** A panel that slides in from the right, over the page: for a form beside a list. */
export function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fade-in fixed inset-0 z-40 bg-foreground/30" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onClick={(e) => e.stopPropagation()}
        className="slide-in-right absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-paper shadow-lifted"
      >
        <div className="flex items-center justify-between gap-4 border-b border-border px-6 py-4">
          <h2 id="drawer-title" className="text-xl font-semibold">
            {title}
          </h2>
          <Button ref={close} variant="secondary" hint="Esc" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="overflow-y-auto p-6">{children}</div>
      </div>
    </div>
  );
}
