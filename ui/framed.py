# ui/framed.py
"""
Base per finestre popup **frameless e fluttuanti**: niente cornice classica di
Windows, card arrotondata con bordo raffinato e ombra (effetto fluttuante),
trascinabile da aree vuote, con bottone ✕ di chiusura.

Le sottoclassi NON usano `QVBoxLayout(self)`: mettono il contenuto in
`self.body` (il layout interno alla card). Esempio:

    class MyDialog(FramelessDialog):
        def __init__(self, parent=None):
            super().__init__(parent, title="Titolo")
            self.body.setContentsMargins(26, 8, 26, 22)
            self.body.addWidget(QLabel("ciao"))
"""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QLabel,
    QGraphicsDropShadowEffect, QWidget,
)

# Margine attorno alla card per l'ombra (deve esserci spazio per il blur).
_SHADOW_MARGIN = 22
_RADIUS = 16

_FRAME_QSS = f"""
QFrame#fl_card {{
    background:#15151b;
    border:1px solid rgba(255,255,255,0.10);
    border-radius:{_RADIUS}px;
}}
QPushButton#fl_close {{
    background:transparent; color:#8b8d98; border:none;
    font-size:15px; font-weight:600; border-radius:7px;
}}
QPushButton#fl_close:hover {{ background:rgba(255,255,255,0.08); color:#f3f4f6; }}
QLabel#fl_title {{ color:#c7c7d0; font-size:12.5px; font-weight:600; background:transparent; }}
"""


class FramelessDialog(QDialog):
    def __init__(self, parent=None, *, title="", stays_on_top=True,
                 closable=True, draggable=True, radius=_RADIUS):
        super().__init__(parent)
        flags = Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        if stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._fl_drag = None
        self._fl_draggable = draggable

        outer = QVBoxLayout(self)
        outer.setContentsMargins(_SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN, _SHADOW_MARGIN)
        outer.setSpacing(0)

        self._card = QFrame(); self._card.setObjectName("fl_card")
        self._card.setStyleSheet(_FRAME_QSS)
        outer.addWidget(self._card)

        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(46)
        eff.setColor(QColor(0, 0, 0, 170))
        eff.setOffset(0, 10)
        self._card.setGraphicsEffect(eff)

        # Layout della card: titlebar opzionale + body per il contenuto.
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        # Barra superiore: titolo (sx) + ✕ (dx). Trascinabile.
        self._titlebar = QWidget(); self._titlebar.setFixedHeight(36)
        tb = QHBoxLayout(self._titlebar)
        tb.setContentsMargins(16, 8, 8, 0); tb.setSpacing(8)
        self._title_lbl = QLabel(title); self._title_lbl.setObjectName("fl_title")
        tb.addWidget(self._title_lbl); tb.addStretch()
        if closable:
            self._close_btn = QPushButton("✕"); self._close_btn.setObjectName("fl_close")
            self._close_btn.setFixedSize(28, 28)
            self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._close_btn.clicked.connect(self.reject)
            tb.addWidget(self._close_btn)
        card_lay.addWidget(self._titlebar)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        card_lay.addLayout(self.body, stretch=1)

    # ── API ────────────────────────────────────────────────────────
    def set_title(self, text):
        self._title_lbl.setText(text)

    def hide_titlebar(self):
        """Nasconde la barra (per dialog che hanno già un loro header)."""
        self._titlebar.setVisible(False)

    # ── Drag (frameless = lo spostiamo a mano) ──────────────────────
    def mousePressEvent(self, e):
        if self._fl_draggable and e.button() == Qt.MouseButton.LeftButton:
            self._fl_drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._fl_drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._fl_drag)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._fl_drag = None
        super().mouseReleaseEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self.raise_(); self.activateWindow()


_CONFIRM_QSS = """
QDialog { background:transparent; }
QLabel#fl_msg { color:#d6d6dd; font-size:12.5px; background:transparent; }
QPushButton { font-size:12px; font-weight:600; border-radius:9px; padding:9px 18px; }
QPushButton#fl_cancel {
    background:rgba(255,255,255,0.05); color:#d6d6dd; border:1px solid rgba(255,255,255,0.10);
}
QPushButton#fl_cancel:hover { background:rgba(255,255,255,0.10); color:#fff; }
QPushButton#fl_ok { background:#a78bfa; color:#1a1430; border:1px solid #a78bfa; }
QPushButton#fl_ok:hover { background:#b9a4ff; }
QPushButton#fl_danger { background:#ef4444; color:#fff; border:1px solid #ef4444; }
QPushButton#fl_danger:hover { background:#f56565; }
"""


def confirm(parent, title, body, ok_text="OK", cancel_text="Annulla", danger=False) -> bool:
    """Dialogo di conferma frameless ed elegante (sostituisce QMessageBox).
    Ritorna True se l'utente conferma."""
    dlg = FramelessDialog(parent, title=title)
    dlg.setModal(True)
    dlg.setStyleSheet(_CONFIRM_QSS)
    dlg.setMinimumWidth(440)
    lay = dlg.body
    lay.setContentsMargins(26, 6, 24, 22); lay.setSpacing(18)
    msg = QLabel(body); msg.setObjectName("fl_msg"); msg.setWordWrap(True)
    lay.addWidget(msg)
    row = QHBoxLayout(); row.addStretch(); row.setSpacing(10)
    cancel = QPushButton(cancel_text); cancel.setObjectName("fl_cancel")
    cancel.setCursor(Qt.CursorShape.PointingHandCursor)
    cancel.clicked.connect(dlg.reject); row.addWidget(cancel)
    ok = QPushButton(ok_text); ok.setObjectName("fl_danger" if danger else "fl_ok")
    ok.setCursor(Qt.CursorShape.PointingHandCursor)
    ok.clicked.connect(dlg.accept); row.addWidget(ok)
    lay.addLayout(row)
    return dlg.exec() == QDialog.DialogCode.Accepted


def alert(parent, title, body, ok_text="OK") -> None:
    """Popup informativo frameless (sostituisce QMessageBox.about/information)."""
    dlg = FramelessDialog(parent, title=title)
    dlg.setModal(True)
    dlg.setStyleSheet(_CONFIRM_QSS)
    dlg.setMinimumWidth(460)
    lay = dlg.body
    lay.setContentsMargins(26, 6, 24, 22); lay.setSpacing(18)
    msg = QLabel(body); msg.setObjectName("fl_msg"); msg.setWordWrap(True)
    msg.setOpenExternalLinks(True); msg.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(msg)
    row = QHBoxLayout(); row.addStretch()
    ok = QPushButton(ok_text); ok.setObjectName("fl_ok")
    ok.setCursor(Qt.CursorShape.PointingHandCursor)
    ok.clicked.connect(dlg.accept); row.addWidget(ok)
    lay.addLayout(row)
    dlg.exec()
