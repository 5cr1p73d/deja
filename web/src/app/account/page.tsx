import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ShieldCheck,
  ShieldAlert,
  CalendarClock,
  Crown,
  ArrowRight,
  Download,
} from "lucide-react";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProfileForm } from "@/components/account/profile-form";
import { formatDate, timeAgo } from "@/lib/utils";

export const metadata: Metadata = { title: "Il mio account" };

export default async function AccountPage() {
  const session = await auth();
  if (!session?.user?.id) redirect("/login");
  const user = await prisma.user.findUnique({ where: { id: session.user.id } });
  if (!user) redirect("/login");

  const isAdmin = user.role === "ADMIN";

  return (
    <div className="space-y-8">
      <div>
        <p className="font-mono text-xs text-fg-dim">// account</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          Ciao, <span className="text-gradient-violet">{user.name}</span>
        </h1>
      </div>

      {/* stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={user.twoFactorEnabled ? ShieldCheck : ShieldAlert}
          tone={user.twoFactorEnabled ? "emerald" : "amber"}
          label="2FA"
          value={user.twoFactorEnabled ? "Attiva" : "Disattivata"}
        />
        <StatCard
          icon={Crown}
          tone={isAdmin ? "violet" : "muted"}
          label="Ruolo"
          value={isAdmin ? "Admin" : "Utente"}
        />
        <StatCard
          icon={CalendarClock}
          tone="muted"
          label="Iscritto"
          value={user.createdAt.toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" })}
        />
        <StatCard
          icon={CalendarClock}
          tone="muted"
          label="Ultimo accesso"
          value={user.lastLoginAt ? timeAgo(user.lastLoginAt) : "—"}
        />
      </div>

      {/* profilo */}
      <Card className="p-6">
        <h2 className="mb-1 text-lg font-semibold">Profilo</h2>
        <p className="mb-4 text-sm text-fg-muted">
          Email <span className="font-mono text-fg">{user.email}</span> · membro dal{" "}
          {formatDate(user.createdAt)}
        </p>
        <ProfileForm initialName={user.name ?? ""} />
      </Card>

      {/* sicurezza + admin */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card spotlight className="flex items-center justify-between gap-4 p-6">
          <div>
            <h3 className="font-semibold">Sicurezza</h3>
            <p className="mt-0.5 text-sm text-fg-muted">
              {user.twoFactorEnabled
                ? "La 2FA protegge il tuo accesso."
                : "Attiva la 2FA per più sicurezza."}
            </p>
          </div>
          <Button href="/account/security" variant="secondary" size="sm">
            Gestisci <ArrowRight className="h-4 w-4" />
          </Button>
        </Card>

        {isAdmin ? (
          <Card spotlight className="flex items-center justify-between gap-4 border-violet/20 p-6">
            <div>
              <h3 className="flex items-center gap-2 font-semibold">
                Dashboard admin <Badge tone="violet">Scr1p73d</Badge>
              </h3>
              <p className="mt-0.5 text-sm text-fg-muted">Controlla utenti, waitlist e tutto il resto.</p>
            </div>
            <Button href="/admin" size="sm">
              Apri <ArrowRight className="h-4 w-4" />
            </Button>
          </Card>
        ) : (
          <Card className="flex items-center justify-between gap-4 p-6">
            <div>
              <h3 className="font-semibold">Scarica Déjà</h3>
              <p className="mt-0.5 text-sm text-fg-muted">Le build arrivano via waitlist.</p>
            </div>
            <Button href="/download" variant="secondary" size="sm">
              <Download className="h-4 w-4" /> Download
            </Button>
          </Card>
        )}
      </div>

      <p className="text-center text-xs text-fg-dim">
        Hai bisogno di aiuto?{" "}
        <Link href="/contatti" className="text-violet hover:underline">
          Scrivici
        </Link>
        .
      </p>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  tone: "violet" | "emerald" | "amber" | "muted";
}) {
  const c =
    tone === "emerald"
      ? "text-emerald"
      : tone === "amber"
      ? "text-amber"
      : tone === "violet"
      ? "text-violet"
      : "text-fg-muted";
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-fg-dim">
        <Icon className={`h-4 w-4 ${c}`} /> {label}
      </div>
      <div className="mt-2 text-lg font-semibold text-fg">{value}</div>
    </div>
  );
}
