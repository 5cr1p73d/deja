# modules/secrets.py
"""
Protezione segreti a riposo per Déjà.

- Windows: **DPAPI** (legato all'account utente; nessuna dipendenza esterna).
- Linux: **keyring** (SecretService → GNOME Keyring/KWallet) se disponibile;
  chiave DB in keyring, valore nel DB = solo un riferimento `keyring:v1:`.
  Senza keyring degrada come prima (plaintext + warning; dbkey in file 0600).

- `protect_secret` / `reveal_secret`: cifrano stringhe (API key) prima di
  salvarle nel DB. Prefissi `dpapi:v1:` / `keyring:v1:` distinguono i valori
  protetti dai legacy in chiaro (migrazione trasparente alla riscrittura).
- `get_db_key_hex`: chiave a 256 bit per SQLCipher, generata una volta,
  MAI nel DB: Windows → `dbkey.bin` protetto DPAPI; Linux → voce keyring
  (fallback file 0600 se keyring assente).
"""
import os
import sys
import base64
import logging

import paths

_log = logging.getLogger("deja")

SECRET_MARKER = "dpapi:v1:"
KEYRING_MARKER = "keyring:v1:"
_KEYRING_SERVICE = "Deja"
_DB_KEYFILE = os.path.join(paths.data_dir(), "dbkey.bin")

# ── DPAPI via ctypes (nessuna dipendenza esterna) ──────────────────
try:
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _DPAPI = True
except Exception:  # non-Windows / ambiente senza crypt32
    _DPAPI = False

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def dpapi_available() -> bool:
    return _DPAPI


# ── Keyring (Linux: SecretService/KWallet) ─────────────────────────
_keyring = None
_keyring_checked = False


def _get_keyring():
    """Backend keyring (solo non-Windows; su Windows si usa DPAPI). Lazy: la
    libreria può mancare o non avere un daemon utilizzabile → None e degrado."""
    global _keyring, _keyring_checked
    if _keyring_checked:
        return _keyring
    _keyring_checked = True
    if sys.platform == "win32":
        return None
    try:
        import keyring
        from keyring.errors import NoKeyringError  # noqa: F401
        kr = keyring.get_keyring()
        # Scarta i backend "fail" (nessun servizio disponibile).
        if kr is None or "fail" in type(kr).__module__:
            _log.warning("keyring senza backend utilizzabile: segreti in chiaro")
            return None
        _keyring = keyring
    except Exception as e:
        _log.warning("keyring non disponibile (%r): segreti in chiaro", e)
        _keyring = None
    return _keyring


def keyring_available() -> bool:
    return _get_keyring() is not None


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(bytes(data), len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _blob_to_bytes(blob: "_DATA_BLOB") -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(blob.pbData)


def dpapi_protect(data: bytes) -> bytes:
    if not _DPAPI:
        raise RuntimeError("DPAPI non disponibile")
    blob_in, _b = _blob(data)
    blob_out = _DATA_BLOB()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptProtectData fallita")
    return _blob_to_bytes(blob_out)


def dpapi_unprotect(data: bytes) -> bytes:
    if not _DPAPI:
        raise RuntimeError("DPAPI non disponibile")
    blob_in, _b = _blob(data)
    blob_out = _DATA_BLOB()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptUnprotectData fallita")
    return _blob_to_bytes(blob_out)


# ── API segreti (stringhe) ─────────────────────────────────────────
def protect_secret(plain: str) -> str:
    """Protegge una stringa per la persistenza nel DB.
    Windows → `dpapi:v1:<b64>`. Linux+keyring → il valore vive nel portachiavi
    di sistema e nel DB va solo un riferimento `keyring:v1:<handle>`.
    Senza backend disponibile: valore in chiaro (non peggiore di prima) + warn."""
    if not plain:
        return plain
    if plain.startswith(SECRET_MARKER) or plain.startswith(KEYRING_MARKER):
        return plain  # già protetto
    if _DPAPI:
        try:
            enc = dpapi_protect(plain.encode("utf-8"))
            return SECRET_MARKER + base64.b64encode(enc).decode("ascii")
        except Exception as e:
            _log.error("protect_secret fallita: %r", e)
            return plain
    kr = _get_keyring()
    if kr is not None:
        try:
            handle = "secret-" + os.urandom(12).hex()
            kr.set_password(_KEYRING_SERVICE, handle, plain)
            return KEYRING_MARKER + handle
        except Exception as e:
            _log.error("protect_secret (keyring) fallita: %r", e)
            return plain
    _log.warning("Nessun backend segreti (DPAPI/keyring): salvato in chiaro")
    return plain


def reveal_secret(stored: str) -> str:
    """Recupera un valore salvato. Gestisce i legacy in chiaro (senza marker)."""
    if not stored:
        return stored
    if stored.startswith(KEYRING_MARKER):
        kr = _get_keyring()
        if kr is None:
            return ""
        try:
            return kr.get_password(_KEYRING_SERVICE, stored[len(KEYRING_MARKER):]) or ""
        except Exception as e:
            _log.error("reveal_secret (keyring) fallita: %r", e)
            return ""
    if not stored.startswith(SECRET_MARKER):
        return stored  # legacy plaintext
    if not _DPAPI:
        return ""
    try:
        raw = base64.b64decode(stored[len(SECRET_MARKER):])
        return dpapi_unprotect(raw).decode("utf-8")
    except Exception as e:
        _log.error("reveal_secret fallita (chiave di altro utente?): %r", e)
        return ""


def is_protected(stored: str) -> bool:
    return bool(stored) and (stored.startswith(SECRET_MARKER)
                             or stored.startswith(KEYRING_MARKER))


# ── Chiave DB (SQLCipher) ──────────────────────────────────────────
def _db_key_windows():
    """Chiave in `dbkey.bin` protetta DPAPI (percorso storico Windows)."""
    if os.path.exists(_DB_KEYFILE):
        with open(_DB_KEYFILE, "rb") as f:
            blob = f.read()
        key = dpapi_unprotect(blob)
        if len(key) == 32:
            return key.hex()
        _log.error("dbkey.bin corrotto (len=%d)", len(key))
        return None
    key = os.urandom(32)
    blob = dpapi_protect(key)
    tmp = _DB_KEYFILE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, _DB_KEYFILE)
    return key.hex()


def _db_key_keyring(kr):
    """Chiave nel portachiavi di sistema (Linux). Fallback file 0600 se il
    set fallisce a metà non è previsto: o keyring o niente cifratura."""
    val = kr.get_password(_KEYRING_SERVICE, "db_key_hex")
    if val:
        v = val.strip()
        if len(v) == 64:
            return v
        _log.error("db_key_hex in keyring corrotto (len=%d)", len(v))
        return None
    key = os.urandom(32).hex()
    kr.set_password(_KEYRING_SERVICE, "db_key_hex", key)
    return key


def get_db_key_hex():
    """Ritorna la chiave SQLCipher come 64 caratteri hex (32 byte), oppure
    None se nessun backend è disponibile (DB resta in chiaro, degradazione
    sicura). Windows: dbkey.bin+DPAPI. Linux: voce keyring 'Deja/db_key_hex'."""
    try:
        if _DPAPI:
            return _db_key_windows()
        kr = _get_keyring()
        if kr is not None:
            return _db_key_keyring(kr)
        _log.warning("Nessun backend chiavi (DPAPI/keyring): DB non cifrabile qui")
        return None
    except Exception as e:
        _log.error("get_db_key_hex fallita: %r", e)
        return None
