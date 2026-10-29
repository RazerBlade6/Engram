"use client";

import { useEffect } from "react";

export type ToastMessage = { id: number; text: string; undo?: () => void };

const VISIBLE_MS = 8000;

/** A short confirmation at the bottom of the screen, optionally with Undo. */
export function Toast({
  toast,
  onDone,
  above = "bottom-6",
}: {
  toast: ToastMessage | null;
  onDone: () => void;
  /** How far up the screen it sits, to clear anything fixed at the bottom. */
  above?: "bottom-6" | "bottom-28";
}) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onDone, VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [toast, onDone]);

  return (
    <div role="status" aria-live="polite" className={`fixed inset-x-0 ${above} flex justify-center px-4`}>
      {toast && (
        <div className="rise-in flex items-center gap-6 rounded-control bg-foreground px-5 py-3 text-paper shadow-lifted">
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
