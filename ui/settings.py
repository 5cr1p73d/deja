# ui/settings.py
import sys
import pyaudiowpatch as pyaudio
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from db import get_conn
import i18n
from i18n import t

OCR_PRESETS = ["ita+eng", "eng", "ita", "spa+eng", "fra+eng", "deu+eng", "por+eng"]

# Script eseguito in un processo separato per enumerare i dispositivi audio.
# PortAudio può abortire (assert C non catchabile in Python) se si crea una
# seconda istanza PyAudio mentre il thread audio ha uno stream loopback attivo.
# In un sottoprocesso pulito l'enumerazione riesce; se abortisce, muore solo il
# figlio e il padre ottiene una lista vuota invece di crashare.
_ENUM_SRC = (
    "import json,sys\n"
    "try:\n"
    " import pyaudiowpatch as pa\n"
    " p=pa.PyAudio(); out=[]\n"
    " for i in range(p.get_device_count()):\n"
    "  d=p.get_device_info_by_index(i)\n"
    "  if d['maxInputChannels']>0 and not d.get('isLoopbackDevice',False):\n"
    "   out.append(['mic',d['index'],d['name']])\n"
    " try:\n"
    "  for d in p.get_loopback_device_info_generator(): out.append(['loopback',d['index'],d['name']])\n"
    " except Exception: pass\n"
    " p.terminate(); sys.stdout.write(json.dumps(out))\n"
    "except Exception: sys.stdout.write('[]')\n"
)

_DEVICES_CACHE = None


def _enum_inprocess():
    pa = pyaudio.PyAudio(); devices = []
    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)
        if dev["maxInputChannels"] > 0 and not dev.get("isLoopbackDevice", False):
            devices.append(("mic", dev["index"], dev["name"]))
    try:
        for dev in pa.get_loopback_device_info_generator():
            devices.append(("loopback", dev["index"], dev["name"]))
    except Exception:
        pass
    pa.terminate(); return devices


def _get_all_devices(force=False):
    """Enumera mic + loopback in modo crash-safe (sottoprocesso), con cache."""
    global _DEVICES_CACHE
    if _DEVICES_CACHE is not None and not force:
        return _DEVICES_CACHE
    # In build frozen sys.executable è l'app stessa: `-c` rilancerebbe Déjà.
    # Lì enumeriamo in-process (best effort).
    if getattr(sys, "frozen", False):
        try:
            _DEVICES_CACHE = _enum_inprocess()
        except Exception:
            _DEVICES_CACHE = []
        return _DEVICES_CACHE
    import subprocess
    import json
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            [sys.executable, "-c", _ENUM_SRC],
            capture_output=True, text=True, timeout=20, creationflags=flags,
        )
        data = json.loads((r.stdout or "[]").strip() or "[]")
        _DEVICES_CACHE = [(tp, idx, name) for tp, idx, name in data]
    except Exception:
        _DEVICES_CACHE = []
    return _DEVICES_CACHE

def save_setting(key, value):
    conn = get_conn()
    conn.cursor().execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit(); conn.close()

