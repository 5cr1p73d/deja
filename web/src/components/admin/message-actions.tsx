"use client";

import { useTransition } from "react";
import { Check, Archive, Loader2, RotateCcw } from "lucide-react";
import { setMessageStatus } from "@/app/admin/actions";
import { useToast } from "@/components/ui/toast";

type Status = "NEW" | "READ" | "ARCHIVED";

export function MessageActions({ id, status }: { id: string; status: string }) {
  const [pending, start] = useTransition();
  const toast = useToast();

  function set(next: Status) {
    start(async () => {
      try {
        await setMessageStatus(id, next);
        toast("Aggiornato", "ok");
      } catch {
        toast("Errore", "error");
      }
    });
  }

  return (
    <div className="flex items-center gap-1.5">
      {pending && <Loader2 className="h-3.5 w-3.5 animate-spin text-fg-dim" />}
      {status !== "READ" && (
        <button
          onClick={() => set("READ")}
          title="Segna come letto"
          className="rounded-lg border border-white/10 p-1.5 text-emerald transition hover:bg-white/5"
        >
          <Check className="h-3.5 w-3.5" />
        </button>
      )}
      {status !== "ARCHIVED" ? (
        <button
          onClick={() => set("ARCHIVED")}
          title="Archivia"
          className="rounded-lg border border-white/10 p-1.5 text-fg-muted transition hover:bg-white/5"
        >
          <Archive className="h-3.5 w-3.5" />
        </button>
      ) : (
        <button
          onClick={() => set("NEW")}
          title="Ripristina"
          className="rounded-lg border border-white/10 p-1.5 text-fg-muted transition hover:bg-white/5"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
