import type { Metadata } from "next";
import { ShieldCheck } from "lucide-react";
import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Verifica 2FA" };

export default function VerifyPage() {
  return (
    <AuthCard title="Verifica in due passaggi">
      <div className="space-y-5 text-sm text-fg-muted">
        <div className="flex items-center gap-2 rounded-xl border border-violet/20 bg-violet/[0.06] px-4 py-3 text-violet">
          <ShieldCheck className="h-4 w-4" />
          La verifica 2FA avviene durante l&apos;accesso.
        </div>
        <p>
          Se hai attivato l&apos;autenticazione a due fattori, il codice ti verrà
          chiesto subito dopo email e password nella pagina di accesso.
        </p>
        <Button href="/login" className="w-full">
          Vai all&apos;accesso
        </Button>
      </div>
    </AuthCard>
  );
}
