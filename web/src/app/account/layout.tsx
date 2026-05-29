import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { DashboardShell, type NavItem } from "@/components/dashboard/shell";
import { SiteBackground } from "@/components/site/background";

const items: NavItem[] = [
  { href: "/account", label: "Panoramica", icon: "dashboard", exact: true },
  { href: "/account/security", label: "Sicurezza", icon: "shield" },
  { href: "/account/sessions", label: "Attività", icon: "activity" },
];

export default async function AccountLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) redirect("/login?callbackUrl=/account");

  return (
    <>
      <SiteBackground />
      <div className="relative z-10">
        <DashboardShell
          items={items}
          user={{ name: session.user.name, email: session.user.email, role: session.user.role }}
          badge={session.user.role === "ADMIN" ? "admin" : undefined}
        >
          {children}
        </DashboardShell>
      </div>
    </>
  );
}
