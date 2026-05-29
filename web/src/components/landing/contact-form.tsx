"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export function ContactForm() {
  const [form, setForm] = useState({ name: "", email: "", subject: "", body: "" });
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const toast = useToast();

  function set<K extends keyof typeof form>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Errore");
      setSent(true);
      toast("Messaggio inviato. Ti rispondiamo presto.", "ok");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Errore", "error");
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <div className="rounded-2xl border border-emerald/25 bg-emerald/10 p-8 text-center">
        <p className="text-lg font-semibold text-fg">Ricevuto. ✓</p>
        <p className="mt-1 text-sm text-fg-muted">
          Il tuo messaggio è nella coda di <span className="text-violet">Scr1p73d</span>.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Nome"
          required
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="Come ti chiami"
        />
        <Input
          label="Email"
          type="email"
          required
          value={form.email}
          onChange={(e) => set("email", e.target.value)}
          placeholder="tu@esempio.com"
        />
      </div>
      <Input
        label="Oggetto"
        required
        value={form.subject}
        onChange={(e) => set("subject", e.target.value)}
        placeholder="Di cosa si tratta"
      />
      <div>
        <label className="mb-1.5 block font-mono text-xs uppercase tracking-wider text-fg-muted">
          Messaggio
        </label>
        <textarea
          required
          rows={5}
          value={form.body}
          onChange={(e) => set("body", e.target.value)}
          placeholder="Scrivi qui…"
          className="w-full resize-y rounded-xl border border-white/10 bg-white/[0.04] px-3.5 py-2.5 text-sm text-fg placeholder:text-fg-dim focus:border-violet/60 focus:bg-white/[0.06] focus:outline-none"
        />
      </div>
      <Button type="submit" size="lg" loading={loading} className="w-full sm:w-auto">
        <Send className="h-4 w-4" /> Invia messaggio
      </Button>
    </form>
  );
}
