# modules/privacy.py
"""
Privacy control hub: pause flag, idle detection, app blocklist, OCR redaction.
"""
import re
import time
import ctypes
import threading
import fnmatch

# ── Global pause flag ─────────────────────────────────────────────
_pause_until = 0.0   # epoch sec. Se > now: paused
_pause_lock = threading.Lock()

def is_paused() -> bool:
    with _pause_lock:
        return time.time() < _pause_until

def pause_for(seconds: int):
    """Privacy mode: pausa capture per N secondi."""
    global _pause_until
    with _pause_lock:
        _pause_until = max(_pause_until, time.time() + seconds)

def pause_until_ts() -> float:
    with _pause_lock:
        return _pause_until

def unpause():
    global _pause_until
    with _pause_lock:
        _pause_until = 0.0


# ── Idle detection (Windows GetLastInputInfo) ─────────────────────
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def idle_seconds() -> float:
    """Secondi da ultima interazione utente (mouse/tastiera). 0 se non Windows."""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(0.0, millis / 1000.0)
    except Exception:
        return 0.0


def is_workstation_locked() -> bool:
    """True se schermo bloccato (Win+L)."""
    try:
        user32 = ctypes.windll.User32
        # OpenInputDesktop: ritorna NULL se locked
        hdesk = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if hdesk == 0:
            return True
        user32.CloseDesktop(hdesk)
        return False
    except Exception:
        return False


# ── App blocklist ─────────────────────────────────────────────────
def parse_blocklist(raw: str) -> list[str]:
    """Comma/newline separated patterns → list. Supporta wildcard fnmatch."""
    if not raw: return []
    parts = []
    for chunk in raw.replace("\n", ",").split(","):
        s = chunk.strip()
        if s: parts.append(s)
    return parts

def is_app_blocked(app_name: str, patterns: list[str]) -> bool:
    if not app_name or not patterns: return False
    name_lower = app_name.lower()
    for p in patterns:
        p = p.strip().lower()
        if not p: continue
        # fnmatch supporta * e ?, oppure substring se no wildcard
        if any(ch in p for ch in "*?[]"):
            if fnmatch.fnmatch(name_lower, p): return True
        else:
            if p in name_lower: return True
    return False


# ── OCR redaction ─────────────────────────────────────────────────
_REDACT_PATTERNS = [
    # Token / API key visibili a schermo (OpenAI sk-, GitHub ghp_, Google AIza,
    # Slack xox*) → tolti per primi (possono contenere cifre che altri pattern
    # spezzerebbero).
    (re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
                r"xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z\-_]{30,})\b"), "***SECRET***"),
    # Carte credito (semplificato): 13-19 digits con separatori opzionali
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "***CARD***"),
    # IBAN (basic): IT + 25 char alfanumeric
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "***IBAN***"),
    # Codice fiscale italiano (6 lettere + 2 cifre + 1 lettera + 2 cifre + 1 lettera + 3 alphanum + 1 lettera)
    (re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.IGNORECASE), "***CF***"),
    # Email
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "***EMAIL***"),
    # Telefono: prefisso internazionale opzionale + gruppi separati (richiede
    # almeno un separatore per evitare di colpire ID/numeri lunghi senza spazi).
    (re.compile(r"(?<!\d)(?:\+\d{1,3}[ .\-]?)?(?:\(?\d{2,4}\)?[ .\-]){1,3}\d{2,4}(?!\d)"), "***TEL***"),
]

def redact_pii(text: str, enabled: bool = True) -> str:
    if not enabled or not text: return text or ""
    out = text
    for pat, repl in _REDACT_PATTERNS:
        out = pat.sub(repl, out)
    return out
