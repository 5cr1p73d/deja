import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AuthCard, OrDivider } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { enabledOAuth } from "@/auth.config";

export const metadata: Metadata = { title: "Accedi" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string }>;
}) {
  const { callbackUrl } = await searchParams;
  const cb = callbackUrl && callbackUrl.startsWith("/") ? callbackUrl : "/account";
  const t = await getTranslations("auth");

  return (
    <AuthCard title={t("loginTitle")} subtitle={t("loginSubtitle")}>
      <OAuthButtons google={enabledOAuth.google} apple={enabledOAuth.apple} callbackUrl={cb} />
      {(enabledOAuth.google || enabledOAuth.apple) && <OrDivider />}
      <LoginForm callbackUrl={cb} />
    </AuthCard>
  );
}
