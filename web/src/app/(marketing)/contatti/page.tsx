import type { Metadata } from "next";
import { Mail, Github, MessageSquare } from "lucide-react";
import { Section, SectionHeading } from "@/components/site/section";
import { Reveal } from "@/components/motion/reveal";
import { ContactForm } from "@/components/landing/contact-form";

export const metadata: Metadata = {
  title: "Contatti",
  description: "Scrivi a chi costruisce Déjà.",
};

export default function ContattiPage() {
  return (
    <Section className="max-w-4xl">
      <SectionHeading
        eyebrow="contatti"
        title="Parliamone"
        desc="Bug, idee, collaborazioni: scrivi pure. Arriva dritto alla dashboard admin."
      />
      <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <Reveal>
          <div className="space-y-4">
            {[
              { icon: MessageSquare, t: "Feedback prodotto", d: "Cosa ti manca? Cosa ami?" },
              { icon: Github, t: "Tecnico", d: "Architettura, moduli, performance." },
              { icon: Mail, t: "Tutto il resto", d: "Risposta in genere entro pochi giorni." },
            ].map((c) => {
              const Icon = c.icon;
              return (
                <div key={c.t} className="flex items-start gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-violet" />
                  <div>
                    <h4 className="font-medium">{c.t}</h4>
                    <p className="text-sm text-fg-muted">{c.d}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </Reveal>
        <Reveal dir="left">
          <ContactForm />
        </Reveal>
      </div>
    </Section>
  );
}
