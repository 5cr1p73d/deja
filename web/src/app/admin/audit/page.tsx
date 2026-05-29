import type { Metadata } from "next";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";

export const metadata: Metadata = { title: "Admin · Audit log" };

export default async function AdminAudit() {
  const logs = await prisma.auditLog.findMany({
    orderBy: { createdAt: "desc" },
    take: 200,
    include: { actor: { select: { name: true, email: true } } },
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="font-mono text-xs text-fg-dim">// audit</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Audit log</h1>
        <p className="mt-1 text-sm text-fg-muted">Ultimi {logs.length} eventi di sistema.</p>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left font-mono text-xs uppercase tracking-wider text-fg-dim">
                <th className="px-5 py-3 font-medium">Quando</th>
                <th className="px-3 py-3 font-medium">Azione</th>
                <th className="px-3 py-3 font-medium">Attore</th>
                <th className="px-3 py-3 font-medium">Target</th>
                <th className="px-5 py-3 font-medium">Meta</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {logs.map((l) => (
                <tr key={l.id} className="hover:bg-white/[0.02]">
                  <td className="whitespace-nowrap px-5 py-2.5 font-mono text-xs text-fg-dim">
                    {formatDate(l.createdAt)}
                  </td>
                  <td className="px-3 py-2.5">
                    <code className="rounded bg-white/[0.05] px-2 py-0.5 font-mono text-xs text-violet">
                      {l.action}
                    </code>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-fg-muted">
                    {l.actor?.name ?? l.actor?.email ?? "—"}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-fg-muted">{l.target ?? "—"}</td>
                  <td className="max-w-[220px] truncate px-5 py-2.5 font-mono text-[11px] text-fg-dim">
                    {l.meta ?? ""}
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-10 text-center text-sm text-fg-dim">
                    Nessun evento.
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
