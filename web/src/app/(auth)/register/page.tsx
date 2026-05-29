import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { AuthCard, OrDivider } from "@/components/auth/auth-card";
import { RegisterForm } from "@/components/auth/register-form";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { enabledOAuth } from "@/auth.config";

export const metadata: Metadata = { title: "Registrati" };

export default async function RegisterPage() {
  const t = await getTranslations("auth");
  return (
    <AuthCard title={t("registerTitle")} subtitle={t("registerSubtitle")}>
      <OAuthButtons google={enabledOAuth.google} apple={enabledOAuth.apple} />
      {(enabledOAuth.google || enabledOAuth.apple) && <OrDivider />}
      <RegisterForm />
    </AuthCard>
  );
}
