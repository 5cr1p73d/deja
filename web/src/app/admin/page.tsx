import type { Metadata } from "next";
import Link from "next/link";
import { Users, ShieldCheck, ListChecks, Inbox, ArrowUpRight, TrendingUp } from "lucide-react";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BarChart } from "@/components/admin/bar-chart";
import { FlagToggle } from "@/components/admin/flag-toggle";
import { timeAgo } from "@/lib/utils";

export const metadata: Metadata = { title: "Admin · Panoramica" };

export default async function AdminOverview() {
  const since = new Date(Date.now() - 14 * 86_400_000);

  const [
    totalUsers,
    admins,
    twoFa,
    waitlistPending,
    waitlistTotal,
    newMessages,
    recentUsers,
    recentLogs,
    flags,
  ] = await Promise.all([
    prisma.user.count(),
    prisma.user.count({ where: { role: "ADMIN" } }),
    prisma.user.count({ where: { twoFactorEnabled: true } }),
    prisma.waitlistEntry.count({ where: { status: "PENDING" } }),
    prisma.waitlistEntry.count(),
    prisma.contactMessage.count({ where: { status: "NEW" } }),
    prisma.user.findMany({ where: { createdAt: { gte: since } }, select: { createdAt: true } }),
    prisma.auditLog.findMany({
      orderBy: { createdAt: "desc" },
      take: 8,
      include: { actor: { select: { name: true, email: true } } },
    }),
    prisma.featureFlag.findMany({ orderBy: { key: "asc" } }),
  ]);

  // bucket signups per gli ultimi 14 giorni
  const days: { label: string; value: number }[] = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86_400_000);
    const key = d.toISOString().slice(0, 10);
    const count = recentUsers.filter((u) => u.createdAt.toISOString().slice(0, 10) === key).length;
    days.push({ label: d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" }), value: count });
  }

  const stats = [
    { icon: Users, tone: "violet", label: "Utenti", value: totalUsers, sub: `${admins} admin` },
    { icon: ShieldCheck, tone: "emerald", label: "Con 2FA", value: twoFa, sub: `${totalUsers ? Math.round((twoFa / totalUsers) * 100) : 0}% del totale` },
    { icon: ListChecks, tone: "amber", label: "Waitlist", value: waitlistPending, sub: `${waitlistTotal} totali` },
    { icon: Inbox, tone: "violet", label: "Messaggi nuovi", value: newMessages, sub: "da leggere" },
  ] as const;

  return (
    <div className="space-y-8">
      <div>
        <p className="font-mono text-xs text-fg-dim">// dashboard</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Panoramica</h1>
      </div>

      {/* stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          const c =
            s.tone === "emerald" ? "text-emerald" : s.tone === "amber" ? "text-amber" : "text-violet";
          return (
            <Card key={s.label} spotlight className="p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase tracking-wider text-fg-dim">{s.label}</span>
                <Icon className={`h-4 w-4 ${c}`} />
              </div>
              <div className="mt-3 text-3xl font-semibold">{s.value}</div>
              <div className="mt-1 text-xs text-fg-muted">{s.sub}</div>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        {/* chart */}
        <Card className="p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-semibold">
              <TrendingUp className="h-4 w-4 text-violet" /> Registrazioni · 14 giorni
            </h2>
            <Badge tone="violet">{recentUsers.length} nuovi</Badge>
          </div>
          <BarChart data={days} />
        </Card>

        {/* feature flags */}
        <Card className="p-6">
          <h2 className="mb-4 font-semibold">Feature flag</h2>
          <div className="space-y-3">
            {flags.map((f) => (
              <div key={f.key} className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <code className="font-mono text-sm text-fg">{f.key}</code>
                  {f.description && (
                    <p className="truncate text-xs text-fg-dim">{f.description}</p>
                  )}
                </div>
                <FlagToggle flagKey={f.key} enabled={f.enabled} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* recent activity */}
      <Card className="p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">Attività recente</h2>
          <Link href="/admin/audit" className="flex items-center gap-1 font-mono text-xs text-violet hover:underline">
            tutto <ArrowUpRight className="h-3 w-3" />
          </Link>
        </div>
        <div className="divide-y divide-white/[0.05]">
          {recentLogs.map((log) => (
            <div key={log.id} className="flex items-center justify-between gap-4 py-2.5 text-sm">
              <div className="flex min-w-0 items-center gap-3">
                <code className="rounded bg-white/[0.05] px-2 py-0.5 font-mono text-xs text-violet">{log.action}</code>
                <span className="truncate text-fg-muted">
                  {log.actor?.name ?? log.target ?? "sistema"}
                </span>
              </div>
              <span className="shrink-0 text-xs text-fg-dim">{timeAgo(log.createdAt)}</span>
            </div>
          ))}
          {recentLogs.length === 0 && (
            <p className="py-6 text-center text-sm text-fg-dim">Nessuna attività.</p>
          )}
        </div>
      </Card>
    </div>
  );
}
