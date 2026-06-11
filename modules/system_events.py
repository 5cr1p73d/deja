# modules/system_events.py
"""
Collector di eventi di sistema. Tutto OFF di default: ogni categoria ha il suo
toggle in Impostazioni → Eventi (chiavi `sysev_*_enabled`, default "0") riletto
a ogni ciclo, quindi on/off live senza riavvio.

Nessun privilegio admin: niente WMI/ETW/Security log. Tutto polling leggero
(psutil, registro, ctypes) + watchdog per il filesystem:

  sysev_process_enabled  – app aperte/chiuse        (diff psutil.pids)
  sysev_focus_enabled    – app in primo piano        (diff foreground exe)
  sysev_file_enabled     – file creati/eliminati/spostati nelle cartelle utente
  sysev_install_enabled  – programmi installati/disinstallati/aggiornati
  sysev_clock_enabled    – orario di sistema cambiato (wall vs GetTickCount64)
  sysev_power_enabled    – sospensione/ripresa        (TickCount vs UnbiasedInterruptTime)
  sysev_session_enabled  – blocco/sblocco sessione    (privacy.is_workstation_locked)
  sysev_device_enabled   – unità/dischi collegati/rimossi (diff disk_partitions)
  sysev_network_enabled  – interfacce di rete su/giù  (diff net_if_stats)

Gli eventi browser (download/tab/visite) NON nascono qui: arrivano
dall'estensione via spool e li inserisce `web_ingest` (chiavi `webev_*_enabled`).

Un solo writer DB: questo thread possiede la sua connessione; i callback di
watchdog (thread propri) accodano in una Queue consumata qui. Gate privacy:
pausa/incognito ferma tutto; blocklist app applicata agli eventi focus;
redazione PII su testo/subject se attiva.
"""
import os
import time
import json
import queue
import logging
import threading

from db import get_conn, log_system_event
from modules import privacy

_log = logging.getLogger("deja.sysevents")

# categoria → chiave settings (tutte default "0" = OFF)
CATEGORIES = ("process", "focus", "file", "install", "clock",
              "power", "session", "device", "network")
SETTING_KEYS = {c: f"sysev_{c}_enabled" for c in CATEGORIES}

# intervalli di polling per watcher (secondi)
_POLL = {"process": 2, "focus": 2, "session": 2, "clockpower": 2,
         "device": 5, "network": 5, "install": 30}

_TICK = 2          # passo del loop principale
_MAX_PER_CYCLE = 200   # tetto inserimenti per ciclo (tempeste watchdog)
_FILE_DEBOUNCE = 5.0   # stesso (path, azione) entro N s → uno solo

# coda eventi file: i thread watchdog producono, il loop consuma
_file_queue = queue.Queue(maxsize=4096)


def _read_flags(conn):
    """Tutti i toggle in UNA query sulla connessione del thread (niente
    get_setting per chiave: aprirebbe 9 connessioni a ciclo)."""
    keys = list(SETTING_KEYS.values()) + ["privacy_redact", "privacy_blocklist", "sysev_file_dirs"]
    ph = ",".join("?" * len(keys))
    vals = {}
    try:
        for k, v in conn.execute(f"SELECT key, value FROM settings WHERE key IN ({ph})", keys):
            vals[k] = v
    except Exception:
        pass
    flags = {c: (vals.get(SETTING_KEYS[c], "0") or "0") == "1" for c in CATEGORIES}
    redact = (vals.get("privacy_redact", "1") or "1") == "1"
    blocklist = privacy.parse_blocklist(vals.get("privacy_blocklist", "") or "")
    file_dirs = (vals.get("sysev_file_dirs", "") or "").strip()
    return flags, redact, blocklist, file_dirs


