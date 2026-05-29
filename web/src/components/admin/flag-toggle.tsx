"use client";

import { useState, useTransition } from "react";
import { cn } from "@/lib/utils";
import { toggleFeatureFlag } from "@/app/admin/actions";
import { useToast } from "@/components/ui/toast";

export function FlagToggle({
  flagKey,
  enabled,
}: {
  flagKey: string;
  enabled: boolean;
}) {
  const [on, setOn] = useState(enabled);
  const [pending, start] = useTransition();
  const toast = useToast();

  function toggle() {
    const next = !on;
    setOn(next);
    start(async () => {
      try {
        await toggleFeatureFlag(flagKey, next);
        toast(`${flagKey}: ${next ? "on" : "off"}`, "ok");
      } catch {
        setOn(!next);
        toast("Errore aggiornamento", "error");
      }
    });
  }

  return (
    <button
      role="switch"
      aria-checked={on}
      disabled={pending}
      onClick={toggle}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-60",
        on ? "bg-violet" : "bg-white/15"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform",
          on ? "translate-x-[22px]" : "translate-x-0.5"
        )}
      />
    </button>
  );
}
