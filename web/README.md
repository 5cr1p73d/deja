# Déjà — Sito Web

Sito ufficiale + backend di **Déjà**, l'app desktop che dà al tuo PC una memoria
locale e cercabile. Frontend dark "coding", molto animato, fedele alla palette
dell'app PyQt6. Backend con DB, autenticazione (email / Google / Apple), **2FA
TOTP** e una **dashboard admin** completa.

## Stack

| Layer | Tecnologia |
|-------|-----------|
| Framework | Next.js 15 (App Router) + React 19 + TypeScript |
| Stile | Tailwind CSS 3 + design tokens palette Déjà |
| Animazioni | Framer Motion (con rispetto di `prefers-reduced-motion`) |
| Auth | Auth.js v5 (NextAuth) — Credentials + Google + Apple, sessioni JWT |
| 2FA | TOTP via `otplib` + QR `qrcode` |
| DB | Prisma ORM + SQLite (dev). Pronto per Postgres in prod |
| Sicurezza | bcrypt (cost 12), rate-limit, header hardening, audit log |

## Avvio rapido

```bash
cd web
npm install
npm run setup     # prisma generate + db push + seed (crea l'admin)
npm run dev       # http://localhost:3000
```

`npm run setup` esegue in sequenza: genera il client Prisma, crea lo schema su
`prisma/dev.db` e fa il seed (admin, feature flag, waitlist demo).

## Account admin (seed)

Creato da `prisma/seed.ts` leggendo le env `ADMIN_*` (vedi `.env.example`):

```
nick:     ADMIN_NICK      (default: Scr1p73d)
email:    ADMIN_EMAIL     (es. admin@example.com)
password: ADMIN_PASSWORD  ← obbligatoria, scegli una password forte
```

Nessuna credenziale di default: il seed fallisce se `ADMIN_PASSWORD` non è
impostata. Login su `/login`, poi dashboard su `/admin`.

## Variabili d'ambiente

Vedi `.env.example`. Le principali:

- `DATABASE_URL` — connessione DB (default SQLite locale).
- `AUTH_SECRET` — segreto sessioni (già generato in `.env`).
- `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` — abilitano il login Google.
- `AUTH_APPLE_ID` / `AUTH_APPLE_SECRET` — abilitano il login Apple (il secret
  è il JWT client ES256 generato dal portale Apple Developer).
- `ADMIN_NICK` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` — bootstrap admin.

> I pulsanti OAuth compaiono solo se le relative env sono valorizzate. Senza,
> il sito funziona comunque con email + password.

## 2FA

1. Login → `/account/security` → **Attiva 2FA**.
2. Scansiona il QR con Google Authenticator / Authy / 1Password.
3. Conferma il codice a 6 cifre → ricevi i codici di recupero (una volta sola).
4. Da lì in poi, al login viene chiesto il codice dopo email + password.

Il flusso usa `/api/auth/precheck` per capire se serve la 2FA (Auth.js maschera
gli errori di `authorize`), poi il vero `signIn` con il token.

## Struttura

```
web/
├── prisma/
│   ├── schema.prisma          # User, Account, Session, Waitlist, ContactMessage, AuditLog, FeatureFlag
│   └── seed.ts                # admin Scr1p73d + flag + demo
├── src/
│   ├── auth.ts                # NextAuth (adapter + Credentials + OAuth)
│   ├── auth.config.ts         # config edge-safe (middleware)
│   ├── middleware.ts          # guardie /account e /admin
│   ├── app/
│   │   ├── (marketing)/       # landing, features, docs, changelog, download, privacy, contatti
│   │   ├── (auth)/            # login, register, verify
│   │   ├── account/           # area utente (panoramica, sicurezza/2FA, attività)
│   │   ├── admin/             # dashboard (utenti, waitlist, messaggi, flag, audit)
│   │   └── api/               # register, waitlist, contact, 2fa/*, account, auth/*
│   ├── components/            # ui, motion, site, landing, auth, account, admin, dashboard
│   └── lib/                   # db, totp, validations, rate-limit, audit, utils
└── ...
```

## Script

| Comando | Cosa fa |
|---------|---------|
| `npm run dev` | dev server |
| `npm run build` | prisma generate + build di produzione |
| `npm start` | server di produzione |
| `npm run db:push` | sincronizza schema → DB |
| `npm run db:seed` | (ri)crea admin + dati demo |
| `npm run db:studio` | Prisma Studio |

## Deploy / produzione

- Cambia `provider` in `prisma/schema.prisma` da `sqlite` a `postgresql` e
  aggiorna `DATABASE_URL` (potrai anche reintrodurre gli `enum` veri).
- Imposta `AUTH_URL` sul dominio pubblico e un `AUTH_SECRET` forte.
- Il rate-limit è in-memory (per-istanza): per multi-nodo usa Redis/Upstash.

---

Costruito da **Scr1p73d**. Palette e funzionalità derivate dall'app Déjà
(`obsidian/deja/`).