# ── Classificazione visibile vs background ──────────────────────────
# Nomi di processi notoriamente di sistema/servizio (mai roba che l'utente
# "usa"): marcati hidden anche se per un attimo avessero una finestra.
_DEJA_HELPER_NAMES = {"tesseract.exe", "conhost.exe"}
_BG_NAMES = {
    "svchost.exe", "dllhost.exe", "runtimebroker.exe", "backgroundtaskhost.exe",
    "wmiprvse.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
    "smss.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "taskhostw.exe",
    "searchindexer.exe", "searchprotocolhost.exe", "searchfilterhost.exe",
    "audiodg.exe", "spoolsv.exe", "wudfhost.exe", "dwm.exe", "msmpeng.exe",
    "securityhealthservice.exe", "securityhealthsystray.exe", "nissrv.exe",
    "applicationframehost.exe", "shellexperiencehost.exe", "lockapp.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe", "systemsettingsbroker.exe",
    "smartscreen.exe", "useroobebroker.exe", "wmiapsrv.exe", "spoolsv.exe",
    "registry", "memory compression", "system", "system idle process",
}


def _visible_window_pids():
    """PID che possiedono almeno una finestra top-level VISIBILE (non tool
    window, con titolo): ≈ le app in taskbar. ctypes EnumWindows, niente dep.

    NB: gli argtypes sono OBBLIGATORI — senza, ctypes assume c_int per gli
    argomenti puntatore e TRONCA l'HWND a 32 bit su Windows 64-bit, facendo
    restituire pid sbagliati a GetWindowThreadProcessId."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    pids = set()
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lp):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex & WS_EX_TOOLWINDOW:
                return True  # tool window: non è un'app in taskbar
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True  # senza titolo: ignora
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                pids.add(pid.value)
        except Exception:
            pass
        return True

    try:
        cb = WNDENUMPROC(_cb)
        user32.EnumWindows(cb, 0)
    except Exception:
        pass
    return pids


def _deja_pids():
    """PID del processo Déjà e dei suoi figli (tesseract/conhost spawnati)."""
    try:
        import psutil
        me = psutil.Process(os.getpid())
        pids = {me.pid}
        for ch in me.children(recursive=True):
            pids.add(ch.pid)
        return pids
    except Exception:
        return {os.getpid()}


def _is_known_background(info, deja_pids):
    """True se il processo è SICURAMENTE background (Déjà, helper, servizio
    Windows noto) a prescindere dalle finestre — decidibile subito, senza
    aspettare la grazia-finestra."""
    pid = info.get("pid")
    name = (info.get("name") or "").lower()
    return pid in deja_pids or name in _DEJA_HELPER_NAMES or name in _BG_NAMES


# ── Process: diff snapshot psutil, con classificazione visibile/nascosto ──
class _ProcWatch:
    # Polidi grazia: un'app appena avviata può non aver ancora disegnato la
    # finestra. Aspettiamo qualche poll prima di decretarla "nascosta".
    GRACE_POLLS = 3

    def __init__(self):
        self.known = {}      # key -> info (con _hidden deciso allo start)
        self.pending = {}    # key -> [info, polls_attesi]
        self.first = True

    def poll(self, emit, blocklist=None):
        import psutil
        bl = blocklist or []
        cur = {}
        for p in psutil.process_iter(["pid", "name", "exe", "username", "create_time"]):
            try:
                info = p.info
                cur[(info["pid"], info.get("create_time") or 0)] = info
            except Exception:
                continue
        if self.first:
            self.known = cur
            self.first = False
            return

        visible = _visible_window_pids()
        deja = _deja_pids()
        now = time.time()

        def _blocked(info):
            # blocklist privacy applicata al nome del processo (parità con gli
            # screenshot, che la applicano al titolo): app bloccata → niente
            # evento né start né stop.
            return bool(bl) and privacy.is_app_blocked(info.get("name") or "", bl)

        def _emit_start(info, hidden):
            emit("process", "start", subject=info.get("name") or "?",
                 detail={"pid": info["pid"], "exe": info.get("exe") or "",
                         "user": info.get("username") or ""},
                 text=f"Aperta app: {info.get('name') or '?'}", hidden=hidden)

        # nuovi pid → in attesa di classificazione (grazia finestra)
        for key, info in cur.items():
            if key not in self.known and key not in self.pending:
                self.pending[key] = [info, 0]

        # risolvi gli in-attesa. Priorità: blocklist → ignora del tutto; nomi
        # background noti (Déjà/helper/servizi) → hidden subito; poi finestra
        # visibile → mostra; infine grazia scaduta senza finestra → background.
        resolved = []
        for key, (info, waited) in self.pending.items():
            if _blocked(info):
                # tracciata in known come bloccata: niente emit, ma evita di
                # rimetterla in pending a ogni ciclo finché è viva.
                info["_blocked"] = True
                self.known[key] = info
                resolved.append(key)
                continue
            bg = _is_known_background(info, deja)
            if key not in cur:
                # morto prima di risolversi (tipico helper transitorio):
                # nascosto se è bg noto o non ha mai avuto finestra.
                h = 1 if (bg or info["pid"] not in visible) else 0
                _emit_start(info, h)
                run_s = max(0, int(now - (info.get("create_time") or now)))
                emit("process", "stop", subject=info.get("name") or "?",
                     detail={"pid": info["pid"], "exe": info.get("exe") or "",
                             "runtime_seconds": run_s},
                     text=f"Chiusa app: {info.get('name') or '?'}", hidden=h)
                resolved.append(key)
            elif bg:
                info["_hidden"] = 1
                _emit_start(info, 1)
                self.known[key] = info
                resolved.append(key)
            elif info["pid"] in visible:
                info["_hidden"] = 0
                _emit_start(info, 0)
                self.known[key] = info
                resolved.append(key)
            elif waited >= self.GRACE_POLLS:
                info["_hidden"] = 1   # nessuna finestra dopo la grazia → background
                _emit_start(info, 1)
                self.known[key] = info
                resolved.append(key)
            else:
                self.pending[key][1] += 1
        for k in resolved:
            self.pending.pop(k, None)

        # chiusure (riusa la classificazione fatta allo start; salta le bloccate)
        for key, info in list(self.known.items()):
            if key not in cur:
                if not info.get("_blocked"):
                    run_s = max(0, int(now - (info.get("create_time") or now)))
                    emit("process", "stop", subject=info.get("name") or "?",
                         detail={"pid": info["pid"], "exe": info.get("exe") or "",
                                 "user": info.get("username") or "",
                                 "runtime_seconds": run_s},
                         text=f"Chiusa app: {info.get('name') or '?'}",
                         hidden=info.get("_hidden", 0))
                del self.known[key]


# ── Focus: app in primo piano (exe + titolo) ────────────────────────
class _FocusWatch:
    def __init__(self):
        self.last_exe = None

    def poll(self, emit, blocklist):
        from modules.web_bridge import _foreground_exe
        exe = _foreground_exe()
        if not exe or exe == self.last_exe:
            return
        title = ""
        try:
            import pygetwindow as gw
            win = gw.getActiveWindow()
            title = win.title if win else ""
        except Exception:
            pass
        self.last_exe = exe
        # parità con gli screenshot: app in blocklist → nessun evento. Il titolo
        # può essere vuoto (alcune finestre non lo espongono): in quel caso il
        # match sul solo titolo fallirebbe, quindi controllo ANCHE il nome exe.
        if blocklist and (privacy.is_app_blocked(title, blocklist)
                          or privacy.is_app_blocked(exe, blocklist)):
            return
        emit("focus", "focus", subject=exe, app=title,
             detail={"exe": exe, "title": title},
             text=f"In primo piano: {exe}" + (f" — {title}" if title else ""))


# ── File: watchdog sulle cartelle utente ────────────────────────────
_FILE_IGNORE_EXT = {".tmp", ".crdownload", ".part", ".partial", ".download", ".swp"}
_FILE_IGNORE_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
_FILE_IGNORE_DIRS = (os.sep + "appdata" + os.sep, os.sep + ".git" + os.sep,
                     os.sep + "__pycache__" + os.sep, os.sep + "node_modules" + os.sep,
                     os.sep + "venv" + os.sep, os.sep + "$recycle.bin" + os.sep)


def _file_noise(path):
    p = (path or "").lower()
    base = os.path.basename(p)
    if base in _FILE_IGNORE_NAMES or base.startswith("~$"):
        return True
    if os.path.splitext(base)[1] in _FILE_IGNORE_EXT:
        return True
    return any(d in p for d in _FILE_IGNORE_DIRS)


def _default_file_dirs():
    home = os.path.expanduser("~")
    cands = [os.path.join(home, n) for n in
             ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
    return [d for d in cands if os.path.isdir(d)]


class _FileWatch:
    """Observer watchdog. I callback girano su thread watchdog → spingono in
    _file_queue; gli insert li fa il loop principale sulla SUA connessione."""

    def __init__(self, dirs):
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _H(FileSystemEventHandler):
            def on_created(self, ev):
                _push(("created", ev.src_path, "", ev.is_directory))

            def on_deleted(self, ev):
                _push(("deleted", ev.src_path, "", ev.is_directory))

            def on_moved(self, ev):
                _push(("moved", ev.src_path, ev.dest_path, ev.is_directory))

        def _push(item):
            try:
                _file_queue.put_nowait(item)
            except queue.Full:
                pass

        self.dirs = dirs
        self.observer = Observer()
        for d in dirs:
            try:
                self.observer.schedule(_H(), d, recursive=True)
            except Exception:
                _log.warning("watch dir fallita: %s", d)
        self.observer.daemon = True
        self.observer.start()

    def stop(self):
        try:
            self.observer.stop()
            self.observer.join(timeout=1)
        except Exception:
            pass


def _drain_file_queue(emit, debounce):
    """Consuma la coda watchdog con debounce (path, azione)."""
    now = time.time()
    drained = 0
    while drained < _MAX_PER_CYCLE:
        try:
            action, src, dest, is_dir = _file_queue.get_nowait()
        except queue.Empty:
            break
        drained += 1
        if _file_noise(src) or (dest and _file_noise(dest)):
            continue
        key = (action, src)
        if now - debounce.get(key, 0) < _FILE_DEBOUNCE:
            continue
        debounce[key] = now
        base = os.path.basename(dest or src)
        det = {"path": src, "is_dir": bool(is_dir),
               "ext": os.path.splitext(src)[1].lower(),
               "dir": os.path.dirname(src)}
        verb = {"created": "creato", "deleted": "eliminato", "moved": "spostato/rinominato"}[action]
        if action == "moved":
            det["dest"] = dest
        if action in ("created", "moved"):
            try:
                det["size_bytes"] = os.path.getsize(dest or src)
            except Exception:
                pass
        kind = "Cartella" if is_dir else "File"
        emit("file", action, subject=(dest or src),
             detail=det, text=f"{kind} {verb}: {base}")
    # pulizia debounce vecchio (no crescita infinita)
    if len(debounce) > 2000:
        cut = now - _FILE_DEBOUNCE
        for k in [k for k, t in debounce.items() if t < cut]:
            debounce.pop(k, None)


# ── Install: diff registro Uninstall (HKLM 64/32 + HKCU) ───────────
class _InstallWatch:
    _ROOTS = None  # lazy: winreg import solo qui

    def __init__(self):
        self.known = None

    def _snapshot(self):
        import winreg
        roots = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0),
        )
        snap = {}
        for hive, sub, wow in roots:
            try:
                k = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | wow)
            except OSError:
                continue
            try:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        sk = winreg.OpenKey(k, name)
                    except OSError:
                        continue
                    try:
                        vals = {}
                        for field in ("DisplayName", "DisplayVersion", "Publisher",
                                      "InstallLocation", "EstimatedSize"):
                            try:
                                vals[field] = winreg.QueryValueEx(sk, field)[0]
                            except OSError:
                                pass
                        if vals.get("DisplayName"):
                            snap[(int(hive), wow, name)] = vals
                    finally:
                        sk.Close()
            finally:
                k.Close()
        return snap

    def poll(self, emit):
        snap = self._snapshot()
        if self.known is None:
            self.known = snap
            return
        for key, v in snap.items():
            old = self.known.get(key)
            det = {"name": v.get("DisplayName", ""), "version": v.get("DisplayVersion", ""),
                   "publisher": v.get("Publisher", ""), "location": v.get("InstallLocation", ""),
                   "estimated_size_kb": v.get("EstimatedSize", 0)}
            if old is None:
                emit("install", "installed", subject=det["name"], detail=det,
                     text=f"Programma installato: {det['name']} {det['version']}".strip())
            elif old.get("DisplayVersion") != v.get("DisplayVersion"):
                det["old_version"] = old.get("DisplayVersion", "")
                emit("install", "updated", subject=det["name"], detail=det,
                     text=f"Programma aggiornato: {det['name']} → {det['version']}".strip())
        for key, v in self.known.items():
            if key not in snap:
                emit("install", "uninstalled", subject=v.get("DisplayName", ""),
                     detail={"name": v.get("DisplayName", ""),
                             "version": v.get("DisplayVersion", ""),
                             "publisher": v.get("Publisher", "")},
                     text=f"Programma disinstallato: {v.get('DisplayName', '')}")
        self.known = snap


# ── Clock + Power: confronto orologi Windows (ctypes, no finestre) ──
class _ClockPowerWatch:
    """GetTickCount64 conta ANCHE il sonno; QueryUnbiasedInterruptTime lo
    ESCLUDE. Quindi: delta(tick) - delta(unbiased) ≈ tempo dormito; e
    delta(wall) - delta(tick) ≈ spostamento dell'orologio di sistema."""

    def __init__(self):
        self.prev = None  # (wall, tick_s, unb_s)

    @staticmethod
    def _now():
        import ctypes
        k32 = ctypes.windll.kernel32
        tick_s = k32.GetTickCount64() / 1000.0
        unb = ctypes.c_ulonglong(0)
        try:
            k32.QueryUnbiasedInterruptTime(ctypes.byref(unb))
            unb_s = unb.value / 1e7  # unità da 100 ns
        except Exception:
            unb_s = tick_s
        return time.time(), tick_s, unb_s

    def poll(self, emit, clock_on, power_on):
        cur = self._now()
        if self.prev is None:
            self.prev = cur
            return
        d_wall = cur[0] - self.prev[0]
        d_tick = cur[1] - self.prev[1]
        d_unb = cur[2] - self.prev[2]
        self.prev = cur
        sleep_s = d_tick - d_unb
        if power_on and sleep_s > 30:
            mins = int(sleep_s // 60)
            emit("power", "resume", subject="standby",
                 detail={"sleep_seconds": int(sleep_s)},
                 text=f"PC ripreso dalla sospensione (dormito ~{mins} min)" if mins
                      else f"PC ripreso dalla sospensione ({int(sleep_s)} s)")
        clock_delta = d_wall - d_tick
        if clock_on and abs(clock_delta) > 10:
            emit("clock", "changed", subject="orologio di sistema",
                 detail={"delta_seconds": round(clock_delta, 1)},
                 text=f"Orario di sistema cambiato di {clock_delta:+.0f} s")


# ── Session: blocco/sblocco (riusa privacy.is_workstation_locked) ───
class _SessionWatch:
    def __init__(self):
        self.last = None

    def poll(self, emit):
        locked = privacy.is_workstation_locked()
        if self.last is None:
            self.last = locked
            return
        if locked != self.last:
            self.last = locked
            emit("session", "lock" if locked else "unlock", subject="sessione",
                 detail={"locked": bool(locked)},
                 text="Sessione bloccata" if locked else "Sessione sbloccata")


# ── Device: unità collegate/rimosse ─────────────────────────────────
def _volume_label(mountpoint):
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(mountpoint), buf, 256, None, None, None, None, 0)
        return buf.value
    except Exception:
        return ""


