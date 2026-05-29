import type { Metadata } from "next";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MessageActions } from "@/components/admin/message-actions";
import { formatDate } from "@/lib/utils";

export const metadata: Metadata = { title: "Admin · Messaggi" };

const STATUS_BADGE = {
  NEW: <Badge tone="violet">nuovo</Badge>,
  READ: <Badge tone="emerald">letto</Badge>,
  ARCHIVED: <Badge>archiviato</Badge>,
} as const;

export default async function AdminMessages() {
  const messages = await prisma.contactMessage.findMany({ orderBy: { createdAt: "desc" } });

  return (
    <div className="space-y-6">
      <div>
        <p className="font-mono text-xs text-fg-dim">// messaggi</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Messaggi dal form contatti</h1>
      </div>

      {messages.length === 0 ? (
        <Card className="p-10 text-center text-sm text-fg-dim">Nessun messaggio.</Card>
      ) : (
        <div className="space-y-4">
          {messages.map((m) => (
            <Card key={m.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-fg">{m.subject}</h3>
                    {STATUS_BADGE[m.status as keyof typeof STATUS_BADGE]}
                  </div>
                  <p className="mt-0.5 font-mono text-xs text-fg-dim">
                    {m.name} · {m.email} · {formatDate(m.createdAt)}
                  </p>
                </div>
                <MessageActions id={m.id} status={m.status} />
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-fg-muted">{m.body}</p>
              <a
                href={`mailto:${m.email}?subject=Re: ${encodeURIComponent(m.subject)}`}
                className="mt-3 inline-block font-mono text-xs text-violet hover:underline"
              >
                rispondi via email →
              </a>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
