export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="w-full max-w-sm">
      <div className="relative">
        <div className="absolute -inset-4 -z-10 bg-radial-violet opacity-50 blur-2xl" />
        <div className="rounded-2xl border border-white/[0.08] bg-ink-850/80 p-7 shadow-card backdrop-blur-xl">
          <div className="mb-6">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="mt-1.5 text-sm text-fg-muted">{subtitle}</p>}
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

/** Divider "oppure" tra OAuth e credenziali. */
export function OrDivider() {
  return (
    <div className="my-5 flex items-center gap-3">
      <span className="h-px flex-1 bg-white/10" />
      <span className="font-mono text-[11px] uppercase tracking-wider text-fg-dim">oppure</span>
      <span className="h-px flex-1 bg-white/10" />
    </div>
  );
}
