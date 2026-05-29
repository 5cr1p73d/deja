import NextAuth from "next-auth";
import { NextResponse } from "next/server";
import authConfig from "@/auth.config";

// Istanza edge-safe (solo lettura sessione JWT, niente adapter/bcrypt).
const { auth } = NextAuth(authConfig);

export default auth((req) => {
  const { nextUrl } = req;
  const session = req.auth;
  const isLoggedIn = !!session?.user;
  const role = session?.user?.role;
  const path = nextUrl.pathname;

  const isAuthPage =
    path === "/login" || path === "/register" || path === "/verify";
  const isAccount = path.startsWith("/account");
  const isAdmin = path.startsWith("/admin");

  // Utente loggato che visita login/register → manda a /account.
  if (isLoggedIn && isAuthPage) {
    return NextResponse.redirect(new URL("/account", nextUrl));
  }

  // Area riservata.
  if (!isLoggedIn && (isAccount || isAdmin)) {
    const url = new URL("/login", nextUrl);
    url.searchParams.set("callbackUrl", path);
    return NextResponse.redirect(url);
  }

  // Solo ADMIN entra in /admin.
  if (isAdmin && role !== "ADMIN") {
    return NextResponse.redirect(new URL("/account?denied=admin", nextUrl));
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/account/:path*", "/admin/:path*", "/login", "/register", "/verify"],
};
