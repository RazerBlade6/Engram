"use client";

import { useEffect } from "react";

export type ToastMessage = { id: number; text: string; undo?: () => void };

const VISIBLE_MS = 8000;

/** A short confirmation at the bottom of the screen, optionally with Undo. */
export function Toast({ toast, onDone }: { toast: ToastMessage | null; onDone: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onDone, VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [toast, onDone]);

  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 bottom-6 flex justify-center px-4">
      {toast && (
        <div className="flex items-center gap-6 rounded-lg bg-foreground px-5 py-3 text-background shadow-lg">
          <span>{toast.text}</span>
          {toast.undo && (
            <button
              onClick={() => {
                toast.undo?.();
                onDone();
              }}
              className="font-semibold underline"
            >
              Undo
            </button>
          )}
        </div>
      )}
    </div>
  );
}
