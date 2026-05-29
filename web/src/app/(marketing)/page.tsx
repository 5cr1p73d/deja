import {
  Camera,
  Search as SearchIcon,
  Bot,
  ShieldCheck,
  Gauge,
  Eye,
  Lock,
  EyeOff,
  CircleSlash,
  Pause,
  ScanLine,
  ArrowRight,
} from "lucide-react";
import { getTranslations } from "next-intl/server";
import { Hero } from "@/components/landing/hero";
import { SearchDemo } from "@/components/landing/search-demo";
import { FAQ } from "@/components/landing/faq";
import { WaitlistForm } from "@/components/landing/waitlist-form";
import { Section, SectionHeading } from "@/components/site/section";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Terminal } from "@/components/site/terminal";
import { CodeBlock } from "@/components/site/code-block";
import { Reveal, StaggerGroup, staggerItem } from "@/components/motion/reveal";
import { CountUp } from "@/components/motion/count-up";
import { MotionItem } from "@/components/landing/motion-item";

const FEATURES = [
  { icon: Camera, tone: "emerald" as const, key: "capture", tags: ["MSS", "Tesseract", "pyaudiowpatch"] },
  { icon: SearchIcon, tone: "violet" as const, key: "search", tags: ["sqlite-vec", "mpnet", "int8"] },
  { icon: Bot, tone: "violet" as const, key: "ai", tags: ["Qwen3-235B", "Kimi-K2.6", "tools"] },
  { icon: Eye, tone: "amber" as const, key: "ask", tags: ["Ctrl+Shift+A", "Gemini Vision"] },
  { icon: ShieldCheck, tone: "emerald" as const, key: "privacy", tags: ["idle-pause", "blocklist", "PII redaction"] },
  { icon: Gauge, tone: "amber" as const, key: "perf", tags: ["WAL", "LRU", "backup"] },
];

const PRIVACY_ICONS = [CircleSlash, Pause, EyeOff, Lock, ScanLine];
const HOW_STEPS = [
  { key: "capture", tone: "emerald" },
  { key: "index", tone: "violet" },
  { key: "search", tone: "amber" },
  { key: "ask", tone: "violet" },
];
const AI_TOOLS = [
  ["search_memories", "search"],
  ["list_recent", "recent"],
  ["list_by_date_range", "range"],
  ["memory_stats", "stats"],
] as const;

const PIPELINE = `# pipeline di cattura → indicizzazione → ricerca
screen = mss.grab(monitor)                 # screenshot multi-monitor
if sha256(screen) == last: skip            # dedup frame identici
text = tesseract.ocr(screen, "ita+eng")    # OCR
text = privacy.redact_pii(text)            # carte, IBAN, CF...
db.insert(screenshots, ts, app, text)

vec = model.encode(text, normalize=True)   # 768-dim multilingue
db.insert(vec_screenshots, quantize_int8(vec))

hits = search.query("quando ho parlato della release?", top_k=10)`;

