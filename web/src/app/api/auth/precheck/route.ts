import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { prisma } from "@/lib/db";
import { loginSchema } from "@/lib/validations";
import { rateLimit, clientIp } from "@/lib/rate-limit";

// Verifica le credenziali SENZA creare sessione, per sapere se serve la 2FA.
// (Auth.js maschera gli errori di authorize come "CredentialsSignin", quindi
//  questo step ci dà un segnale pulito prima del vero signIn.)
export async function POST(req: Request) {
  const ip = clientIp(req);
  const rl = rateLimit(`precheck:${ip}`, 10, 60_000);
  if (!rl.ok) {
    return NextResponse.json(
      { error: `Troppi tentativi. Riprova tra ${rl.retryAfter}s.` },
      { status: 429 }
    );
  }

  const parsed = loginSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ error: "Dati non validi" }, { status: 400 });
  }
  const { email, password } = parsed.data;

  const user = await prisma.user.findUnique({
    where: { email: email.toLowerCase() },
  });
  // Risposta uniforme per credenziali errate (no user enumeration).
  if (!user || !user.passwordHash || !(await bcrypt.compare(password, user.passwordHash))) {
    return NextResponse.json({ error: "Email o password errate" }, { status: 401 });
  }
  if (user.banned) {
    return NextResponse.json({ error: "Account sospeso" }, { status: 403 });
  }

  return NextResponse.json({ ok: true, need2fa: user.twoFactorEnabled });
}
