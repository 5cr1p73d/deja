"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
      <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.4-1.6 4.1-5.5 4.1-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.9 2.9 14.7 2 12 2 6.9 2 2.8 6.1 2.8 11.2S6.9 20.4 12 20.4c5.6 0 9.3-3.9 9.3-9.4 0-.6-.1-1.1-.2-1.6H12z" />
    </svg>
  );
}
function AppleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 fill-fg" aria-hidden>
      <path d="M16.4 12.8c0-2.2 1.8-3.3 1.9-3.3-1-1.5-2.6-1.7-3.2-1.7-1.4-.1-2.6.8-3.3.8-.7 0-1.7-.8-2.8-.8-1.4 0-2.8.8-3.5 2.1-1.5 2.6-.4 6.4 1.1 8.5.7 1 1.5 2.2 2.6 2.1 1-.04 1.4-.7 2.7-.7 1.2 0 1.6.7 2.7.6 1.1 0 1.8-1 2.5-2 .8-1.2 1.1-2.3 1.1-2.4-.02-.01-2.1-.8-2.1-3.2zM14.6 6.3c.6-.7 1-1.7.9-2.6-.8.03-1.9.5-2.5 1.2-.5.6-1 1.6-.9 2.5.9.07 1.8-.4 2.5-1.1z" />
    </svg>
  );
}

export function OAuthButtons({
  google,
  apple,
  callbackUrl = "/account",
}: {
  google: boolean;
  apple: boolean;
  callbackUrl?: string;
}) {
  const [loading, setLoading] = useState<string | null>(null);
  const t = useTranslations("auth");
  if (!google && !apple) return null;

  function go(provider: "google" | "apple") {
    setLoading(provider);
    signIn(provider, { callbackUrl });
  }

  return (
    <div className="space-y-2.5">
      {google && (
        <button
          onClick={() => go("google")}
          disabled={!!loading}
          className={cn(
            "flex h-11 w-full items-center justify-center gap-2.5 rounded-xl border border-white/10 bg-white/[0.04] text-sm font-medium transition hover:bg-white/[0.08] disabled:opacity-50"
          )}
        >
          {loading === "google" ? <Loader2 className="h-4 w-4 animate-spin" /> : <GoogleIcon />}
          {t("continueGoogle")}
        </button>
      )}
      {apple && (
        <button
          onClick={() => go("apple")}
          disabled={!!loading}
          className="flex h-11 w-full items-center justify-center gap-2.5 rounded-xl border border-white/10 bg-white/[0.04] text-sm font-medium transition hover:bg-white/[0.08] disabled:opacity-50"
        >
          {loading === "apple" ? <Loader2 className="h-4 w-4 animate-spin" /> : <AppleIcon />}
          {t("continueApple")}
        </button>
      )}
    </div>
  );
}
