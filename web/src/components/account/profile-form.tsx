"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AtSign, Save } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export function ProfileForm({ initialName }: { initialName: string }) {
  const [name, setName] = useState(initialName);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const toast = useToast();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/account", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Errore");
        return;
      }
      toast("Profilo aggiornato.", "ok");
      router.refresh();
    } catch {
      setError("Errore di rete");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <div className="flex-1">
        <Input
          label="Nick"
          value={name}
          onChange={(e) => setName(e.target.value)}
          icon={<AtSign className="h-4 w-4" />}
          error={error ?? undefined}
        />
      </div>
      <Button type="submit" loading={loading} disabled={name === initialName}>
        <Save className="h-4 w-4" /> Salva
      </Button>
    </form>
  );
}
