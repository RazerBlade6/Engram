import type { Metadata } from "next";

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
        <UsageTracker />
      </body>
    </html>
  );
}
