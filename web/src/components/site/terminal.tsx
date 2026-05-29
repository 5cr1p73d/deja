import { cn } from "@/lib/utils";

/** Finestra "terminale/editor" con barra titolo e traffic lights. */
export function Terminal({
  title = "deja — ~/memory",
  children,
  className,
  glow = false,
  tabs,
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
  glow?: boolean;
  tabs?: string[];
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-white/[0.08] bg-ink-850/90 backdrop-blur-xl",
        glow && "shadow-glow",
        className
      )}
    >
      <div className="flex items-center gap-2 border-b border-white/[0.06] bg-white/[0.02] px-4 py-2.5">
        <span className="flex gap-1.5">
          <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        </span>
        <span className="ml-3 truncate font-mono text-xs text-fg-muted">{title}</span>
        {tabs && (
          <span className="ml-auto hidden gap-1 sm:flex">
            {tabs.map((t, i) => (
              <span
                key={t}
                className={cn(
                  "rounded-md px-2.5 py-1 font-mono text-[11px]",
                  i === 0
                    ? "bg-white/[0.06] text-fg"
                    : "text-fg-dim hover:text-fg-muted"
                )}
              >
                {t}
              </span>
            ))}
          </span>
        )}
      </div>
      <div className="p-4 font-mono text-sm leading-relaxed sm:p-5">{children}</div>
    </div>
  );
}
