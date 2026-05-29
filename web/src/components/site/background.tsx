"use client";

import { useEffect, useRef } from "react";

/**
 * Sfondo FX fisso: griglia tenue + glow radiale + particelle che derivano
 * lente (canvas). Rispetta prefers-reduced-motion (niente animazione).
 */
export function SiteBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const colors = ["#a78bfa", "#6c63ff", "#10b981", "#f59e0b"];
    let w = 0,
      h = 0,
      raf = 0;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);

    type P = { x: number; y: number; vx: number; vy: number; r: number; c: string };
    let parts: P[] = [];

    function resize() {
      w = canvas!.clientWidth;
      h = canvas!.clientHeight;
      canvas!.width = w * DPR;
      canvas!.height = h * DPR;
      ctx!.setTransform(DPR, 0, 0, DPR, 0, 0);
      const count = Math.min(70, Math.floor((w * h) / 26000));
      parts = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
        r: Math.random() * 1.6 + 0.5,
        c: colors[Math.floor(Math.random() * colors.length)],
      }));
    }

    function draw() {
      ctx!.clearRect(0, 0, w, h);
      for (const p of parts) {
        if (!reduce) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0) p.x = w;
          if (p.x > w) p.x = 0;
          if (p.y < 0) p.y = h;
          if (p.y > h) p.y = 0;
        }
        ctx!.beginPath();
        ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx!.fillStyle = p.c;
        ctx!.globalAlpha = 0.5;
        ctx!.fill();
      }
      ctx!.globalAlpha = 1;
      if (!reduce) raf = requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* glow radiale in alto */}
      <div className="absolute inset-x-0 top-0 h-[600px] bg-radial-violet" />
      {/* griglia tenue con fade */}
      <div className="absolute inset-0 bg-grid-faint bg-[size:48px_48px] [mask-image:radial-gradient(80%_60%_at_50%_0%,black,transparent)]" />
      {/* particelle */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      {/* vignette in basso */}
      <div className="absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-ink-900 to-transparent" />
    </div>
  );
}
