import type { Metadata } from "next";
import { ShieldCheck, Lock, EyeOff, ScanLine, Server, Database } from "lucide-react";
import { Section, SectionHeading } from "@/components/site/section";
import { Reveal } from "@/components/motion/reveal";
import { Card } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Privacy",
  description: "Come Déjà protegge i tuoi dati: local-first, redazione PII, controllo totale.",
};

const PILLARS = [
  { icon: Server, title: "Local-first", desc: "Cattura, OCR, trascrizione, embedding e ricerca girano sul tuo PC. Nessun server, nessun account obbligatorio." },
  { icon: ScanLine, title: "Redazione PII", desc: "Regex su OCR per carte di credito, IBAN, codice fiscale, email e numeri di telefono prima di scrivere nel DB." },
  { icon: EyeOff, title: "Pausa intelligente", desc: "Stop manuale dal tray, auto-pausa su inattività e quando il PC è bloccato. Niente cattura di ciò che non vuoi." },
  { icon: Lock, title: "Blocklist app", desc: "Escludi app sensibili (password manager, home banking) con pattern glob o substring." },
];

const PII: [string, string][] = [
  ["Carta di credito", "[CARTA]"],
  ["IBAN", "[IBAN]"],
  ["Codice fiscale", "[CF]"],
  ["Email", "[EMAIL]"],
  ["Telefono", "[TEL]"],
];

export default function PrivacyPage() {
  return (
    <>
      <Section className="pb-8">
        <SectionHeading
          eyebrow="privacy"
          title={<>I tuoi ricordi restano <span className="text-emerald">tuoi</span></>}
          desc="Déjà è progettato per non aver mai bisogno del cloud. Questa pagina spiega cosa succede ai tuoi dati — cioè quasi niente, perché non si muovono."
        />
        <div className="grid gap-5 sm:grid-cols-2">
          {PILLARS.map((p, i) => {
            const Icon = p.icon;
            return (
              <Reveal key={p.title} delay={i * 0.05}>
                <Card spotlight className="h-full p-6">
                  <Icon className="mb-3 h-6 w-6 text-emerald" />
                  <h3 className="mb-1.5 text-lg font-semibold">{p.title}</h3>
                  <p className="text-sm leading-relaxed text-fg-muted">{p.desc}</p>
                </Card>
              </Reveal>
            );
          })}
        </div>
      </Section>

      <Section className="py-8">
        <div className="grid items-center gap-10 lg:grid-cols-2">
          <Reveal>
            <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-6">
              <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold">
                <ScanLine className="h-5 w-5 text-emerald" /> Cosa viene oscurato
              </h3>
              <div className="space-y-2">
                {PII.map(([label, token]) => (
                  <div key={label} className="flex items-center justify-between rounded-lg bg-white/[0.02] px-3 py-2 text-sm">
                    <span className="text-fg-muted">{label}</span>
                    <code className="rounded bg-emerald/15 px-2 py-0.5 font-mono text-xs text-emerald">{token}</code>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>
          <Reveal dir="left">
            <div className="space-y-4">
              <h3 className="flex items-center gap-2 text-xl font-semibold">
                <Database className="h-5 w-5 text-violet" /> Dove vivono i dati
              </h3>
              <ul className="space-y-3 text-sm text-fg-muted">
                <li className="flex gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald" /> SQLite locale (<code className="font-mono text-violet">deja.db</code>) in modalità WAL, sul tuo disco.</li>
                <li className="flex gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald" /> Screenshot come JPEG compressi, audio come OPUS, embedding int8.</li>
                <li className="flex gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald" /> Backup e restore sono file zip che controlli tu.</li>
                <li className="flex gap-3"><Lock className="mt-0.5 h-4 w-4 shrink-0 text-amber" /> La chat AI esce solo se la attivi con la tua API key.</li>
                <li className="flex gap-3"><Lock className="mt-0.5 h-4 w-4 shrink-0 text-amber" /> La Vision (Gemini) invia l&apos;immagine a Google: è off di default, con avviso esplicito.</li>
              </ul>
            </div>
          </Reveal>
        </div>
      </Section>

      <Section className="pt-8">
        <Reveal>
          <div className="mx-auto max-w-3xl rounded-2xl border border-white/[0.07] bg-white/[0.02] p-6 text-sm leading-relaxed text-fg-muted">
            <h3 className="mb-3 text-base font-semibold text-fg">Nota sul sito</h3>
            <p>
              Questo sito raccoglie solo ciò che gli dai: email per la waitlist,
              dati account se ti registri, messaggi che invii dal form contatti.
              Le password sono salvate con hash bcrypt; la 2FA usa TOTP. Niente
              tracker di terze parti.
            </p>
          </div>
        </Reveal>
      </Section>
    </>
  );
}
