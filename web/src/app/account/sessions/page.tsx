import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LogIn, ShieldCheck, ShieldOff, UserCog, Activity } from "lucide-react";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { formatDate, timeAgo } from "@/lib/utils";

export const metadata: Metadata = { title: "Attività" };

const ICONS: Record<string, { icon: React.ElementType; tone: string; label: string }> = {
  login: { icon: LogIn, tone: "text-emerald", label: "Accesso (password)" },
  oauth_login: { icon: LogIn, tone: "text-violet", label: "Accesso (OAuth)" },
  "2fa_enable": { icon: ShieldCheck, tone: "text-emerald", label: "2FA attivata" },
  "2fa_disable": { icon: ShieldOff, tone: "text-amber", label: "2FA disattivata" },
  profile_update: { icon: UserCog, tone: "text-fg-muted", label: "Profilo aggiornato" },
  register: { icon: Activity, tone: "text-violet", label: "Registrazione" },
};

export default async function SessionsPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/login");

  const logs = await prisma.auditLog.findMany({
    where: { actorId: session.user.id },
    orderBy: { createdAt: "desc" },
    take: 25,
  });

  return (
    <div className="space-y-8">
      <div>
        <p className="font-mono text-xs text-fg-dim">// attività</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Attività recente</h1>
        <p className="mt-1 text-sm text-fg-muted">Gli ultimi eventi del tuo account.</p>
      </div>

      <Card className="divide-y divide-white/[0.05] p-0">
        {logs.length === 0 ? (
          <div className="p-10 text-center text-sm text-fg-dim">Nessuna attività registrata.</div>
        ) : (
          logs.map((log) => {
            const m = ICONS[log.action] ?? { icon: Activity, tone: "text-fg-muted", label: log.action };
            const Icon = m.icon;
            return (
              <div key={log.id} className="flex items-center gap-4 px-5 py-3.5">
                <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/[0.04] ${m.tone}`}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-fg">{m.label}</div>
                  <div className="font-mono text-xs text-fg-dim">{formatDate(log.createdAt)}</div>
                </div>
                <span className="shrink-0 text-xs text-fg-muted">{timeAgo(log.createdAt)}</span>
              </div>
            );
          })
        )}
      </Card>
    </div>
  );
}
