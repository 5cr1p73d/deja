"use client";

import { forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

type Props = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string;
  hint?: string;
  icon?: React.ReactNode;
};

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { label, error, hint, icon, className, id, ...rest },
  ref
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="mb-1.5 block font-mono text-xs uppercase tracking-wider text-fg-muted"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {icon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-muted">
            {icon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "w-full rounded-xl border bg-white/[0.04] px-3.5 py-2.5 text-sm text-fg placeholder:text-fg-dim",
            "transition-colors focus:border-violet/60 focus:bg-white/[0.06] focus:outline-none",
            icon && "pl-10",
            error ? "border-danger/50" : "border-white/10",
            className
          )}
          aria-invalid={!!error}
          {...rest}
        />
      </div>
      {error ? (
        <p className="mt-1.5 text-xs text-danger">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-fg-dim">{hint}</p>
      ) : null}
    </div>
  );
});
