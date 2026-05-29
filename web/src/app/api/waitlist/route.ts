import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { waitlistSchema } from "@/lib/validations";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { logAudit } from "@/lib/audit";

export async function POST(req: Request) {
  const ip = clientIp(req);
  const rl = rateLimit(`waitlist:${ip}`, 6, 60_000);
  if (!rl.ok) {
    return NextResponse.json(
      { error: `Troppe richieste. Riprova tra ${rl.retryAfter}s.` },
      { status: 429 }
    );
  }

  const flag = await prisma.featureFlag.findUnique({ where: { key: "waitlist_open" } });
  if (flag && !flag.enabled) {
    return NextResponse.json({ error: "La waitlist è chiusa al momento." }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body non valido" }, { status: 400 });
  }
  const parsed = waitlistSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Dati non validi" },
      { status: 400 }
    );
  }
  const { email, name, platform, referrer } = parsed.data;
  const emailLc = email.toLowerCase();

  const existing = await prisma.waitlistEntry.findUnique({ where: { email: emailLc } });
  if (existing) {
    // Idempotente: non rivelare nulla, restituiamo posizione.
    const position = await prisma.waitlistEntry.count({
      where: { createdAt: { lte: existing.createdAt } },
    });
    return NextResponse.json({ ok: true, position, already: true });
  }

  const entry = await prisma.waitlistEntry.create({
    data: {
      email: emailLc,
      name: name || null,
      platform: platform || null,
      referrer: referrer || null,
    },
  });
  const position = await prisma.waitlistEntry.count();
  await logAudit({ action: "waitlist_join", target: emailLc, ip, meta: { platform } });

  return NextResponse.json({ ok: true, position, id: entry.id });
}
