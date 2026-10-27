import type { Metadata } from "next";
import { Suspense } from "react";

import { UsageTracker } from "@/components/usage-tracker";

import "./globals.css";

export const metadata: Metadata = {
  title: "Engram",
  description: "Turn course materials into spaced-repetition practice.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        {children}
        {/* It reads the URL, which some routes know only at request time. */}
        <Suspense>
          <UsageTracker />
        </Suspense>
      </body>
    </html>
  );
}
