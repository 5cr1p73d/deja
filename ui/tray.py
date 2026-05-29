# ui/tray.py
import io
from PIL import Image, ImageDraw
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

def _make_tray_icon(paused=False):
    size = 64
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    base = "#3a3a44" if paused else "#6c63ff"
    draw.ellipse([4, 4, size-4, size-4], fill=base)
    draw.text((22, 16), "D", fill="white")
    if not paused:
        # pallino rosso "REC" = registrazione attiva (indicatore visibile)
        r = 10
        draw.ellipse([size-6-2*r, size-6-2*r, size-6, size-6], fill="#ef4444")
        draw.ellipse([size-6-2*r, size-6-2*r, size-6, size-6], outline="#0e0e12", width=2)
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
        menu = QMenu()
        a_open = menu.addAction(t("tray.open")); a_open.triggered.connect(self._open_window)
        menu.addSeparator()
        a_set  = menu.addAction(t("tray.audio_settings")); a_set.triggered.connect(self._open_settings)
        a_ai   = menu.addAction(t("tray.ai_settings")); a_ai.triggered.connect(self._open_ai_settings)
        a_diary = menu.addAction(t("tray.diary")); a_diary.triggered.connect(self._open_diary)
        a_ask   = menu.addAction(t("tray.ask_screen"))
        a_ask.triggered.connect(self._open_ask_screen)
        menu.addSeparator()
        a_backup = menu.addAction(t("tray.backup")); a_backup.triggered.connect(self._backup)
        a_restore = menu.addAction(t("tray.restore")); a_restore.triggered.connect(self._restore)
        menu.addSeparator()
        priv_menu = menu.addMenu(t("tray.privacy"))
        for label, secs in [(t("tray.pause_5"), 300), (t("tray.pause_15"), 900),
                            (t("tray.pause_30"), 1800), (t("tray.pause_2h"), 7200)]:
            a = priv_menu.addAction(label)
            a.triggered.connect(lambda _checked, s=secs, l=label: self._pause(s, l))
        priv_menu.addSeparator()
        a_unpause = priv_menu.addAction(t("tray.resume"))
        a_unpause.triggered.connect(self._unpause)
        menu.addSeparator()
        a_restart_audio = menu.addAction(t("tray.restart_audio"))
        a_restart_audio.triggered.connect(self._restart_audio)
        menu.addSeparator()
        self._a_autostart = menu.addAction(t("tray.autostart"))
        self._a_autostart.setCheckable(True)
        self._a_autostart.setEnabled(autostart.is_supported())
        try:
            self._a_autostart.setChecked(autostart.is_enabled())
        except Exception:
            pass
        self._a_autostart.toggled.connect(self._toggle_autostart)
        a_about = menu.addAction(t("tray.about")); a_about.triggered.connect(self._open_about)
        menu.addSeparator()
        a_quit = menu.addAction(t("tray.quit")); a_quit.triggered.connect(self._quit)
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
        self._window.show(); self._window.raise_(); self._window.activateWindow()

    def _quit(self):
        self._stop_event.set(); self._app.quit()

    def _open_settings(self):
        dlg = SettingsDialog(); dlg.exec()

    def _open_ai_settings(self):
        dlg = AppSettingsDialog(self._window); dlg.exec()

    def _open_diary(self):
        dlg = DiaryDialog(self._window); dlg.exec()

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
            try: self._window.toast(f"Errore: {e}", level="error")
            except Exception: print(f"[Tray] ask_screen fail: {e}")

    def _backup(self):
        from datetime import datetime
        default_name = f"deja_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        path, _ = QFileDialog.getSaveFileName(None, "Backup DB Deja", default_name, "Zip (*.zip)")
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
            try: self._window.toast(f"Errore: {e}", level="error")
            except Exception: print(f"[Audio] restart fail: {e}")

    def _restore(self):
        ans = QMessageBox.warning(None, "Conferma Restore",
            "ATTENZIONE: questa operazione SOVRASCRIVE il DB corrente.\n"
            "Il DB attuale verrà salvato come deja.db.prev_backup.\n\n"
            "Vuoi continuare?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes: return
        path, _ = QFileDialog.getOpenFileName(None, "Restore DB Deja", "", "Zip (*.zip)")
        if not path: return
        ok, msg = restore_db(path)
        try: self._window.toast(msg, level=("ok" if ok else "error"), duration_ms=8000)
        except Exception: print(msg)
