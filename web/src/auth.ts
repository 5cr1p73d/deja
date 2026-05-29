import NextAuth from "next-auth";
import { PrismaAdapter } from "@auth/prisma-adapter";
import Credentials from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";

import { prisma } from "@/lib/db";
import authConfig from "@/auth.config";
import { loginSchema } from "@/lib/validations";
import { verifyTotp } from "@/lib/totp";
import { logAudit } from "@/lib/audit";

// Errori specifici lanciati da authorize → CallbackRouteError sul client.
// Il messaggio è riconosciuto via `error.cause` lato server action.
export class TwoFactorRequiredError extends Error {
  code = "2FA_REQUIRED";
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  adapter: PrismaAdapter(prisma),
  providers: [
    ...authConfig.providers,
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
        token: { label: "Codice 2FA", type: "text" },
      },
      async authorize(creds) {
        const parsed = loginSchema.safeParse(creds);
        if (!parsed.success) return null;
        const { email, password, token } = parsed.data;

        const user = await prisma.user.findUnique({
          where: { email: email.toLowerCase() },
        });
        if (!user || !user.passwordHash) return null;
        if (user.banned) throw new Error("ACCOUNT_BANNED");

        const ok = await bcrypt.compare(password, user.passwordHash);
        if (!ok) return null;

        if (user.twoFactorEnabled) {
          if (!token) throw new Error("2FA_REQUIRED");
          if (!user.twoFactorSecret || !verifyTotp(token, user.twoFactorSecret)) {
            throw new Error("2FA_INVALID");
          }
        }

        await prisma.user.update({
          where: { id: user.id },
          data: { lastLoginAt: new Date() },
        });
        await logAudit({ action: "login", actorId: user.id, target: user.email });

        return {
          id: user.id,
          email: user.email,
          name: user.name,
          image: user.image,
          role: user.role as "USER" | "ADMIN",
        };
      },
    }),
  ],
  events: {
    async signIn({ user, account }) {
      if (account?.provider && account.provider !== "credentials") {
        await logAudit({
          action: "oauth_login",
          actorId: user.id,
          target: user.email,
          meta: { provider: account.provider },
        });
      }
    },
  },
});
