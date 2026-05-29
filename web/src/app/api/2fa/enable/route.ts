import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { verifyTotp, generateRecoveryCodes } from "@/lib/totp";
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
  if (!user?.twoFactorSecret) {
    return NextResponse.json({ error: "Avvia prima la configurazione" }, { status: 400 });
  }
  if (!verifyTotp(parsed.data.token, user.twoFactorSecret)) {
    return NextResponse.json({ error: "Codice non valido o scaduto" }, { status: 400 });
  }

  await prisma.user.update({
    where: { id: user.id },
    data: { twoFactorEnabled: true },
  });
  await logAudit({ action: "2fa_enable", actorId: user.id, target: user.email });

  const recoveryCodes = generateRecoveryCodes();
  return NextResponse.json({ ok: true, recoveryCodes });
}
