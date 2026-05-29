import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── Palette Déjà (presa dall'app PyQt6) ──
        ink: {
          DEFAULT: "#0e0e12", // BG_HEX app
          950: "#08080b",
          900: "#0e0e12",
          850: "#121218",
          800: "#16161d",
          700: "#1c1c25",
          600: "#23232e",
        },
        // accent primario: violet (C_AI_HEX)
        violet: {
          DEFAULT: "#a78bfa",
          soft: "#c4b5fd",
          deep: "#8b5cf6",
        },
        // indigo tray icon
        indigo: {
          DEFAULT: "#6c63ff",
        },
        // screenshots = emerald (C_SS_HEX)
        emerald: {
          DEFAULT: "#10b981",
        },
        // audio = amber (C_AUDIO_HEX)
        amber: {
          DEFAULT: "#f59e0b",
        },
        danger: "#ef4444",
        fg: {
          DEFAULT: "#f3f4f6", // TEXT_PRIMARY
          muted: "#8b8d98", // TEXT_SECONDARY
          dim: "#5a5d6a",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: [
          "var(--font-mono)",
          "JetBrains Mono",
          "Fira Code",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(167,139,250,0.18), 0 8px 40px -8px rgba(167,139,250,0.35)",
        "glow-emerald": "0 0 0 1px rgba(16,185,129,0.18), 0 8px 40px -8px rgba(16,185,129,0.35)",
        "glow-amber": "0 0 0 1px rgba(245,158,11,0.18), 0 8px 40px -8px rgba(245,158,11,0.35)",
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 20px 60px -20px rgba(0,0,0,0.7)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(to right, rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.035) 1px, transparent 1px)",
        "radial-violet":
          "radial-gradient(60% 60% at 50% 0%, rgba(167,139,250,0.18) 0%, transparent 70%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "caret-blink": {
          "0%,70%,100%": { opacity: "1" },
          "20%,50%": { opacity: "0" },
        },
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.95)", opacity: "0.7" },
          "100%": { transform: "scale(1.4)", opacity: "0" },
        },
        "border-flow": {
          "0%,100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.22,1,0.36,1) both",
        shimmer: "shimmer 2.2s linear infinite",
        "caret-blink": "caret-blink 1.1s steps(1) infinite",
        float: "float 6s ease-in-out infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.4,0,0.2,1) infinite",
        "border-flow": "border-flow 6s ease infinite",
      },
    },
  },
  plugins: [],
};

export default config;
