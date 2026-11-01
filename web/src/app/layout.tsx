import type { Metadata } from "next";
import { Caveat, Figtree, Literata } from "next/font/google";
import { Suspense } from "react";

import { SiteNav } from "@/components/site-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { UsageTracker } from "@/components/usage-tracker";

import { THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });
// Built for long reading; used only for card text and source passages.
const literata = Literata({ subsets: ["latin"], variable: "--font-literata", axes: ["opsz"], display: "swap" });
// Handwriting, for the short notes on an index card (its course), never for anything longer.
const caveat = Caveat({ subsets: ["latin"], variable: "--font-caveat", display: "swap" });

export const metadata: Metadata = {
  title: "Engram",
  description: "Turn course materials into spaced-repetition practice.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The theme script sets data-theme on <html> before React hydrates, so the server's
    // markup can differ from the browser's there.
    <html lang="en" className={`${figtree.variable} ${literata.variable} ${caveat.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        {/* These read the URL, which some routes know only at request time. */}
        <Suspense>
          <SiteNav />
        </Suspense>
        {children}
        <Suspense>
          <UsageTracker />
          <ThemeToggle />
        </Suspense>
      </body>
    </html>
  );
}
