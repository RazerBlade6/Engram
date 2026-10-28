"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useProfile } from "@/lib/profile";
import { supabase } from "@/lib/supabase";

/** Pages without the bar: signed out, and review, which keeps the screen to the card. */
const BARE = [/^\/sign-in/, /^\/auth\//, /^\/review/];

/** The bar along the top of every signed-in page. */
export function SiteNav() {
  const pathname = usePathname();
  if (BARE.some((pattern) => pattern.test(pathname))) return null;
  return <Nav pathname={pathname} />;
}

function Nav({ pathname }: { pathname: string }) {
  const router = useRouter();
  const profile = useProfile();
  if (!profile) return null;

  const links = [
    { href: "/", label: "Today", current: pathname === "/" || pathname.startsWith("/courses/") },
    { href: "/calendar", label: "Calendar", current: pathname.startsWith("/calendar") },
    { href: "/ask", label: "Ask", current: pathname.startsWith("/ask") },
    ...(profile.role === "admin"
      ? [{ href: "/admin", label: "Admin", current: pathname.startsWith("/admin") }]
      : []),
  ];

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/sign-in");
  }

  return (
    <header className="border-b border-border bg-white">
      <nav aria-label="Main" className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
        <Link href="/" className="mr-2 text-lg font-semibold text-accent">
          Engram
        </Link>
        <ul className="flex flex-1 flex-wrap items-center gap-x-1">
          {links.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                aria-current={link.current ? "page" : undefined}
                className={`block rounded-lg px-3 py-2 text-lg hover:bg-accent/10 ${
                  link.current ? "font-semibold text-foreground" : "text-muted"
                }`}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
        <button onClick={signOut} className="text-muted underline hover:text-foreground">
          Sign out
        </button>
      </nav>
    </header>
  );
}
