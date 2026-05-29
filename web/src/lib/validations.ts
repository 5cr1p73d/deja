import { z } from "zod";

export const nickRegex = /^[a-zA-Z0-9_]{3,32}$/;

export const loginSchema = z.object({
  email: z.string().email("Email non valida"),
  password: z.string().min(1, "Password richiesta"),
  token: z.string().optional(),
});

export const registerSchema = z.object({
  name: z
    .string()
    .regex(nickRegex, "Nick: 3-32 caratteri, lettere/numeri/underscore"),
  email: z.string().email("Email non valida"),
  password: z
    .string()
    .min(8, "Minimo 8 caratteri")
    .regex(/[a-z]/, "Serve una minuscola")
    .regex(/[A-Z]/, "Serve una maiuscola")
    .regex(/[0-9]/, "Serve un numero"),
});

export const waitlistSchema = z.object({
  email: z.string().email("Email non valida"),
  name: z.string().max(64).optional().or(z.literal("")),
  platform: z.enum(["windows", "mac", "linux"]).optional(),
  referrer: z.string().max(120).optional().or(z.literal("")),
});

export const contactSchema = z.object({
  name: z.string().min(2, "Nome troppo corto").max(80),
  email: z.string().email("Email non valida"),
  subject: z.string().min(3, "Oggetto troppo corto").max(140),
  body: z.string().min(10, "Messaggio troppo corto").max(4000),
});

export const totpTokenSchema = z.object({
  token: z
    .string()
    .regex(/^\d{6}$/, "Codice a 6 cifre"),
});

export type LoginInput = z.infer<typeof loginSchema>;
export type RegisterInput = z.infer<typeof registerSchema>;
export type WaitlistInput = z.infer<typeof waitlistSchema>;
export type ContactInput = z.infer<typeof contactSchema>;
