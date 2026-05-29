import { PrismaClient } from "@prisma/client";
import bcrypt from "bcryptjs";

const prisma = new PrismaClient();

async function main() {
  const nick = process.env.ADMIN_NICK || "Scr1p73d";
  const email = (process.env.ADMIN_EMAIL || "admin@example.com").toLowerCase();
  const password = process.env.ADMIN_PASSWORD;
  if (!password) {
    throw new Error(
      "ADMIN_PASSWORD non impostata. Copia .env.example in .env e imposta una password forte prima del seed."
    );
  }
  const passwordHash = await bcrypt.hash(password, 12);

  const admin = await prisma.user.upsert({
    where: { email },
    update: { name: nick, role: "ADMIN", passwordHash },
    create: {
      name: nick,
      email,
      passwordHash,
      role: "ADMIN",
      emailVerified: new Date(),
    },
  });
  console.log(`✓ Admin pronto: ${admin.name} <${admin.email}> (role=${admin.role})`);
  console.log(`  Password presa da ADMIN_PASSWORD  ← cambiala dopo il primo login`);

  // Feature flags di default
  const flags: Array<[string, boolean, string]> = [
    ["downloads_open", true, "Mostra i pulsanti di download nella pagina /download"],
    ["waitlist_open", true, "Accetta nuove iscrizioni alla waitlist"],
    ["public_changelog", true, "Changelog visibile pubblicamente"],
    ["maintenance_mode", false, "Banner di manutenzione in cima al sito"],
    ["vision_beta", true, "Evidenzia la feature Vision (Gemini) come beta"],
  ];
  for (const [key, enabled, description] of flags) {
    await prisma.featureFlag.upsert({
      where: { key },
      update: { description },
      create: { key, enabled, description },
    });
  }
  console.log(`✓ ${flags.length} feature flag`);

  // Demo: qualche iscritto alla waitlist così la dashboard non è vuota.
  const demo: Array<[string, string, string]> = [
    ["luca.bianchi@example.com", "Luca Bianchi", "windows"],
    ["sara.verdi@example.com", "Sara Verdi", "windows"],
    ["dev.null@example.com", "Anonimo", "linux"],
  ];
  for (const [e, n, p] of demo) {
    await prisma.waitlistEntry.upsert({
      where: { email: e },
      update: {},
      create: { email: e, name: n, platform: p },
    });
  }
  console.log(`✓ ${demo.length} iscritti demo in waitlist`);

  await prisma.auditLog.create({
    data: { action: "seed", target: email, meta: JSON.stringify({ by: "prisma/seed" }) },
  });
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    process.exit(1);
  });
