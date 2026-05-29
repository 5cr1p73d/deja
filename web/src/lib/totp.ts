import { authenticator } from "otplib";
import QRCode from "qrcode";

// Finestra ±1 step (30s) per tollerare drift di clock.
authenticator.options = { window: 1, step: 30 };

const ISSUER = process.env.TOTP_ISSUER || "Déjà";

export function generateTotpSecret(): string {
  return authenticator.generateSecret();
}

export function otpauthUri(accountLabel: string, secret: string): string {
  return authenticator.keyuri(accountLabel, ISSUER, secret);
}

export function verifyTotp(token: string, secret: string): boolean {
  try {
    return authenticator.verify({ token: token.replace(/\s+/g, ""), secret });
  } catch {
    return false;
  }
}

export async function qrDataUrl(otpauth: string): Promise<string> {
  return QRCode.toDataURL(otpauth, {
    margin: 1,
    width: 240,
    color: { dark: "#f3f4f6", light: "#0e0e1200" },
  });
}

/** Codici di recupero one-time (mostrati una volta all'utente). */
export function generateRecoveryCodes(n = 8): string[] {
  const codes: string[] = [];
  const alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
  // Nota: usa crypto per casualità reale.
  const { randomBytes } = require("crypto") as typeof import("crypto");
  for (let i = 0; i < n; i++) {
    const bytes = randomBytes(5);
    let s = "";
    for (let j = 0; j < 5; j++) s += alphabet[bytes[j] % alphabet.length];
    codes.push(s.slice(0, 5) + "-" + randomBytes(3).toString("hex").toUpperCase());
  }
  return codes;
}
