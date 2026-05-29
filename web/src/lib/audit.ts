import { prisma } from "@/lib/db";

export async function logAudit(opts: {
  action: string;
  actorId?: string | null;
  target?: string | null;
  meta?: Record<string, unknown> | null;
  ip?: string | null;
}) {
  try {
    await prisma.auditLog.create({
      data: {
        action: opts.action,
        actorId: opts.actorId ?? null,
        target: opts.target ?? null,
        meta: opts.meta ? JSON.stringify(opts.meta) : null,
        ip: opts.ip ?? null,
      },
    });
  } catch {
    // logging non deve mai rompere il flusso principale
  }
}
