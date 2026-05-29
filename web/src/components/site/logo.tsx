import Link from "next/link";
import { cn } from "@/lib/utils";

export function Logo({
  className,
  withText = true,
  href = "/",
}: {
  className?: string;
  withText?: boolean;
  href?: string | null;
}) {
  const mark = (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <span className="relative grid h-8 w-8 place-items-center">
        <svg viewBox="0 0 64 64" className="h-8 w-8">
          <defs>
            <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#c4b5fd" />
              <stop offset="0.6" stopColor="#a78bfa" />
              <stop offset="1" stopColor="#6c63ff" />
            </linearGradient>
          </defs>
          <circle cx="32" cy="32" r="18" fill="none" stroke="url(#lg)" strokeWidth="3.5" />
          <circle cx="32" cy="32" r="6.5" fill="url(#lg)" />
          <circle
            cx="32"
            cy="32"
            r="26"
            fill="none"
            stroke="#a78bfa"
            strokeWidth="1.5"
            opacity="0.3"
          />
        </svg>
      </span>
      {withText && (
        <span className="font-mono text-lg font-semibold tracking-tight text-fg">
          Déjà
        </span>
      )}
    </span>
  );

  if (href) {
    return (
      <Link href={href} aria-label="Déjà — home">
        {mark}
      </Link>
    );
  }
  return mark;
}
