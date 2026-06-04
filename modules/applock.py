# modules/applock.py
"""
Blocco applicazione di Déjà: l'accesso a UI/cronologia richiede uno sblocco
esplicito. Due metodi:

- **Windows Hello** (biometrico/PIN di sistema) via WinRT `UserConsentVerifier`
  (pacchetti `winrt-*`). Degrada a non-disponibile se assente.
- **PIN app**: PBKDF2-HMAC-SHA256 (200k iter) + salt random; hash e salt salvati
  cifrati con DPAPI (`modules/secrets`). Funziona sempre, anche senza Hello.

Stato `_locked` in memoria. `ensure_unlocked()` è il gate da chiamare prima di
rivelare dati. Default: blocco ATTIVO, re-lock a OGNI accesso.
"""
import os
import hmac
import hashlib
import logging

from db import get_setting, save_setting
from modules import secrets

_log = logging.getLogger("deja")

_PBKDF2_ITER = 200_000
_SALT_BYTES = 16

# Parte bloccata: la prima azione che rivela dati dovrà sbloccare.
_locked = True
_hello_cache = None  # None = non ancora verificato


# ── Stato ──────────────────────────────────────────────────────────
def is_locked() -> bool:
    return _locked


def lock_now() -> None:
    global _locked
    _locked = True


def mark_unlocked() -> None:
    global _locked
    _locked = False


# ── Config (settings) ──────────────────────────────────────────────
def lock_enabled() -> bool:
    return (get_setting("lock_enabled", "1") or "1") == "1"


def set_lock_enabled(on: bool) -> None:
    save_setting("lock_enabled", "1" if on else "0")


def relock_policy() -> str:
    # every_access (default) | idle | manual
    return get_setting("lock_relock", "every_access") or "every_access"


def lock_method() -> str:
    # hello | pin | both
    m = get_setting("lock_method", "") or ""
    if m:
        return m
    return "both" if hello_available() else "pin"


def lock_idle_min() -> int:
    try:
        return int(get_setting("lock_idle_min", "5") or 5)
    except (ValueError, TypeError):
        return 5


# ── Windows Hello ──────────────────────────────────────────────────
def hello_available() -> bool:
    global _hello_cache
    if _hello_cache is not None:
        return _hello_cache
    _hello_cache = False
    try:
        import asyncio
        from winrt.windows.security.credentials.ui import (
            UserConsentVerifier, UserConsentVerifierAvailability,
        )
        avail = asyncio.run(UserConsentVerifier.check_availability_async())
        _hello_cache = (avail == UserConsentVerifierAvailability.AVAILABLE)
    except Exception as e:
        _log.info("Windows Hello non disponibile: %r", e)
        _hello_cache = False
    return _hello_cache


def hello_verify(message: str = "Sblocca Déjà") -> bool:
    """Mostra il prompt Hello e ritorna True se l'identità è verificata.
    Richiede una finestra in foreground; in caso di errore ritorna False
    (il chiamante ricade sul PIN)."""
    try:
        import asyncio
        from winrt.windows.security.credentials.ui import (
            UserConsentVerifier, UserConsentVerificationResult,
        )
        res = asyncio.run(UserConsentVerifier.request_verification_async(message))
        return res == UserConsentVerificationResult.VERIFIED
    except Exception as e:
        _log.warning("Hello verify fallita: %r", e)
        return False


# ── PIN app ────────────────────────────────────────────────────────
def _hash_pin(pin: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _PBKDF2_ITER)


def has_pin() -> bool:
    return bool(get_setting("lock_pin_hash"))


def set_pin(pin: str) -> None:
    salt = os.urandom(_SALT_BYTES)
    h = _hash_pin(pin, salt)
    save_setting("lock_pin_hash", secrets.protect_secret(h.hex()))
    save_setting("lock_pin_salt", secrets.protect_secret(salt.hex()))


def clear_pin() -> None:
    save_setting("lock_pin_hash", "")
    save_setting("lock_pin_salt", "")


def verify_pin(pin: str) -> bool:
    sh = get_setting("lock_pin_hash")
    ss = get_setting("lock_pin_salt")
    if not sh or not ss:
        return False
    try:
        salt = bytes.fromhex(secrets.reveal_secret(ss))
        expected = bytes.fromhex(secrets.reveal_secret(sh))
    except Exception:
        return False
    return hmac.compare_digest(_hash_pin(pin, salt), expected)


# ── Gate ───────────────────────────────────────────────────────────
def has_usable_method() -> bool:
    """Esiste un modo per sbloccare (PIN impostato o Hello disponibile)?
    Se no, non si applica il blocco per non bloccare fuori l'utente."""
    return has_pin() or hello_available()


def needs_unlock() -> bool:
    """True se serve uno sblocco per rivelare dati ora."""
    return lock_enabled() and is_locked() and has_usable_method()


def ensure_unlocked(parent=None) -> bool:
    """Chiamare PRIMA di rivelare dati. Se serve, apre il LockDialog.
    Ritorna True se l'accesso è consentito."""
    if not needs_unlock():
        return True
    try:
        from ui.lock import require_unlock
    except Exception as e:
        _log.error("LockDialog non caricabile, accesso negato: %r", e)
        return False
    if require_unlock(parent):
        mark_unlocked()
        return True
    return False
