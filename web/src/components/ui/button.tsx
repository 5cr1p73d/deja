"use client";

import { forwardRef } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-violet/90 text-ink-900 hover:bg-violet shadow-glow font-semibold",
  secondary: "bg-white/[0.06] text-fg hover:bg-white/[0.1] border border-white/10",
  outline:
    "bg-transparent text-fg border border-white/15 hover:border-violet/60 hover:bg-violet/[0.06]",
  ghost: "bg-transparent text-fg-muted hover:text-fg hover:bg-white/[0.05]",
  danger: "bg-danger/15 text-danger border border-danger/30 hover:bg-danger/25",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5 rounded-lg",
  md: "h-10 px-4 text-sm gap-2 rounded-xl",
  lg: "h-12 px-6 text-base gap-2.5 rounded-xl",
};

const base =
  "inline-flex items-center justify-center whitespace-nowrap transition-all duration-200 active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none select-none";

type Props = {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  href?: string;
} & Omit<React.AllHTMLAttributes<HTMLElement>, "size">;

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = "primary", size = "md", loading, className, children, href, ...rest },
  ref
) {
  const classes = cn(base, variants[variant], sizes[size], className);

  if (href) {
    return (
      <Link href={href} className={classes} {...(rest as React.AnchorHTMLAttributes<HTMLAnchorElement>)}>
        {children}
      </Link>
    );
  }

  return (
    <button
      ref={ref}
      className={classes}
      disabled={loading || rest.disabled}
      {...(rest as React.ButtonHTMLAttributes<HTMLButtonElement>)}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
});
