"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useTranslations } from "next-intl";
import { ArrowRight, Download, ShieldCheck, Cpu, HardDrive } from "lucide-react";
import { Terminal } from "@/components/site/terminal";
import { Button } from "@/components/ui/button";
import { Magnetic } from "@/components/motion/magnetic";
import { Typewriter } from "@/components/motion/typewriter";

const lines: { p: string; t: string; c?: string }[] = [
  { p: "deja@local", t: "~ status", c: "" },
  { p: "", t: "● capture   screenshot+OCR    1 fps   ok", c: "text-emerald" },
  { p: "", t: "● audio     mic + loopback    whisper ok", c: "text-amber" },
  { p: "", t: "● indexer   embeddings 768d   sqlite-vec", c: "text-violet" },
  { p: "deja@local", t: "~ search \"quando ho parlato della release?\"", c: "" },
  { p: "", t: "→ [au:88] Meet · 2h fa · score 0.91", c: "text-fg-muted" },
  { p: "", t: '  "spostiamo la release di Déjà a venerdì…"', c: "text-fg/80" },
];

export function Hero() {
  const reduce = useReducedMotion();
  const t = useTranslations("hero");
  const tc = useTranslations("common");
  const words = t.raw("words") as string[];
  return (
    <section className="relative mx-auto max-w-6xl px-5 pb-10 pt-20 sm:pt-28">
      <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_1fr]">
        {/* sinistra */}
        <div>
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 font-mono text-xs text-fg-muted"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-emerald" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald" />
            </span>
            {t("badge")}
          </motion.div>

          <h1 className="text-balance text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            {t("titleLine1")}
            <br />
            <span className="text-gradient">{t("remembers")}</span>{" "}
            <Typewriter className="text-gradient-violet" words={words} />
          </h1>

          <p className="mt-6 max-w-xl text-pretty text-lg leading-relaxed text-fg-muted">
            {t("subtitlePre")} <span className="text-fg">{t("inLocal")}</span>
            {t("subtitlePost")}
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Magnetic>
              <Button href="/download" size="lg">
                <Download className="h-4 w-4" /> {tc("downloadWindows")}
              </Button>
            </Magnetic>
            <Button href="/#how" variant="outline" size="lg">
              {tc("howItWorks")} <ArrowRight className="h-4 w-4" />
            </Button>
          </div>

          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-fg-dim">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald" /> {t("trustNoCloud")}
            </span>
            <span className="flex items-center gap-1.5">
              <HardDrive className="h-3.5 w-3.5 text-violet" /> {t("trustData")}
            </span>
            <span className="flex items-center gap-1.5">
              <Cpu className="h-3.5 w-3.5 text-amber" /> {t("trustDevice")}
            </span>
          </div>
        </div>

        {/* destra: terminale */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
          className="relative"
        >
          <div className="absolute -inset-6 -z-10 bg-radial-violet blur-2xl" />
          <Terminal title="deja — ~/memory" glow tabs={["status", "search", "ai"]}>
            <div className="space-y-1">
              {lines.map((l, i) => (
                <motion.div
                  key={i}
                  initial={reduce ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.4 + i * 0.35, duration: 0.3 }}
                  className="flex gap-2"
                >
                  {l.p && <span className="shrink-0 text-violet">{l.p}</span>}
                  {l.p && <span className="shrink-0 text-fg-dim">$</span>}
                  <span className={l.c || "text-fg/90"}>{l.t}</span>
                </motion.div>
              ))}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.4 + lines.length * 0.35 }}
                className="flex gap-2 pt-1"
              >
                <span className="text-violet">deja@local</span>
                <span className="text-fg-dim">$</span>
                <span className="inline-block h-4 w-2 animate-caret-blink bg-violet" />
              </motion.div>
            </div>
          </Terminal>
        </motion.div>
      </div>
    </section>
  );
}
