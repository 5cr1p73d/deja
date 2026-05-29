import type { Metadata } from "next";
import { Section } from "@/components/site/section";
import { Reveal } from "@/components/motion/reveal";
import { CodeBlock } from "@/components/site/code-block";
import { Badge } from "@/components/ui/badge";

export const metadata: Metadata = {
  title: "Documentazione",
  description: "Architettura, moduli, AI e stack tecnico di Déjà.",
};

const NAV = [
  { id: "architettura", label: "Architettura" },
  { id: "cattura", label: "Cattura" },
  { id: "ricerca", label: "Ricerca" },
  { id: "ai", label: "AI & RAG" },
  { id: "stack", label: "Stack" },
];

const STACK: [string, string][] = [
  ["GUI", "PyQt6 — QSystemTrayIcon, QStackedWidget"],
  ["DB", "SQLite WAL + sqlite-vec (int8 cosine, 768-dim)"],
  ["Embeddings", "paraphrase-multilingual-mpnet-base-v2 (768-dim)"],
  ["STT", "faster-whisper large-v3-turbo (CPU int8)"],
  ["OCR", "Tesseract (ita+eng)"],
  ["Audio", "pyaudiowpatch (loopback, callback-based)"],
  ["AI API", "OpenAI SDK — Qwen3-235B / Kimi-K2.6, 128K ctx"],
  ["Vision", "Gemini 2.5 Flash (OpenAI-compat)"],
  ["Hotkey", "keyboard — ctrl+shift+d, ctrl+shift+a"],
];

const SEARCH_CODE = `query text
  → encode(normalize=True)                 # 768-dim
  → sqlite-vec KNN:
      WHERE emb MATCH vec_int8(?) ORDER BY distance LIMIT k
  → score = 1.0 - distance                 # cosine
  → soglie: screenshot ≥ 0.18, audio ≥ 0.15
  ‖ PARALLELO: match esatto tokenizzato (LIKE AND, fuzzy)
  → merge dedup: esatti prima → score desc → ts desc`;

const AI_CODE = `def chat_stream(history, user_msg):
    """yields (kind, content): text | tool_call | tool_result | error"""
    # loop max 5 iterazioni di tool calling
    # tools: search_memories, list_recent, list_by_date_range, memory_stats
    # auto-trim history se token stimati > budget contesto
    ...`;

export default function DocsPage() {
  return (
    <Section className="max-w-6xl">
      <Reveal>
        <div className="mb-10">
          <Badge tone="violet" className="mb-3">docs</Badge>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Documentazione tecnica
          </h1>
          <p className="mt-3 max-w-2xl text-fg-muted">
            Come è fatta Déjà sotto il cofano. Estratto dal vault di progetto.
          </p>
        </div>
      </Reveal>

      <div className="grid gap-10 lg:grid-cols-[200px_1fr]">
        {/* sidebar */}
        <aside className="hidden lg:block">
          <nav className="sticky top-24 space-y-1">
            {NAV.map((n) => (
              <a
                key={n.id}
                href={`#${n.id}`}
                className="block rounded-lg px-3 py-2 font-mono text-sm text-fg-muted transition hover:bg-white/[0.04] hover:text-fg"
              >
                {n.label}
              </a>
            ))}
          </nav>
        </aside>

        <div className="min-w-0 space-y-14">
          <Doc id="architettura" title="Architettura">
            <p>
              <code className="text-violet">main.py</code> avvia QApplication e 3
              thread daemon coordinati da un unico{" "}
              <code className="text-violet">stop_event</code>:
            </p>
            <ul className="my-4 space-y-2">
              <DocLi name="t_capture" desc="loop screenshot + OCR ogni 5s" tone="emerald" />
              <DocLi name="t_indexer" desc="embedding pendenti → tabelle vec ogni 10s" tone="violet" />
              <DocLi name="t_audio" desc="record mic+loopback, segmenti 30s, transcribe" tone="amber" />
            </ul>
            <p>
              La GUI Qt sta sul main thread. L&apos;hotkey gira su un thread separato
              ed emette un signal che fa il toggle dell&apos;overlay.
            </p>
          </Doc>

          <Doc id="cattura" title="Pipeline di cattura">
            <CodeBlock
              filename="capture.py"
              code={`shot = mss.grab(monitor)        # multi-monitor aware
jpeg = compress(shot, q=70)     # resize 75%
if sha256(jpeg) == last: skip   # dedup
text = tesseract(shot, "ita+eng")
text = redact_pii(text)         # carte, IBAN, CF, email, tel
db.insert(screenshots, ts, app, jpeg, text)`}
            />
          </Doc>

          <Doc id="ricerca" title="Ricerca semantica + esatta">
            <CodeBlock filename="search.py" code={SEARCH_CODE} lang="text" />
          </Doc>

          <Doc id="ai" title="AI & RAG">
            <p>
              Endpoint OpenAI-compatibile. L&apos;assistente decide quando interrogare
              la memoria via tool calling, poi cita i ricordi con marker{" "}
              <code className="text-amber">[ss:ID]</code> /{" "}
              <code className="text-amber">[au:ID]</code> resi come card inline.
            </p>
            <CodeBlock filename="ai_assistant.py" code={AI_CODE} className="mt-4" />
          </Doc>

          <Doc id="stack" title="Stack tecnico">
            <div className="overflow-hidden rounded-xl border border-white/[0.07]">
              <table className="w-full text-sm">
                <tbody className="divide-y divide-white/[0.06]">
                  {STACK.map(([k, v]) => (
                    <tr key={k} className="hover:bg-white/[0.02]">
                      <td className="w-32 px-4 py-2.5 font-mono text-violet">{k}</td>
                      <td className="px-4 py-2.5 text-fg-muted">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Doc>
        </div>
      </div>
    </Section>
  );
}

function Doc({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24">
      <Reveal>
        <h2 className="mb-4 flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <span className="font-mono text-violet">#</span>
          {title}
        </h2>
        <div className="space-y-3 leading-relaxed text-fg-muted [&_code]:rounded [&_code]:bg-white/[0.06] [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.85em]">
          {children}
        </div>
      </Reveal>
    </section>
  );
}

function DocLi({ name, desc, tone }: { name: string; desc: string; tone: "violet" | "emerald" | "amber" }) {
  const c = tone === "emerald" ? "text-emerald" : tone === "amber" ? "text-amber" : "text-violet";
  return (
    <li className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <code className={`font-mono text-sm ${c}`}>{name}</code>
      <span className="text-sm text-fg-muted">{desc}</span>
    </li>
  );
}
