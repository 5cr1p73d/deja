import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Logo } from "@/components/site/logo";
import { Badge } from "@/components/ui/badge";

export async function Footer() {
  const t = await getTranslations("footer");
  const l = (k: string) => t(`links.${k}`);

  const cols: { title: string; links: { href: string; label: string }[] }[] = [
    {
      title: t("product"),
      links: [
        { href: "/funzionalita", label: l("features") },
        { href: "/download", label: l("download") },
        { href: "/changelog", label: l("changelog") },
        { href: "/docs", label: l("documentation") },
      ],
    },
    {
      title: t("resources"),
      links: [
        { href: "/docs#architettura", label: l("architecture") },
        { href: "/docs#ai", label: l("aiRag") },
        { href: "/privacy", label: l("privacy") },
        { href: "/contatti", label: l("contact") },
      ],
    },
    {
      title: t("account"),
      links: [
        { href: "/login", label: l("login") },
        { href: "/register", label: l("register") },
        { href: "/account", label: l("myAccount") },
      ],
    },
  ];

  return (
    <footer className="relative z-10 border-t border-white/[0.06] bg-ink-950/40">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-10 px-5 py-14 md:grid-cols-5">
        <div className="col-span-2">
          <Logo />
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-fg-muted">{t("tagline")}</p>
          <div className="mt-4">
            <Badge tone="emerald">● {t("onDevice")}</Badge>
          </div>
        </div>
        {cols.map((c) => (
          <div key={c.title}>
            <h4 className="mb-3 font-mono text-xs uppercase tracking-wider text-fg-dim">{c.title}</h4>
            <ul className="space-y-2">
              {c.links.map((lnk) => (
                <li key={lnk.href + lnk.label}>
                  <Link href={lnk.href} className="text-sm text-fg-muted transition hover:text-fg">
                    {lnk.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-white/[0.06]">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 py-5 text-xs text-fg-dim sm:flex-row">
          <p className="font-mono">
            © {new Date().getFullYear()} Déjà · {t("builtBy")}{" "}
            <span className="text-violet">Scr1p73d</span>
          </p>
          <p className="font-mono">
            PyQt6 · SQLite + sqlite-vec · Whisper · sentence-transformers
          </p>
        </div>
      </div>
    </footer>
  );
}
