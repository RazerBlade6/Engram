"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { cx } from "@/lib/cx";
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
  // The page the menu was opened on: going to another page (a link, or Back) closes it.
  const [menuOn, setMenuOn] = useState<string | null>(null);
  const menuOpen = menuOn === pathname;
  const closeMenu = useCallback(() => setMenuOn(null), []);

  if (!profile) return null;

  const links = [
    { href: "/", label: "Today", current: pathname === "/" || pathname.startsWith("/courses/") },
    { href: "/calendar", label: "Calendar", current: pathname.startsWith("/calendar") },
    { href: "/ask", label: "Ask", current: pathname.startsWith("/ask") },
    ...(profile.role === "admin" ? [{ href: "/admin", label: "Admin", current: pathname.startsWith("/admin") }] : []),
  ];

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/sign-in");
  }

  return (
    <header className="border-b border-border bg-bar">
      <nav aria-label="Main" className="mx-auto flex max-w-6xl items-center gap-x-6 px-6 py-3 max-md:px-4">
        <Link href="/" className="mr-2 text-xl font-bold text-accent">
          Engram
        </Link>
        {/* On a phone the links don't fit in a row; they're in the menu instead (D67). */}
        <ul className="flex flex-1 flex-wrap items-center gap-x-1 max-md:hidden">
          {links.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                aria-current={link.current ? "page" : undefined}
                className={cx(
                  "block rounded-control px-3 py-1.5 text-lg transition-colors duration-150",
                  link.current
                    ? "bg-accent-soft font-semibold text-foreground"
                    : "text-muted hover:bg-foreground/5 hover:text-foreground",
                )}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
        <Button variant="quiet" onClick={signOut} className="max-md:hidden">
          Sign out
        </Button>
        <button
          type="button"
          onClick={() => setMenuOn(pathname)}
          aria-expanded={menuOpen}
          aria-controls="site-menu"
          className="ml-auto flex items-center gap-2 rounded-control px-3 py-2 font-semibold text-foreground transition-colors duration-150 hover:bg-foreground/5 md:hidden"
        >
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="size-5">
            <path d="M3 5.5h14M3 10h14M3 14.5h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Menu
        </button>
      </nav>
      {menuOpen && <Menu links={links} onSignOut={signOut} onClose={closeMenu} />}
    </header>
  );
}

/** The phone's navigation: a sidebar over the page, with every page and Sign out. */
function Menu({
  links,
  onSignOut,
  onClose,
}: {
  links: { href: string; label: string; current: boolean }[];
  onSignOut: () => void;
  onClose: () => void;
}) {
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fade-in fixed inset-0 z-40 bg-foreground/30 md:hidden" onClick={onClose}>
      <div
        id="site-menu"
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        onClick={(e) => e.stopPropagation()}
        className="slide-in-right absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col bg-bar shadow-lifted"
      >
        <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
          <span className="text-xl font-bold text-accent">Engram</span>
          <Button ref={close} variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
        <ul className="flex flex-col gap-1 p-3">
          {links.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                aria-current={link.current ? "page" : undefined}
                onClick={onClose}
                className={cx(
                  "block rounded-control px-4 py-3 text-lg transition-colors duration-150",
                  link.current
                    ? "bg-accent-soft font-semibold text-foreground"
                    : "text-muted hover:bg-foreground/5 hover:text-foreground",
                )}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="mt-auto border-t border-border p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          <Button variant="quiet" onClick={onSignOut} className="w-full justify-start px-4">
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );
}
