import type { Metadata } from "next";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { UserRowActions } from "@/components/admin/user-row-actions";
import { initials, timeAgo } from "@/lib/utils";

export const metadata: Metadata = { title: "Admin · Utenti" };

export default async function AdminUsers() {
  const session = await auth();
  const users = await prisma.user.findMany({ orderBy: { createdAt: "desc" } });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono text-xs text-fg-dim">// utenti</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Utenti</h1>
        </div>
        <Badge tone="violet">{users.length} totali</Badge>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left font-mono text-xs uppercase tracking-wider text-fg-dim">
                <th className="px-5 py-3 font-medium">Utente</th>
                <th className="px-3 py-3 font-medium">Ruolo</th>
                <th className="px-3 py-3 font-medium">2FA</th>
                <th className="px-3 py-3 font-medium">Stato</th>
                <th className="px-3 py-3 font-medium">Iscritto</th>
                <th className="px-5 py-3 text-right font-medium">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-white/[0.02]">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-violet/20 font-mono text-xs text-violet">
                        {initials(u.name, u.email)}
                      </span>
                      <div className="min-w-0">
                        <div className="truncate font-medium text-fg">{u.name ?? "—"}</div>
                        <div className="truncate font-mono text-xs text-fg-dim">{u.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    {u.role === "ADMIN" ? <Badge tone="violet">admin</Badge> : <Badge>utente</Badge>}
                  </td>
                  <td className="px-3 py-3">
                    {u.twoFactorEnabled ? (
                      <Badge tone="emerald">on</Badge>
                    ) : (
                      <span className="text-fg-dim">off</span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {u.banned ? <Badge tone="danger">bannato</Badge> : <Badge tone="emerald">attivo</Badge>}
                  </td>
                  <td className="px-3 py-3 text-xs text-fg-muted">{timeAgo(u.createdAt)}</td>
                  <td className="px-5 py-3">
                    <UserRowActions
                      id={u.id}
                      role={u.role}
                      banned={u.banned}
                      isSelf={u.id === session?.user?.id}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <p className="font-mono text-xs text-fg-dim">
        Scudo = cambia ruolo · Ban = sospendi · Cestino = elimina. Non puoi agire su te stesso.
      </p>
    </div>
  );
}
