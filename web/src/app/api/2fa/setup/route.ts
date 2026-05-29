import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { generateTotpSecret, otpauthUri, qrDataUrl } from "@/lib/totp";

export async function POST() {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  }
  const user = await prisma.user.findUnique({ where: { id: session.user.id } });
  if (!user) return NextResponse.json({ error: "Utente non trovato" }, { status: 404 });
  if (user.twoFactorEnabled) {
    return NextResponse.json({ error: "2FA già attiva" }, { status: 400 });
  }

  const secret = generateTotpSecret();
  const otpauth = otpauthUri(user.email, secret);
  // Salva il secret in pending (enabled resta false finché non verificato).
  await prisma.user.update({
    where: { id: user.id },
    data: { twoFactorSecret: secret, twoFactorEnabled: false },
  });
  const qr = await qrDataUrl(otpauth);

  return NextResponse.json({ secret, otpauth, qr });
}
