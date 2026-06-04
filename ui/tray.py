# ui/tray.py
import io
import re
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import QTimer
from ui.settings import SettingsDialog
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from ui.window import SettingsDialog as AppSettingsDialog, DiaryDialog
from db import backup_db, restore_db
from modules import privacy
import config
import paths
import autostart
import i18n
from i18n import t

# Menu sobrio e coerente col resto dell'app: un accento lavanda, voci arrotondate.
MENU_QSS = """
QMenu {
    background:#1b1b21; color:#e7e7ec;
    border:1px solid rgba(255,255,255,0.09); border-radius:11px; padding:7px;
}
QMenu::item {
    padding:8px 24px 8px 14px; margin:1px 4px; border-radius:7px; font-size:12px;
}
QMenu::item:selected { background:rgba(167,139,250,0.20); color:#ffffff; }
QMenu::item:disabled { color:#6a6a74; }
QMenu::separator { height:1px; background:rgba(255,255,255,0.07); margin:6px 12px; }
QMenu::indicator { width:15px; height:15px; left:8px; }
QMenu::right-arrow { width:10px; height:10px; margin-right:8px; }
"""

# Toglie eventuali emoji/simboli iniziali dalle etichette i18n: tray pulito e sobrio.
_LEAD_SYMBOLS = re.compile(r'^[\s\W_]+', re.UNICODE)
def _lbl(s: str) -> str:
    return _LEAD_SYMBOLS.sub('', s or '').strip()


