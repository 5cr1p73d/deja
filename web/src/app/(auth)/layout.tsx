import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Logo } from "@/components/site/logo";
import { SiteBackground } from "@/components/site/background";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteBackground />
      <div className="relative z-10 flex min-h-screen flex-col">
        <header className="flex items-center justify-between px-6 py-5">
          <Logo />
          <Link
            href="/"
            className="flex items-center gap-1.5 font-mono text-xs text-fg-muted transition hover:text-fg"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> torna al sito
          </Link>
        </header>
        <main id="main" className="flex flex-1 items-center justify-center px-5 py-10">
          {children}
        </main>
      </div>
    </>
  );
}
