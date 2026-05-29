import type { Metadata } from "next";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { WaitlistRowActions } from "@/components/admin/waitlist-row-actions";
import { timeAgo } from "@/lib/utils";

export const metadata: Metadata = { title: "Admin · Waitlist" };

const STATUS_BADGE = {
  PENDING: <Badge tone="amber">in attesa</Badge>,
  INVITED: <Badge tone="violet">invitato</Badge>,
  CONVERTED: <Badge tone="emerald">convertito</Badge>,
} as const;

export default async function AdminWaitlist() {
  const [entries, pending, invited, converted] = await Promise.all([
    prisma.waitlistEntry.findMany({ orderBy: { createdAt: "desc" } }),
    prisma.waitlistEntry.count({ where: { status: "PENDING" } }),
    prisma.waitlistEntry.count({ where: { status: "INVITED" } }),
    prisma.waitlistEntry.count({ where: { status: "CONVERTED" } }),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <p className="font-mono text-xs text-fg-dim">// waitlist</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Waitlist</h1>
      </div>

      <div className="flex flex-wrap gap-3">
        <Badge tone="amber">{pending} in attesa</Badge>
        <Badge tone="violet">{invited} invitati</Badge>
        <Badge tone="emerald">{converted} convertiti</Badge>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left font-mono text-xs uppercase tracking-wider text-fg-dim">
                <th className="px-5 py-3 font-medium">Email</th>
                <th className="px-3 py-3 font-medium">Nome</th>
                <th className="px-3 py-3 font-medium">Piattaforma</th>
                <th className="px-3 py-3 font-medium">Stato</th>
                <th className="px-3 py-3 font-medium">Iscritto</th>
                <th className="px-5 py-3 text-right font-medium">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {entries.map((e) => (
                <tr key={e.id} className="hover:bg-white/[0.02]">
                  <td className="px-5 py-3 font-mono text-xs text-fg">{e.email}</td>
                  <td className="px-3 py-3 text-fg-muted">{e.name ?? "—"}</td>
                  <td className="px-3 py-3">
                    <span className="font-mono text-xs text-fg-muted">{e.platform ?? "—"}</span>
                  </td>
                  <td className="px-3 py-3">{STATUS_BADGE[e.status as keyof typeof STATUS_BADGE]}</td>
                  <td className="px-3 py-3 text-xs text-fg-muted">{timeAgo(e.createdAt)}</td>
                  <td className="px-5 py-3">
                    <WaitlistRowActions id={e.id} status={e.status} />
                  </td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-sm text-fg-dim">
                    Nessuna iscrizione.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