def _load_font(size):
    for name in ("segoeuisb.ttf", "seguisb.ttf", "segoeuib.ttf", "segoeui.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _make_tray_icon(paused=False):
    """Icona vettoriale-like: disco brand con 'D' centrata, anello sottile,
    pallino REC quando attivo. Disegnata a 256px e ridotta da Qt (bordi netti)."""
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if paused:
        fill, ring, txt = (60, 60, 70, 255), (92, 92, 104, 255), (158, 158, 168, 255)
    else:
        fill, ring, txt = (108, 99, 255, 255), (150, 141, 255, 255), (255, 255, 255, 255)
    pad = 16
    d.ellipse([pad, pad, S - pad, S - pad], fill=fill)
    d.ellipse([pad, pad, S - pad, S - pad], outline=ring, width=5)
    # "D" centrata
    f = _load_font(148)
    try:
        bb = d.textbbox((0, 0), "D", font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        d.text(((S - tw) / 2 - bb[0], (S - th) / 2 - bb[1]), "D", font=f, fill=txt)
    except Exception:
        d.text((S / 2 - 40, S / 2 - 60), "D", fill=txt)
    if not paused:
        # Pallino REC con alone scuro per stacco dallo sfondo
        d.ellipse([S - 90, S - 90, S - 12, S - 12], fill=(20, 20, 26, 255))
        d.ellipse([S - 82, S - 82, S - 20, S - 20], fill=(239, 68, 68, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    pixmap = QPixmap(); pixmap.loadFromData(buf.getvalue())
    return QIcon(pixmap)

class DejaTray(QSystemTrayIcon):
    def __init__(self, window, stop_event, app):
        super().__init__()
        self._window = window; self._stop_event = stop_event; self._app = app
        self._icon_active = _make_tray_icon(paused=False)
        self._icon_paused = _make_tray_icon(paused=True)
        self.setIcon(self._icon_active)
        self.setToolTip(t("tray.tooltip_active"))
        menu = QMenu(); menu.setStyleSheet(MENU_QSS)
        a_open = menu.addAction(_lbl(t("tray.open")) + "   (Ctrl+Shift+D)"); a_open.triggered.connect(self._open_window)
        a_lock = menu.addAction(_lbl(t("tray.lock_now"))); a_lock.triggered.connect(self._lock_now)
        menu.addSeparator()
        a_set  = menu.addAction(_lbl(t("tray.audio_settings"))); a_set.triggered.connect(self._open_settings)
        a_ai   = menu.addAction(_lbl(t("tray.ai_settings"))); a_ai.triggered.connect(self._open_ai_settings)
        a_diary = menu.addAction(_lbl(t("tray.diary"))); a_diary.triggered.connect(self._open_diary)
        a_ask   = menu.addAction(_lbl(t("tray.ask_screen")))
        a_ask.triggered.connect(self._open_ask_screen)
        menu.addSeparator()
        a_backup = menu.addAction(_lbl(t("tray.backup"))); a_backup.triggered.connect(self._backup)
        a_restore = menu.addAction(_lbl(t("tray.restore"))); a_restore.triggered.connect(self._restore)
        menu.addSeparator()
        priv_menu = menu.addMenu(_lbl(t("tray.privacy"))); priv_menu.setStyleSheet(MENU_QSS)
        for label, secs in [(_lbl(t("tray.pause_5")), 300), (_lbl(t("tray.pause_15")), 900),
                            (_lbl(t("tray.pause_30")), 1800), (_lbl(t("tray.pause_2h")), 7200)]:
            a = priv_menu.addAction(label)
            a.triggered.connect(lambda _checked, s=secs, l=label: self._pause(s, l))
        priv_menu.addSeparator()
        a_unpause = priv_menu.addAction(_lbl(t("tray.resume")))
        a_unpause.triggered.connect(self._unpause)
        menu.addSeparator()
        a_restart_audio = menu.addAction(_lbl(t("tray.restart_audio")))
        a_restart_audio.triggered.connect(self._restart_audio)
        menu.addSeparator()
        self._a_autostart = menu.addAction(_lbl(t("tray.autostart")))
        self._a_autostart.setCheckable(True)
        self._a_autostart.setEnabled(autostart.is_supported())
        try:
            self._a_autostart.setChecked(autostart.is_enabled())
        except Exception:
            pass
        self._a_autostart.toggled.connect(self._toggle_autostart)
        a_about = menu.addAction(_lbl(t("tray.about"))); a_about.triggered.connect(self._open_about)
        menu.addSeparator()
        a_quit = menu.addAction(_lbl(t("tray.quit"))); a_quit.triggered.connect(self._quit)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

        # Indicatore di stato: aggiorna icona/tooltip (registrazione vs pausa).
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._refresh_state)
        self._state_timer.start(1500)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self._open_window()

    def _refresh_state(self):
        try:
            paused = privacy.is_paused()
        except Exception:
            paused = False
        self.setIcon(self._icon_paused if paused else self._icon_active)
        self.setToolTip(t("tray.tooltip_paused") if paused else t("tray.tooltip_active"))

    def _notify(self, msg, level="info", ms=3000):
        try:
            self._window.toast(msg, level=level, duration_ms=ms)
        except Exception:
            print(msg)

    def _toggle_autostart(self, checked):
        ok = autostart.set_enabled(checked)
        if ok:
            self._notify(t("tray.autostart_on") if checked else t("tray.autostart_off"), "ok")
        else:
            try:
                self._a_autostart.blockSignals(True)
                self._a_autostart.setChecked(autostart.is_enabled())
                self._a_autostart.blockSignals(False)
            except Exception:
                pass
            self._notify(t("tray.autostart_fail"), "error")

    def _open_about(self):
        ocr = t("about.ocr_active") if config.TESSERACT_CMD else t("about.ocr_missing")
        QMessageBox.about(
            None,
            t("about.title"),
            t(
                "about.body",
                version=config.APP_VERSION,
                ocr=ocr,
                lang=i18n.LANGUAGES.get(i18n.get_language(), i18n.get_language()),
                data=paths.data_dir(),
                log=paths.log_file(),
            ),
        )

    def _open_window(self):
        from modules import applock
        if not applock.ensure_unlocked(self._window): return
        self._window.show(); self._window.raise_(); self._window.activateWindow()

    def _lock_now(self):
        from modules import applock
        applock.lock_now()
        try:
            if self._window.isVisible():
                self._window.hide()
        except Exception:
            pass
        try:
            self._window.toast(t("tray.locked"), level="ok", duration_ms=2000)
        except Exception:
            pass

    def _quit(self):
        self._stop_event.set(); self._app.quit()

    def _open_settings(self):
        dlg = SettingsDialog(self._window); dlg.exec()

    def _open_ai_settings(self):
        dlg = AppSettingsDialog(self._window); dlg.exec()

    def _open_diary(self):
        from modules import applock
        if not applock.ensure_unlocked(self._window): return
        dlg = DiaryDialog(self._window); dlg.exec()
        try:
            if applock.lock_enabled() and applock.relock_policy() == "every_access":
                applock.lock_now()
        except Exception:
            pass

    def _open_ask_screen(self):
        try:
            from ui.window import open_ask_screen_dialog
            existing = getattr(self._window, "_ask_dialog", None)
            if existing is not None:
                try:
                    if existing.isVisible():
                        existing.raise_(); existing.activateWindow(); return
                except RuntimeError:
                    pass
            dlg = open_ask_screen_dialog(parent=None)
            self._window._ask_dialog = dlg
        except Exception as e:
            try: self._window.toast(t("tray.generic_error", e=e), level="error")
            except Exception: print(f"[Tray] ask_screen fail: {e}")

    def _backup(self):
        from datetime import datetime
        default_name = f"deja_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        path, _ = QFileDialog.getSaveFileName(None, t("tray.backup_title"), default_name, "Zip (*.zip)")
        if not path: return
        ok, msg = backup_db(path)
        try: self._window.toast(msg, level=("ok" if ok else "error"), duration_ms=5000)
        except Exception: print(msg)

    def _pause(self, secs, label):
        privacy.pause_for(secs)
        try: self._window.toast(t("tray.paused_for", label=label), level="info", duration_ms=4000)
        except Exception: print(f"[Privacy] {label}")
        self.setToolTip(t("tray.tooltip_paused"))

    def _unpause(self):
        privacy.unpause()
        try: self._window.toast(t("tray.resumed"), level="ok", duration_ms=3000)
        except Exception: print("[Privacy] resumed")
        self.setToolTip(t("tray.tooltip_active"))

    def _restart_audio(self):
        try:
            from modules.audio import request_restart
            request_restart()
            self._window.toast(t("tray.restart_audio_msg"), level="info", duration_ms=3000)
        except Exception as e:
            try: self._window.toast(t("tray.generic_error", e=e), level="error")
            except Exception: print(f"[Audio] restart fail: {e}")

    def _restore(self):
        ans = QMessageBox.warning(None, t("tray.restore_confirm_title"),
            t("tray.restore_confirm_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes: return
        path, _ = QFileDialog.getOpenFileName(None, t("tray.restore_title"), "", "Zip (*.zip)")
        if not path: return
        ok, msg = restore_db(path)
        try: self._window.toast(msg, level=("ok" if ok else "error"), duration_ms=8000)
        except Exception: print(msg)