class _DeviceWatch:
    def __init__(self):
        self.known = None

    def poll(self, emit):
        import psutil
        cur = {}
        try:
            for p in psutil.disk_partitions(all=False):
                cur[p.device] = p
        except Exception:
            return
        if self.known is None:
            self.known = cur
            return
        for dev, p in cur.items():
            if dev not in self.known:
                det = {"device": dev, "mountpoint": p.mountpoint, "fstype": p.fstype,
                       "removable": "removable" in (p.opts or ""),
                       "label": _volume_label(p.mountpoint)}
                try:
                    det["total_bytes"] = psutil.disk_usage(p.mountpoint).total
                except Exception:
                    pass
                lab = f" ({det['label']})" if det.get("label") else ""
                emit("device", "connected", subject=dev, detail=det,
                     text=f"Unità collegata: {dev}{lab}")
        for dev, p in self.known.items():
            if dev not in cur:
                emit("device", "removed", subject=dev,
                     detail={"device": dev, "fstype": p.fstype},
                     text=f"Unità rimossa: {dev}")
        self.known = cur


# ── Network: interfacce su/giù ──────────────────────────────────────
class _NetWatch:
    def __init__(self):
        self.known = None

    def poll(self, emit):
        import psutil
        try:
            cur = {n: s.isup for n, s in psutil.net_if_stats().items()}
        except Exception:
            return
        if self.known is None:
            self.known = cur
            return
        for name, up in cur.items():
            if self.known.get(name) is not None and up != self.known[name]:
                emit("network", "up" if up else "down", subject=name,
                     detail={"interface": name, "isup": bool(up)},
                     text=f"Rete '{name}' {'connessa' if up else 'disconnessa'}")
        self.known = cur


