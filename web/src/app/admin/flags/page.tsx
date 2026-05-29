import type { Metadata } from "next";
import { prisma } from "@/lib/db";
import { Card } from "@/components/ui/card";
import { FlagToggle } from "@/components/admin/flag-toggle";

export const metadata: Metadata = { title: "Admin · Feature flag" };

export default async function AdminFlags() {
  const flags = await prisma.featureFlag.findMany({ orderBy: { key: "asc" } });

  return (
    <div className="space-y-6">
      <div>
        <p className="font-mono text-xs text-fg-dim">// feature flag</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Feature flag</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Interruttori che cambiano il comportamento del sito in tempo reale.
        </p>
      </div>

      <Card className="divide-y divide-white/[0.05] p-0">
        {flags.map((f) => (
          <div key={f.key} className="flex items-center justify-between gap-4 px-5 py-4">
            <div className="min-w-0">
              <code className="font-mono text-sm text-fg">{f.key}</code>
              {f.description && <p className="mt-0.5 text-sm text-fg-muted">{f.description}</p>}
            </div>
            <FlagToggle flagKey={f.key} enabled={f.enabled} />
          </div>
        ))}
        {flags.length === 0 && (
          <div className="p-10 text-center text-sm text-fg-dim">Nessun flag.</div>
        )}
      </Card>
    </div>
  );
}
