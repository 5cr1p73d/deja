import { cn } from "@/lib/utils";

type Tone = "violet" | "emerald" | "amber" | "danger" | "muted";

const tones: Record<Tone, string> = {
  violet: "bg-violet/15 text-violet border-violet/25",
  emerald: "bg-emerald/15 text-emerald border-emerald/25",
  amber: "bg-amber/15 text-amber border-amber/25",
  danger: "bg-danger/15 text-danger border-danger/30",
  muted: "bg-white/[0.05] text-fg-muted border-white/10",
};

export function Badge({
  children,
  tone = "muted",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
