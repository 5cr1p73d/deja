"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { AnimatePresence, motion } from "framer-motion";
import { Globe, Check, Loader2 } from "lucide-react";
import { locales, localeNames, localeFlags, type Locale } from "@/i18n/config";
import { cn } from "@/lib/utils";

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const locale = useLocale() as Locale;
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();

  function pick(l: Locale) {
    document.cookie = `NEXT_LOCALE=${l}; path=/; max-age=31536000; samesite=lax`;
    setOpen(false);
    start(() => router.refresh());
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-2 text-sm text-fg-muted transition hover:bg-white/[0.08] hover:text-fg",
          compact && "w-full justify-center"
        )}
        aria-label="Change language"
      >
        {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
        <span className="font-mono text-xs uppercase">{locale}</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.97 }}
            transition={{ duration: 0.16 }}
            className={cn(
              "absolute z-50 mt-2 w-40 overflow-hidden rounded-xl border border-white/10 bg-ink-800/95 p-1 backdrop-blur-xl",
              compact ? "left-0" : "right-0"
            )}
            onMouseLeave={() => setOpen(false)}
          >
            {locales.map((l) => (
              <button
                key={l}
                onClick={() => pick(l)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition hover:bg-white/[0.06]",
                  l === locale ? "text-fg" : "text-fg-muted"
                )}
              >
                <span>{localeFlags[l]}</span>
                <span className="flex-1 text-left">{localeNames[l]}</span>
                {l === locale && <Check className="h-3.5 w-3.5 text-violet" />}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
