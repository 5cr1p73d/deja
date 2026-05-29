import { Navbar } from "@/components/site/navbar";
import { Footer } from "@/components/site/footer";
import { SiteBackground } from "@/components/site/background";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SiteBackground />
      <Navbar />
      <main id="main" className="relative z-10 pt-16">
        {children}
      </main>
      <Footer />
    </>
  );
}
