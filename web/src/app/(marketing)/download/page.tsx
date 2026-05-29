import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import {
  Cpu,
  HardDrive,
  MonitorDown,
  Keyboard,
  Terminal as TermIcon,
  Download,
  Github,
  ShieldAlert,
  ScanLine,
  ArrowRight,
} from "lucide-react";
import { Section, SectionHeading } from "@/components/site/section";
import { Reveal } from "@/components/motion/reveal";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Terminal } from "@/components/site/terminal";
import { CodeBlock } from "@/components/site/code-block";
import { WaitlistForm } from "@/components/landing/waitlist-form";
import { APP_VERSION, DOWNLOAD_URL, REPO_URL, INSTALLER_NAME, INSTALLER_SIZE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Download",
  description: "Scarica Déjà per Windows. Requisiti, installazione e scorciatoie.",
};

const TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/wiki";

export default async function DownloadPage() {
  const t = await getTranslations("download");
  const HOTKEYS: [string, string][] = [
    ["Ctrl + Shift + D", t("hk1")],
    ["Ctrl + Shift + A", t("hk2")],
    ["↑ / ↓", t("hk3")],
    ["Enter", t("hk4")],
    ["Esc", t("hk5")],
  ];
  const REQS = [
    { icon: MonitorDown, k: "OS", v: t("reqOs") },
    { icon: Cpu, k: "CPU", v: t("reqCpu") },
    { icon: HardDrive, k: "Disk", v: t("reqDisk") },
  ];

  return (
    <>
      <Section className="pb-10">
        <SectionHeading
          eyebrow={t("eyebrow")}
          title={<>{t("titlePre")}<span className="text-gradient-violet">{t("titleHi")}</span></>}
          desc={t("desc")}
        />

        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <Reveal>
            <Card spotlight className="flex h-full flex-col justify-between p-8">
              <div>
                <div className="mb-5 flex items-center gap-3">
                  <span className="grid h-12 w-12 place-items-center rounded-xl bg-violet/15 text-violet">
                    <MonitorDown className="h-6 w-6" />
                  </span>
                  <div>
                    <h3 className="text-xl font-semibold">{t("cardName")}</h3>
                    <span className="font-mono text-xs text-fg-dim">{t("cardVersion", { version: APP_VERSION })}</span>
                  </div>
                  <Badge tone="emerald" className="ml-auto">● stable</Badge>
                </div>

                <Button href={DOWNLOAD_URL} target="_blank" rel="noopener noreferrer" size="lg" className="w-full sm:w-auto">
                  <Download className="h-4 w-4" /> {t("cta")}
                </Button>
                <p className="mt-2 font-mono text-xs text-fg-dim">
                  {t("size", { size: INSTALLER_SIZE, file: INSTALLER_NAME })}
                </p>

                <a
                  href={REPO_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center gap-1.5 text-sm text-fg-muted transition hover:text-violet"
                >
                  <Github className="h-4 w-4" /> {t("source")}
                </a>
              </div>

              <div className="mt-6 flex items-start gap-2 rounded-xl border border-amber/20 bg-amber/[0.06] px-4 py-3 text-xs text-fg-muted">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber" />
                {t("smartscreen")}
              </div>
            </Card>
          </Reveal>

          <Reveal dir="left">
            <div className="grid h-full content-start gap-4">
              <h3 className="font-mono text-xs uppercase tracking-wider text-fg-dim">{t("reqTitle")}</h3>
              {REQS.map((r) => {
                const Icon = r.icon;
                return (
                  <div key={r.k} className="flex items-center gap-4 rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                    <Icon className="h-5 w-5 shrink-0 text-violet" />
                    <div>
                      <div className="font-mono text-xs uppercase tracking-wider text-fg-dim">{r.k}</div>
                      <div className="text-sm text-fg/90">{r.v}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Reveal>
        </div>

        {/* steps + tesseract */}
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Reveal>
            <Card className="h-full p-6">
              <h3 className="mb-4 font-semibold">{t("stepsTitle")}</h3>
              <ol className="space-y-3">
                {[t("step1"), t("step2"), t("step3")].map((s, i) => (
                  <li key={i} className="flex gap-3 text-sm text-fg-muted">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-violet/30 font-mono text-xs text-violet">
                      {i + 1}
                    </span>
                    {s}
                  </li>
                ))}
              </ol>
            </Card>
          </Reveal>
          <Reveal dir="left">
            <Card className="flex h-full flex-col justify-between p-6">
              <div className="flex items-start gap-3">
                <ScanLine className="mt-0.5 h-5 w-5 shrink-0 text-emerald" />
                <p className="text-sm leading-relaxed text-fg-muted">{t("tesseract")}</p>
              </div>
              <a
                href={TESSERACT_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-4 inline-flex items-center gap-1.5 font-mono text-xs text-violet hover:underline"
              >
                {t("tesseractLink")} <ArrowRight className="h-3 w-3" />
              </a>
            </Card>
          </Reveal>
        </div>
      </Section>

      <Section className="py-10">
        <div className="grid gap-8 lg:grid-cols-2">
          <Reveal>
            <h3 className="mb-4 flex items-center gap-2 text-xl font-semibold">
              <TermIcon className="h-5 w-5 text-emerald" /> {t("devTitle")}
            </h3>
            <p className="mb-4 text-sm text-fg-muted">{t("devNote")}</p>
            <CodeBlock
              filename="powershell"
              lang="bash"
              showLines={false}
              code={`git clone ${REPO_URL} deja && cd deja
python -m venv venv
venv\\Scripts\\python.exe -m pip install -r requirements.txt
venv\\Scripts\\python.exe main.py`}
            />
          </Reveal>

          <Reveal dir="left">
            <h3 className="mb-4 flex items-center gap-2 text-xl font-semibold">
              <Keyboard className="h-5 w-5 text-amber" /> {t("hotkeysTitle")}
            </h3>
            <Terminal title="hotkeys">
              <div className="space-y-2">
                {HOTKEYS.map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-4">
                    <kbd className="rounded-md border border-white/10 bg-white/[0.05] px-2 py-1 font-mono text-xs text-violet">{k}</kbd>
                    <span className="text-right text-xs text-fg-muted">{v}</span>
                  </div>
                ))}
              </div>
            </Terminal>
          </Reveal>
        </div>
      </Section>

      <Section className="pt-0">
        <Reveal>
          <div className="mx-auto max-w-xl rounded-2xl border border-white/[0.07] bg-white/[0.02] p-6 text-center">
            <p className="mb-4 text-sm text-fg-muted">{t("notify")}</p>
            <div className="flex justify-center">
              <WaitlistForm />
            </div>
          </div>
        </Reveal>
      </Section>
    </>
  );
}
