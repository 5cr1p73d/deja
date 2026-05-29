"use client";

import { useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Card scura con hairline. Con `spotlight` segue il cursore con un alone
 * violet (effetto "coding panel"). Degrada a card statica senza motion.
 */
export function Card({
  children,
  className,
  spotlight = false,
  as: Tag = "div",
}: {
  children: React.ReactNode;
  className?: string;
  spotlight?: boolean;
  as?: keyof React.JSX.IntrinsicElements;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: -200, y: -200, on: false });

  const Comp = Tag as React.ElementType;

  return (
    <Comp
      ref={ref}
      onMouseMove={
        spotlight
          ? (e: React.MouseEvent) => {
              const r = ref.current?.getBoundingClientRect();
              if (!r) return;
              setPos({ x: e.clientX - r.left, y: e.clientY - r.top, on: true });
            }
          : undefined
      }
      onMouseLeave={spotlight ? () => setPos((p) => ({ ...p, on: false })) : undefined}
      className={cn(
        "relative overflow-hidden rounded-2xl border border-white/[0.07] bg-white/[0.025] shadow-card",
        className
      )}
    >
      {spotlight && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 transition-opacity duration-300"
          style={{
            opacity: pos.on ? 1 : 0,
            background: `radial-gradient(420px circle at ${pos.x}px ${pos.y}px, rgba(167,139,250,0.10), transparent 45%)`,
          }}
        />
      )}
      <div className="relative">{children}</div>
    </Comp>
  );
}
