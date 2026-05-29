"use client";

import { useTransition } from "react";
import { Ban, Trash2, ShieldCheck, Loader2, UserCheck } from "lucide-react";
import { setUserRole, setUserBanned, deleteUser } from "@/app/admin/actions";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

export function UserRowActions({
  id,
  role,
  banned,
  isSelf,
}: {
  id: string;
  role: string;
  banned: boolean;
  isSelf: boolean;
}) {
  const [pending, start] = useTransition();
  const toast = useToast();

  function run(fn: () => Promise<void>, okMsg: string) {
    start(async () => {
      try {
        await fn();
        toast(okMsg, "ok");
      } catch (e) {
        toast(e instanceof Error ? e.message : "Errore", "error");
      }
    });
  }

  return (
    <div className="flex items-center justify-end gap-1.5">
      {pending && <Loader2 className="h-3.5 w-3.5 animate-spin text-fg-dim" />}
      <button
        title={role === "ADMIN" ? "Rendi utente" : "Rendi admin"}
        disabled={pending || isSelf}
        onClick={() => run(() => setUserRole(id, role === "ADMIN" ? "USER" : "ADMIN"), "Ruolo aggiornato")}
        className={cn(
          "rounded-lg border border-white/10 p-1.5 transition hover:bg-white/5 disabled:opacity-30",
          role === "ADMIN" ? "text-violet" : "text-fg-muted"
        )}
      >
        <ShieldCheck className="h-3.5 w-3.5" />
      </button>
      <button
        title={banned ? "Sblocca" : "Banna"}
        disabled={pending || isSelf}
        onClick={() => run(() => setUserBanned(id, !banned), banned ? "Sbloccato" : "Bannato")}
        className={cn(
          "rounded-lg border border-white/10 p-1.5 transition hover:bg-white/5 disabled:opacity-30",
          banned ? "text-emerald" : "text-amber"
        )}
      >
        {banned ? <UserCheck className="h-3.5 w-3.5" /> : <Ban className="h-3.5 w-3.5" />}
      </button>
      <button
        title="Elimina"
        disabled={pending || isSelf}
        onClick={() => {
          if (confirm("Eliminare definitivamente questo utente?")) {
            run(() => deleteUser(id), "Utente eliminato");
          }
        }}
        className="rounded-lg border border-white/10 p-1.5 text-danger transition hover:bg-danger/10 disabled:opacity-30"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
