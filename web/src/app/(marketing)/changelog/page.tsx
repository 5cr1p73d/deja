import type { Metadata } from "next";
import { Section, SectionHeading } from "@/components/site/section";
import { Reveal } from "@/components/motion/reveal";
import { Badge } from "@/components/ui/badge";

export const metadata: Metadata = {
  title: "Changelog",
  description: "L'evoluzione di Déjà, fase per fase.",
};

const PHASES: { v: string; title: string; tone: "violet" | "emerald" | "amber"; items: string[] }[] = [
  { v: "Fase 0", title: "Base cattura & ricerca", tone: "emerald", items: ["Screenshot + OCR loop", "Audio mic + loopback con Whisper", "Embedding multilingue mpnet", "Ricerca semantica base", "Overlay PyQt6 con hotkey"] },
  { v: "Fase 1", title: "Integrazione AI", tone: "violet", items: ["Client OpenAI-compatibile", "Tool calling: search / list / stats", "chat_stream + RAG inline", "Tab AI nei Settings"] },
  { v: "Fase 2", title: "Persistenza & qualità", tone: "violet", items: ["Settings e chat history su DB", "Fuzzy exact tokenize", "Indice ts DESC", "Cache LRU embedding", "VACUUM allo shutdown"] },
  { v: "Fase 3", title: "UX polish I", tone: "amber", items: ["Timestamp relativi", "Match highlight <mark>", "Filter pills con badge", "Navigazione da tastiera"] },
  { v: "Fase 4", title: "Card AI inline", tone: "violet", items: ["Sorgenti interagibili ss/au", "Card dentro la bolla assistant", "Parser _split_text_refs"] },
  { v: "Fase 5", title: "Performance", tone: "amber", items: ["Quantizzazione int8 sqlite-vec", "Migrazione legacy → vec0", "Voice input chat", "Cross-reference ±5 min", "Daily summary con cache"] },
  { v: "Fase 6", title: "Extra UI", tone: "amber", items: ["Toast notifications", "Skeleton shimmer", "Export markdown", "Backup/restore zip", "Drag&drop immagine → OCR"] },
  { v: "Fase 7", title: "Privacy", tone: "emerald", items: ["Auto-pausa idle/lock", "Blocklist app fnmatch", "Submenu privacy nel tray", "Redazione PII via regex"] },
  { v: "Fase 8", title: "Discovery", tone: "violet", items: ["Cronologia ricerche", "Filtro app in sidebar", "Pinned memories", "Tag manuali", "Filtri avanzati (data, app, tag)"] },
  { v: "Fase 9", title: "Polish visivo II", tone: "amber", items: ["Avatar con hash colore app", "Header sticky (OGGI/IERI)", "Waveform audio inline", "Sfondo a particelle"] },
  { v: "Fase 10", title: "Affidabilità audio", tone: "amber", items: ["Hot-swap device senza restart", "Watchdog heartbeat 5 min", "Voce tray: riavvia audio"] },
  { v: "Fase 11", title: "Diary AI + fix", tone: "violet", items: ["Fix crash Unicode", "Retry 3x backoff su 502/503/504", "DiaryDialog con date picker"] },
  { v: "Fase 13", title: "Ask Screen", tone: "amber", items: ["Cattura istantanea + OCR + AI", "Hotkey Ctrl+Shift+A", "Refactor multi-hotkey", "Snap salvato in timeline"] },
  { v: "Fase 14", title: "Vision (Gemini)", tone: "violet", items: ["Vera vision per Ask Screen", "Endpoint Gemini OpenAI-compat", "Client separato dall'AI testo", "Badge vision · gemini-…", "Disclaimer privacy esplicito"] },
];

export default function ChangelogPage() {
  return (
    <Section>
      <SectionHeading
        eyebrow="changelog"
        title="L'evoluzione di Déjà"
        desc="Quattordici fasi, dalla cattura grezza alla vera vision. Ogni riga è una cosa che prima non c'era."
      />
      <div className="relative mx-auto max-w-3xl">
        <div className="absolute bottom-0 left-[7px] top-2 w-px bg-gradient-to-b from-violet/40 via-white/10 to-transparent sm:left-[calc(7rem+7px)]" />
        <div className="space-y-10">
          {PHASES.map((p, i) => (
            <Reveal key={p.v} delay={Math.min(i * 0.03, 0.2)}>
              <div className="relative flex flex-col gap-3 sm:flex-row sm:gap-6">
                <div className="flex items-center gap-3 sm:w-28 sm:flex-col sm:items-end sm:gap-1 sm:pt-0.5">
                  <span className="font-mono text-sm text-fg-muted">{p.v}</span>
                </div>
                <span className="absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full border-2 border-violet bg-ink-900 sm:left-[calc(7rem)]" />
                <div className="pl-6 sm:pl-8">
                  <div className="mb-2 flex items-center gap-2">
                    <h3 className="text-lg font-semibold">{p.title}</h3>
                    <Badge tone={p.tone}>{p.items.length} novità</Badge>
                  </div>
                  <ul className="space-y-1.5">
                    {p.items.map((it) => (
                      <li key={it} className="flex items-start gap-2 text-sm text-fg-muted">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-violet/70" />
                        {it}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </Section>
  );
}
