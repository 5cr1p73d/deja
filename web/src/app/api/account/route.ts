import { NextResponse } from "next/server";
import { z } from "zod";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { nickRegex } from "@/lib/validations";
import { logAudit } from "@/lib/audit";

const patchSchema = z.object({
  name: z.string().regex(nickRegex, "Nick: 3-32 caratteri, lettere/numeri/underscore"),
});

export async function PATCH(req: Request) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  }
  const parsed = patchSchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0]?.message ?? "Dati non validi" },
      { status: 400 }
    );
  }
  await prisma.user.update({
    where: { id: session.user.id },
    data: { name: parsed.data.name },
  });
  await logAudit({ action: "profile_update", actorId: session.user.id });
  return NextResponse.json({ ok: true });
}
