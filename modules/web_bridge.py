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
import re
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
    "vivaldi.exe", "firefox.exe", "browser.exe", "comet.exe", "arc.exe",
    "zen.exe", "floorp.exe", "librewolf.exe", "waterfox.exe", "thorium.exe",
    "chromium.exe", "brave-browser.exe", "yandex.exe", "dragon.exe",
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


# ── Foreground browser ─────────────────────────────────────────────
# Nomi WM_CLASS dei browser su Linux/X11 (equivalente degli exe su Windows).
_BROWSERS_LINUX = {
    "google-chrome", "chromium", "chromium-browser", "microsoft-edge",
    "brave-browser", "firefox", "opera", "vivaldi",
}
_fg_cache = {"ts": 0.0, "val": ""}  # xdotool = subprocess: cache 2s


def _foreground_exe_linux() -> str:
    import time as _t
    import subprocess
    now = _t.time()
    if now - _fg_cache["ts"] < 2:
        return _fg_cache["val"]
    val = ""
    try:
        r = subprocess.run(["xdotool", "getactivewindow", "getwindowclassname"],
                           capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            val = r.stdout.strip().lower()
    except Exception:
        pass
    _fg_cache.update(ts=now, val=val)
    return val


def _foreground_exe() -> str:
    import sys
    if sys.platform != "win32":
        return _foreground_exe_linux() if sys.platform == "linux" else ""
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


def _browser_set() -> set:
    """Lista browser nota + eventuali extra aggiunti dall'utente
    (setting `web_browsers_extra`, separati da virgola) — così un browser nuovo
    non rompe la feature. Windows: nomi exe. Linux: nomi WM_CLASS."""
    import sys
    extra = (get_setting("web_browsers_extra", "") or "")
    if sys.platform == "linux":
        out = set(_BROWSERS_LINUX)
        for e in extra.replace("\n", ",").split(","):
            e = e.strip().lower().removesuffix(".exe")
            if e:
                out.add(e)
        return out
    out = set(_BROWSERS)
    for e in extra.replace("\n", ",").split(","):
        e = e.strip().lower()
        if e:
            out.add(e if e.endswith(".exe") else e + ".exe")
    return out


def is_browser_foreground() -> bool:
    return _foreground_exe() in _browser_set()


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


# Linux: i browser Chromium leggono i manifest da directory utente fisse
# (niente registro). L'host è uno script sh invece del .bat.
_NM_LINUX_DIRS = (
    "~/.config/google-chrome/NativeMessagingHosts",
    "~/.config/chromium/NativeMessagingHosts",
    "~/.config/microsoft-edge/NativeMessagingHosts",
    "~/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts",
)


def _write_manifest(mpath: str, host_path: str, ext_id: str):
    manifest = {
        "name": HOST_ID,
        "description": "Deja browser bridge",
        "path": host_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _install_native_host_linux(ext_id: str):
    import sys
    d = paths.data_dir()
    sh = os.path.join(d, "web_host.sh")
    if getattr(sys, "frozen", False):
        body = f'#!/bin/sh\nexec "{sys.executable}" --web-host "$@"\n'
    else:
        body = f'#!/bin/sh\nexec "{sys.executable}" "{_host_script()}" "$@"\n'
    with open(sh, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    os.chmod(sh, 0o755)
    written = []
    for base in _NM_LINUX_DIRS:
        try:
            bdir = os.path.expanduser(base)
            os.makedirs(bdir, exist_ok=True)
            mpath = os.path.join(bdir, HOST_ID + ".json")
            _write_manifest(mpath, sh, ext_id)
            written.append(mpath)
        except Exception:
            pass
    if not written:
        return False, "nessuna directory browser scrivibile"
    _log.info("Native host (linux) registrato per ext_id=%s", ext_id)
    return True, written[0]


def install_native_host(ext_id: str = None):
    """Registra l'host native messaging per i browser Chromium.
    Windows: chiavi HKCU + manifest .bat. Linux: manifest nelle directory
    NativeMessagingHosts dei browser + script sh. Ritorna (ok, msg)."""
    import sys
    ext_id = (ext_id or get_setting("web_ext_id", "") or "").strip().lower()
    # Un ID Chrome è esattamente 32 caratteri in a–p. `isalpha()` è
    # unicode-aware: accettava 32 lettere accentate/cirilliche e registrava un
    # manifest inutile dicendo "fatto".
    if not re.fullmatch(r"[a-p]{32}", ext_id):
        return False, "ID estensione non valido"
    if sys.platform == "linux":
        return _install_native_host_linux(ext_id)
    try:
        import winreg
    except Exception:
        return False, "registrazione non disponibile su questa piattaforma"

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
    """Rimuove la registrazione dell'host (best effort)."""
    import sys
    if sys.platform == "linux":
        for base in _NM_LINUX_DIRS:
            try:
                p = os.path.join(os.path.expanduser(base), HOST_ID + ".json")
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        return
    try:
        import winreg
    except Exception:
        return
    for base in _NM_REG_BASES:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base + "\\" + HOST_ID)
        except Exception:
            pass
