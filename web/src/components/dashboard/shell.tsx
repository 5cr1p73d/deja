"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import {
  LogOut,
  ArrowUpRight,
  Circle,
  LayoutDashboard,
  ShieldCheck,
  Activity,
  Users,
  ListChecks,
  Inbox,
  ToggleLeft,
  ScrollText,
  type LucideIcon,
} from "lucide-react";
import { Logo } from "@/components/site/logo";
import { cn, initials } from "@/lib/utils";

// Registry icone: i layout (server) passano una stringa, qui la mappiamo al
// componente. NON si possono passare funzioni (componenti) da Server a Client.
const ICONS: Record<string, LucideIcon> = {
  dashboard: LayoutDashboard,
  shield: ShieldCheck,
  activity: Activity,
  users: Users,
  list: ListChecks,
  inbox: Inbox,
  toggle: ToggleLeft,
  scroll: ScrollText,
};

export type NavItem = { href: string; label: string; icon: string; exact?: boolean };

export function DashboardShell({
  items,
  user,
  accent = "violet",
  badge,
  children,
}: {
  items: NavItem[];
  user: { name?: string | null; email?: string | null; role?: string };
  accent?: "violet" | "amber";
  badge?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl gap-0 px-0 sm:px-5">
      {/* sidebar */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] py-6 pr-4 md:flex">
        <div className="px-2">
          <Logo />
          {badge && (
            <span className="mt-3 inline-block rounded-md bg-violet/15 px-2 py-0.5 font-mono text-[11px] text-violet">
              {badge}
            </span>
          )}
        </div>
        <nav className="mt-8 flex-1 space-y-1">
          {items.map((it) => {
            const active = it.exact ? pathname === it.href : pathname === it.href || pathname.startsWith(it.href + "/");
            const Icon = ICONS[it.icon] ?? Circle;
            return (
              <Link
                key={it.href}
                href={it.href}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
                  active
                    ? "bg-white/[0.06] text-fg"
                    : "text-fg-muted hover:bg-white/[0.03] hover:text-fg"
                )}
              >
                <Icon className={cn("h-4 w-4", active && (accent === "amber" ? "text-amber" : "text-violet"))} />
                {it.label}
              </Link>
            );
          })}
        </nav>
        <div className="space-y-1 border-t border-white/[0.06] pt-4">
          <Link
            href="/"
            className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-fg-muted transition hover:bg-white/[0.03] hover:text-fg"
          >
            <ArrowUpRight className="h-4 w-4" /> Vai al sito
          </Link>
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-fg-muted transition hover:bg-white/[0.03] hover:text-danger"
          >
            <LogOut className="h-4 w-4" /> Esci
          </button>
        </div>
      </aside>

      {/* main */}
      <div className="min-w-0 flex-1">
        {/* topbar mobile */}
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4 md:hidden">
          <Logo />
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="text-fg-muted hover:text-danger"
            aria-label="Esci"
          >
            <LogOut className="h-5 w-5" />
          </button>
        </div>
        {/* mobile nav */}
        <div className="flex gap-1 overflow-x-auto border-b border-white/[0.06] px-3 py-2 md:hidden">
          {items.map((it) => {
            const active = it.exact ? pathname === it.href : pathname.startsWith(it.href);
            const Icon = ICONS[it.icon] ?? Circle;
            return (
              <Link
                key={it.href}
                href={it.href}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs",
                  active ? "bg-white/[0.06] text-fg" : "text-fg-muted"
                )}
              >
                <Icon className="h-3.5 w-3.5" /> {it.label}
              </Link>
            );
          })}
        </div>

        <div className="px-5 py-8 sm:px-8">
          <div className="mb-6 flex items-center gap-3 md:hidden">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-violet/20 font-mono text-sm text-violet">
              {initials(user.name, user.email)}
            </span>
            <div>
              <div className="text-sm font-medium">{user.name}</div>
              <div className="text-xs text-fg-dim">{user.email}</div>
            </div>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
