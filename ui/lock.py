# ui/lock.py
"""
Schermata di sblocco di Déjà (Windows Hello + PIN) e dialog di setup PIN.
Riusa lo stile scuro dell'onboarding. Modale, stays-on-top.
"""
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)

import i18n
from i18n import t
from modules import applock
from ui.framed import FramelessDialog

_log = logging.getLogger("deja")


def _dump_new_windows(seen: set) -> None:
    """Logga (una volta per coppia exe|classe) le finestre top-level estranee
    visibili — per identificare la finestra-prompt di Windows Hello."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        own = ctypes.windll.kernel32.GetCurrentProcessId()
        cls = ctypes.create_unicode_buffer(256)
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _l):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value == own:
                return True
            exe = _proc_basename(pid.value)
            user32.GetClassNameW(hwnd, cls, 256)
            key = (exe, cls.value)
            if key not in seen:
                seen.add(key)
                _log.info("Hello-scan finestra: exe=%s classe=%s", exe, cls.value)
            return True

        user32.EnumWindows(EnumProc(_cb), 0)
    except Exception:
        pass


def _force_foreground(win) -> None:
    """Porta la finestra in primo piano forzandolo (AttachThreadInput trick)."""
    try:
        import ctypes
        hwnd = int(win.winId())
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        HWND_TOPMOST = -1
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)
        fg = user32.GetForegroundWindow()
        cur_tid = kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if fg_tid and fg_tid != cur_tid:
            user32.AttachThreadInput(fg_tid, cur_tid, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if fg_tid and fg_tid != cur_tid:
            user32.AttachThreadInput(fg_tid, cur_tid, False)
    except Exception:
        pass


# Match per la finestra-prompt di Windows Hello/credenziali da ri-centrare.
# Il nome del processo è il segnale più affidabile (la classe finestra cambia
# tra versioni di Windows); la classe resta come fallback.
_HELLO_EXES = ("credentialuibroker.exe", "consent.exe", "logonui.exe")
_HELLO_CLASS_HINTS = ("credential", "hello")


def _proc_basename(pid) -> str:
    try:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
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


def _find_hello_window():
    """Cerca la finestra del prompt Hello (per processo, poi per classe).
    Esclude il nostro stesso processo. Ritorna l'HWND o None."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        own_pid = ctypes.windll.kernel32.GetCurrentProcessId()
        cls = ctypes.create_unicode_buffer(256)
        hit = []
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value == own_pid:
                return True
            exe = _proc_basename(pid.value)
            if exe in _HELLO_EXES:
                hit.append(hwnd)
                return False
            user32.GetClassNameW(hwnd, cls, 256)
            name = cls.value.lower()
            if any(h in name for h in _HELLO_CLASS_HINTS):
                hit.append(hwnd)
                return False
            return True

        user32.EnumWindows(EnumProc(_cb), 0)
        return hit[0] if hit else None
    except Exception:
        return None


def _center_hello_prompt():
    """Sposta il prompt di Windows Hello al centro dello schermo sotto il
    cursore (nasce in alto a sinistra). Ritorna (w, h) se spostata, else None."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        hwnd = _find_hello_window()
        if not hwnd:
            return None

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
            ]

        hmon = user32.MonitorFromPoint(pt, 2)  # NEAREST
        mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        mw = mi.rcMonitor.right - mi.rcMonitor.left
        mh = mi.rcMonitor.bottom - mi.rcMonitor.top
        x = mi.rcMonitor.left + (mw - w) // 2
        y = mi.rcMonitor.top + (mh - h) // 2

        HWND_TOP = 0
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(hwnd, HWND_TOP, x, y, 0, 0, SWP_NOSIZE | SWP_SHOWWINDOW)
        return (w, h)
    except Exception:
        return None


_QSS = """
QDialog { background:transparent; }
QLabel { color:#f3f4f6; background:transparent; }
QLabel#muted { color:#8b8d98; font-size:12px; }
QLabel#h1 { font-size:20px; font-weight:600; }
QLabel#err { color:#ef4444; font-size:12px; }
QLineEdit { background:rgba(255,255,255,0.05); color:#f3f4f6; border:1px solid rgba(255,255,255,0.14);
    border-radius:10px; padding:10px 14px; font-size:15px; letter-spacing:3px; }
QLineEdit:focus { border:1px solid rgba(167,139,250,0.6); }
QPushButton#primary { background:#a78bfa; color:#0e0e12; font-weight:600;
    border:none; border-radius:10px; padding:10px 18px; }
QPushButton#primary:disabled { background:rgba(167,139,250,0.25); color:#5a5d6a; }
QPushButton#ghost { background:transparent; color:#8b8d98; border:1px solid rgba(255,255,255,0.12);
    border-radius:10px; padding:10px 16px; }
