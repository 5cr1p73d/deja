# modules/web_bridge.py
"""
Bridge con l'estensione browser (canale sicuro, **senza porta di rete**).

L'estensione → host nativo (native messaging) → scrive `web_state.json` nella
user data dir. Qui lo leggiamo per decidere se **saltare la cattura** quando la
tab attiva del browser è una schermata di login o un sito escluso dall'utente.

Tutto è **OFF di default**: se la feature non è abilitata o lo stato è assente/
stantio, `should_skip()` ritorna False e la cattura procede come sempre.
"""
import os
import json
import time
import logging

import paths
from db import get_setting, save_setting

_log = logging.getLogger("deja")

# Browser noti (basename exe in foreground). Lo skip vale solo se in primo
# piano c'è un browser: la tab attiva dell'estensione = ciò che è a schermo.
_BROWSERS = {
    "chrome.exe", "msedge.exe", "brave.exe", "opera.exe", "opera_gx.exe",
    "vivaldi.exe", "firefox.exe", "browser.exe",
}

# s: oltre, lo stato è stantio (browser chiuso) → ignora. Tollerante perché
# l'estensione fa heartbeat ogni ~30s (limite minimo di chrome.alarms in MV3).
_STATE_MAX_AGE = 75.0


def state_path() -> str:
    return os.path.join(paths.data_dir(), "web_state.json")


# ── Config (settings) ──────────────────────────────────────────────
def enabled() -> bool:
    return (get_setting("web_bridge_enabled", "0") or "0") == "1"


def set_enabled(on: bool) -> None:
    save_setting("web_bridge_enabled", "1" if on else "0")


def _norm_domain(s: str) -> str:
    """Normalizza un input in dominio: accetta anche URL completi o con www.
    'https://archive.org/signup' → 'archive.org', 'www.Bank.com' → 'bank.com'."""
    s = (s or "").strip().lower()
    if not s:
        return ""
    if "://" in s or "/" in s:
        try:
            from urllib.parse import urlparse
            host = urlparse(s if "://" in s else "http://" + s).hostname or ""
            s = host
        except Exception:
            s = s.split("/", 1)[0]
    s = s.lstrip(".")
    if s.startswith("www."):
        s = s[4:]
    return s


def excluded_domains() -> list:
    raw = get_setting("web_excluded_domains", "") or ""
    out = []
    for line in raw.replace(",", "\n").splitlines():
        d = _norm_domain(line)
        if d:
            out.append(d)
    return out


def set_excluded_domains(text: str) -> None:
    save_setting("web_excluded_domains", text or "")


# ── Stato dall'estensione ──────────────────────────────────────────
def read_state():
    """Ritorna il dict di stato se presente e fresco, altrimenti None."""
    p = state_path()
    try:
        if not os.path.exists(p):
            return None
        if (time.time() - os.path.getmtime(p)) > _STATE_MAX_AGE:
            return None
        with open(p, "r", encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return None
    if not isinstance(st, dict):
        return None
    # Doppio controllo freschezza anche col ts interno (se presente).
    ts = st.get("ts")
    if isinstance(ts, (int, float)) and (time.time() - ts) > _STATE_MAX_AGE:
        return None
    return st


# ── Foreground browser (ctypes) ────────────────────────────────────
def _foreground_exe() -> str:
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value.rsplit("\\", 1)[-1].lower()
        finally:
            k32.CloseHandle(h)
    except Exception:
        return ""


def is_browser_foreground() -> bool:
    return _foreground_exe() in _BROWSERS


# ── Decisione ──────────────────────────────────────────────────────
def _domain_excluded(domain: str) -> bool:
    domain = _norm_domain(domain)
    if not domain:
        return False
    for d in excluded_domains():
        if domain == d or domain.endswith("." + d):
            return True
    return False


def should_skip() -> bool:
    """True se va saltata la cattura ORA per via dell'estensione browser:
    abilitata + stato fresco + browser in foreground + (login o sito escluso)."""
    if not enabled():
        return False
    st = read_state()
    if not st:
        return False
    if not is_browser_foreground():
        return False
    tab = st.get("tab") or {}
    if tab.get("is_login"):
        return True
    if tab.get("is_excluded"):
        return True
    # Difesa extra: rivaluta l'esclusione lato app (lista può essere cambiata).
    return _domain_excluded(tab.get("domain", ""))


def is_connected() -> bool:
    """True se l'estensione sta scrivendo stato fresco (host connesso)."""
    return read_state() is not None


# ── Registrazione host native messaging ────────────────────────────
HOST_ID = "com.deja.bridge"

# Browser Chromium che leggono la chiave registro HKCU.
_NM_REG_BASES = (
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
)


def _host_script() -> str:
    return paths.resource_path(os.path.join("extension", "host", "web_host.py"))


def install_native_host(ext_id: str = None):
    """Registra l'host native messaging per i browser Chromium (HKCU).
    Richiede l'ID dell'estensione (incollato dall'utente). Ritorna (ok, msg)."""
    import sys
    ext_id = (ext_id or get_setting("web_ext_id", "") or "").strip()
    if not ext_id or len(ext_id) != 32 or not ext_id.isalpha():
        return False, "ID estensione non valido"
    try:
        import winreg
    except Exception:
        return False, "registrazione disponibile solo su Windows"

    d = paths.data_dir()
    bat = os.path.join(d, "web_host.bat")
    if getattr(sys, "frozen", False):
        body = f'@echo off\r\n"{sys.executable}" --web-host %*\r\n'
    else:
        body = f'@echo off\r\n"{sys.executable}" "{_host_script()}" %*\r\n'
    with open(bat, "w", encoding="utf-8") as f:
        f.write(body)

    manifest = {
        "name": HOST_ID,
        "description": "Deja browser bridge",
        "path": bat,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }
    mpath = os.path.join(d, HOST_ID + ".json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    for base in _NM_REG_BASES:
        try:
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + HOST_ID)
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, mpath)
            winreg.CloseKey(k)
        except Exception:
            pass
    _log.info("Native host registrato per ext_id=%s", ext_id)
    return True, mpath


def uninstall_native_host():
    """Rimuove le chiavi registro dell'host (best effort)."""
    try:
        import winreg
    except Exception:
        return
    for base in _NM_REG_BASES:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + "\\" + HOST_ID)
        except Exception:
            pass
