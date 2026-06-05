# ui/app_shell.py
"""Nuova shell APP di Déjà (pivot da overlay Spotlight → app completa).

Layout a 3 colonne (rif. mockup design/deja-app.html, approvato):
  [ sidebar nav ] [ topbar + timeline ] [ detail ]

FASE 1 (questo file): scaffold strutturale renderizzabile con dati placeholder.
Niente DB/worker qui ancora — le fasi successive ci alloggiano dentro i pezzi
funzionali esistenti (search, preview, chat, audio player) da ui/window.py.

Standalone: non tocca DejaWindow, così l'app attuale resta funzionante mentre
la nuova shell si sviluppa in parallelo.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle, QFrame,
)
from PyQt6.QtCore import Qt, QSize, QRectF, QPointF
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
)

from ui import theme

# Ruoli item timeline
TL_TITLE = Qt.ItemDataRole.UserRole + 1
TL_SUB = Qt.ItemDataRole.UserRole + 2
TL_TIME = Qt.ItemDataRole.UserRole + 3
TL_HUE = Qt.ItemDataRole.UserRole + 4
TL_KIND = Qt.ItemDataRole.UserRole + 5
TL_HOUR = Qt.ItemDataRole.UserRole + 6   # header riga ora

# tinte per tipo (palette Déjà)
HUE = {
    "screen": theme.EMERALD_RGB,
    "audio": theme.AMBER_RGB,
    "note": theme.VIOLET_RGB,
    "code": (96, 165, 250),
}


class TimelineDelegate(QStyledItemDelegate):
    """Righe timeline uniformi: media box + titolo/sotto + orario, pallino su spina."""
    ROW_H = 64
    HOUR_H = 30

    def sizeHint(self, opt, idx):
        if idx.data(TL_HOUR):
            return QSize(opt.rect.width(), self.HOUR_H)
        return QSize(opt.rect.width(), self.ROW_H)

    def paint(self, p, opt, idx):
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(opt.rect)

        if idx.data(TL_HOUR):
            p.setPen(QColor(theme.INK_FAINT))
            f = QFont(theme.MONO, 8, QFont.Weight.Medium)
            f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
            p.setFont(f)
            p.drawText(r.adjusted(30, 8, -8, -2), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       idx.data(TL_HOUR))
            p.restore(); return

        hue = QColor(*idx.data(TL_HUE)) if idx.data(TL_HUE) else QColor(theme.VIOLET)
        is_sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        is_hov = bool(opt.state & QStyle.StateFlag.State_MouseOver)

        # spina + pallino
        spine_x = r.left() + 9
        p.setPen(QPen(QColor(255, 255, 255, 26), 1.5))
        p.drawLine(QPointF(spine_x, r.top()), QPointF(spine_x, r.bottom()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(13, 13, 17))
        p.drawEllipse(QPointF(spine_x, r.center().y()), 6.5, 6.5)
        p.setBrush(hue)
        p.drawEllipse(QPointF(spine_x, r.center().y()), 4, 4)

        card = r.adjusted(26, 4, -8, -4)
        path = QPainterPath(); path.addRoundedRect(card, 11, 11)
        if is_sel:
            p.fillPath(path, QColor(255, 255, 255, 14))
            bar = QPainterPath(); bar.addRoundedRect(QRectF(card.left() + 1, card.top() + 8, 2, card.height() - 16), 1, 1)
            p.fillPath(bar, hue)
        elif is_hov:
            p.fillPath(path, QColor(255, 255, 255, 8))

        # media box
        MW, MH = 70.0, 46.0
        media = QRectF(card.left() + 12, card.center().y() - MH / 2, MW, MH)
        mp = QPainterPath(); mp.addRoundedRect(media, 8, 8)
        kind = idx.data(TL_KIND)
        if kind in ("audio", "note"):
            fill = QColor(hue); fill.setAlpha(40)
            p.fillPath(mp, fill)
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(hue.red(), hue.green(), hue.blue(), 80), 1)); p.drawPath(mp)
            p.setPen(QPen(hue, 1.8, cap=Qt.PenCapStyle.RoundCap))
            if kind == "audio":
                hs = [5, 11, 16, 9, 14, 7, 4]; gi = 6.0
                cx = media.center().x(); cy = media.center().y(); sx = cx - (len(hs) - 1) * gi / 2
                for i, bh in enumerate(hs):
                    p.drawLine(QPointF(sx + i * gi, cy - bh / 2), QPointF(sx + i * gi, cy + bh / 2))
            else:
                cy = media.center().y(); lx = media.left() + 16; rx = media.right() - 16
                for dy in (-6, 0, 6):
                    p.drawLine(QPointF(lx, cy + dy), QPointF(rx if dy != 6 else rx - 10, cy + dy))
        else:
            # placeholder "screenshot": gradiente (fase 1; poi thumbnail vera)
            g = QLinearGradient(media.topLeft(), media.bottomRight())
            base = QColor(hue); base.setAlpha(70)
            g.setColorAt(0, base); g.setColorAt(1, QColor(14, 14, 19))
            p.fillPath(mp, QBrush(g))
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 30), 1)); p.drawPath(mp)

        # testo
        tx = media.right() + 13
        tw = card.right() - 64 - tx
        p.setPen(QColor(theme.INK) if is_sel else QColor("#dcdce4"))
        p.setFont(QFont(theme.SANS, 11, QFont.Weight.Medium))
        from PyQt6.QtGui import QFontMetrics
        title = QFontMetrics(p.font()).elidedText(idx.data(TL_TITLE) or "", Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, card.top() + 13, tw, 18), Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(QColor(theme.INK_DIM)); p.setFont(QFont(theme.SANS, 9))
        sub = QFontMetrics(p.font()).elidedText(idx.data(TL_SUB) or "", Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, card.top() + 31, tw, 16), Qt.AlignmentFlag.AlignVCenter, sub)

        p.setPen(QColor(theme.INK_FAINT)); p.setFont(QFont(theme.MONO, 9))
        p.drawText(card.adjusted(0, 0, -14, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   idx.data(TL_TIME) or "")
        p.restore()


def _nav_btn(label, on=False):
    b = QPushButton(label); b.setCheckable(True); b.setChecked(on)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{text-align:left; padding:8px 12px; border:none; border-radius:8px;"
        f" color:{theme.INK_SOFT}; background:transparent; font-family:'{theme.SANS}';"
        f" font-size:13px; font-weight:500;}}"
        f"QPushButton:hover{{background:rgba(255,255,255,0.035); color:{theme.INK};}}"
        f"QPushButton:checked{{background:rgba(255,255,255,0.05); color:{theme.INK};}}"
    )
    return b


class AppShell(QWidget):
    """Finestra-app principale (scaffold fase 1)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Déjà")
        self.resize(1180, 740)
        self._build()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor("#101014")); g.setColorAt(1, QColor("#0b0b0e"))
        p.fillRect(self.rect(), QBrush(g))

    def _build(self):
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── Sidebar ──
        side = QWidget(); side.setFixedWidth(226)
        side.setStyleSheet(f"background:transparent; border-right:1px solid {theme.LINE};")
        sl = QVBoxLayout(side); sl.setContentsMargins(12, 16, 12, 14); sl.setSpacing(2)
        brand = QLabel("  Déjà"); brand.setFont(QFont(theme.SANS, 15, QFont.Weight.DemiBold))
        brand.setStyleSheet(f"color:{theme.INK}; padding:6px 8px 16px;")
        sl.addWidget(brand)
        for lbl in ("Menu",):
            m = QLabel(lbl.upper()); m.setFont(QFont(theme.MONO, 8))
            m.setStyleSheet(f"color:{theme.INK_FAINT}; letter-spacing:2px; padding:8px 10px 4px;")
            sl.addWidget(m)
        for i, lbl in enumerate(("Timeline", "Cerca", "Assistente", "Galleria")):
            sl.addWidget(_nav_btn(lbl, on=(i == 0)))
        gm = QLabel("GESTIONE"); gm.setFont(QFont(theme.MONO, 8))
        gm.setStyleSheet(f"color:{theme.INK_FAINT}; letter-spacing:2px; padding:12px 10px 4px;")
        sl.addWidget(gm)
        for lbl in ("Impostazioni", "Info & Privacy"):
            sl.addWidget(_nav_btn(lbl))
        sl.addStretch()
        status = QFrame(); status.setStyleSheet(f"border:1px solid {theme.LINE}; border-radius:10px;")
        stl = QVBoxLayout(status); stl.setContentsMargins(12, 10, 12, 10); stl.setSpacing(6)
        cap = QLabel("● Cattura attiva"); cap.setStyleSheet(f"color:{theme.EMERALD}; font-size:11px;")
        arc = QLabel("Archivio   1,1 GB"); arc.setStyleSheet(f"color:{theme.INK_SOFT}; font-size:11px;")
        stl.addWidget(cap); stl.addWidget(arc)
        sl.addWidget(status)
        root.addWidget(side)

        # ── Main (topbar + timeline) ──
        main = QWidget(); ml = QVBoxLayout(main); ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(0)
        top = QWidget(); top.setFixedHeight(58); top.setStyleSheet(f"border-bottom:1px solid {theme.LINE};")
        tl = QHBoxLayout(top); tl.setContentsMargins(20, 0, 20, 0); tl.setSpacing(12)
        search = QLineEdit(); search.setPlaceholderText("Cerca nei tuoi ricordi…")
        search.setStyleSheet(
            f"QLineEdit{{background:rgba(255,255,255,0.035); border:1px solid {theme.LINE};"
            f" border-radius:10px; padding:8px 12px; color:{theme.INK}; font-family:'{theme.SANS}'; font-size:13px;}}"
        )
        search.setFixedHeight(36); tl.addWidget(search, stretch=1)
        for i, lbl in enumerate(("Tutto", "Schermo", "Audio")):
            seg = _nav_btn(lbl, on=(i == 0)); seg.setFixedHeight(32)
            tl.addWidget(seg)
        ml.addWidget(top)

        day = QLabel("  Oggi   ·   6 giugno 2026 · 3.000 ricordi")
        day.setFont(QFont(theme.SANS, 13, QFont.Weight.DemiBold))
        day.setStyleSheet(f"color:{theme.INK}; padding:14px 18px 6px;")
        ml.addWidget(day)

        self.timeline = QListWidget()
        self.timeline.setStyleSheet(theme.results_list() + f" QListWidget{{padding:4px 12px;}}")
        self.timeline.setItemDelegate(TimelineDelegate(self.timeline))
        self.timeline.currentRowChanged.connect(self._on_pick)
        ml.addWidget(self.timeline, stretch=1)
        root.addWidget(main, stretch=1)

        # ── Detail ──
        self.detail = QWidget(); self.detail.setFixedWidth(366)
        self.detail.setStyleSheet(f"border-left:1px solid {theme.LINE};")
        self._dl = QVBoxLayout(self.detail); self._dl.setContentsMargins(18, 16, 18, 16); self._dl.setSpacing(12)
        self._detail_title = QLabel("—"); self._detail_title.setFont(QFont(theme.SANS, 14, QFont.Weight.DemiBold))
        self._detail_title.setStyleSheet(f"color:{theme.INK};")
        self._detail_sub = QLabel(""); self._detail_sub.setFont(QFont(theme.MONO, 9))
        self._detail_sub.setStyleSheet(f"color:{theme.INK_DIM}; letter-spacing:1px;")
        self._detail_body = QLabel("Seleziona un ricordo"); self._detail_body.setWordWrap(True)
        self._detail_body.setStyleSheet(f"color:{theme.INK_SOFT}; font-size:13px;")
        self._detail_body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._dl.addWidget(self._detail_title); self._dl.addWidget(self._detail_sub)
        self._dl.addWidget(self._detail_body, stretch=1)
        root.addWidget(self.detail)

        self._populate()  # dopo che il detail esiste (setCurrentRow → _on_pick)

    def _hdr(self, txt):
        it = QListWidgetItem(); it.setData(TL_HOUR, txt)
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.timeline.addItem(it)

    def _ev(self, title, sub, time, kind):
        it = QListWidgetItem()
        it.setData(TL_TITLE, title); it.setData(TL_SUB, sub); it.setData(TL_TIME, time)
        it.setData(TL_KIND, kind); it.setData(TL_HUE, HUE.get(kind, theme.VIOLET_RGB))
        self.timeline.addItem(it)

    def _populate(self):
        self._hdr("17:00")
        self._ev("VS Code — window.py", "refactor delegate · timeline", "17:05", "code")
        self._hdr("16:00")
        self._ev("Nota — Slack #design", "“…Déjà a timeline piena, niente overlay”", "16:42", "note")
        self._ev("Team Sync — Zoom", "registrazione 45:12 · trascritta", "16:30", "audio")
        self._hdr("15:00")
        self._ev("Design Session — Figma", "overlay timeline mockup", "15:42", "screen")
        self._ev("Chrome — reference UI", "dribbble · dashboard timeline", "15:18", "screen")
        self._ev("PowerShell — build", "pyinstaller · deja 1.1.0", "15:02", "screen")
        self.timeline.setCurrentRow(4)  # Figma

    def _on_pick(self, row):
        it = self.timeline.item(row)
        if not it or it.data(TL_HOUR):
            return
        self._detail_title.setText(it.data(TL_TITLE) or "—")
        kindlbl = {"screen": "Schermo", "audio": "Registrazione vocale",
                   "note": "Nota", "code": "Schermo"}.get(it.data(TL_KIND), "")
        self._detail_sub.setText(f"{kindlbl} · oggi {it.data(TL_TIME)}".upper())
        self._detail_body.setText(it.data(TL_SUB) or "")
