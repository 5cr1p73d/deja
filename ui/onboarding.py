# ui/onboarding.py
"""
Wizard di primo avvio: scelta lingua, consenso esplicito alla cattura
schermo+audio, stato dipendenze e default sensati. Mostrato una sola volta.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QFrame, QWidget, QComboBox,
)

from db import get_setting, save_setting
import config
import i18n
from i18n import t
from ui.framed import FramelessDialog


def needs_onboarding() -> bool:
    return (get_setting("onboarding_done", "0") or "0") != "1"


_CARD_QSS = """
QDialog { background:transparent; }
QLabel { color:#f3f4f6; background:transparent; }
QLabel#muted { color:#8b8d98; }
QLabel#h1 { font-size:22px; font-weight:600; }
QCheckBox { color:#f3f4f6; spacing:10px; font-size:13px; }
QCheckBox::indicator { width:18px; height:18px; border-radius:5px;
    border:1px solid rgba(255,255,255,0.25); background:rgba(255,255,255,0.05); }
QCheckBox::indicator:checked { background:#a78bfa; border:1px solid #a78bfa; }
QComboBox { background:#1a1a1f; color:#f3f4f6; border:1px solid rgba(255,255,255,0.12);
    border-radius:8px; padding:4px 10px; min-width:140px; }
QComboBox QAbstractItemView { background:#1a1a1f; color:#f3f4f6; selection-background-color:#a78bfa; }
QPushButton#primary { background:#a78bfa; color:#0e0e12; font-weight:600;
    border:none; border-radius:10px; padding:10px 18px; }
QPushButton#primary:disabled { background:rgba(167,139,250,0.25); color:#5a5d6a; }
QPushButton#ghost { background:transparent; color:#8b8d98; border:none; padding:10px 14px; }
QPushButton#ghost:hover { color:#f3f4f6; }
"""


class OnboardingDialog(FramelessDialog):
    def __init__(self, parent=None):
        super().__init__(parent, closable=False)
        self.hide_titlebar()  # ha i suoi bottoni; trascinabile da aree vuote
        self.setModal(True)
        self.setMinimumWidth(580)
        self.setStyleSheet(_CARD_QSS)
        self._accepted = False
        self._tr: list[tuple[QWidget, str]] = []  # (widget, chiave) per retranslate

        self._ocr_ok = bool(config.TESSERACT_CMD)

        root = self.body
        root.setContentsMargins(34, 22, 34, 26)
        root.setSpacing(14)

        # ── Riga lingua ──
        lang_row = QHBoxLayout()
        self._lang_lbl = QLabel()
        self._lang_lbl.setObjectName("muted")
        self._reg(self._lang_lbl, "onb.lang")
        self._lang_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self._lang_combo.addItem(f"{i18n.LANG_FLAGS.get(code, '')} {name}", code)
        cur = i18n.get_language()
        keys = list(i18n.LANGUAGES.keys())
        self._lang_combo.setCurrentIndex(keys.index(cur) if cur in keys else 0)
        self._lang_combo.currentIndexChanged.connect(self._on_lang)
        lang_row.addStretch(1)
        lang_row.addWidget(self._lang_lbl)
        lang_row.addWidget(self._lang_combo)
        root.addLayout(lang_row)

        # ── Header ──
        head = QLabel(); head.setObjectName("h1")
        root.addWidget(self._reg(head, "onb.title"))
        sub = QLabel(); sub.setObjectName("muted")
        root.addWidget(self._reg(sub, "onb.subtitle"))

        intro = QLabel(); intro.setWordWrap(True)
        root.addWidget(self._reg(intro, "onb.intro"))

        root.addWidget(self._hline())
        ptitle = QLabel(); ptitle.setStyleSheet("font-weight:600;")
        root.addWidget(self._reg(ptitle, "onb.privacy_title"))
        root.addWidget(self._row("onb.p_local", True))
        root.addWidget(self._row("onb.p_redact", True))
        root.addWidget(self._row("onb.p_pause", True))

        root.addWidget(self._hline())
        dtitle = QLabel(); dtitle.setStyleSheet("font-weight:600;")
        root.addWidget(self._reg(dtitle, "onb.deps_title"))
        root.addWidget(self._row("onb.ocr_ok" if self._ocr_ok else "onb.ocr_missing", self._ocr_ok))
        root.addWidget(self._row("onb.models_note", None))
        root.addWidget(self._row("onb.ai_note", None))

        root.addWidget(self._hline())
        self._consent = QCheckBox()
        self._reg(self._consent, "onb.consent")
        self._consent.stateChanged.connect(self._on_consent)
        root.addWidget(self._consent)

        btns = QHBoxLayout()
        self._quit_btn = QPushButton(); self._quit_btn.setObjectName("ghost")
        self._reg(self._quit_btn, "onb.exit")
        self._quit_btn.clicked.connect(self.reject)
        self._start_btn = QPushButton(); self._start_btn.setObjectName("primary")
        self._reg(self._start_btn, "onb.start")
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._finish)
        btns.addWidget(self._quit_btn); btns.addStretch(1); btns.addWidget(self._start_btn)
        root.addLayout(btns)

        self._retranslate()

    # ── helpers ──
    def _reg(self, w: QWidget, key: str) -> QWidget:
        self._tr.append((w, key))
        return w

    def _hline(self) -> QFrame:
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:rgba(255,255,255,0.08);")
        return line

    def _row(self, key: str, ok) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(10)
        dot = QLabel("●")
        color = "#10b981" if ok else ("#f59e0b" if ok is None else "#ef4444")
        dot.setStyleSheet(f"color:{color}; background:transparent; font-size:11px;")
        txt = QLabel(); txt.setTextFormat(Qt.TextFormat.RichText)
        txt.setOpenExternalLinks(True); txt.setWordWrap(True)
        self._reg(txt, key)
        h.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(txt, 1)
        return w

    def _retranslate(self):
        self.setWindowTitle(t("onb.title"))
        for w, key in self._tr:
            try:
                w.setText(t(key, version=config.APP_VERSION))
            except Exception:
                w.setText(t(key))

    def _on_lang(self):
        code = self._lang_combo.currentData()
        if code:
            i18n.set_language(code)
            self._retranslate()

    def _on_consent(self):
        self._start_btn.setEnabled(self._consent.isChecked())

    def _finish(self):
        save_setting("onboarding_done", "1")
        save_setting("consent_capture", "1")
        save_setting("ui_language", i18n.get_language())
        if get_setting("privacy_redact") is None:
            save_setting("privacy_redact", "1")
        if get_setting("privacy_idle_min") is None:
            save_setting("privacy_idle_min", "5")
        # Blocco app attivo di default. Se Windows Hello non è disponibile,
        # proponi subito un PIN così il blocco è applicabile.
        if get_setting("lock_enabled") is None:
            save_setting("lock_enabled", "1")
        try:
            from modules import applock
            if (applock.lock_enabled() and not applock.hello_available()
                    and not applock.has_pin()):
                from ui.lock import setup_pin
                setup_pin(self)
        except Exception:
            pass
        self._accepted = True
        self.accept()


def run_onboarding(parent=None) -> bool:
    if not needs_onboarding():
        return True
    dlg = OnboardingDialog(parent)
    dlg.exec()
    return bool(getattr(dlg, "_accepted", False))