export default async function HomePage() {
  const tf = await getTranslations("features");
  const th = await getTranslations("how");
  const ts = await getTranslations("searchDemo");
  const tp = await getTranslations("privacySection");
  const ta = await getTranslations("aiSection");
  const tst = await getTranslations("stats");
  const tfaq = await getTranslations("faq");
  const tcta = await getTranslations("cta");
  const tc = await getTranslations("common");
  const privacyPoints = tp.raw("points") as string[];

  return (
    <>
      <Hero />

      {/* stack marquee */}
      <div className="mask-fade-x border-y border-white/[0.06] py-4">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-8 gap-y-2 px-5 font-mono text-xs text-fg-dim">
          {["PyQt6","SQLite + sqlite-vec","faster-whisper","Tesseract OCR","sentence-transformers","OpenAI SDK","Gemini Vision","MSS"].map(
            (t) => (
              <span key={t} className="transition hover:text-fg-muted">{t}</span>
            )
          )}
        </div>
      </div>

      {/* FEATURES */}
      <Section id="features">
        <SectionHeading eyebrow={tf("eyebrow")} title={tf("title")} desc={tf("desc")} />
        <StaggerGroup className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <MotionItem key={f.key} variants={staggerItem}>
                <Card spotlight className="h-full p-6">
                  <div
                    className={`mb-4 inline-grid h-11 w-11 place-items-center rounded-xl ${
                      f.tone === "emerald"
                        ? "bg-emerald/15 text-emerald"
                        : f.tone === "amber"
                        ? "bg-amber/15 text-amber"
                        : "bg-violet/15 text-violet"
                    }`}
                  >
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="mb-2 text-lg font-semibold">{tf(`cards.${f.key}.title`)}</h3>
                  <p className="text-sm leading-relaxed text-fg-muted">{tf(`cards.${f.key}.desc`)}</p>
                  <div className="mt-4 flex flex-wrap gap-1.5">
                    {f.tags.map((t) => (
                      <span key={t} className="chip">{t}</span>
                    ))}
                  </div>
                </Card>
              </MotionItem>
            );
          })}
        </StaggerGroup>
      </Section>

      {/* HOW IT WORKS */}
      <Section id="how">
        <SectionHeading eyebrow={th("eyebrow")} title={th("title")} desc={th("desc")} align="left" />
        <div className="grid items-start gap-8 lg:grid-cols-2">
          <Reveal dir="right">
            <ol className="space-y-5">
              {HOW_STEPS.map((s, i) => (
                <li key={s.key} className="flex gap-4">
                  <span
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border font-mono text-sm ${
                      s.tone === "emerald"
                        ? "border-emerald/30 text-emerald"
                        : s.tone === "amber"
                        ? "border-amber/30 text-amber"
                        : "border-violet/30 text-violet"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <div>
                    <h4 className="font-semibold">{th(`steps.${s.key}.title`)}</h4>
                    <p className="mt-0.5 text-sm text-fg-muted">{th(`steps.${s.key}.desc`)}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Reveal>
          <Reveal dir="left" delay={0.1}>
            <CodeBlock code={PIPELINE} filename="pipeline.py" />
          </Reveal>
        </div>
      </Section>

      {/* SEARCH DEMO */}
      <Section>
        <SectionHeading
          eyebrow={ts("eyebrow")}
          title={<>{ts("titlePre")}<span className="text-gradient-violet">{ts("titleHi")}</span></>}
          desc={ts("desc")}
        />
        <Reveal>
          <SearchDemo />
        </Reveal>
      </Section>

      {/* PRIVACY */}
      <Section>
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <SectionHeading
              eyebrow={tp("eyebrow")}
              align="left"
              title={<>{tp("titlePre")}<span className="text-emerald">{tp("titleHi")}</span></>}
              desc={tp("desc")}
            />
            <StaggerGroup className="space-y-3">
              {privacyPoints.map((point, i) => {
                const Icon = PRIVACY_ICONS[i] ?? CircleSlash;
                return (
                  <MotionItem key={point} variants={staggerItem}>
                    <div className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
                      <Icon className="h-4 w-4 shrink-0 text-emerald" />
                      <span className="text-sm text-fg/90">{point}</span>
                    </div>
                  </MotionItem>
                );
              })}
            </StaggerGroup>
          </div>
          <Reveal dir="left">
            <Terminal title="privacy — pre-capture checks" className="lg:ml-auto">
              <div className="space-y-1 text-[13px]">
                <Line c="text-fg-dim">{"# capturer.py — ordine controlli"}</Line>
                <Line><span className="text-violet">if</span> privacy.is_paused(): <span className="text-fg-dim">continue</span></Line>
                <Line><span className="text-violet">if</span> idle_seconds() {">"} THRESHOLD: <span className="text-fg-dim">continue</span></Line>
                <Line><span className="text-violet">if</span> is_workstation_locked(): <span className="text-fg-dim">continue</span></Line>
                <Line><span className="text-violet">if</span> is_app_blocked(app): <span className="text-fg-dim">continue</span></Line>
                <Line c="text-emerald">{"# → cattura consentita"}</Line>
                <Line>shot = mss.grab(monitor)</Line>
              </div>
            </Terminal>
          </Reveal>
        </div>
      </Section>

      {/* AI */}
      <Section>
        <SectionHeading
          eyebrow={ta("eyebrow")}
          title={<>{ta("titlePre")}<span className="text-gradient-violet">{ta("titleHi")}</span></>}
          desc={ta("desc")}
        />
        <div className="grid items-start gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <Reveal>
            <Terminal title="deja — ~/ai/chat" glow>
              <div className="space-y-3 text-[13px]">
                <div className="flex justify-end">
                  <span className="max-w-[80%] rounded-2xl rounded-br-sm bg-violet/15 px-3 py-2 text-fg/90">
                    {ta("userMsg")}
                  </span>
                </div>
                <div className="text-fg-dim">
                  <span className="text-amber">⚙ tool</span> search_memories(...)
                </div>
                <div className="max-w-[88%] rounded-2xl rounded-bl-sm border border-white/10 bg-white/[0.03] px-3 py-2 text-fg/90">
                  {ta("answer")}{" "}
                  <span className="rounded bg-amber/15 px-1 font-mono text-[11px] text-amber">[au:88]</span>
                </div>
              </div>
            </Terminal>
          </Reveal>
          <StaggerGroup className="grid gap-4">
            {AI_TOOLS.map(([name, key]) => (
              <MotionItem key={name} variants={staggerItem}>
                <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                  <code className="font-mono text-sm text-violet">{name}()</code>
                  <p className="mt-1 text-sm text-fg-muted">{ta(`tools.${key}`)}</p>
                </div>
              </MotionItem>
            ))}
          </StaggerGroup>
        </div>
      </Section>

      {/* STATS */}
      <Section>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { to: 768, label: tst("embedding"), suffix: "" },
            { to: 4, label: tst("compression"), prefix: "~", suffix: "×" },
            { to: 128, label: tst("context"), suffix: "K" },
            { to: 100, label: tst("onDevice"), suffix: "%" },
          ].map((s) => (
            <Reveal key={s.label}>
              <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-6 text-center">
                <div className="font-mono text-3xl font-semibold text-gradient-violet sm:text-4xl">
                  <CountUp to={s.to} prefix={s.prefix} suffix={s.suffix} />
                </div>
                <p className="mt-1 text-xs uppercase tracking-wider text-fg-dim">{s.label}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* FAQ */}
      <Section>
        <SectionHeading eyebrow={tfaq("eyebrow")} title={tfaq("title")} />
        <FAQ />
      </Section>

      {/* CTA */}
      <Section>
        <Reveal>
          <div className="border-gradient relative overflow-hidden rounded-3xl p-10 text-center sm:p-16">
            <div className="absolute inset-0 -z-10 bg-radial-violet opacity-60" />
            <Badge tone="violet" className="mb-4">{tc("earlyAccess")}</Badge>
            <h2 className="mx-auto max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              {tcta("titlePre")}<span className="text-gradient">{tcta("titleHi")}</span>
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-fg-muted">{tcta("desc")}</p>
            <div className="mt-8 flex justify-center">
              <WaitlistForm />
            </div>
            <a
              href="/docs"
              className="mt-6 inline-flex items-center gap-1.5 font-mono text-xs text-fg-muted transition hover:text-violet"
            >
              {tc("readDocs")} <ArrowRight className="h-3 w-3" />
            </a>
          </div>
        </Reveal>
      </Section>
    </>
  );
}

function Line({ children, c }: { children: React.ReactNode; c?: string }) {
  return <div className={c || "text-fg/90"}>{children}</div>;
}
