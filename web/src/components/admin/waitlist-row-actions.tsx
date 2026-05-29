"use client";

import { useTransition } from "react";
import { Trash2, Loader2 } from "lucide-react";
import { setWaitlistStatus, deleteWaitlistEntry } from "@/app/admin/actions";
import { useToast } from "@/components/ui/toast";

type Status = "PENDING" | "INVITED" | "CONVERTED";

export function WaitlistRowActions({ id, status }: { id: string; status: string }) {
  const [pending, start] = useTransition();
  const toast = useToast();

  return (
    <div className="flex items-center justify-end gap-2">
      {pending && <Loader2 className="h-3.5 w-3.5 animate-spin text-fg-dim" />}
      <select
        defaultValue={status}
        disabled={pending}
        onChange={(e) =>
          start(async () => {
            try {
              await setWaitlistStatus(id, e.target.value as Status);
              toast("Stato aggiornato", "ok");
            } catch {
              toast("Errore", "error");
            }
          })
        }
        className="rounded-lg border border-white/10 bg-ink-800 px-2 py-1 text-xs text-fg focus:outline-none"
      >
        <option value="PENDING">In attesa</option>
        <option value="INVITED">Invitato</option>
        <option value="CONVERTED">Convertito</option>
      </select>
      <button
        title="Elimina"
        disabled={pending}
        onClick={() =>
          confirm("Rimuovere dalla waitlist?") &&
          start(async () => {
            try {
              await deleteWaitlistEntry(id);
              toast("Rimosso", "ok");
            } catch {
              toast("Errore", "error");
            }
          })
        }
        className="rounded-lg border border-white/10 p-1.5 text-danger transition hover:bg-danger/10"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
