# ui/region_select.py
"""
Selettore di area schermo per la cattura. Overlay fullscreen translucido su
tutto il desktop virtuale: l'area FUORI dalla selezione è oscurata, DENTRO è
trasparente ⇒ si vede lo schermo reale in tempo reale (preview live di cosa
verrà catturato). Trascina per disegnare, Invio conferma, Esc annulla.

`select_region(parent) -> dict|None` ritorna {left, top, width, height} in
coordinate assolute (virtual desktop) o None se annullato.
"""
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QGuiApplication
from PyQt6.QtWidgets import QDialog

from i18n import t


class RegionSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Copre l'intero desktop virtuale (anche multi-monitor, origini negative).
        vg = QGuiApplication.primaryScreen().virtualGeometry()
        self._origin = vg.topLeft()
        self.setGeometry(vg)
        self._start = None
        self._end = None
        self._region = None  # risultato (coord assolute)

    # ── Disegno: dim fuori, trasparente dentro la selezione ──
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = self.rect()
        dim = QColor(0, 0, 0, 110)
        sel = self._sel_rect()
        if sel is None:
            p.fillRect(full, dim)
        else:
            # Oscura tutto tranne il rettangolo selezionato (4 bande).
            p.fillRect(QRect(full.left(), full.top(), full.width(), sel.top() - full.top()), dim)
            p.fillRect(QRect(full.left(), sel.bottom(), full.width(), full.bottom() - sel.bottom()), dim)
            p.fillRect(QRect(full.left(), sel.top(), sel.left() - full.left(), sel.height()), dim)
            p.fillRect(QRect(sel.right(), sel.top(), full.right() - sel.right(), sel.height()), dim)
            # Bordo selezione + dimensioni.
            p.setPen(QPen(QColor(167, 139, 250), 2))
            p.drawRect(sel)
            label = f"{sel.width()} × {sel.height()}"
            p.setPen(QColor(255, 255, 255))
            p.drawText(sel.left() + 6, max(sel.top() - 8, 14), label)
        # Suggerimento in alto.
        p.setPen(QColor(230, 230, 235))
        p.drawText(full.left() + 20, full.top() + 28, t("region.hint"))

    def _sel_rect(self):
        if self._start is None or self._end is None:
            return None
        return QRect(self._start, self._end).normalized()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.position().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._end = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._end = e.position().toPoint()
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.reject(); return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirm(); return
        super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self._confirm()

    def _confirm(self):
        sel = self._sel_rect()
        if sel is None or sel.width() < 8 or sel.height() < 8:
            return  # selezione troppo piccola: ignora
        # Coord assolute = origine virtual desktop + rettangolo locale.
        self._region = {
            "left": self._origin.x() + sel.left(),
            "top": self._origin.y() + sel.top(),
            "width": sel.width(),
            "height": sel.height(),
        }
        self.accept()


def select_region(parent=None):
    dlg = RegionSelectDialog(parent)
    dlg.showFullScreen()
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg._region
    return None
