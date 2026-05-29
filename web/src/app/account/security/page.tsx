import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { KeyRound, ShieldCheck, Fingerprint } from "lucide-react";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { TwoFactorSetup } from "@/components/account/two-factor-setup";

export const metadata: Metadata = { title: "Sicurezza" };

export default async function SecurityPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/login");
  const user = await prisma.user.findUnique({ where: { id: session.user.id } });
  if (!user) redirect("/login");

  return (
    <div className="space-y-8">
      <div>
        <p className="font-mono text-xs text-fg-dim">// sicurezza</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Sicurezza dell&apos;account</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Proteggi l&apos;accesso con un secondo fattore.
        </p>
      </div>

      <Card className="p-6">
        <div className="mb-5 flex items-center gap-2">
          <Fingerprint className="h-5 w-5 text-violet" />
          <h2 className="text-lg font-semibold">Autenticazione a due fattori (TOTP)</h2>
        </div>
        <TwoFactorSetup enabled={user.twoFactorEnabled} />
      </Card>

      <Card className="p-6">
        <div className="mb-3 flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-fg-muted" />
          <h2 className="text-lg font-semibold">Metodo di accesso</h2>
        </div>
        <p className="text-sm text-fg-muted">
          {user.passwordHash
            ? "Accedi con email e password."
            : "Accedi tramite provider OAuth (Google/Apple). Puoi comunque attivare la 2FA qui sopra."}
        </p>
      </Card>

      <div className="flex items-start gap-3 rounded-xl border border-violet/15 bg-violet/[0.05] p-4 text-sm text-fg-muted">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-violet" />
        Le password sono salvate con hash <span className="font-mono text-fg">bcrypt</span> (cost 12).
        Il segreto TOTP non lascia mai questo server in chiaro dopo l&apos;attivazione.
      </div>
    </div>
  );
}
