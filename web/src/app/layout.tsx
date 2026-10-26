import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Engram",
  description: "Turn course materials into spaced-repetition practice.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