QPushButton#ghost:hover { color:#f3f4f6; }
"""


class LockDialog(FramelessDialog):
    def __init__(self, parent=None):
        super().__init__(parent, stays_on_top=True, closable=False)
        self.hide_titlebar()  # lock screen pulito: si esce con Esc
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setWindowFlag(Qt.WindowType.Tool, True)  # niente bottone taskbar
        self.setStyleSheet(_QSS)
        self._unlocked = False
        self._fails = 0
        self._revealed = False

        root = self.body
        root.setContentsMargins(32, 14, 32, 24)
        root.setSpacing(12)

        title = QLabel("🔒 " + t("lock.title")); title.setObjectName("h1")
        root.addWidget(title)
        sub = QLabel(t("lock.subtitle")); sub.setObjectName("muted"); sub.setWordWrap(True)
        root.addWidget(sub)
        root.addSpacing(6)

        method = applock.lock_method()
        self._use_hello = method in ("hello", "both") and applock.hello_available()
        self._use_pin = method in ("pin", "both") and applock.has_pin()

        if self._use_hello:
            self.hello_btn = QPushButton("👤 " + t("lock.hello")); self.hello_btn.setObjectName("primary")
            self.hello_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.hello_btn.setAutoDefault(False); self.hello_btn.setDefault(False)
            self.hello_btn.clicked.connect(self._try_hello)
            root.addWidget(self.hello_btn)

        if self._use_pin:
            self.pin = QLineEdit(); self.pin.setEchoMode(QLineEdit.EchoMode.Password)
            self.pin.setPlaceholderText(t("lock.pin_ph"))
            self.pin.setMaxLength(32)
            self.pin.returnPressed.connect(self._try_pin)
            root.addWidget(self.pin)

        self.err = QLabel(""); self.err.setObjectName("err"); self.err.setWordWrap(True)
        root.addWidget(self.err)

        foot = QHBoxLayout(); foot.addStretch()
        if self._use_pin:
            self.unlock_btn = QPushButton(t("lock.unlock")); self.unlock_btn.setObjectName("primary")
            self.unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.unlock_btn.setAutoDefault(False); self.unlock_btn.setDefault(False)
            self.unlock_btn.clicked.connect(self._try_pin)
            foot.addWidget(self.unlock_btn)
        root.addLayout(foot)

        # Niente metodo disponibile (caso limite): consenti uscita.
        if not self._use_hello and not self._use_pin:
            self.err.setText(t("lock.no_method"))

        # Se c'è Hello: parti INVISIBILE (solo il prompt nativo di Hello si
        # vede). La card PIN appare solo se Hello viene chiuso/fallisce.
        if self._use_hello:
            self.setWindowOpacity(0.0)
            QTimer.singleShot(150, self._try_hello)
        elif self._use_pin:
            self._revealed = True
            QTimer.singleShot(0, self.pin.setFocus)
        else:
            self._revealed = True

    def _center_on_cursor_screen(self):
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry()
            self.move(g.center() - self.rect().center())

    def _reveal(self, error_key=None):
        """Mostra la card di sblocco di Déjà (PIN). Chiamata quando Hello è
        chiuso/fallito, così le due UI non si sovrappongono."""
        self._revealed = True
        self.setWindowOpacity(1.0)
        self.adjustSize()
        self._center_on_cursor_screen()
        self.raise_(); self.activateWindow()
        _force_foreground(self)
        if error_key:
            self.err.setText(t(error_key))
        if self._use_pin and hasattr(self, "pin"):
            self.pin.setFocus()

    def showEvent(self, e):
        super().showEvent(e)
        self._center_on_cursor_screen()
        if self._use_hello and not self._revealed:
            # Resta invisibile: in primo piano c'è solo il prompt di Hello.
            return
        self.raise_(); self.activateWindow()
        _force_foreground(self)

    def _try_hello(self):
        # Hello gira in un thread: `asyncio.run` bloccherebbe il loop Qt e
        # congelerebbe la UI. Intanto ri-centriamo il prompt (nasce in alto a
        # sinistra) e facciamo polling per l'esito.
        if getattr(self, "_hello_running", False) or not self._use_hello:
            return
        # Nascondi la card di Déjà mentre il prompt nativo di Hello è a schermo
        # (anche su retry manuale): si vede solo una UI per volta.
        self.setWindowOpacity(0.0)
        self._revealed = False
        self._hello_running = True
        self._hello_result = None
        msg = t("lock.hello_msg")

        import threading

        def _run():
            try:
                ok = applock.hello_verify(msg)
            except Exception:
                ok = False
            self._hello_result = ok
            self._hello_running = False

        threading.Thread(target=_run, daemon=True).start()

        self._center_tries = 0
        self._win_seen = set()
        self._last_size = None
        self._stable = 0
        self._centered_done = False
        self._center_timer = QTimer(self)
        self._center_timer.timeout.connect(self._tick_center)
        self._center_timer.start(100)

        self._done_timer = QTimer(self)
        self._done_timer.timeout.connect(self._tick_hello_done)
        self._done_timer.start(80)

    def _tick_center(self):
        self._center_tries += 1
        # Diagnostica: nei primi ~3s logga le finestre estranee viste, così se
        # il prompt non viene centrato sappiamo exe/classe reali del broker.
        if self._center_tries <= 30:
            _dump_new_windows(self._win_seen)
        if self._centered_done:
            self._center_timer.stop()
            return
        # Centra finché la dimensione del prompt si stabilizza (il broker si
        # ri-dispone dopo lo spawn), poi SMETTI: così l'utente può spostarlo.
        size = _center_hello_prompt()
        if size:
            if size == self._last_size:
                self._stable += 1
            else:
                self._stable = 0
                self._last_size = size
            if self._stable >= 2:
                self._centered_done = True
                self._center_timer.stop()
        if self._center_tries > 100:
            self._center_timer.stop()

    def _tick_hello_done(self):
        if getattr(self, "_hello_running", False):
            return
        self._done_timer.stop()
        ct = getattr(self, "_center_timer", None)
        if ct is not None:
            ct.stop()
        if self._hello_result:
            self._unlocked = True
            self.accept()
            return
        # Hello chiuso/fallito → mostra la card PIN di Déjà (o l'errore).
        if self._use_pin:
            self._reveal()
        else:
            self._reveal("lock.hello_fail")

    def _try_pin(self):
        if self._fails_locked():
            return
        if applock.verify_pin(self.pin.text()):
            self._unlocked = True
            self.accept()
            return
        self._fails += 1
        self.pin.clear()
        self.err.setText(t("lock.pin_error"))
        if self._fails >= 3:
            # Anti-bruteforce: blocca l'input per qualche secondo.
            delay = min(30, 2 ** (self._fails - 2))  # 2,4,8,16,30s
            self._disable_for(delay)

    def _fails_locked(self):
        return getattr(self, "_locked_until_active", False)

    def _disable_for(self, secs):
        self._locked_until_active = True
        if hasattr(self, "pin"): self.pin.setEnabled(False)
        if hasattr(self, "unlock_btn"): self.unlock_btn.setEnabled(False)
        self.err.setText(t("lock.too_many", secs=secs))
        QTimer.singleShot(secs * 1000, self._reenable)

    def _reenable(self):
        self._locked_until_active = False
        if hasattr(self, "pin"): self.pin.setEnabled(True); self.pin.setFocus()
        if hasattr(self, "unlock_btn"): self.unlock_btn.setEnabled(True)
        self.err.setText("")

    # L'utente non può chiudere il lock con Esc/X aggirando lo sblocco:
    # reject equivale a "non sbloccato".
    def reject(self):
        self._unlocked = False
        super().reject()


# Un solo LockDialog alla volta: premere più volte l'hotkey (o aprire più
# percorsi protetti) non deve impilare più prompt di Windows Hello.
_active_dialog = None


def require_unlock(parent=None) -> bool:
    global _active_dialog
    if _active_dialog is not None:
        # Sblocco già in corso: porta davanti quello esistente, non aprirne un altro.
        try:
            _active_dialog.raise_(); _active_dialog.activateWindow()
        except Exception:
            pass
        return False
    dlg = LockDialog(parent)
    _active_dialog = dlg
    try:
        dlg.exec()
    finally:
        _active_dialog = None
    return bool(getattr(dlg, "_unlocked", False))


class PinSetupDialog(FramelessDialog):
    """Imposta/cambia il PIN dell'app (min 4 cifre/char)."""
    def __init__(self, parent=None):
        super().__init__(parent, title="")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(_QSS)
        self._ok = False

        root = self.body
        root.setContentsMargins(32, 4, 32, 24); root.setSpacing(12)
        title = QLabel("🔐 " + t("lock.set_pin_title")); title.setObjectName("h1")
        root.addWidget(title)
        sub = QLabel(t("lock.set_pin_sub")); sub.setObjectName("muted"); sub.setWordWrap(True)
        root.addWidget(sub)

        self.p1 = QLineEdit(); self.p1.setEchoMode(QLineEdit.EchoMode.Password)
        self.p1.setPlaceholderText(t("lock.pin_ph")); self.p1.setMaxLength(32)
        root.addWidget(self.p1)
        self.p2 = QLineEdit(); self.p2.setEchoMode(QLineEdit.EchoMode.Password)
        self.p2.setPlaceholderText(t("lock.pin_confirm")); self.p2.setMaxLength(32)
        self.p2.returnPressed.connect(self._save)
        root.addWidget(self.p2)

        self.err = QLabel(""); self.err.setObjectName("err"); self.err.setWordWrap(True)
        root.addWidget(self.err)

        foot = QHBoxLayout(); foot.addStretch()
        cancel = QPushButton(t("lock.cancel")); cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject); foot.addWidget(cancel)
        save = QPushButton(t("lock.save_pin")); save.setObjectName("primary")
        save.clicked.connect(self._save); foot.addWidget(save)
        root.addLayout(foot)

    def _save(self):
        a, b = self.p1.text(), self.p2.text()
        if len(a) < 4:
            self.err.setText(t("lock.pin_too_short")); return
        if a != b:
            self.err.setText(t("lock.pin_mismatch")); return
        applock.set_pin(a)
        self._ok = True
        self.accept()


def setup_pin(parent=None) -> bool:
    dlg = PinSetupDialog(parent)
    dlg.exec()
    return bool(getattr(dlg, "_ok", False))
