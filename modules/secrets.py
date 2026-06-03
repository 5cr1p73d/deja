# modules/secrets.py
"""
Protezione segreti a riposo per Déjà (Windows DPAPI, legato all'utente).

- `protect_secret` / `reveal_secret`: cifrano stringhe (API key) prima di
  salvarle nel DB. I valori cifrati hanno il prefisso `dpapi:v1:` per
  distinguerli da quelli legacy in chiaro (migrazione trasparente alla prima
  riscrittura).
- `get_db_key_hex`: chiave a 256 bit per SQLCipher, generata una volta e
  salvata su disco protetta con DPAPI (`dbkey.bin`), MAI nel DB.

DPAPI lega i dati all'account utente Windows: copiati su un altro PC/utente non
sono decifrabili (atteso e corretto per la privacy). Se DPAPI non è disponibile
(es. OS non Windows in dev) le funzioni degradano in modo sicuro e segnalano.
"""
import os
import base64
import logging

import paths

_log = logging.getLogger("deja")

SECRET_MARKER = "dpapi:v1:"
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
    """Cifra una stringa per la persistenza. Ritorna `dpapi:v1:<b64>`.
    Se DPAPI non è disponibile, ritorna il valore in chiaro (non peggiore di
    prima) e logga un avviso."""
    if not plain:
        return plain
    if plain.startswith(SECRET_MARKER):
        return plain  # già cifrato
    if not _DPAPI:
        _log.warning("DPAPI non disponibile: segreto salvato in chiaro")
        return plain
    try:
        enc = dpapi_protect(plain.encode("utf-8"))
        return SECRET_MARKER + base64.b64encode(enc).decode("ascii")
    except Exception as e:
        _log.error("protect_secret fallita: %r", e)
        return plain


def reveal_secret(stored: str) -> str:
    """Decifra un valore salvato. Gestisce i legacy in chiaro (senza marker)."""
    if not stored:
        return stored
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
    return bool(stored) and stored.startswith(SECRET_MARKER)


# ── Chiave DB (SQLCipher) ──────────────────────────────────────────
def get_db_key_hex():
    """Ritorna la chiave SQLCipher come 64 caratteri hex (32 byte), oppure
    None se DPAPI non è disponibile (in tal caso il DB resta in chiaro,
    degradazione sicura). La chiave è generata una sola volta e salvata in
    `dbkey.bin` protetta con DPAPI."""
    if not _DPAPI:
        _log.warning("DPAPI non disponibile: DB non cifrabile su questo ambiente")
        return None
    try:
        if os.path.exists(_DB_KEYFILE):
            with open(_DB_KEYFILE, "rb") as f:
                blob = f.read()
            key = dpapi_unprotect(blob)
            if len(key) == 32:
                return key.hex()
            _log.error("dbkey.bin corrotto (len=%d)", len(key))
            return None
        # Genera nuova chiave
        key = os.urandom(32)
        blob = dpapi_protect(key)
        tmp = _DB_KEYFILE + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, _DB_KEYFILE)
        return key.hex()
    except Exception as e:
        _log.error("get_db_key_hex fallita: %r", e)
        return None
