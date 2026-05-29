"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, ShieldAlert, Copy, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";

type Phase = "idle" | "setup" | "saving" | "codes";

export function TwoFactorSetup({ enabled }: { enabled: boolean }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string>("");
  const [token, setToken] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const toast = useToast();

  async function startSetup() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/2fa/setup", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setQr(data.qr);
      setSecret(data.secret);
      setPhase("setup");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Errore", "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirmEnable(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/2fa/enable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Errore");
        return;
      }
      setCodes(data.recoveryCodes || []);
      setPhase("codes");
      toast("2FA attivata 🔐", "ok");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    const otp = prompt("Inserisci un codice 2FA per disattivarla:");
    if (!otp) return;
    setBusy(true);
    try {
      const res = await fetch("/api/2fa/disable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: otp.replace(/\D/g, "") }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      toast("2FA disattivata.", "info");
      router.refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Errore", "error");
    } finally {
      setBusy(false);
    }
  }

  function copySecret() {
    navigator.clipboard?.writeText(secret).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  // ── Stato: già attiva ──
  if (enabled && phase !== "codes") {
    return (
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald/15 text-emerald">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div>
            <div className="flex items-center gap-2 font-medium">
              2FA attiva <Badge tone="emerald">on</Badge>
            </div>
            <p className="text-sm text-fg-muted">Ti viene chiesto un codice ad ogni accesso.</p>
          </div>
        </div>
        <Button variant="danger" size="sm" onClick={disable} loading={busy}>
          Disattiva
        </Button>
      </div>
    );
  }

  // ── Codici di recupero (mostrati una volta) ──
  if (phase === "codes") {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-emerald">
          <ShieldCheck className="h-5 w-5" />
          <span className="font-medium">2FA attivata. Salva i codici di recupero.</span>
        </div>
        <p className="text-sm text-fg-muted">
          Usali se perdi l&apos;accesso all&apos;app. Vengono mostrati una sola volta.
        </p>
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-white/10 bg-ink-950/60 p-4 font-mono text-sm">
          {codes.map((c) => (
            <span key={c} className="text-violet-soft">{c}</span>
          ))}
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            navigator.clipboard?.writeText(codes.join("\n"));
            toast("Codici copiati.", "ok");
          }}
        >
          <Copy className="h-4 w-4" /> Copia codici
        </Button>
      </div>
    );
  }

  // ── Setup: QR + verifica ──
  if (phase === "setup") {
    return (
      <form onSubmit={confirmEnable} className="grid gap-6 sm:grid-cols-[auto_1fr]">
        <div className="flex flex-col items-center gap-2">
          {qr && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={qr} alt="QR code 2FA" className="h-44 w-44 rounded-xl border border-white/10 bg-white/[0.03] p-2" />
          )}
          <button
            type="button"
            onClick={copySecret}
            className="flex items-center gap-1.5 font-mono text-[11px] text-fg-muted hover:text-violet"
          >
            {copied ? <Check className="h-3 w-3 text-emerald" /> : <Copy className="h-3 w-3" />}
            {copied ? "copiato" : "copia chiave manuale"}
          </button>
        </div>
        <div className="space-y-3">
          <p className="text-sm text-fg-muted">
            Scansiona il QR con Google Authenticator, Authy o 1Password, poi inserisci
            il codice generato.
          </p>
          <Input
            label="Codice a 6 cifre"
            inputMode="numeric"
            maxLength={6}
            value={token}
            onChange={(e) => setToken(e.target.value.replace(/\D/g, ""))}
            placeholder="000000"
            className="font-mono tracking-[0.4em]"
            error={error ?? undefined}
          />
          <div className="flex gap-2">
            <Button type="submit" loading={busy} disabled={token.length !== 6}>
              Attiva 2FA
            </Button>
            <Button type="button" variant="ghost" onClick={() => setPhase("idle")}>
              Annulla
            </Button>
          </div>
        </div>
      </form>
    );
  }

  // ── Idle: non attiva ──
  return (
    <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-amber/15 text-amber">
          <ShieldAlert className="h-5 w-5" />
        </span>
        <div>
          <div className="font-medium">2FA disattivata</div>
          <p className="text-sm text-fg-muted">Aggiungi un secondo fattore via app TOTP.</p>
        </div>
      </div>
      <Button onClick={startSetup} loading={busy}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
        Attiva 2FA
      </Button>
    </div>
  );
}