def get_setting(key):
    conn = get_conn()
    row = conn.cursor().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close(); return row[0] if row else None

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("set.window_title"))
        self.setFixedSize(480, 470)
        # Stessa accortezza del dialog principale: l'overlay di Déjà è stays-on-top,
        # quindi anche questa finestra deve restare sopra, altrimenti finisce dietro
        # l'overlay e il modal blocca tutto.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        try:
            from ui.window import SETTINGS_QSS
            self.setStyleSheet(SETTINGS_QSS)
        except Exception:
            self.setStyleSheet("QDialog{background:#17171c;} QLabel{color:#e7e7ec;}")

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        body = QVBoxLayout(); body.setContentsMargins(26, 24, 26, 18); body.setSpacing(13)
        root.addLayout(body, stretch=1)

        def section(text):
            l = QLabel(text); l.setObjectName("section"); body.addWidget(l)

        def field(label, widget):
            row = QHBoxLayout(); row.setSpacing(12)
            k = QLabel(label); k.setObjectName("field"); k.setFixedWidth(140)
            row.addWidget(k); row.addWidget(widget, stretch=1)
            body.addLayout(row)

        devices = _get_all_devices()
        mics      = [(idx, name) for tp, idx, name in devices if tp == "mic"]
        loopbacks = [(idx, name) for tp, idx, name in devices if tp == "loopback"]

        section(t("set.audio"))
        self.mic_combo = QComboBox(); self.mic_combo.addItem(t("set.dont_record"), None)
        for idx, name in mics: self.mic_combo.addItem(name, idx)
        field(t("set.mic"), self.mic_combo)

        self.out_combo = QComboBox(); self.out_combo.addItem(t("set.dont_record"), None)
        for idx, name in loopbacks: self.out_combo.addItem(name, idx)
        field(t("set.system_audio"), self.out_combo)

        saved_mic = get_setting("audio_mic_index"); saved_out = get_setting("audio_out_index")
        if saved_mic:
            for i in range(self.mic_combo.count()):
                if str(self.mic_combo.itemData(i)) == saved_mic: self.mic_combo.setCurrentIndex(i)
        if saved_out:
            for i in range(self.out_combo.count()):
                if str(self.out_combo.itemData(i)) == saved_out: self.out_combo.setCurrentIndex(i)

        body.addSpacing(6)
        section(t("set.ui_language").upper())
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang_combo.addItem(f"{i18n.LANG_FLAGS.get(code,'')} {name}", code)
        cur_lang = i18n.get_language()
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == cur_lang:
                self.lang_combo.setCurrentIndex(i)
        field(t("set.ui_language"), self.lang_combo)

        self.ocr_combo = QComboBox()
        cur_ocr = get_setting("ocr_lang") or "ita+eng"
        presets = list(OCR_PRESETS)
        if cur_ocr not in presets:
            presets.insert(0, cur_ocr)
        for p in presets:
            self.ocr_combo.addItem(p, p)
        self.ocr_combo.setCurrentIndex(max(0, presets.index(cur_ocr)))
        field(t("set.ocr_language"), self.ocr_combo)

        note = QLabel(t("set.restart_note")); note.setObjectName("caption")
        note.setWordWrap(True); body.addWidget(note)
        body.addStretch()

        foot_sep = QFrame(); foot_sep.setFrameShape(QFrame.Shape.HLine)
        foot_sep.setStyleSheet("background:rgba(255,255,255,0.07); max-height:1px; min-height:1px; border:none;")
        root.addWidget(foot_sep)
        footer = QHBoxLayout(); footer.setContentsMargins(26, 14, 26, 16); footer.setSpacing(10)
        cancel = QPushButton(t("set.cancel")); cancel.clicked.connect(self.reject)
        save = QPushButton(t("set.save")); save.setObjectName("save_btn"); save.clicked.connect(self._save)
        footer.addStretch(); footer.addWidget(cancel); footer.addWidget(save)
        root.addLayout(footer)

    def showEvent(self, e):
        super().showEvent(e)
        self.raise_(); self.activateWindow()

    def _save(self):
        old_lang = i18n.get_language()
        mic_idx = self.mic_combo.currentData(); out_idx = self.out_combo.currentData()
        conn = get_conn(); c = conn.cursor()
        if mic_idx is not None: c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",("audio_mic_index",mic_idx))
        else: c.execute("DELETE FROM settings WHERE key='audio_mic_index'")
        if out_idx is not None: c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",("audio_out_index",out_idx))
        else: c.execute("DELETE FROM settings WHERE key='audio_out_index'")
        # Lingua UI + lingue OCR
        c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("ocr_lang", self.ocr_combo.currentData()))
        conn.commit(); conn.close()
        new_lang = self.lang_combo.currentData()
        i18n.set_language(new_lang)
        # Hot-swap: trigger restart immediato audio thread (no app restart needed)
        try:
            from modules.audio import request_restart
            request_restart()
            print("[Settings] Audio device aggiornato. Hot-swap richiesto.")
        except Exception as e:
            print(f"[Settings] Hot-swap fail: {e}")
        self.accept()
        # Il cambio lingua richiede un riavvio per ridisegnare tutta la UI.
        if new_lang != old_lang:
            self._prompt_restart()

    def _prompt_restart(self):
        """Chiede conferma e, se accettata, riavvia l'app (lo shutdown pulito +
        rilancio avvengono in main.py via la proprietà 'restart_requested')."""
        from PyQt6.QtWidgets import QMessageBox, QApplication
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(t("set.restart_title"))
        box.setText(t("set.restart_body"))
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        yes = box.addButton(t("set.restart_now"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(t("set.restart_later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            app = QApplication.instance()
            if app is not None:
                app.setProperty("restart_requested", True)
                app.quit()
