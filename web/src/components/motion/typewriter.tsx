"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

/** Scrive a macchina una sequenza di stringhe, in loop. */
export function Typewriter({
  words,
  className,
  typeMs = 65,
  holdMs = 1400,
}: {
  words: string[];
  className?: string;
  typeMs?: number;
  holdMs?: number;
}) {
  const reduce = useReducedMotion();
  const [text, setText] = useState(words[0] ?? "");
  const [i, setI] = useState(0);
  const [del, setDel] = useState(false);

  useEffect(() => {
    if (reduce) {
      setText(words[i % words.length] ?? "");
      return;
    }
    const full = words[i % words.length] ?? "";
    let t: ReturnType<typeof setTimeout>;
    if (!del && text === full) {
      t = setTimeout(() => setDel(true), holdMs);
    } else if (del && text === "") {
      setDel(false);
      setI((v) => v + 1);
    } else {
      t = setTimeout(
        () => {
          setText((cur) =>
            del ? full.slice(0, cur.length - 1) : full.slice(0, cur.length + 1)
          );
        },
        del ? typeMs / 2 : typeMs
      );
    }
    return () => clearTimeout(t);
  }, [text, del, i, words, typeMs, holdMs, reduce]);

  return (
    <span className={className}>
      {text}
      <span className="ml-0.5 inline-block w-[2px] animate-caret-blink bg-violet align-middle" style={{ height: "1em" }} />
    </span>
  );
}
