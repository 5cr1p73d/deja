"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export function WaitlistForm({ compact = false }: { compact?: boolean }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState<null | number>(null);
  const toast = useToast();
  const t = useTranslations("waitlist");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, platform: "windows" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || t("error"));
      setDone(data.position ?? 0);
      toast(t("joined") + " " + t("noSpam"), "ok");
    } catch (err) {
      toast(err instanceof Error ? err.message : t("error"), "error");
    } finally {
      setLoading(false);
    }
  }

  if (done !== null) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-emerald/25 bg-emerald/10 px-4 py-3 text-sm">
        <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald" />
        <span className="text-fg">
          {t("joined")}{" "}
          {done > 0 && (
            <>{t("position")} <span className="font-mono text-emerald">#{done}</span>.</>
          )}{" "}
          {t("noSpam")}
        </span>
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      className={`flex w-full gap-2 ${compact ? "" : "max-w-md"} flex-col sm:flex-row`}
    >
      <div className="relative flex-1">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-sm text-fg-dim">
          {">"}
        </span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("placeholder")}
          className="h-12 w-full rounded-xl border border-white/10 bg-white/[0.04] pl-8 pr-3 font-mono text-sm text-fg placeholder:text-fg-dim focus:border-violet/60 focus:outline-none"
        />
      </div>
      <Button type="submit" size="lg" loading={loading} className="shrink-0">
        {t("join")} <ArrowRight className="h-4 w-4" />
      </Button>
    </form>
  );
}
