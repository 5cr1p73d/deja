"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

const KEYWORDS = new Set([
  "def","class","return","import","from","as","if","elif","else","for","while",
  "try","except","finally","with","yield","lambda","in","is","not","and","or",
  "None","True","False","await","async","pass","raise","const","let","var",
  "function","export","await","new","await","type","interface","extends","public",
]);
const BUILTINS = new Set([
  "self","print","len","range","int","str","float","list","dict","set",
  "np","ctx","conn","db","search","prisma","auth",
]);

type Tok = { t: string; cls: string; style?: React.CSSProperties };

function tokenizeLine(line: string): Tok[] {
  const re =
    /(#[^\n]*|\/\/[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)|(\b\d+\.?\d*\b)|([A-Za-z_]\w*)(?=\s*\()|([A-Za-z_]\w*)|([{}()[\].,:;=+\-*/<>!|&%@]+)/g;
  const out: Tok[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) {
    if (m.index > last) out.push({ t: line.slice(last, m.index), cls: "text-fg/90" });
    if (m[1]) out.push({ t: m[1], cls: "italic text-fg-dim" });
    else if (m[2]) out.push({ t: m[2], cls: "text-emerald" });
    else if (m[3]) out.push({ t: m[3], cls: "text-amber" });
    else if (m[4]) out.push({ t: m[4], cls: "", style: { color: "#7dd3fc" } });
    else if (m[5]) {
      const w = m[5];
      if (KEYWORDS.has(w)) out.push({ t: w, cls: "font-medium text-violet" });
      else if (BUILTINS.has(w)) out.push({ t: w, cls: "text-violet-soft" });
      else out.push({ t: w, cls: "text-fg/90" });
    } else if (m[6]) out.push({ t: m[6], cls: "text-fg-muted" });
    last = re.lastIndex;
  }
  if (last < line.length) out.push({ t: line.slice(last), cls: "text-fg/90" });
  return out;
}

export function CodeBlock({
  code,
  lang = "python",
  showLines = true,
  className,
  filename,
}: {
  code: string;
  lang?: string;
  showLines?: boolean;
  className?: string;
  filename?: string;
}) {
  const [copied, setCopied] = useState(false);
  const lines = code.replace(/\n$/, "").split("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard non disponibile */
    }
  }

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border border-white/[0.08] bg-ink-950/70",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2">
        <span className="font-mono text-[11px] text-fg-dim">
          {filename ?? `${lang}`}
        </span>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[11px] text-fg-muted opacity-0 transition hover:bg-white/5 hover:text-fg group-hover:opacity-100"
          aria-label="Copia codice"
        >
          {copied ? <Check className="h-3 w-3 text-emerald" /> : <Copy className="h-3 w-3" />}
          {copied ? "copiato" : "copia"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-relaxed">
        <code>
          {lines.map((line, i) => (
            <div key={i} className="table-row">
              {showLines && (
                <span className="table-cell select-none pr-4 text-right text-fg-dim/60">
                  {i + 1}
                </span>
              )}
              <span className="table-cell">
                {line.length === 0 ? (
                  <span>&nbsp;</span>
                ) : (
                  tokenizeLine(line).map((tok, j) => (
                    <span key={j} className={tok.cls} style={tok.style}>
                      {tok.t}
                    </span>
                  ))
                )}
              </span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}