# ── Loop principale ─────────────────────────────────────────────────
def run(stop_event):
    # Dipendenze opzionali verificate UNA volta (niente spam di eccezioni nel
    # loop se il build ne è privo): senza psutil cadono processi/device/rete,
    # senza watchdog cadono i file. Il resto (ctypes/winreg) è stdlib.
    try:
        import psutil  # noqa: F401
        have_psutil = True
    except Exception as e:
        have_psutil = False
        print(f"[SysEvents] psutil non disponibile ({e!r}): processi/unità/rete disattivati.")
    try:
        import watchdog  # noqa: F401
        have_watchdog = True
    except Exception as e:
        have_watchdog = False
        print(f"[SysEvents] watchdog non disponibile ({e!r}): eventi file disattivati.")

    conn = get_conn()
    print("[SysEvents] Avviato.")
    watchers = {}          # nome → istanza (creati solo quando il toggle è ON)
    file_watch = None
    file_dirs_cur = None
    debounce = {}
    last_poll = {}         # nome → epoch ultimo poll
    pending = 0

    def due(name, now):
        if now - last_poll.get(name, 0) >= _POLL[name]:
            last_poll[name] = now
            return True
        return False

    while not stop_event.is_set():
        try:
            flags, redact_on, blocklist, file_dirs_set = _read_flags(conn)
            if not have_psutil:
                flags["process"] = flags["device"] = flags["network"] = False
            if not have_watchdog:
                flags["file"] = False

            # tutto OFF → idle economico, butta giù l'observer file se attivo
            if not any(flags.values()):
                if file_watch is not None:
                    file_watch.stop(); file_watch = None; file_dirs_cur = None
                watchers.clear()
                stop_event.wait(timeout=3)
                continue

            # pausa/incognito ferma anche gli eventi — e NIENTE back-fill:
            # scarta la coda file accumulata e azzera gli snapshot dei watcher,
            # così l'attività avvenuta DURANTE la pausa non viene mai loggata
            # a posteriori (i diff ripartono da una baseline fresca).
            if privacy.is_paused():
                while not _file_queue.empty():
                    try: _file_queue.get_nowait()
                    except queue.Empty: break
                watchers.clear()
                stop_event.wait(timeout=_TICK)
                continue

            now = time.time()
            pending = 0

            def emit(category, action, subject="", app="", detail=None, text="", hidden=0):
                nonlocal pending
                if pending >= _MAX_PER_CYCLE:
                    return
                subject = privacy.redact_pii(subject or "", enabled=redact_on)
                app = privacy.redact_pii(app or "", enabled=redact_on)
                text = privacy.redact_pii(text or "", enabled=redact_on)
                # redazione anche sui valori del detail JSON (titoli finestre,
                # path, nomi file possono contenere email/PII): stesso gate
                # degli altri campi, altrimenti privacy_redact è aggirabile.
                if isinstance(detail, dict) and redact_on:
                    detail = {k: (privacy.redact_pii(v, enabled=True)
                                  if isinstance(v, str) else v)
                              for k, v in detail.items()}
                log_system_event(conn, "system", category, action,
                                 subject=subject, app=app, detail=detail, text=text,
                                 hidden=hidden)
                pending += 1

            # crea/distruggi watcher in base ai toggle (live)
            def _sync(name, cls, on):
                if on and name not in watchers:
                    watchers[name] = cls()
                elif not on and name in watchers:
                    watchers.pop(name, None)

            _sync("process", _ProcWatch, flags["process"])
            _sync("focus", _FocusWatch, flags["focus"])
            _sync("install", _InstallWatch, flags["install"])
            _sync("session", _SessionWatch, flags["session"])
            _sync("device", _DeviceWatch, flags["device"])
            _sync("network", _NetWatch, flags["network"])
            if flags["clock"] or flags["power"]:
                if "clockpower" not in watchers:
                    watchers["clockpower"] = _ClockPowerWatch()
            else:
                watchers.pop("clockpower", None)

            # file watcher: observer dedicato, ricreato se cambiano le cartelle
            if flags["file"]:
                dirs = ([d.strip() for d in file_dirs_set.split(";") if d.strip() and os.path.isdir(d.strip())]
                        if file_dirs_set else _default_file_dirs())
                if file_watch is None or dirs != file_dirs_cur:
                    if file_watch is not None:
                        file_watch.stop()
                    file_watch = _FileWatch(dirs) if dirs else None
                    file_dirs_cur = dirs
            elif file_watch is not None:
                file_watch.stop(); file_watch = None; file_dirs_cur = None
                # svuota la coda residua senza inserire
                while not _file_queue.empty():
                    try: _file_queue.get_nowait()
                    except queue.Empty: break

            # poll per watcher (ognuno col suo passo)
            if "process" in watchers and due("process", now):
                watchers["process"].poll(emit, blocklist)
            if "focus" in watchers and due("focus", now):
                watchers["focus"].poll(emit, blocklist)
            if "session" in watchers and due("session", now):
                watchers["session"].poll(emit)
            if "clockpower" in watchers and due("clockpower", now):
                watchers["clockpower"].poll(emit, flags["clock"], flags["power"])
            if "device" in watchers and due("device", now):
                watchers["device"].poll(emit)
            if "network" in watchers and due("network", now):
                watchers["network"].poll(emit)
            if "install" in watchers and due("install", now):
                watchers["install"].poll(emit)
            if file_watch is not None:
                _drain_file_queue(emit, debounce)

            if pending:
                conn.commit()
        except Exception as e:
            _log.exception("Errore ciclo system_events")
            print(f"[SysEvents] Errore ciclo (continuo): {e}")
        stop_event.wait(timeout=_TICK)

    if file_watch is not None:
        file_watch.stop()
    conn.close()
    print("[SysEvents] Fermato.")
