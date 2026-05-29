# ui/settings.py
import pyaudiowpatch as pyaudio
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton
from PyQt6.QtGui import QFont
from db import get_conn
import i18n
from i18n import t

OCR_PRESETS = ["ita+eng", "eng", "ita", "spa+eng", "fra+eng", "deu+eng", "por+eng"]

def _get_all_devices():
    pa = pyaudio.PyAudio(); devices = []
    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)
        if dev["maxInputChannels"] > 0 and not dev.get("isLoopbackDevice", False):
            devices.append(("mic", dev["index"], dev["name"]))
    try:
        for dev in pa.get_loopback_device_info_generator():
            devices.append(("loopback", dev["index"], dev["name"]))
    except: pass
    pa.terminate(); return devices

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
        self.setWindowTitle("Deja -- Impostazioni")
        self.setFixedSize(480, 380)
        self.setStyleSheet("background:#0f0f1a;color:#f1f0ff;font-family:'Segoe UI';")
        layout = QVBoxLayout(self); layout.setSpacing(14); layout.setContentsMargins(24,24,24,24)
        devices = _get_all_devices()
        mics      = [(idx,name) for t,idx,name in devices if t=="mic"]
        loopbacks = [(idx,name) for t,idx,name in devices if t=="loopback"]
        layout.addWidget(QLabel("Microfono (input):"))
        self.mic_combo = QComboBox(); self.mic_combo.addItem("-- Non registrare --", None)
        for idx,name in mics: self.mic_combo.addItem(name, idx)
        layout.addWidget(self.mic_combo)
        layout.addWidget(QLabel("Audio PC (output loopback):"))
        self.out_combo = QComboBox(); self.out_combo.addItem("-- Non registrare --", None)
        for idx,name in loopbacks: self.out_combo.addItem(name, idx)
        layout.addWidget(self.out_combo)
        saved_mic = get_setting("audio_mic_index"); saved_out = get_setting("audio_out_index")
        if saved_mic:
            for i in range(self.mic_combo.count()):
                if str(self.mic_combo.itemData(i)) == saved_mic: self.mic_combo.setCurrentIndex(i)
        if saved_out:
            for i in range(self.out_combo.count()):
                if str(self.out_combo.itemData(i)) == saved_out: self.out_combo.setCurrentIndex(i)
        # ── Lingua interfaccia ──
        layout.addWidget(QLabel(t("set.ui_language") + ":"))
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang_combo.addItem(f"{i18n.LANG_FLAGS.get(code,'')} {name}", code)
        cur_lang = i18n.get_language()
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == cur_lang:
                self.lang_combo.setCurrentIndex(i)
        layout.addWidget(self.lang_combo)

        # ── Lingue OCR ──
        layout.addWidget(QLabel(t("set.ocr_language") + ":"))
        self.ocr_combo = QComboBox()
        cur_ocr = get_setting("ocr_lang") or "ita+eng"
        presets = list(OCR_PRESETS)
        if cur_ocr not in presets:
            presets.insert(0, cur_ocr)
        for p in presets:
            self.ocr_combo.addItem(p, p)
        self.ocr_combo.setCurrentIndex(max(0, presets.index(cur_ocr)))
        layout.addWidget(self.ocr_combo)

        note = QLabel(t("set.restart_note")); note.setStyleSheet("color:#8b8d98;font-size:11px;")
        layout.addWidget(note)

        btn = QPushButton("Salva"); btn.setFixedHeight(36)
        btn.setStyleSheet("QPushButton{background:rgba(167,139,250,0.15);color:#a78bfa;"
                          "border:1px solid rgba(167,139,250,0.3);border-radius:8px;}"
                          "QPushButton:hover{background:rgba(167,139,250,0.25);}")
        btn.clicked.connect(self._save); layout.addWidget(btn)

    def _save(self):
        mic_idx = self.mic_combo.currentData(); out_idx = self.out_combo.currentData()
        conn = get_conn(); c = conn.cursor()
        if mic_idx is not None: c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",("audio_mic_index",mic_idx))
        else: c.execute("DELETE FROM settings WHERE key='audio_mic_index'")
        if out_idx is not None: c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",("audio_out_index",out_idx))
        else: c.execute("DELETE FROM settings WHERE key='audio_out_index'")
        # Lingua UI + lingue OCR
        c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("ocr_lang", self.ocr_combo.currentData()))
        conn.commit(); conn.close()
        i18n.set_language(self.lang_combo.currentData())
        # Hot-swap: trigger restart immediato audio thread (no app restart needed)
        try:
            from modules.audio import request_restart
            request_restart()
            print("[Settings] Audio device aggiornato. Hot-swap richiesto.")
        except Exception as e:
            print(f"[Settings] Hot-swap fail: {e}")
        self.accept()
