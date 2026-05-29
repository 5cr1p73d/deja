import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { verifyTotp } from "@/lib/totp";
import { totpTokenSchema } from "@/lib/validations";
import { logAudit } from "@/lib/audit";

export async function POST(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  }

  const parsed = totpTokenSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ error: "Codice a 6 cifre richiesto" }, { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { id: session.user.id } });
  if (!user?.twoFactorEnabled || !user.twoFactorSecret) {
    return NextResponse.json({ error: "2FA non attiva" }, { status: 400 });
  }
  if (!verifyTotp(parsed.data.token, user.twoFactorSecret)) {
    return NextResponse.json({ error: "Codice non valido" }, { status: 400 });
  }

  await prisma.user.update({
    where: { id: user.id },
    data: { twoFactorEnabled: false, twoFactorSecret: null },
  });
  await logAudit({ action: "2fa_disable", actorId: user.id, target: user.email });

  return NextResponse.json({ ok: true });
}
