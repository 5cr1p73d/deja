import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import {
  Camera,
  Search as SearchIcon,
  Bot,
  Eye,
  ShieldCheck,
  Gauge,
  LayoutDashboard,
  Check,
  ArrowRight,
  Download,
  type LucideIcon,
} from "lucide-react";
import { Section, SectionHeading } from "@/components/site/section";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Reveal, StaggerGroup, staggerItem } from "@/components/motion/reveal";
import { MotionItem } from "@/components/landing/motion-item";

export const metadata: Metadata = {
  title: "Funzionalità",
  description: "Tutte le funzionalità di Déjà: cattura, ricerca semantica, AI, Vision, privacy, performance.",
};

type Tone = "violet" | "emerald" | "amber";

const HL_ICONS: LucideIcon[] = [Eye, SearchIcon, Bot];
const HL_TONES: Tone[] = ["amber", "violet", "emerald"];

const CAT_META: Record<string, { icon: LucideIcon; tone: Tone }> = {
  capture: { icon: Camera, tone: "emerald" },
  search: { icon: SearchIcon, tone: "violet" },
  ai: { icon: Bot, tone: "violet" },
  ask: { icon: Eye, tone: "amber" },
  privacy: { icon: ShieldCheck, tone: "emerald" },
  perf: { icon: Gauge, tone: "amber" },
  ui: { icon: LayoutDashboard, tone: "violet" },
};

const TONE_BG: Record<Tone, string> = {
  violet: "bg-violet/15 text-violet",
  emerald: "bg-emerald/15 text-emerald",
  amber: "bg-amber/15 text-amber",
};
const TONE_CHECK: Record<Tone, string> = {
  violet: "text-violet",
  emerald: "text-emerald",
  amber: "text-amber",
};
const TONE_GLOW: Record<Tone, string> = {
  violet: "shadow-glow",
  emerald: "shadow-glow-emerald",
  amber: "shadow-glow-amber",
};

export default async function FeaturesPage() {
  const t = await getTranslations("featuresPage");
  const tc = await getTranslations("common");
  const highlights = t.raw("highlights") as { title: string; desc: string }[];
  const categories = t.raw("categories") as { key: string; title: string; items: string[] }[];

  return (
    <>
      <Section className="pb-8">
        <SectionHeading eyebrow={t("eyebrow")} title={t("title")} desc={t("desc")} />

        {/* highlights wow */}
        <div className="grid gap-5 md:grid-cols-3">
          {highlights.map((h, i) => {
            const Icon = HL_ICONS[i] ?? Eye;
            const tone = HL_TONES[i] ?? "violet";
            return (
              <Reveal key={h.title} delay={i * 0.06}>
                <Card spotlight className={`h-full p-6 ${TONE_GLOW[tone]}`}>
                  <div className={`mb-4 inline-grid h-12 w-12 place-items-center rounded-xl ${TONE_BG[tone]}`}>
                    <Icon className="h-6 w-6" />
                  </div>
                  <h3 className="mb-2 text-lg font-semibold">{h.title}</h3>
                  <p className="text-sm leading-relaxed text-fg-muted">{h.desc}</p>
                </Card>
              </Reveal>
            );
          })}
        </div>
      </Section>

      {/* categorie */}
      <Section className="pt-0">
        <StaggerGroup className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {categories.map((cat) => {
            const meta = CAT_META[cat.key] ?? { icon: LayoutDashboard, tone: "violet" as Tone };
            const Icon = meta.icon;
            return (
              <MotionItem key={cat.key} variants={staggerItem}>
                <Card spotlight className="flex h-full flex-col p-6">
                  <div className="mb-4 flex items-center gap-3">
                    <span className={`grid h-10 w-10 place-items-center rounded-xl ${TONE_BG[meta.tone]}`}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <h3 className="text-base font-semibold">{cat.title}</h3>
                  </div>
                  <ul className="space-y-2.5">
                    {cat.items.map((it) => (
                      <li key={it} className="flex items-start gap-2.5 text-sm text-fg-muted">
                        <Check className={`mt-0.5 h-4 w-4 shrink-0 ${TONE_CHECK[meta.tone]}`} />
                        <span>{it}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              </MotionItem>
            );
          })}
        </StaggerGroup>
      </Section>

      {/* CTA */}
      <Section className="pt-0">
        <Reveal>
          <div className="border-gradient relative overflow-hidden rounded-3xl p-10 text-center sm:p-14">
            <div className="absolute inset-0 -z-10 bg-radial-violet opacity-60" />
            <h2 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{t("ctaTitle")}</h2>
            <p className="mx-auto mt-3 max-w-md text-fg-muted">{t("ctaDesc")}</p>
            <div className="mt-7 flex flex-wrap justify-center gap-3">
              <Button href="/download" size="lg">
                <Download className="h-4 w-4" /> {tc("download")}
              </Button>
              <Button href="/#how" variant="outline" size="lg">
                {tc("howItWorks")} <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Reveal>
      </Section>
    </>
  );
}
