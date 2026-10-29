import type { Metadata } from "next";
import { Figtree, Literata } from "next/font/google";
import { Suspense } from "react";

import { SiteNav } from "@/components/site-nav";
import { UsageTracker } from "@/components/usage-tracker";

import "./globals.css";

const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });
// Built for long reading; used only for card text and source passages.
const literata = Literata({ subsets: ["latin"], variable: "--font-literata", axes: ["opsz"], display: "swap" });

export const metadata: Metadata = {
  title: "Engram",
  description: "Turn course materials into spaced-repetition practice.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${figtree.variable} ${literata.variable}`}>
      <body>
        {/* These read the URL, which some routes know only at request time. */}
        <Suspense>
          <SiteNav />
        </Suspense>
        {children}
        <Suspense>
          <UsageTracker />
        </Suspense>
      </body>
    </html>
  );
}
