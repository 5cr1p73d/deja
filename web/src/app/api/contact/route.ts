import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { contactSchema } from "@/lib/validations";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { logAudit } from "@/lib/audit";

export async function POST(req: Request) {
  const ip = clientIp(req);
  const rl = rateLimit(`contact:${ip}`, 4, 60_000);
  if (!rl.ok) {
    return NextResponse.json(
      { error: `Troppi messaggi. Riprova tra ${rl.retryAfter}s.` },
      { status: 429 }
    );
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body non valido" }, { status: 400 });
  }
  const parsed = contactSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Dati non validi" },
      { status: 400 }
    );
  }
  const { name, email, subject, body: message } = parsed.data;

  await prisma.contactMessage.create({
    data: { name, email: email.toLowerCase(), subject, body: message },
  });
  await logAudit({ action: "contact", target: email.toLowerCase(), ip });

  return NextResponse.json({ ok: true });
}
