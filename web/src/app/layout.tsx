import type { Metadata, Viewport } from "next";
import "./globals.css";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.AUTH_URL || "http://localhost:3000"),
  title: {
    default: "Déjà — la memoria locale del tuo PC",
    template: "%s · Déjà",
  },
  description:
    "Déjà cattura schermo e audio sul tuo PC, li trascrive e indicizza in locale, e ti lascia cercare qualsiasi cosa tu abbia visto o sentito. Ricerca semantica + AI, 100% on-device.",
  keywords: [
    "Déjà",
    "Rewind AI alternativa",
    "memoria PC",
    "ricerca semantica",
    "OCR",
    "Whisper",
    "privacy",
    "Windows",
  ],
  authors: [{ name: "Scr1p73d" }],
  openGraph: {
    title: "Déjà — la memoria locale del tuo PC",
    description:
      "Ricorda tutto ciò che vedi e senti sul PC. Locale, privato, cercabile. Ricerca semantica + AI on-device.",
    type: "website",
    locale: "it_IT",
  },
  twitter: { card: "summary_large_image" },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#0e0e12",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();
  return (
    <html lang={locale} className="dark">
      <body className="grain antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-violet focus:px-4 focus:py-2 focus:text-ink-900"
        >
          Skip to content
        </a>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
