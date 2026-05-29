"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { Mail, KeyRound, ShieldCheck, ArrowRight, ArrowLeft } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

type Step = "creds" | "2fa";

export function LoginForm({ callbackUrl = "/account" }: { callbackUrl?: string }) {
  const [step, setStep] = useState<Step>("creds");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const toast = useToast();
  const t = useTranslations("auth");
  const tc = useTranslations("common");

  async function doSignIn(otp?: string) {
    const res = await signIn("credentials", {
      email,
      password,
      token: otp ?? "",
      redirect: false,
    });
    if (res?.error) {
      setError(step === "2fa" ? t("wrongCode") : t("wrongCreds"));
      return false;
    }
    toast(t("welcomeBack"), "ok");
    router.push(callbackUrl);
    router.refresh();
    return true;
  }

  async function onCreds(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/auth/precheck", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Errore");
        return;
      }
      if (data.need2fa) {
        setStep("2fa");
      } else {
        await doSignIn();
      }
    } catch {
      setError("Errore di rete");
    } finally {
      setLoading(false);
    }
  }

  async function on2fa(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await doSignIn(token);
    } finally {
      setLoading(false);
    }
  }

  if (step === "2fa") {
    return (
      <form onSubmit={on2fa} className="space-y-4">
        <div className="flex items-center gap-2 rounded-xl border border-violet/20 bg-violet/[0.06] px-4 py-3 text-sm text-violet">
          <ShieldCheck className="h-4 w-4" />
          {t("twoFaPrompt")}
        </div>
        <Input
          label={t("code6")}
          inputMode="numeric"
          autoFocus
          maxLength={6}
          value={token}
          onChange={(e) => setToken(e.target.value.replace(/\D/g, ""))}
          placeholder="000000"
          className="text-center font-mono text-lg tracking-[0.5em]"
          error={error ?? undefined}
        />
        <Button type="submit" size="lg" loading={loading} className="w-full">
          {t("verifyLogin")} <ArrowRight className="h-4 w-4" />
        </Button>
        <button
          type="button"
          onClick={() => {
            setStep("creds");
            setToken("");
            setError(null);
          }}
          className="flex w-full items-center justify-center gap-1.5 text-xs text-fg-muted hover:text-fg"
        >
          <ArrowLeft className="h-3 w-3" /> {t("otherAccount")}
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={onCreds} className="space-y-4">
      <Input
        label={t("email")}
        type="email"
        required
        autoFocus
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        icon={<Mail className="h-4 w-4" />}
      />
      <div>
        <Input
          label={t("password")}
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          icon={<KeyRound className="h-4 w-4" />}
          error={error ?? undefined}
        />
      </div>
      <Button type="submit" size="lg" loading={loading} className="w-full">
        {t("signIn")} <ArrowRight className="h-4 w-4" />
      </Button>
      <p className="text-center text-sm text-fg-muted">
        {t("noAccount")}{" "}
        <Link href="/register" className="text-violet hover:underline">
          {tc("register")}
        </Link>
      </p>
    </form>
  );
}
