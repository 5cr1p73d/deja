"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { AnimatePresence, motion } from "framer-motion";
import { Search, Image as ImageIcon, Mic, Sparkles, CornerDownLeft } from "lucide-react";
import { cn, stringHue } from "@/lib/utils";

type Item = {
  id: number;
  kind: "ss" | "au";
  app: string;
  text: string;
  ago: string;
  tags: string[];
};

// Dataset finto ma realistico (mostra cosa Déjà indicizza).
const DATA: Item[] = [
  { id: 101, kind: "ss", app: "VS Code", text: "TypeError: cannot read property 'map' of undefined in checkout.tsx", ago: "12 min fa", tags: ["bug", "react"] },
  { id: 88, kind: "au", app: "Meet", text: "decidiamo di spostare la release di Déjà a venerdì, blocco sul modulo audio", ago: "2h fa", tags: ["riunione"] },
  { id: 142, kind: "ss", app: "Chrome", text: "documentazione sqlite-vec: int8 quantization e distance_metric cosine", ago: "ieri", tags: ["ricerca"] },
  { id: 77, kind: "au", app: "Microfono", text: "promemoria: chiamare la banca per il bonifico IBAN entro lunedì", ago: "ieri", tags: ["todo"] },
  { id: 39, kind: "ss", app: "Figma", text: "palette colori: violet a78bfa, emerald 10b981, amber f59e0b sfondo 0e0e12", ago: "3 giorni fa", tags: ["design"] },
  { id: 51, kind: "ss", app: "Terminal", text: "git rebase -i HEAD~3 poi force push sul branch feature/whisper", ago: "4 giorni fa", tags: ["git"] },
  { id: 64, kind: "au", app: "Sistema", text: "tutorial: come configurare faster-whisper large v3 turbo su CPU int8", ago: "5 giorni fa", tags: ["audio", "ml"] },
];

const PRESETS = ["bug react", "release venerdì", "sqlite vettori", "iban banca"];

function score(item: Item, q: string): number {
  if (!q.trim()) return 0;
  const tokens = q.toLowerCase().split(/\s+/).filter(Boolean);
  const hay = (item.text + " " + item.app + " " + item.tags.join(" ")).toLowerCase();
  let s = 0;
  for (const t of tokens) {
    if (hay.includes(t)) s += 0.5;
    // match parziale (fuzzy leggero)
    else if (hay.split(/\W+/).some((w) => w.startsWith(t.slice(0, 3)) && t.length >= 3)) s += 0.22;
  }
  return Math.min(0.99, s / tokens.length + (hay.includes(q.toLowerCase()) ? 0.3 : 0));
}

function highlight(text: string, q: string) {
  const tokens = q.toLowerCase().split(/\s+/).filter((t) => t.length >= 2);
  if (!tokens.length) return text;
  const re = new RegExp(`(${tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).map((part, i) =>
    tokens.includes(part.toLowerCase()) ? (
      <mark key={i} className="rounded bg-violet/25 px-0.5 text-violet-soft">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

export function SearchDemo() {
  const [q, setQ] = useState("bug react");
  const [filter, setFilter] = useState<"all" | "ss" | "au">("all");

  const results = useMemo(() => {
    return DATA.map((d) => ({ d, s: score(d, q) }))
      .filter(({ s }) => s > 0.15)
      .filter(({ d }) => filter === "all" || d.kind === filter)
      .sort((a, b) => b.s - a.s);
  }, [q, filter]);

  const counts = useMemo(
    () => ({
      all: DATA.filter((d) => score(d, q) > 0.15).length,
      ss: DATA.filter((d) => d.kind === "ss" && score(d, q) > 0.15).length,
      au: DATA.filter((d) => d.kind === "au" && score(d, q) > 0.15).length,
    }),
    [q]
  );

  const t = useTranslations("searchDemo");

  return (
    <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-ink-850/80 shadow-card backdrop-blur-xl">
      {/* barra ricerca */}
      <div className="flex items-center gap-3 border-b border-white/[0.06] px-4 py-3">
        <Search className="h-4 w-4 text-fg-muted" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("placeholder")}
          className="flex-1 bg-transparent text-sm text-fg placeholder:text-fg-dim focus:outline-none"
        />
        <kbd className="hidden items-center gap-1 rounded-md border border-white/10 bg-white/[0.04] px-2 py-1 font-mono text-[10px] text-fg-dim sm:flex">
          <CornerDownLeft className="h-3 w-3" /> {t("enter")}
        </kbd>
      </div>

      {/* pills */}
      <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.06] px-4 py-2.5">
        {([
          ["all", t("all"), counts.all],
          ["ss", t("screens"), counts.ss],
          ["au", t("audio"), counts.au],
        ] as const).map(([k, label, n]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition",
              filter === k
                ? "border-violet/40 bg-violet/15 text-violet"
                : "border-white/10 text-fg-muted hover:text-fg"
            )}
          >
            {label}
            <span className="font-mono text-[10px] opacity-70">{n}</span>
          </button>
        ))}
        <span className="ml-auto flex items-center gap-1 font-mono text-[11px] text-fg-dim">
          <Sparkles className="h-3 w-3 text-violet" /> {t("semantic")}
        </span>
      </div>

      {/* risultati */}
      <div className="min-h-[260px] divide-y divide-white/[0.04]">
        <AnimatePresence mode="popLayout">
          {results.map(({ d, s }, idx) => {
            const hue = stringHue(d.app);
            return (
              <motion.div
                key={d.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.25, delay: idx * 0.03 }}
                className="group flex items-start gap-3 px-4 py-3 hover:bg-white/[0.02]"
              >
                <span
                  className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg font-mono text-xs font-semibold"
                  style={{
                    background: `hsl(${hue} 60% 50% / 0.18)`,
                    color: `hsl(${hue} 70% 72%)`,
                  }}
                >
                  {d.kind === "ss" ? <ImageIcon className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-xs text-fg-dim">
                    <span className="font-medium text-fg-muted">{d.app}</span>
                    <span>·</span>
                    <span>{d.ago}</span>
                    <span
                      className={cn(
                        "ml-1 rounded px-1 font-mono text-[10px]",
                        d.kind === "ss" ? "text-emerald" : "text-amber"
                      )}
                    >
                      {d.kind === "ss" ? "screenshot" : "audio"}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate text-sm text-fg/90">{highlight(d.text, q)}</p>
                </div>
                <div className="hidden w-16 shrink-0 flex-col items-end gap-1 pt-1 sm:flex">
                  <span className="font-mono text-[10px] text-violet">{(s * 100).toFixed(0)}%</span>
                  <span className="h-1 w-full overflow-hidden rounded-full bg-white/10">
                    <span className="block h-full rounded-full bg-violet" style={{ width: `${s * 100}%` }} />
                  </span>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {results.length === 0 && (
          <div className="grid place-items-center px-4 py-16 text-center text-sm text-fg-dim">
            {t("empty")}
          </div>
        )}
      </div>

      {/* preset */}
      <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.06] px-4 py-3">
        <span className="font-mono text-[11px] text-fg-dim">{t("try")}</span>
        {PRESETS.map((p) => (
          <button
            key={p}
            onClick={() => setQ(p)}
            className="rounded-md border border-white/10 px-2 py-1 font-mono text-[11px] text-fg-muted transition hover:border-violet/40 hover:text-violet"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}
