"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { AtSign, Mail, KeyRound, ArrowRight, Check, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export function RegisterForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const toast = useToast();
  const t = useTranslations("auth");
  const tc = useTranslations("common");
  const rules = [
    { re: /.{8,}/, label: t("rule8") },
    { re: /[a-z]/, label: t("ruleLower") },
    { re: /[A-Z]/, label: t("ruleUpper") },
    { re: /[0-9]/, label: t("ruleNumber") },
  ];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Errore");
        return;
      }
      toast(t("creating"), "ok");
      const r = await signIn("credentials", {
        email,
        password,
        token: "",
        redirect: false,
      });
      if (r?.error) {
        router.push("/login");
      } else {
        router.push("/account");
        router.refresh();
      }
    } catch {
      setError("Errore di rete");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Input
        label={t("nick")}
        required
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="your_nick"
        icon={<AtSign className="h-4 w-4" />}
        hint={t("nickHint")}
      />
      <Input
        label={t("email")}
        type="email"
        required
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
        <div className="mt-2 flex flex-wrap gap-2">
          {rules.map((r) => {
            const ok = r.re.test(password);
            return (
              <span
                key={r.label}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[11px] ${
                  ok ? "bg-emerald/15 text-emerald" : "bg-white/[0.04] text-fg-dim"
                }`}
              >
                {ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                {r.label}
              </span>
            );
          })}
        </div>
      </div>
      <Button type="submit" size="lg" loading={loading} className="w-full">
        {t("createAccount")} <ArrowRight className="h-4 w-4" />
      </Button>
      <p className="text-center text-sm text-fg-muted">
        {t("hasAccount")}{" "}
        <Link href="/login" className="text-violet hover:underline">
          {tc("login")}
        </Link>
      </p>
    </form>
  );
}
