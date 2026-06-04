# ui/lock.py
"""
Schermata di sblocco di Déjà (Windows Hello + PIN) e dialog di setup PIN.
Riusa lo stile scuro dell'onboarding. Modale, stays-on-top.
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)

import i18n
from i18n import t
from modules import applock

_QSS = """
QDialog { background:#0e0e12; }
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


class LockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(_QSS)
        self._unlocked = False
        self._fails = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
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
            self.unlock_btn.clicked.connect(self._try_pin)
            foot.addWidget(self.unlock_btn)
        root.addLayout(foot)

        # Niente metodo disponibile (caso limite): consenti uscita.
        if not self._use_hello and not self._use_pin:
            self.err.setText(t("lock.no_method"))

        # Auto-tentativo Hello all'apertura (la finestra è già in foreground).
        if self._use_hello:
            QTimer.singleShot(150, self._try_hello)
        elif self._use_pin:
            QTimer.singleShot(0, self.pin.setFocus)

    def showEvent(self, e):
        super().showEvent(e)
        self.raise_(); self.activateWindow()

    def _try_hello(self):
        if applock.hello_verify(t("lock.hello_msg")):
            self._unlocked = True
            self.accept()
        else:
            # Hello annullato/fallito: resta il PIN se disponibile.
            if not self._use_pin:
                self.err.setText(t("lock.hello_fail"))

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


def require_unlock(parent=None) -> bool:
    dlg = LockDialog(parent)
    dlg.exec()
    return bool(getattr(dlg, "_unlocked", False))


class PinSetupDialog(QDialog):
    """Imposta/cambia il PIN dell'app (min 4 cifre/char)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(_QSS)
        self._ok = False

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24); root.setSpacing(12)
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
