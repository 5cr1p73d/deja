import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { DashboardShell, type NavItem } from "@/components/dashboard/shell";
import { SiteBackground } from "@/components/site/background";

const items: NavItem[] = [
  { href: "/admin", label: "Panoramica", icon: "dashboard", exact: true },
  { href: "/admin/users", label: "Utenti", icon: "users" },
  { href: "/admin/waitlist", label: "Waitlist", icon: "list" },
  { href: "/admin/messages", label: "Messaggi", icon: "inbox" },
  { href: "/admin/flags", label: "Feature flag", icon: "toggle" },
  { href: "/admin/audit", label: "Audit log", icon: "scroll" },
];

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) redirect("/login?callbackUrl=/admin");
  if (session.user.role !== "ADMIN") redirect("/account?denied=admin");

  return (
    <>
      <SiteBackground />
      <div className="relative z-10">
        <DashboardShell
          items={items}
          user={{ name: session.user.name, email: session.user.email, role: session.user.role }}
          badge="admin · Scr1p73d"
        >
          {children}
        </DashboardShell>
      </div>
    </>
  );
}
