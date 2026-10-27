"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useProfile } from "@/lib/profile";

/** Renders its children for admins only. The API enforces the same rule on every request. */
export function AdminOnly({ children }: { children: ReactNode }) {
  const profile = useProfile();
  if (!profile) return null;
  if (profile.role !== "admin") {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-3xl font-semibold">Admins only</h1>
        <p className="mt-4">
          <Link href="/" className="text-accent underline">
            Back to Engram
          </Link>
        </p>
      </main>
    );
  }
  return children;
}
