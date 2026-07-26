# modules/privacy.py
"""
Privacy control hub: pause flag, idle detection, app blocklist, OCR redaction.
Idle/lock: Windows via user32; Linux via XScreenSaver (libXss) e DBus
(best-effort: se mancano, idle=0 e locked=False → nessuna pausa automatica).
"""
import os
import re
import sys
import time
import ctypes
import threading
import fnmatch
import subprocess

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


# ── Idle detection ─────────────────────────────────────────────────
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


# X11/XScreenSaver via ctypes (nessuna dipendenza python): lazy, una volta.
_xss = None            # (xlib, xss, dpy, root) oppure False se non disponibile
_xss_lock = threading.Lock()


class _XScreenSaverInfo(ctypes.Structure):
    _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int),
                ("kind", ctypes.c_int), ("til_or_since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong), ("eventMask", ctypes.c_ulong)]


def _get_xss():
    """Inizializza libX11+libXss (solo Linux/X11). False se impossibile."""
    global _xss
    if _xss is not None:
        return _xss
    with _xss_lock:
        if _xss is not None:
            return _xss
        try:
            if sys.platform != "linux" or not os.environ.get("DISPLAY"):
                _xss = False
                return _xss
            xlib = ctypes.CDLL("libX11.so.6")
            xss = ctypes.CDLL("libXss.so.1")
            xlib.XOpenDisplay.restype = ctypes.c_void_p
            xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            xlib.XDefaultRootWindow.restype = ctypes.c_ulong
            xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(_XScreenSaverInfo)
            xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                  ctypes.POINTER(_XScreenSaverInfo)]
            dpy = xlib.XOpenDisplay(None)
            if not dpy:
                _xss = False
                return _xss
            root = xlib.XDefaultRootWindow(dpy)
            _xss = (xlib, xss, dpy, root)
        except Exception:
            _xss = False
    return _xss


def idle_seconds() -> float:
    """Secondi da ultima interazione utente (mouse/tastiera).
    Windows: GetLastInputInfo. Linux/X11: XScreenSaver. Altrimenti 0."""
    if sys.platform == "win32":
        try:
            lii = _LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(lii)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
        except Exception:
            return 0.0
    x = _get_xss()
    if not x:
        return 0.0
    try:
        xlib, xss, dpy, root = x
        info = xss.XScreenSaverAllocInfo()
        xss.XScreenSaverQueryInfo(dpy, root, info)
        idle_ms = info.contents.idle
        xlib.XFree(info)
        return max(0.0, idle_ms / 1000.0)
    except Exception:
        return 0.0


# Cache lock-state Linux: il probe è un subprocess gdbus, non va rifatto a
# ogni ciclo di cattura (5s). 10s di cache bastano; gdbus assente → off per sempre.
_lock_cache = {"ts": 0.0, "val": False, "dead": False}


def _linux_locked() -> bool:
    """Lock schermo su Linux, best-effort: org.freedesktop.ScreenSaver via
    gdbus (KDE/Cinnamon/MATE) poi GNOME. Fallisce → False (mai bloccare la
    cattura per un errore di rilevamento)."""
    if _lock_cache["dead"]:
        return False
    now = time.time()
    if now - _lock_cache["ts"] < 10:
        return _lock_cache["val"]
    probes = (
        ["gdbus", "call", "--session", "--dest", "org.freedesktop.ScreenSaver",
         "--object-path", "/org/freedesktop/ScreenSaver",
         "--method", "org.freedesktop.ScreenSaver.GetActive"],
        ["gdbus", "call", "--session", "--dest", "org.gnome.ScreenSaver",
         "--object-path", "/org/gnome/ScreenSaver",
         "--method", "org.gnome.ScreenSaver.GetActive"],
    )
    val = False
    for cmd in probes:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                val = "true" in r.stdout.lower()
                break
        except FileNotFoundError:
            _lock_cache["dead"] = True  # gdbus non installato: inutile riprovare
            return False
        except Exception:
            continue
    _lock_cache.update(ts=now, val=val)
    return val


def is_workstation_locked() -> bool:
    """True se schermo bloccato (Win+L / lock screen)."""
    if sys.platform == "win32":
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
    if sys.platform == "linux":
        return _linux_locked()
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
