"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";
import { useTranslations } from "next-intl";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, X, LayoutDashboard, LogOut, User as UserIcon, Shield } from "lucide-react";
import { Logo } from "@/components/site/logo";
import { Button } from "@/components/ui/button";
import { Magnetic } from "@/components/motion/magnetic";
import { LanguageSwitcher } from "@/components/site/language-switcher";
import { cn, initials } from "@/lib/utils";

const LINKS = [
  { href: "/funzionalita", key: "features" },
  { href: "/#how", key: "how" },
  { href: "/privacy", key: "privacy" },
  { href: "/docs", key: "docs" },
  { href: "/changelog", key: "changelog" },
] as const;

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const { data: session } = useSession();
  const pathname = usePathname();
  const t = useTranslations("nav");
  const tc = useTranslations("common");

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-all duration-300",
        scrolled
          ? "border-b border-white/[0.06] bg-ink-900/70 backdrop-blur-xl"
          : "border-b border-transparent"
      )}
    >
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Logo />

        <div className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-lg px-3 py-2 text-sm text-fg-muted transition hover:bg-white/[0.04] hover:text-fg"
            >
              {t(l.key)}
            </Link>
          ))}
        </div>

        <div className="hidden items-center gap-2 md:flex">
          <LanguageSwitcher />
          {session?.user ? (
            <div className="relative">
              <button
                onClick={() => setMenu((v) => !v)}
                className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] py-1 pl-1 pr-3 transition hover:bg-white/[0.08]"
              >
                <span className="grid h-7 w-7 place-items-center rounded-full bg-violet/20 font-mono text-xs text-violet">
                  {initials(session.user.name, session.user.email)}
                </span>
                <span className="max-w-[120px] truncate text-sm">{session.user.name}</span>
              </button>
              <AnimatePresence>
                {menu && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.97 }}
                    transition={{ duration: 0.16 }}
                    className="absolute right-0 mt-2 w-52 overflow-hidden rounded-xl border border-white/10 bg-ink-800/95 p-1 backdrop-blur-xl"
                    onMouseLeave={() => setMenu(false)}
                  >
                    <MenuLink href="/account" icon={<UserIcon className="h-4 w-4" />}>
                      {tc("myAccount")}
                    </MenuLink>
                    {session.user.role === "ADMIN" && (
                      <MenuLink href="/admin" icon={<Shield className="h-4 w-4 text-violet" />}>
                        {tc("adminDashboard")}
                      </MenuLink>
                    )}
                    <button
                      onClick={() => signOut({ callbackUrl: "/" })}
                      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-fg-muted transition hover:bg-white/[0.05] hover:text-danger"
                    >
                      <LogOut className="h-4 w-4" /> {tc("logout")}
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <>
              <Button href="/login" variant="ghost" size="sm">
                {tc("login")}
              </Button>
              <Magnetic>
                <Button href="/download" size="sm">
                  {tc("download")}
                </Button>
              </Magnetic>
            </>
          )}
        </div>

        <button
          className="rounded-lg p-2 text-fg-muted md:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Menu"
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </nav>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden border-t border-white/[0.06] bg-ink-900/95 backdrop-blur-xl md:hidden"
          >
            <div className="flex flex-col gap-1 p-4">
              {LINKS.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className="rounded-lg px-3 py-2.5 text-sm text-fg-muted hover:bg-white/5 hover:text-fg"
                >
                  {t(l.key)}
                </Link>
              ))}
              <div className="mt-2"><LanguageSwitcher compact /></div>
              <div className="mt-2 flex gap-2">
                {session?.user ? (
                  <>
                    <Button href="/account" variant="secondary" size="sm" className="flex-1">
                      <LayoutDashboard className="h-4 w-4" /> {tc("myAccount")}
                    </Button>
                    {session.user.role === "ADMIN" && (
                      <Button href="/admin" size="sm" className="flex-1">
                        Admin
                      </Button>
                    )}
                  </>
                ) : (
                  <>
                    <Button href="/login" variant="secondary" size="sm" className="flex-1">
                      {tc("login")}
                    </Button>
                    <Button href="/download" size="sm" className="flex-1">
                      {tc("download")}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}

function MenuLink({
  href,
  icon,
  children,
}: {
  href: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-fg-muted transition hover:bg-white/[0.05] hover:text-fg"
    >
      {icon}
      {children}
    </Link>
  );
}
