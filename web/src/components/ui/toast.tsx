"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, AlertTriangle, XCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Level = "ok" | "info" | "warn" | "error";
type Toast = { id: number; level: Level; message: string };

const ToastCtx = createContext<(message: string, level?: Level) => void>(() => {});

export function useToast() {
  return useContext(ToastCtx);
}

const meta: Record<Level, { icon: typeof Info; color: string; ring: string }> = {
  ok: { icon: CheckCircle2, color: "text-emerald", ring: "shadow-glow-emerald" },
  info: { icon: Info, color: "text-violet", ring: "shadow-glow" },
  warn: { icon: AlertTriangle, color: "text-amber", ring: "shadow-glow-amber" },
  error: { icon: XCircle, color: "text-danger", ring: "" },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((message: string, level: Level = "info") => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((t) => [...t, { id, level, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  const dismiss = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[90] flex w-[min(92vw,360px)] flex-col gap-2">
        <AnimatePresence>
          {toasts.map((t) => {
            const m = meta[t.level];
            const Icon = m.icon;
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, x: 40, scale: 0.96 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 40, scale: 0.96 }}
                transition={{ type: "spring", stiffness: 380, damping: 30 }}
                className={cn(
                  "pointer-events-auto flex items-start gap-3 rounded-xl border border-white/10 bg-ink-800/90 p-3 pr-2 backdrop-blur-xl",
                  m.ring
                )}
              >
                <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", m.color)} />
                <p className="flex-1 text-sm text-fg/90">{t.message}</p>
                <button
                  onClick={() => dismiss(t.id)}
                  className="rounded-md p-1 text-fg-muted transition hover:bg-white/5 hover:text-fg"
                  aria-label="Chiudi notifica"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}
