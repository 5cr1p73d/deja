# ui/app_shell.py
"""Shell APP principale di Déjà (rif. mockup design/deja-app.html, approvato).

Finestra avviata da main.py (pivot completato: l'overlay Spotlight `DejaWindow`
è stato pensionato in F6). Layout a 3 colonne:
  [ sidebar nav ] [ stack pagine: timeline/cerca/assistente/galleria/settings ] [ detail ]

Riusa i COMPONENTI di ui/window.py (ChatPage, SearchWorker, WaveformWidget,
SettingsDialog avanzato, embed card, helper) invece di duplicarli.
"""
from __future__ import annotations

import time as _time
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle, QFrame,
    QSlider, QScrollArea, QStackedWidget, QComboBox, QSpinBox,
)
from PyQt6.QtCore import (
    Qt, QSize, QRectF, QPointF, QPoint, QRect, QThread, pyqtSignal, QTimer,
    QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
    QPixmap, QFontMetrics, QIcon,
)

from ui import theme
from modules.audio import decode_audio
from modules import ai_assistant
# Riuso da window.py (componenti standalone, già importato dall'app via tray).
from ui.window import (
    WaveformWidget, _rounded_pixmap, _fmt_time, SearchWorker, ChatWorker, ChatPage,
    AssistantTurnBubble, EmbedScreenshotCard, EmbedAudioCard, FullscreenViewer,
    _md_to_html, _strip_refs, _REF_RE,
)

# Ruoli item timeline
TL_TITLE = Qt.ItemDataRole.UserRole + 1
TL_SUB = Qt.ItemDataRole.UserRole + 2
TL_TIME = Qt.ItemDataRole.UserRole + 3
TL_HUE = Qt.ItemDataRole.UserRole + 4
TL_KIND = Qt.ItemDataRole.UserRole + 5
TL_HOUR = Qt.ItemDataRole.UserRole + 6   # header riga ora
TL_ID = Qt.ItemDataRole.UserRole + 7    # id record DB (thumb lazy / detail)
TL_THUMB = Qt.ItemDataRole.UserRole + 8  # QPixmap miniatura | False (nessuna)
TL_IDX = Qt.ItemDataRole.UserRole + 9   # indice in _records

# tinte per tipo (palette Déjà)
HUE = {
    "screen": theme.EMERALD_RGB,
    "audio": theme.AMBER_RGB,
    "note": theme.VIOLET_RGB,
    "code": (96, 165, 250),
}

# Cache miniature screenshot per id. Lazy: si decodificano SOLO le righe visibili
# (vedi AppShell._ensure_visible_thumbs) — lezione portata da window.py: in un
# archivio da migliaia di item, decodificarle tutte freezerebbe la UI.
_THUMB_CACHE = {}            # id -> QPixmap | None
_THUMB_PX = 96


def _decode_thumb(blob):
    """Blob immagine → QPixmap miniatura cover (o None). Nessun accesso DB."""
    try:
        src = QPixmap()
        if blob and src.loadFromData(bytes(blob)) and not src.isNull():
            return src.scaled(_THUMB_PX, _THUMB_PX,
                              Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


class TimelineWorker(QThread):
    """Carica una pagina di cronologia (screenshot+audio+web) dal DB, in background."""
    done = pyqtSignal(list)

    def __init__(self, limit=3000, offset=0):
        super().__init__(); self._limit = limit; self._offset = offset

    def run(self):
        try:
            from modules import search as search_module
            self.done.emit(search_module.get_all(limit=self._limit, offset=self._offset))
        except Exception:
            self.done.emit([])


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
            # screenshot: thumbnail reale se già caricata (lazy), altrimenti
            # gradiente come placeholder finché la riga non entra nel viewport.
            thumb = idx.data(TL_THUMB)
            if isinstance(thumb, QPixmap) and not thumb.isNull():
                p.save(); p.setClipPath(mp)
                scaled = thumb.scaled(int(MW), int(MH),
                                      Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
                ox = media.left() - (scaled.width() - MW) / 2
                oy = media.top() - (scaled.height() - MH) / 2
                p.drawPixmap(QPointF(ox, oy), scaled)
                p.restore()
                p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 36), 1)); p.drawPath(mp)
            else:
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
        title = QFontMetrics(p.font()).elidedText(idx.data(TL_TITLE) or "", Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, card.top() + 13, tw, 18), Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(QColor(theme.INK_DIM)); p.setFont(QFont(theme.SANS, 9))
        sub = QFontMetrics(p.font()).elidedText(idx.data(TL_SUB) or "", Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, card.top() + 31, tw, 16), Qt.AlignmentFlag.AlignVCenter, sub)

        p.setPen(QColor(theme.INK_FAINT)); p.setFont(QFont(theme.MONO, 9))
        p.drawText(card.adjusted(0, 0, -14, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   idx.data(TL_TIME) or "")
        p.restore()


# ── Icone (line-icons in stile mockup, viewBox 24, stroke currentColor) ─────
ICONS = {
    "timeline": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>',
    "assistant": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "gallery": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8 2 2 0 1 1-2.8 2.8 1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0 1.6 1.6 0 0 0-2.7-1.1 2 2 0 1 1-2.8-2.8A1.6 1.6 0 0 0 4.6 15a2 2 0 1 1 0-4 1.6 1.6 0 0 0 1.1-2.7 2 2 0 1 1 2.8-2.8A1.6 1.6 0 0 0 11 4.6 2 2 0 1 1 15 4.6a1.6 1.6 0 0 0 2.7 1.1 2 2 0 1 1 2.8 2.8A1.6 1.6 0 0 0 19.4 11a2 2 0 1 1 0 4z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
    # detail / badge
    "screen": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "note": '<path d="M6 4h9l5 5v11H6z"/><path d="M9 13h6M9 16h4"/>',
    "audio": '<rect x="9" y="3" width="6" height="10" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    "web": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    # azioni
    "expand": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a0 0 0 0 1 0 0h10"/>',
    "link": '<path d="M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1"/>',
    # settings sub-nav
    "capture": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="12" cy="12" r="3.2"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z"/>',
    "spark": '<path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "sliders": '<path d="M4 7h16M4 12h16M4 17h10"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="12" r="2"/>',
    "chevup": '<path d="M6 15l6-6 6 6"/>',
    "chevdown": '<path d="M6 9l6 6 6-6"/>',
    "star": '<path d="M12 3l2.6 5.6L21 9.5l-4.5 4.3L17.6 21 12 17.7 6.4 21l1.1-7.2L3 9.5l6.4-.9z"/>',
    "ai": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "min": '<path d="M12 7v5l3 2"/><circle cx="12" cy="12" r="9"/>',
    "winmin": '<path d="M5 12h14"/>',
    "winmax": '<rect x="5.5" y="5.5" width="13" height="13" rx="1.5"/>',
    "winrestore": '<rect x="5.5" y="8.5" width="10" height="10" rx="1.5"/><path d="M8.5 8.5V6A1.5 1.5 0 0 1 10 4.5h8A1.5 1.5 0 0 1 19.5 6v8A1.5 1.5 0 0 1 18 15.5h-2.5"/>',
    "winclose": '<path d="M6 6l12 12M18 6L6 18"/>',
}


def _svg_pixmap(key, color, px=18, sw=1.7):
    """Renderizza un'icona linea (dal set ICONS) in una QPixmap nitida (2x)."""
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtCore import QByteArray
    inner = ICONS.get(key, "")
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
           f"stroke='{color}' stroke-width='{sw}' stroke-linecap='round' stroke-linejoin='round'>"
           f"{inner}</svg>")
    scale = 2
    pm = QPixmap(px * scale, px * scale); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p); p.end()
    pm.setDevicePixelRatio(scale)
    return pm


class BrandLogo(QWidget):
    """Mark Déjà: quadrato scuro + mezzo-anello viola + pallino (no logo arcobaleno)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, 35, 35)
        path = QPainterPath(); path.addRoundedRect(r, 10, 10)
        p.fillPath(path, QColor("#15151b"))
        p.setPen(QPen(QColor(255, 255, 255, 26), 1)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
        # mezzo-anello viola
        p.setPen(QPen(QColor(theme.VIOLET), 2.0, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(11.75, 11.75, 12.5, 12.5), 60 * 16, 250 * 16)
        # pallino centrale
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(theme.VIOLET))
        p.drawEllipse(QRectF(16.1, 16.1, 3.8, 3.8))


class NavButton(QPushButton):
    """Voce di navigazione (stile mockup .nav a): icona + label, barra viola se attiva."""
    def __init__(self, label, icon_key=None, on=False, parent=None):
        super().__init__(parent)
        self._label = label; self._icon_key = icon_key
        self.setCheckable(True); self.setChecked(on)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setStyleSheet("QPushButton{border:none; background:transparent;}")
        # hover animato (morbido) + transizione stato attivo
        self._hov = 0.0
        self._act = 1.0 if on else 0.0
        self._hanim = QPropertyAnimation(self, b"hov", self)
        self._hanim.setDuration(150); self._hanim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._aanim = QPropertyAnimation(self, b"act", self)
        self._aanim.setDuration(200); self._aanim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, e): self._animate(self._hanim, 1.0); super().enterEvent(e)
    def leaveEvent(self, e): self._animate(self._hanim, 0.0); super().leaveEvent(e)

    def setChecked(self, on):
        super().setChecked(on)
        if hasattr(self, "_aanim"):
            self._animate(self._aanim, 1.0 if on else 0.0)

    @staticmethod
    def _animate(anim, end):
        anim.stop(); anim.setEndValue(end); anim.start()

    def getHov(self): return self._hov
    def setHov(self, v): self._hov = float(v); self.update()
    hov = pyqtProperty(float, getHov, setHov)

    def getAct(self): return self._act
    def setAct(self, v): self._act = float(v); self.update()
    act = pyqtProperty(float, getAct, setAct)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        a = self._act; h = self._hov
        bg_a = int(13 * a + 9 * h * (1 - a))
        if bg_a > 0:
            path = QPainterPath(); path.addRoundedRect(r.adjusted(0, 1, 0, -1), 8, 8)
            p.fillPath(path, QColor(255, 255, 255, bg_a))
        if a > 0.01:
            bh = 16 * a
            bar = QPainterPath()
            bar.addRoundedRect(QRectF(0, r.center().y() - bh / 2, 2.5, bh), 1.5, 1.5)
            vio = QColor(theme.VIOLET); vio.setAlphaF(min(1.0, a))
            p.fillPath(bar, vio)
        ink = _lerp_color(QColor(theme.INK_SOFT), QColor(theme.INK), max(a, h))
        x = 12.0
        if self._icon_key:
            pm = _svg_pixmap(self._icon_key, ink.name(), 17)
            p.drawPixmap(QRectF(x, r.center().y() - 8.5, 17, 17).toRect(), pm)
            x += 17 + 12
        p.setPen(ink); f = QFont(theme.SANS, 10); f.setWeight(QFont.Weight.Medium); p.setFont(f)
        p.drawText(QRectF(x, 0, r.width() - x - 8, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)


def _nav_btn(label, on=False, icon=None):
    return NavButton(label, icon_key=icon, on=on)


# Scrollbar sottile e discreta (stile mockup) — da appendere agli stylesheet.
SCROLLBAR_QSS = (
    "QScrollBar:vertical{background:transparent; width:10px; margin:2px;}"
    "QScrollBar::handle:vertical{background:rgba(255,255,255,0.09); border-radius:5px;"
    " min-height:34px; border:2px solid transparent; background-clip:padding;}"
    "QScrollBar::handle:vertical:hover{background:rgba(167,139,250,0.45);}"
    "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
    "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
)


def _mono_label(text, size=8, tracking=2.0, color=None):
    """Etichetta mono con tracking reale (QSS letter-spacing è ignorato da Qt)."""
    lb = QLabel(text)
    f = QFont(theme.MONO, size); f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + tracking * 8)
    lb.setFont(f)
    lb.setStyleSheet(f"color:{color or theme.INK_FAINT}; background:transparent;")
    return lb


def _lerp_color(c1, c2, t):
    return QColor(int(c1.red() + (c2.red() - c1.red()) * t),
                  int(c1.green() + (c2.green() - c1.green()) * t),
                  int(c1.blue() + (c2.blue() - c1.blue()) * t),
                  int(c1.alpha() + (c2.alpha() - c1.alpha()) * t))


class ToggleSwitch(QPushButton):
    """Interruttore pillola (look mockup `.sw`): knob + colore animati (OutCubic)."""
    def __init__(self, on=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True); self.setChecked(on)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 24)
        self.setStyleSheet("QPushButton{border:none; background:transparent;}")
        self._p = 1.0 if on else 0.0
        self._anim = QPropertyAnimation(self, b"prog", self)
        self._anim.setDuration(180); self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggle)

    def _on_toggle(self, on):
        self._anim.stop(); self._anim.setStartValue(self._p)
        self._anim.setEndValue(1.0 if on else 0.0); self._anim.start()

    def getProg(self): return self._p
    def setProg(self, v): self._p = float(v); self.update()
    prog = pyqtProperty(float, getProg, setProg)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._p
        track = _lerp_color(QColor(255, 255, 255, 24), QColor(theme.VIOLET), t)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath(); path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, track)
        if t < 1:
            p.setPen(QPen(QColor(255, 255, 255, int(26 * (1 - t)) + 8), 1))
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
        d = self.height() - 6
        kx = 3 + t * (self.width() - d - 6)
        knob = _lerp_color(QColor(theme.INK_SOFT), QColor("#ffffff"), t)
        p.setBrush(knob); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(kx, 3, d, d))


class Stepper(QWidget):
    """Selettore numerico con chevron su/giù (no caret, no QSpinBox), stile mockup .fsel."""
    def __init__(self, value, lo, hi, step=1, suffix="", parent=None):
        super().__init__(parent)
        self._v = value; self._lo = lo; self._hi = hi; self._step = step; self._suffix = suffix
        self.setObjectName("stepper")
        self.setFixedHeight(34); self.setFixedWidth(118)
        self.setStyleSheet(f"QWidget#stepper{{background:rgba(255,255,255,0.04); border:1px solid {theme.LINE};"
                           f" border-radius:9px;}}")
        lay = QHBoxLayout(self); lay.setContentsMargins(12, 0, 5, 0); lay.setSpacing(0)
        self._lbl = QLabel(); self._lbl.setStyleSheet(f"color:{theme.INK}; font-size:13px; border:none; background:transparent;")
        col = QVBoxLayout(); col.setContentsMargins(0, 4, 0, 4); col.setSpacing(3)
        self._up = self._chev("chevup"); self._dn = self._chev("chevdown")
        self._up.clicked.connect(lambda: self._bump(+1)); self._dn.clicked.connect(lambda: self._bump(-1))
        col.addWidget(self._up); col.addWidget(self._dn)
        lay.addWidget(self._lbl, stretch=1); lay.addLayout(col)
        self._render()

    def _chev(self, key):
        b = QPushButton(); b.setFixedSize(26, 11); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setIcon(QIcon(_svg_pixmap(key, theme.INK_SOFT, 12, sw=2.4))); b.setIconSize(QSize(11, 11))
        b.setStyleSheet(f"QPushButton{{border:1px solid {theme.LINE}; background:rgba(255,255,255,0.05); border-radius:5px;}}"
                        "QPushButton:hover{background:rgba(167,139,250,0.22); border:1px solid rgba(167,139,250,0.45);}"
                        "QPushButton:disabled{background:transparent; border:1px solid rgba(255,255,255,0.04);}")
        return b

    def _bump(self, d):
        self.setValue(self._v + d * self._step)

    def _render(self):
        self._lbl.setText(f"{self._v}{self._suffix}")
        self._up.setEnabled(self._v < self._hi); self._dn.setEnabled(self._v > self._lo)

    def value(self): return self._v
    def setValue(self, v):
        self._v = max(self._lo, min(self._hi, int(v))); self._render()


class SegButton(QPushButton):
    """Bottone del segmento filtro (mockup .seg button): bg se attivo + dot colorato."""
    def __init__(self, label, dot=None, on=False, parent=None):
        super().__init__(parent)
        self._label = label; self._dot = dot; self._hover = False
        self.setCheckable(True); self.setChecked(on); self.setFixedHeight(23)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QPushButton{border:none; background:transparent;}")
        f = QFont(theme.SANS, 10); f.setWeight(QFont.Weight.Medium)
        fm = QFontMetrics(f)
        self.setMinimumWidth(fm.horizontalAdvance(label) + (40 if dot else 24))

    def enterEvent(self, e): self._hover = True; self.update(); super().enterEvent(e)
    def leaveEvent(self, e): self._hover = False; self.update(); super().leaveEvent(e)

    def paintEvent(self, _):
        # La pillola attiva è disegnata/animata da _SegBar (slide). Qui solo dot + testo.
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        ink = QColor(theme.INK) if (self.isChecked() or self._hover) else QColor(theme.INK_SOFT)
        x = 11.0
        if self._dot:
            p.setBrush(QColor(*self._dot)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x, r.center().y() - 3, 6, 6)); x += 6 + 7
        p.setPen(ink); f = QFont(theme.SANS, 10); f.setWeight(QFont.Weight.Medium); p.setFont(f)
        p.drawText(QRectF(x, 0, r.width() - x - 11, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)


class _SegBar(QWidget):
    """Segmento filtri con UNA pillola che SLIDA sul bottone attivo (indicatore mobile)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # sottoclasse QWidget: serve WA_StyledBackground per dipingere bg/bordo da stylesheet
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(31)
        self.setObjectName("segtray")
        self.setStyleSheet("QWidget#segtray{background:rgba(255,255,255,0.022);"
                           " border:1px solid rgba(255,255,255,0.10); border-radius:9px;}")
        # pillola mobile (dietro ai bottoni)
        self._pill = QWidget(self); self._pill.setObjectName("segpill")
        self._pill.setStyleSheet("QWidget#segpill{background:#26262f; border:1px solid rgba(255,255,255,0.12);"
                                 " border-radius:7px;}")
        # slide pulito (niente overshoot/rimbalzo → non esce dal tray)
        self._anim = QPropertyAnimation(self._pill, b"geometry", self)
        self._anim.setDuration(280); self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._buttons = []; self._active = 0
        self._lay = QHBoxLayout(self); self._lay.setContentsMargins(4, 0, 4, 0); self._lay.setSpacing(4)

    def add_button(self, btn):
        self._buttons.append(btn); self._lay.addWidget(btn)

    def set_active(self, idx, animate=True):
        if idx < 0 or idx >= len(self._buttons):
            return
        self._active = idx
        for i, b in enumerate(self._buttons):
            b.setChecked(i == idx)
        self._place_pill(animate)

    def _target_rect(self):
        g = self._buttons[self._active].geometry()
        return QRect(g.x(), g.y() + 2, g.width(), g.height() - 4)

    def _place_pill(self, animate):
        if not self._buttons:
            return
        tr = self._target_rect()
        if animate and self.isVisible():
            self._anim.stop(); self._anim.setStartValue(self._pill.geometry())
            self._anim.setEndValue(tr); self._anim.start()
        else:
            self._anim.stop(); self._pill.setGeometry(tr)
        self._pill.lower()  # dietro al testo dei bottoni

    def resizeEvent(self, e):
        super().resizeEvent(e); self._place_pill(False)

    def showEvent(self, e):
        super().showEvent(e); self._place_pill(False)


class AppShell(QWidget):
    """Finestra-app principale (scaffold fase 1)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Déjà")
        self.resize(1180, 740)
        self.setMinimumSize(900, 600)
        # Frame custom (niente cornice Windows). Resize via nativeEvent (WM_NCHITTEST).
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._radius = 13
        self._resize_margin = 6
        # Stato detail/audio (player portato da window.py)
        self._current_type = None
        self._current_pixmap = None
        self._current_audio = None        # (blob, fmt)
        self._audio_data = None           # ndarray decodificato
        self._audio_offset = 0
        self._playback_start = None
        self._is_playing = False
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(80)
        self._playback_timer.timeout.connect(self._update_slider)
        self._build()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor("#101014")); g.setColorAt(1, QColor("#0b0b0e"))
        if getattr(self, "_is_max", False):
            # massimizzato: niente angoli arrotondati (riempi tutto)
            p.fillRect(self.rect(), QBrush(g))
            return
        # finestra arrotondata premium (sfondo translucido fuori dal raggio)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        rad = self._radius
        path = QPainterPath(); path.addRoundedRect(r, rad, rad)
        p.fillPath(path, QBrush(g))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    # ── Frame custom: massimizza senza coprire la taskbar ───────────
    def is_maxed(self):
        return getattr(self, "_is_max", False)

    def toggle_max(self):
        if getattr(self, "_is_max", False):
            self._is_max = False
            if getattr(self, "_normal_geom", None) is not None:
                self.setGeometry(self._normal_geom)
        else:
            self._normal_geom = self.geometry()
            from PyQt6.QtWidgets import QApplication
            scr = self.screen() or QApplication.primaryScreen()
            self.setGeometry(scr.availableGeometry())
            self._is_max = True
        self.update()

    def _make_grips(self):
        """Resize della finestra frameless via QSizeGrip ai 4 angoli (nativo, niente
        codice WM_NCHITTEST che crashava). Riposizionati in resizeEvent."""
        from PyQt6.QtWidgets import QSizeGrip
        self._grips = []
        for _ in range(4):
            g = QSizeGrip(self); g.setFixedSize(16, 16)
            g.setStyleSheet("background:transparent; image:none;")
            self._grips.append(g)

    def _place_grips(self):
        if not getattr(self, "_grips", None):
            return
        w, h, s = self.width(), self.height(), 16
        tl, tr, bl, br = self._grips
        tl.move(0, 0); tr.move(w - s, 0); bl.move(0, h - s); br.move(w - s, h - s)
        for g in self._grips:
            g.raise_(); g.setVisible(not self.is_maxed())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_grips()
        self._place_winctl()

    # ── Controlli finestra (overlay, niente barra dedicata) ─────────
    def _build_winctl(self):
        self._winctl = QWidget(self); self._winctl.setObjectName("winctl")
        self._winctl.setStyleSheet("QWidget#winctl{background:transparent;}")
        l = QHBoxLayout(self._winctl); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(0)
        self._b_min = self._winbtn("winmin", self.showMinimized)
        self._b_max = self._winbtn("winmax", self._toggle_max_ctl)
        self._b_close = self._winbtn("winclose", self.close, danger=True)
        for b in (self._b_min, self._b_max, self._b_close):
            l.addWidget(b)
        self._winctl.adjustSize()
        self._place_winctl()

    def _winbtn(self, icon, slot, danger=False):
        b = QPushButton(); b.setFixedSize(42, 28); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setIcon(QIcon(_svg_pixmap(icon, theme.INK_SOFT, 15, sw=1.5))); b.setIconSize(QSize(15, 15))
        hover = "rgba(239,68,68,0.90)" if danger else "rgba(255,255,255,0.07)"
        b.setStyleSheet(f"QPushButton{{border:none; background:transparent; border-radius:7px;}}"
                        f"QPushButton:hover{{background:{hover};}}")
        b.clicked.connect(slot)
        return b

    def _place_winctl(self):
        wc = getattr(self, "_winctl", None)
        if wc is None:
            return
        pad = 0 if self.is_maxed() else 4
        wc.move(self.width() - wc.width() - pad, pad)
        wc.raise_()

    def _toggle_max_ctl(self):
        self.toggle_max(); self._sync_winctl_icon(); self._place_winctl()

    def _sync_winctl_icon(self):
        key = "winrestore" if self.is_maxed() else "winmax"
        self._b_max.setIcon(QIcon(_svg_pixmap(key, theme.INK_SOFT, 15, sw=1.5)))

    # ── Trascinamento finestra dalla fascia header (top 58px) ───────
    def _in_drag_band(self, e):
        return e.position().y() <= 58 and e.position().x() <= self.width() - self._winctl.width() - 8

    def mousePressEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton and not self.is_maxed()
                and self._in_drag_band(e)):
            self._wdrag = self.frameGeometry().topLeft() - e.globalPosition().toPoint()
            e.accept(); return
        self._wdrag = None
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if getattr(self, "_wdrag", None) is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() + self._wdrag); e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._wdrag = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._in_drag_band(e):
            self._toggle_max_ctl(); e.accept(); return
        super().mouseDoubleClickEvent(e)

    def _build(self):
        # Niente barra-titolo dedicata: le colonne arrivano fino in cima e i controlli
        # finestra (min/max/chiudi) galleggiano in alto a destra (overlay). La fascia
        # superiore (header) fa da area-trascinamento. Così non c'è spazio vuoto sopra.
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        cols = QWidget(); root = QHBoxLayout(cols); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        outer.addWidget(cols, stretch=1)

        # ── Sidebar ──
        side = QWidget(); side.setFixedWidth(226)
        side.setObjectName("sidebar"); side.setStyleSheet(f"QWidget#sidebar{{background:transparent; border-right:1px solid {theme.LINE};}}")
        sl = QVBoxLayout(side); sl.setContentsMargins(12, 16, 12, 22); sl.setSpacing(1)
        brand = QWidget(); bl = QHBoxLayout(brand); bl.setContentsMargins(13, 9, 8, 28); bl.setSpacing(11)
        bl.addWidget(BrandLogo())
        bname = QLabel("Déjà"); f = QFont(theme.SANS, 15); f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99); bname.setFont(f)
        bname.setStyleSheet(f"color:{theme.INK}; background:transparent;")
        bl.addWidget(bname); bl.addStretch()
        sl.addWidget(brand)

        self._nav = {}   # key -> NavButton
        ml_lbl = _mono_label("MENU"); ml_lbl.setContentsMargins(10, 14, 0, 4); sl.addWidget(ml_lbl)
        for key, lbl, icon in (("timeline", "Timeline", "timeline"), ("search", "Cerca", "search"),
                               ("assistant", "Assistente", "assistant"), ("gallery", "Galleria", "gallery")):
            b = _nav_btn(lbl, on=(key == "timeline"), icon=icon)
            b.clicked.connect(lambda _=False, k=key: self._switch_page(k))
            self._nav[key] = b; sl.addWidget(b)
        gm = _mono_label("GESTIONE"); gm.setContentsMargins(10, 12, 0, 4); sl.addWidget(gm)
        b_set = _nav_btn("Impostazioni", icon="settings"); b_set.clicked.connect(lambda: self._switch_page("settings"))
        self._nav["settings"] = b_set
        b_info = _nav_btn("Info e Privacy", icon="info"); b_info.setCheckable(False)
        b_info.clicked.connect(self._open_about)
        sl.addWidget(b_set); sl.addWidget(b_info)
        sl.addStretch()

        # Stato cattura + archivio (card)
        status = QFrame(); status.setObjectName("statuscard")
        status.setStyleSheet(f"QFrame#statuscard{{border:1px solid {theme.LINE}; border-radius:12px;}}"
                             " QLabel{border:none; background:transparent;}")
        stl = QVBoxLayout(status); stl.setContentsMargins(15, 14, 15, 15); stl.setSpacing(11)
        cap = QLabel("●  Cattura attiva"); cap.setStyleSheet(f"color:{theme.EMERALD}; font-size:12px; font-weight:500;")
        stl.addWidget(cap)
        arc_row = QHBoxLayout(); arc_row.setContentsMargins(0, 0, 0, 0)
        arc_k = QLabel("Archivio"); arc_k.setStyleSheet(f"color:{theme.INK_DIM}; font-size:12px;")
        self._archive_lbl = QLabel("—")
        af = QFont(theme.MONO, 9); self._archive_lbl.setFont(af)
        self._archive_lbl.setStyleSheet(f"color:{theme.INK_SOFT};")
        arc_row.addWidget(arc_k); arc_row.addStretch(); arc_row.addWidget(self._archive_lbl)
        stl.addLayout(arc_row)
        sl.addWidget(status)

        # Profilo
        import getpass
        try:
            username = getpass.getuser() or "Utente"
        except Exception:
            username = "Utente"
        prof = QWidget(); prl = QHBoxLayout(prof); prl.setContentsMargins(8, 20, 8, 2); prl.setSpacing(11)
        av = QLabel(username[:1].upper()); av.setFixedSize(34, 34); av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(f"background:#22222b; border:1px solid {theme.LINE}; border-radius:9px;"
                         f" color:{theme.INK_SOFT}; font-size:14px; font-weight:600;")
        pcol = QVBoxLayout(); pcol.setSpacing(1)
        pn = QLabel(username); pn.setStyleSheet(f"color:{theme.INK}; font-size:13px; font-weight:600;")
        ph = QLabel("locale · cifrato"); ph.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px;")
        pcol.addWidget(pn); pcol.addWidget(ph)
        prl.addWidget(av); prl.addLayout(pcol); prl.addStretch()
        sl.addWidget(prof)
        root.addWidget(side)

        # ── Stack pagine ──
        self._stack = QStackedWidget()
        self._page_index = {}
        for key, w in (("timeline", self._build_timeline_page()),
                       ("search", self._build_search_page()),
                       ("assistant", self._build_assistant_page()),
                       ("gallery", self._build_gallery_page()),
                       ("settings", self._build_settings_page())):
            self._page_index[key] = self._stack.addWidget(w)
        root.addWidget(self._stack, stretch=1)

        # ── Detail (condiviso da Timeline e Cerca) ──
        root.addWidget(self._build_detail())

        self._make_grips()  # resize angoli (finestra frameless)
        self._build_winctl()  # controlli finestra overlay in alto a destra
        self._records = []
        self._search_records = []
        self._gallery_loaded = False
        self._tl_filter = "all"
        self._load()  # carica i dati reali dopo che il detail esiste

    # ── Pagina Timeline ─────────────────────────────────────────────
    def _build_timeline_page(self):
        main = QWidget(); ml = QVBoxLayout(main); ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(0)
        top = QWidget(); top.setObjectName("hbar"); top.setFixedHeight(58); top.setStyleSheet(f"QWidget#hbar{{border-bottom:1px solid {theme.LINE};}}")
        tl = QHBoxLayout(top); tl.setContentsMargins(20, 0, 20, 0); tl.setSpacing(12)
        self._tl_search = QLineEdit(); self._tl_search.setPlaceholderText("Cerca nei tuoi ricordi…")
        self._tl_search.setStyleSheet(
            f"QLineEdit{{background:rgba(255,255,255,0.035); border:1px solid {theme.LINE};"
            f" border-radius:10px; padding:8px 12px; color:{theme.INK}; font-family:'{theme.SANS}'; font-size:13px;}}"
        )
        self._tl_search.setFixedHeight(36)
        self._tl_search.returnPressed.connect(self._jump_to_search)
        tl.addWidget(self._tl_search, stretch=1)

        # Segmento filtro tipo: pillola che SLIDA sul filtro attivo (_SegBar)
        seg = _SegBar()
        self._tl_seg = {}; self._tl_seg_keys = []
        for key, label, dot in (("all", "Tutto", None), ("screenshot", "Schermo", theme.EMERALD_RGB),
                                ("audio", "Audio", theme.AMBER_RGB)):
            b = SegButton(label, dot=dot, on=(key == "all"))
            b.clicked.connect(lambda _=False, k=key: self._set_tl_filter(k))
            self._tl_seg[key] = b; self._tl_seg_keys.append(key); seg.add_button(b)
        self._seg_bar = seg
        tl.addWidget(seg)
        ml.addWidget(top)

        self._day_label = QLabel("Caricamento cronologia…")
        self._day_label.setFont(QFont(theme.SANS, 13, QFont.Weight.DemiBold))
        self._day_label.setStyleSheet(f"color:{theme.INK}; padding:14px 18px 6px;")
        ml.addWidget(self._day_label)

        self.timeline = QListWidget()
        self.timeline.setStyleSheet(theme.results_list() + f" QListWidget{{padding:4px 12px;}}")
        self.timeline.setItemDelegate(TimelineDelegate(self.timeline))
        self.timeline.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timeline.currentRowChanged.connect(
            self._make_pick_handler(lambda: self.timeline, "_records"))
        self.timeline.verticalScrollBar().valueChanged.connect(
            lambda _: self._ensure_visible_thumbs(self.timeline))
        ml.addWidget(self.timeline, stretch=1)
        return main

    def _build_detail(self):
        self.detail = QWidget(); self.detail.setFixedWidth(366)
        self.detail.setObjectName("detailcol"); self.detail.setStyleSheet(f"QWidget#detailcol{{border-left:1px solid {theme.LINE};}}")
        dl = QVBoxLayout(self.detail); dl.setContentsMargins(0, 0, 0, 0); dl.setSpacing(0)

        # ── Header con linea divisoria (mockup .dhead) ──
        head = QWidget(); head.setObjectName("dhead")
        head.setStyleSheet(f"QWidget#dhead{{border-bottom:1px solid {theme.LINE};}}"
                           " QWidget#dhead QLabel{border:none; background:transparent;}")
        # margine destro ampio: lascia spazio ai controlli finestra (overlay top-right)
        hl = QHBoxLayout(head); hl.setContentsMargins(18, 14, 134, 14); hl.setSpacing(11)
        self._detail_badge = QLabel(); self._detail_badge.setFixedSize(30, 30)
        self._detail_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tcol = QVBoxLayout(); tcol.setSpacing(5); tcol.setContentsMargins(0, 1, 0, 0)
        self._detail_title = QLabel("Seleziona un ricordo"); self._detail_title.setWordWrap(False)
        tf = QFont(theme.SANS, 13); tf.setWeight(QFont.Weight.DemiBold); self._detail_title.setFont(tf)
        self._detail_title.setStyleSheet(f"color:{theme.INK};")
        self._detail_sub = QLabel("")
        sf = QFont(theme.MONO, 8); sf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
        self._detail_sub.setFont(sf); self._detail_sub.setStyleSheet(f"color:{theme.INK_DIM};")
        tcol.addWidget(self._detail_title); tcol.addWidget(self._detail_sub)
        hl.addWidget(self._detail_badge, alignment=Qt.AlignmentFlag.AlignTop)
        hl.addLayout(tcol, stretch=1)
        dl.addWidget(head)

        # ── Corpo scrollabile: preview/testo + azioni + contesto ──
        body = QWidget(); body.setObjectName("detailbody")
        body.setStyleSheet("QWidget#detailbody{background:transparent;}")
        bv = QVBoxLayout(body); bv.setContentsMargins(18, 16, 18, 18); bv.setSpacing(14)

        self._shot_label = QLabel(); self._shot_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._shot_label.setStyleSheet("background:transparent;")
        bv.addWidget(self._shot_label)

        self._detail_body = QLabel("Seleziona un ricordo dalla timeline."); self._detail_body.setWordWrap(True)
        self._detail_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._detail_body.setOpenExternalLinks(True)
        self._detail_body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._detail_body.setStyleSheet(f"color:{theme.INK_SOFT}; font-size:13px; line-height:1.6;")
        bv.addWidget(self._detail_body)

        bv.addWidget(self._build_audio_bar())

        # Azioni (per tipo)
        self._detail_actions = QWidget()
        aw = QHBoxLayout(self._detail_actions); aw.setContentsMargins(0, 0, 0, 0); aw.setSpacing(7)
        self._act_open = self._act_btn("Apri", "expand", primary=True); self._act_open.clicked.connect(self._detail_open)
        self._act_link = self._act_btn("Apri link", "link"); self._act_link.clicked.connect(self._detail_open_link)
        self._act_ai = self._act_btn("Chiedi all'AI", "ai"); self._act_ai.clicked.connect(self._detail_ask_ai)
        self._act_star = self._act_btn("", "star"); self._act_star.clicked.connect(self._detail_pin)
        self._act_copy = self._act_btn("", "copy"); self._act_copy.clicked.connect(self._detail_copy)
        aw.addWidget(self._act_open); aw.addWidget(self._act_link); aw.addWidget(self._act_ai)
        aw.addStretch(); aw.addWidget(self._act_star); aw.addWidget(self._act_copy)
        bv.addWidget(self._detail_actions)

        # Contesto: tipi di ricordo attorno a questo momento
        self._ctx_wrap = QWidget()
        cv = QVBoxLayout(self._ctx_wrap); cv.setContentsMargins(0, 4, 0, 0); cv.setSpacing(9)
        ctxlbl = QLabel("INTORNO A QUESTO MOMENTO")
        cf = QFont(theme.MONO, 8); cf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 116); ctxlbl.setFont(cf)
        ctxlbl.setStyleSheet(f"color:{theme.INK_FAINT};")
        self._ctx_chips = QWidget(); self._ctx_chips_l = QHBoxLayout(self._ctx_chips)
        self._ctx_chips_l.setContentsMargins(0, 0, 0, 0); self._ctx_chips_l.setSpacing(7)
        self._ctx_chips_l.addStretch()
        cv.addWidget(ctxlbl); cv.addWidget(self._ctx_chips)
        bv.addWidget(self._ctx_wrap)

        bv.addStretch()
        self._body_scroll = QScrollArea(); self._body_scroll.setWidgetResizable(True)
        self._body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body_scroll.setStyleSheet("QScrollArea{background:transparent; border:none;}" + SCROLLBAR_QSS)
        self._body_scroll.viewport().setAutoFillBackground(False)
        self._body_scroll.viewport().setStyleSheet("background:transparent;")
        self._body_scroll.setWidget(body)
        dl.addWidget(self._body_scroll, stretch=1)
        # compat: _shot_scroll non più separato (preview ora inline nel corpo)
        self._shot_scroll = self._shot_label
        return self.detail

    def _build_audio_bar(self):
        self._audio_bar = QWidget()
        self._audio_bar.setStyleSheet(
            f"background:rgba(255,255,255,0.03); border:1px solid {theme.LINE}; border-radius:12px;")
        al = QVBoxLayout(self._audio_bar); al.setContentsMargins(14, 12, 14, 12); al.setSpacing(8)
        self.waveform = WaveformWidget()
        al.addWidget(self.waveform)
        self.audio_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_slider.setMaximum(100)
        self.audio_slider.sliderPressed.connect(self._on_slider_pressed)
        self.audio_slider.sliderMoved.connect(self._on_slider_moved)
        self.audio_slider.sliderReleased.connect(self._on_slider_released)
        al.addWidget(self.audio_slider)
        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(8)
        self.play_btn = QPushButton("▶  Ascolta"); self.play_btn.setFixedHeight(32)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setStyleSheet(
            f"QPushButton{{background:rgba(245,158,11,0.15); color:{theme.AMBER};"
            f" border:1px solid rgba(245,158,11,0.30); border-radius:8px; font-size:12px;"
            f" font-weight:600; padding:0 14px; font-family:'{theme.SANS}';}}"
            "QPushButton:hover{background:rgba(245,158,11,0.25);}")
        self.play_btn.clicked.connect(self._play_audio)
        self.audio_time_cur = QLabel("0:00"); self.audio_time_total = QLabel("0:00")
        for lb in (self.audio_time_cur, self.audio_time_total):
            lb.setFont(QFont(theme.MONO, 9)); lb.setStyleSheet(f"color:{theme.INK_FAINT};")
        row.addWidget(self.play_btn); row.addWidget(self.audio_time_cur)
        row.addStretch(); row.addWidget(self.audio_time_total)
        al.addLayout(row)
        self._audio_bar.hide()
        return self._audio_bar

    # ── Pagina Cerca ────────────────────────────────────────────────
    def _build_search_page(self):
        page = QWidget(); pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
        top = QWidget(); top.setObjectName("hbar"); top.setFixedHeight(58); top.setStyleSheet(f"QWidget#hbar{{border-bottom:1px solid {theme.LINE};}}")
        tlr = QHBoxLayout(top); tlr.setContentsMargins(20, 0, 20, 0); tlr.setSpacing(12)
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Cerca per rilevanza nei ricordi…")
        self.search_input.setStyleSheet(
            f"QLineEdit{{background:rgba(255,255,255,0.035); border:1px solid {theme.LINE};"
            f" border-radius:10px; padding:8px 12px; color:{theme.INK}; font-family:'{theme.SANS}'; font-size:13px;}}"
            f"QLineEdit:focus{{border:1px solid rgba(167,139,250,0.5);}}")
        self.search_input.setFixedHeight(36)
        self.search_input.returnPressed.connect(self._do_search)
        tlr.addWidget(self.search_input, stretch=1)
        pl.addWidget(top)

        self._search_status = QLabel("Scrivi e premi Invio")
        self._search_status.setFont(QFont(theme.SANS, 13, QFont.Weight.DemiBold))
        self._search_status.setStyleSheet(f"color:{theme.INK}; padding:14px 18px 6px;")
        pl.addWidget(self._search_status)

        self.search_list = QListWidget()
        self.search_list.setStyleSheet(theme.results_list() + f" QListWidget{{padding:4px 12px;}}")
        self.search_list.setItemDelegate(TimelineDelegate(self.search_list))
        self.search_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.search_list.currentRowChanged.connect(
            self._make_pick_handler(lambda: self.search_list, "_search_records"))
        self.search_list.verticalScrollBar().valueChanged.connect(
            lambda _: self._ensure_visible_thumbs(self.search_list))
        pl.addWidget(self.search_list, stretch=1)
        return page

    def _set_tl_filter(self, key):
        self._tl_filter = key
        # pillola che slida sul filtro attivo
        if key in self._tl_seg_keys:
            self._seg_bar.set_active(self._tl_seg_keys.index(key), animate=True)
        self._build_rows()
        for i in range(self.timeline.count()):
            it = self.timeline.item(i)
            if it and not it.data(TL_HOUR):
                self.timeline.setCurrentRow(i); break
        QTimer.singleShot(0, lambda: self._ensure_visible_thumbs(self.timeline))

    def _jump_to_search(self):
        q = self._tl_search.text().strip()
        self._switch_page("search")
        if q:
            self.search_input.setText(q); self._do_search()

    def _do_search(self):
        q = self.search_input.text().strip()
        if not q:
            return
        self._search_status.setText(f"Ricerca di «{q}»…")
        self.search_list.clear()
        self._search_worker = SearchWorker(q)
        self._search_worker.done.connect(lambda res, qq=q: self._on_search_done(res, qq))
        self._search_worker.error.connect(lambda e: self._search_status.setText(f"Errore: {e}"))
        self._search_worker.start()

    def _on_search_done(self, results, q):
        self._search_records = results or []
        n = len(self._search_records)
        self._search_status.setText(
            f"{n} risultat{'o' if n == 1 else 'i'} per «{q}»" if n else f"Nessun risultato per «{q}»")
        self.search_list.blockSignals(True); self.search_list.clear()
        for idx, r in enumerate(self._search_records):
            kind = self._kind_of(r)
            title, _ = self._row_text(r, kind)
            score = r.get("score")
            sub = ("✓ esatto" if r.get("exact") else
                   (f"rilevanza {int(score * 100)}%" if isinstance(score, (int, float)) else ""))
            it = QListWidgetItem()
            it.setData(TL_TITLE, title); it.setData(TL_SUB, sub)
            it.setData(TL_TIME, self._clock(r.get("ts", "")))
            it.setData(TL_KIND, kind); it.setData(TL_HUE, HUE.get(kind, theme.VIOLET_RGB))
            it.setData(TL_ID, r.get("id")); it.setData(TL_IDX, idx)
            self.search_list.addItem(it)
        self.search_list.blockSignals(False)
        if n:
            self.search_list.setCurrentRow(0)
        QTimer.singleShot(0, lambda: self._ensure_visible_thumbs(self.search_list))

    # ── Pagina Galleria ─────────────────────────────────────────────
    def _build_gallery_page(self):
        page = QWidget(); pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
        head = QLabel("Galleria"); head.setFont(QFont(theme.SANS, 13, QFont.Weight.DemiBold))
        head.setStyleSheet(f"color:{theme.INK}; padding:18px 18px 8px;")
        pl.addWidget(head)
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setIconSize(QSize(150, 96))
        self.gallery.setSpacing(10)
        self.gallery.setGridSize(QSize(166, 124))
        self.gallery.setUniformItemSizes(True)
        self.gallery.setStyleSheet(
            SCROLLBAR_QSS +
            f"QListWidget{{background:transparent; border:none; padding:8px 14px;}}"
            f"QListWidget::item{{color:{theme.INK_DIM}; border-radius:8px;}}"
            f"QListWidget::item:selected{{background:rgba(255,255,255,0.06);}}")
        self.gallery.verticalScrollBar().valueChanged.connect(lambda _: self._ensure_gallery_thumbs())
        self.gallery.itemDoubleClicked.connect(
            lambda it: self._on_embed_ss_click(it.data(TL_ID)) if it.data(TL_ID) is not None else None)
        pl.addWidget(self.gallery, stretch=1)
        return page

    def _load_gallery(self):
        """Riempie la galleria con i soli screenshot (icone lazy)."""
        shots = [r for r in self._records if r.get("type") == "screenshot"]
        self._gallery_records = shots
        self.gallery.clear()
        for r in shots:
            it = QListWidgetItem(self._clock(r.get("ts", "")))
            it.setData(TL_ID, r.get("id"))
            it.setSizeHint(QSize(166, 124))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.gallery.addItem(it)
        self._gallery_loaded = True
        QTimer.singleShot(0, self._ensure_gallery_thumbs)

    def _ensure_gallery_thumbs(self):
        """Carica le icone galleria solo per le celle visibili (1 conn DB).
        Guard di rientranza: in IconMode `setIcon` rilancia il layout della vista,
        che può ri-emettere valueChanged → ricorsione → crash. Il flag la blocca."""
        if getattr(self, "_gal_busy", False):
            return
        self._gal_busy = True
        try:
            lw = self.gallery; n = lw.count()
            if n == 0:
                return
            vph = lw.viewport().rect().height()
            top_it = lw.itemAt(8, 4); bot_it = lw.itemAt(8, max(4, vph - 4))
            start = lw.row(top_it) if top_it is not None else 0
            end = lw.row(bot_it) if bot_it is not None else n - 1
            start = max(0, start - 6); end = min(n - 1, end + 18)
            need = [(lw.item(i), lw.item(i).data(TL_ID)) for i in range(start, end + 1)
                    if lw.item(i) and lw.item(i).icon().isNull() and lw.item(i).data(TL_ID) is not None]
            if not need:
                return
            from db import get_conn
            from PyQt6.QtGui import QIcon
            conn = get_conn()
            try:
                cur = conn.cursor()
                for it, sid in need:
                    if sid in _THUMB_CACHE:
                        pm = _THUMB_CACHE[sid]
                    else:
                        row = cur.execute("SELECT image FROM screenshots WHERE id=?", (sid,)).fetchone()
                        pm = _decode_thumb(row[0]) if row and row[0] else None
                        if len(_THUMB_CACHE) > 1500:
                            _THUMB_CACHE.clear()
                        _THUMB_CACHE[sid] = pm
                    if pm is not None:
                        it.setIcon(QIcon(pm))
            finally:
                conn.close()
        except Exception:
            pass
        finally:
            self._gal_busy = False

    # ── Pagina Assistente ───────────────────────────────────────────
    def _build_assistant_page(self):
        self.chat_page = ChatPage()
        self.chat_page.send_clicked.connect(self._send_chat_message)
        self.chat_page.new_chat_btn.clicked.connect(self._reset_chat)
        self._chat_history = []
        self._chat_worker = None
        self._chat_thinking = None
        self._chat_current_bubble = None
        self._chat_current_container = None
        self._chat_current_text = ""
        self._chat_turn_bubbles = []
        self._chat_loaded = False
        self._chat_audio_playing = None
        return self.chat_page

    # ── Switch pagina + gestione ────────────────────────────────────
    def _switch_page(self, key):
        idx = self._page_index.get(key)
        if idx is None:
            return
        self._stack.setCurrentIndex(idx)
        self._fade_in(self._stack.currentWidget())
        for k, b in self._nav.items():
            b.setChecked(k == key)
        # Detail condiviso solo per Timeline e Cerca
        self.detail.setVisible(key in ("timeline", "search"))
        if key == "search":
            self.search_input.setFocus()
        elif key == "gallery" and not self._gallery_loaded:
            self._load_gallery()
        elif key == "assistant":
            if not self._chat_loaded:
                self._load_chat_from_db(); self._chat_loaded = True
            self.chat_page.input.setFocus()

    def _fade_in(self, w):
        """Fade morbido del contenuto entrante (mockup @keyframes fade)."""
        try:
            from PyQt6.QtWidgets import QGraphicsOpacityEffect
            from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
            eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff)
            a = QPropertyAnimation(eff, b"opacity", self)
            a.setDuration(220); a.setStartValue(0.0); a.setEndValue(1.0)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            a.finished.connect(lambda: w.setGraphicsEffect(None))
            a.start(); self._page_fade = a
        except Exception:
            pass

    def _open_settings(self, page="general"):
        try:
            from ui.window import SettingsDialog
            dlg = SettingsDialog(self)
            dlg.select_page(page); dlg.exec()
        except Exception as e:
            self.toast(f"Impostazioni non disponibili: {e}", level="error")

    def _open_about(self):
        try:
            from ui.framed import alert as _alert
            import config, paths, i18n
            from i18n import t
            ocr = t("about.ocr_active") if config.TESSERACT_CMD else t("about.ocr_missing")
            _alert(self, t("about.title"),
                   t("about.body", version=config.APP_VERSION, ocr=ocr,
                     lang=i18n.LANGUAGES.get(i18n.get_language(), i18n.get_language()),
                     data=paths.data_dir(), log=paths.log_file()))
        except Exception as e:
            self.toast(f"Info non disponibili: {e}", level="error")

    # ── Pagina Impostazioni (in-app, stile mockup deja-app.html) ────
    def _build_settings_page(self):
        from db import get_setting
        page = QWidget(); pl = QVBoxLayout(page); pl.setContentsMargins(0, 0, 0, 0); pl.setSpacing(0)
        top = QWidget(); top.setObjectName("hbar"); top.setFixedHeight(58); top.setStyleSheet(f"QWidget#hbar{{border-bottom:1px solid {theme.LINE};}}")
        tlr = QHBoxLayout(top); tlr.setContentsMargins(20, 0, 20, 0)
        ttl = QLabel("Impostazioni"); ttl.setFont(QFont(theme.SANS, 14, QFont.Weight.DemiBold))
        ttl.setStyleSheet(f"color:{theme.INK};"); tlr.addWidget(ttl); tlr.addStretch()
        pl.addWidget(top)

        body = QWidget(); bl = QHBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)
        # sub-nav
        nav = QWidget(); nav.setFixedWidth(176)
        nav.setObjectName("setnav"); nav.setStyleSheet(f"QWidget#setnav{{border-right:1px solid {theme.LINE};}}")
        nvl = QVBoxLayout(nav); nvl.setContentsMargins(12, 14, 12, 14); nvl.setSpacing(2)
        self._set_stack = QStackedWidget()
        self._set_subnav = {}
        subpages = (("capture", "Cattura", "capture", self._build_set_capture),
                    ("privacy", "Area & Privacy", "shield", self._build_set_privacy),
                    ("ai", "AI", "spark", self._build_set_ai),
                    ("security", "Sicurezza", "lock", self._build_set_security),
                    ("advanced", "Avanzate", "sliders", self._build_set_advanced))
        for i, (key, label, icon, builder) in enumerate(subpages):
            b = _nav_btn(label, on=(i == 0), icon=icon)
            b.clicked.connect(lambda _=False, k=key: self._set_select(k))
            self._set_subnav[key] = b; nvl.addWidget(b)
            sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.Shape.NoFrame)
            sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sc.setStyleSheet("QScrollArea{background:transparent; border:none;}" + SCROLLBAR_QSS)
            sc.viewport().setAutoFillBackground(False)
            sc.viewport().setStyleSheet("background:transparent;")
            sc.setWidget(builder(get_setting))
            self._set_stack.addWidget(sc)
        nvl.addStretch()
        bl.addWidget(nav); bl.addWidget(self._set_stack, stretch=1)
        pl.addWidget(body, stretch=1)

        foot = QWidget(); foot.setObjectName("setfoot"); foot.setFixedHeight(58); foot.setStyleSheet(f"QWidget#setfoot{{border-top:1px solid {theme.LINE};}}")
        fl = QHBoxLayout(foot); fl.setContentsMargins(20, 0, 20, 0); fl.setSpacing(10)
        fl.addStretch()
        cancel = QPushButton("Annulla"); cancel.setFixedHeight(34); cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QPushButton{{background:transparent; color:{theme.INK_SOFT}; border:1px solid {theme.LINE};"
            f" border-radius:8px; padding:0 16px; font-family:'{theme.SANS}'; font-size:12px;}}"
            "QPushButton:hover{background:rgba(255,255,255,0.04);}")
        cancel.clicked.connect(lambda: self._switch_page("timeline"))
        save = QPushButton("Salva impostazioni"); save.setFixedHeight(34); save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setStyleSheet(
            f"QPushButton{{background:{theme.VIOLET}; color:#16121f; border:none; border-radius:8px;"
            f" padding:0 18px; font-family:'{theme.SANS}'; font-size:12px; font-weight:700;}}"
            "QPushButton:hover{background:#b9a3ff;}")
        save.clicked.connect(self._save_settings)
        fl.addWidget(cancel); fl.addWidget(save)
        pl.addWidget(foot)
        return page

    def _set_select(self, key):
        idx = list(self._set_subnav.keys()).index(key)
        self._set_stack.setCurrentIndex(idx)
        for k, b in self._set_subnav.items():
            b.setChecked(k == key)

    # helper: contenitore scrollabile di una sotto-pagina
    @staticmethod
    def _set_body():
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w); lay.setContentsMargins(26, 22, 26, 22); lay.setSpacing(12)
        return w, lay

    @staticmethod
    def _set_section(text, first=False):
        s = QLabel(text.upper())
        f = QFont(theme.MONO, 8); f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 116)
        s.setFont(f)
        s.setContentsMargins(0, 2 if first else 22, 0, 6)
        s.setStyleSheet(f"color:{theme.INK_FAINT}; background:transparent;")
        return s

    def _set_row(self, title, desc, control):
        # riga con sola LINEA divisoria in basso (no pill/card) — come mockup .frow
        row = QFrame(); row.setObjectName("frow")
        row.setStyleSheet(f"QFrame#frow{{border:none; border-bottom:1px solid {theme.LINE};}}"
                          " QFrame#frow QLabel{border:none; background:transparent;}")
        rl = QHBoxLayout(row); rl.setContentsMargins(2, 13, 2, 13); rl.setSpacing(20)
        # blocco testo in un QWidget reale + AlignLeft espliciti: così il titolo è SEMPRE
        # a sinistra a prescindere dalla larghezza del controllo (toggle/stepper/input).
        leftw = QWidget(); leftw.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(leftw); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(3)
        t = QLabel(title); t.setStyleSheet(f"color:{theme.INK}; font-size:13px; font-weight:500;")
        d = QLabel(desc); d.setWordWrap(True)
        d.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px;")
        lv.addWidget(t); lv.addWidget(d)
        rl.addWidget(leftw, stretch=1)
        if control is not None:
            rl.addWidget(control, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row

    def _set_input(self, text="", placeholder=""):
        e = QLineEdit(text); e.setPlaceholderText(placeholder); e.setFixedHeight(32); e.setMinimumWidth(180)
        e.setStyleSheet(
            f"QLineEdit{{background:rgba(255,255,255,0.04); color:{theme.INK}; border:1px solid {theme.LINE};"
            f" border-radius:8px; padding:0 10px; font-family:'{theme.SANS}'; font-size:12px;}}"
            f"QLineEdit:focus{{border:1px solid rgba(167,139,250,0.5);}}")
        return e

    def _build_set_capture(self, get_setting):
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Cattura", first=True))
        self._s_cap_screens = ToggleSwitch((get_setting("capture_screenshots_enabled", "1") or "1") == "1")
        lay.addWidget(self._set_row("Cattura schermate", "Salva periodicamente schermate del desktop.", self._s_cap_screens))
        self._s_cap_audio = ToggleSwitch((get_setting("capture_audio_enabled", "1") or "1") == "1")
        lay.addWidget(self._set_row("Cattura audio", "Registra e trascrive microfono / audio di sistema.", self._s_cap_audio))
        import config as _cfg
        self._s_interval = self._set_input(str(getattr(_cfg, "CAPTURE_INTERVAL", "")), "es. 4")
        self._s_interval.setFixedWidth(90)
        lay.addWidget(self._set_row("Intervallo schermate (s)", "Secondi tra una schermata e l'altra.", self._s_interval))
        lay.addStretch()
        return w

    def _build_set_privacy(self, get_setting):
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Area schermo & Privacy", first=True))
        self._s_redact = ToggleSwitch((get_setting("privacy_redact", "1") or "1") == "1")
        lay.addWidget(self._set_row("Oscura dati sensibili (PII)", "Maschera email, carte e password nel testo riconosciuto.", self._s_redact))
        try: _idle0 = int(get_setting("privacy_idle_min", "5") or 5)
        except Exception: _idle0 = 5
        self._s_idle = Stepper(_idle0, 0, 120, step=1, suffix=" min")
        lay.addWidget(self._set_row("Pausa dopo inattività", "Sospende la cattura quando non usi il PC (0 = mai).", self._s_idle))
        self._s_blocklist = self._set_input(get_setting("privacy_blocklist", "") or "", "app o titoli da non catturare, virgola")
        lay.addWidget(self._set_row("App / titoli esclusi", "Non catturare finestre che contengono queste parole.", self._s_blocklist))

        lay.addWidget(self._set_section("Estensione browser"))
        try:
            from modules import web_bridge as _wb
            web_on = _wb.enabled()
        except Exception:
            web_on = False
        self._s_web_enabled = ToggleSwitch(web_on)
        lay.addWidget(self._set_row("Abilita estensione", "Cattura le pagine visitate (canale locale, nessuna porta di rete).", self._s_web_enabled))
        self._s_web_excluded = self._set_input(get_setting("web_excluded_domains", "") or "", "bank.com, mail.google.com")
        lay.addWidget(self._set_row("Domini da non catturare", "Uno o più domini separati da virgola.", self._s_web_excluded))
        lay.addStretch()
        return w

    def _build_set_ai(self, get_setting):
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Assistente AI", first=True))
        self._s_ai_url = self._set_input(get_setting("ai_base_url", "") or "", "https://api.openai.com/v1")
        lay.addWidget(self._set_row("Endpoint (base URL)", "URL compatibile OpenAI per la chat.", self._s_ai_url))
        self._s_ai_key = self._set_input("", "•••• (lascia vuoto per non cambiare)")
        self._s_ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._set_row("API key", "Salvata cifrata (DPAPI). Vuoto = invariata.", self._s_ai_key))
        self._s_ai_model = self._set_input(get_setting("ai_model", "") or "", "es. gpt-4o-mini")
        lay.addWidget(self._set_row("Modello chat", "Nome del modello sull'endpoint.", self._s_ai_model))
        self._s_ai_inline = ToggleSwitch((get_setting("ai_inline_rag", "1") or "1") == "1")
        lay.addWidget(self._set_row("Cita i ricordi (RAG)", "L'assistente allega schermate/audio pertinenti alle risposte.", self._s_ai_inline))
        lay.addStretch()
        return w

    def _build_set_security(self, get_setting):
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Sicurezza", first=True))
        try:
            from modules import applock
            lock_on = applock.lock_enabled()
        except Exception:
            lock_on = False
        self._s_lock_enabled = ToggleSwitch(lock_on)
        lay.addWidget(self._set_row("Blocco app (Windows Hello)", "Richiede sblocco all'apertura e per dati sensibili.", self._s_lock_enabled))
        self._s_lock_relock = QComboBox()
        self._s_lock_relock.addItem("Ogni accesso", "every_access")
        self._s_lock_relock.addItem("Una volta per sessione", "once")
        cur = get_setting("lock_relock", "every_access") or "every_access"
        self._s_lock_relock.setCurrentIndex(max(0, self._s_lock_relock.findData(cur)))
        self._s_lock_relock.setFixedHeight(32); self._s_lock_relock.setMinimumWidth(190)
        self._s_lock_relock.setStyleSheet(
            f"QComboBox{{background:rgba(255,255,255,0.04); color:{theme.INK}; border:1px solid {theme.LINE};"
            f" border-radius:8px; padding:0 10px; font-size:12px;}}")
        lay.addWidget(self._set_row("Ri-blocco", "Quando richiedere di nuovo lo sblocco.", self._s_lock_relock))
        lay.addStretch()
        return w

    def _build_set_advanced(self, get_setting):
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Avanzate", first=True))
        hint = QLabel("Modelli AI (download), Vision/Ask-Screen, lingua interfaccia e "
                      "manutenzione restano nella finestra avanzata.")
        hint.setWordWrap(True); hint.setStyleSheet(f"color:{theme.INK_DIM}; font-size:12px;")
        lay.addWidget(hint)
        btn = QPushButton("Apri impostazioni avanzate…"); btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton{{background:rgba(167,139,250,0.14); color:{theme.VIOLET}; border:1px solid rgba(167,139,250,0.30);"
            f" border-radius:8px; padding:0 16px; font-family:'{theme.SANS}'; font-size:12px; font-weight:600;}}"
            "QPushButton:hover{background:rgba(167,139,250,0.24);}")
        btn.clicked.connect(lambda: self._open_settings("models"))
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addStretch()
        return w

    def _save_settings(self):
        from db import save_setting
        import config as _cfg
        errs = 0
        # Cattura
        try:
            save_setting("capture_screenshots_enabled", "1" if self._s_cap_screens.isChecked() else "0")
            save_setting("capture_audio_enabled", "1" if self._s_cap_audio.isChecked() else "0")
            raw = self._s_interval.text().strip()
            if raw:
                dv = getattr(_cfg, "CAPTURE_INTERVAL", None)
                try:
                    val = type(dv)(raw) if dv is not None else raw
                    save_setting("capture_interval", val); setattr(_cfg, "CAPTURE_INTERVAL", val)
                except (ValueError, TypeError):
                    pass
            try:
                from modules.audio import request_restart; request_restart()
            except Exception:
                pass
        except Exception as e:
            errs += 1; print(f"[Set] cattura: {e}")
        # Privacy
        try:
            save_setting("privacy_redact", "1" if self._s_redact.isChecked() else "0")
            save_setting("privacy_idle_min", str(self._s_idle.value()))
            save_setting("privacy_blocklist", self._s_blocklist.text().strip())
        except Exception as e:
            errs += 1; print(f"[Set] privacy: {e}")
        # Estensione browser
        try:
            from modules import web_bridge as _wb
            _wb.set_enabled(self._s_web_enabled.isChecked())
            _wb.set_excluded_domains(self._s_web_excluded.text().strip())
        except Exception as e:
            errs += 1; print(f"[Set] web: {e}")
        # AI
        try:
            from modules.secrets import protect_secret as _protect
            k = self._s_ai_key.text().strip()
            if k:
                save_setting("ai_api_key", _protect(k))
            save_setting("ai_base_url", self._s_ai_url.text().strip())
            save_setting("ai_model", self._s_ai_model.text().strip())
            save_setting("ai_inline_rag", "1" if self._s_ai_inline.isChecked() else "0")
        except Exception as e:
            errs += 1; print(f"[Set] ai: {e}")
        # Sicurezza
        try:
            from modules import applock
            applock.set_lock_enabled(self._s_lock_enabled.isChecked())
            save_setting("lock_relock", self._s_lock_relock.currentData())
        except Exception as e:
            errs += 1; print(f"[Set] sicurezza: {e}")
        self.toast("Impostazioni salvate" if not errs else f"Salvate con {errs} errori (vedi log)",
                   level=("ok" if not errs else "error"))

    # ── Chat / Assistente (orchestrazione portata da window.py) ─────
    def _load_chat_from_db(self):
        try:
            history = ai_assistant.load_chat_history()
        except Exception as e:
            print(f"[Chat] load fail: {e}"); history = []
        self.chat_page.clear_messages(); self._chat_history = []
        for m in history:
            role, content = m["role"], m["content"]
            if role == "user":
                self.chat_page.add_user(content)
            elif role == "assistant":
                container, lbl = self.chat_page.add_assistant("")
                self._finalize_bubble(container, lbl, content)
            self._chat_history.append({"role": role, "content": content})
        if not ai_assistant.is_configured():
            self.chat_page.add_notice("Configura una API key in Impostazioni → AI per usare l'Assistente.")

    def _reset_chat(self):
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return
        try: ai_assistant.clear_chat_history()
        except Exception as e: print(f"[Chat] clear fail: {e}")
        self._chat_history = []; self._chat_turn_bubbles = []
        self.chat_page.clear_messages()
        if not ai_assistant.is_configured():
            self.chat_page.add_notice("Configura una API key in Impostazioni → AI per usare l'Assistente.")
        else:
            self.chat_page.set_busy(False); self.chat_page.input.setFocus()

    def _send_chat_message(self, text):
        if not text.strip():
            return
        if not ai_assistant.is_configured():
            self.chat_page.add_error("API key mancante. Apri Impostazioni → AI.")
            return
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return
        self.chat_page.add_user(text)
        _, lbl = self.chat_page.add_thinking()
        self._chat_thinking = lbl
        self._chat_current_bubble = None; self._chat_current_text = ""
        self._chat_turn_bubbles = []
        self.chat_page.set_busy(True)
        try: ai_assistant.save_chat_message("user", text)
        except Exception as e: print(f"[Chat] save user fail: {e}")
        self._chat_worker = ChatWorker(self._chat_history, text)
        self._chat_worker.chunk.connect(self._on_chat_chunk)
        self._chat_worker.finished_streaming.connect(lambda u=text: self._on_chat_done(u))
        self._chat_worker.start()

    def _remove_thinking(self):
        if self._chat_thinking is None:
            return
        try:
            parent = self._chat_thinking.parentWidget()
            if parent is not None:
                self.chat_page.msg_layout.removeWidget(parent); parent.deleteLater()
        except Exception:
            pass
        self._chat_thinking = None

    def _on_chat_chunk(self, kind, content):
        if kind == "text":
            self._remove_thinking()
            if self._chat_current_bubble is None:
                container, lbl = self.chat_page.add_assistant("")
                self._chat_current_bubble = lbl; self._chat_current_container = container
                self._chat_current_text = ""
                self._chat_turn_bubbles.append({"container": container, "label": lbl, "text": ""})
            self._chat_current_text += content
            self._chat_current_bubble.setText(self._chat_current_text)
            if self._chat_turn_bubbles:
                self._chat_turn_bubbles[-1]["text"] = self._chat_current_text
        elif kind == "tool":
            self._remove_thinking()
            if self._chat_current_container is not None and self._chat_current_text:
                self._finalize_bubble(self._chat_current_container, self._chat_current_bubble, self._chat_current_text)
            self._chat_current_bubble = None; self._chat_current_container = None; self._chat_current_text = ""
            self.chat_page.add_tool(content)
            _, lbl = self.chat_page.add_thinking(); self._chat_thinking = lbl
        elif kind == "error":
            self._remove_thinking(); self.chat_page.add_error(content)
            self._chat_current_bubble = None; self._chat_current_container = None; self._chat_current_text = ""

    def _on_chat_done(self, user_msg):
        self._remove_thinking()
        for b in self._chat_turn_bubbles:
            if b["text"]:
                self._finalize_bubble(b["container"], b["label"], b["text"])
        full_assistant = "\n\n".join(b["text"] for b in self._chat_turn_bubbles if b["text"])
        self._chat_history.append({"role": "user", "content": user_msg})
        if full_assistant:
            self._chat_history.append({"role": "assistant", "content": full_assistant})
            try: ai_assistant.save_chat_message("assistant", full_assistant)
            except Exception as e: print(f"[Chat] save assistant fail: {e}")
        self._chat_current_bubble = None; self._chat_current_container = None; self._chat_current_text = ""
        self._chat_turn_bubbles = []
        self.chat_page.set_busy(False); self.chat_page.input.setFocus()

    def _split_text_refs(self, raw_text):
        segs = []; pos = 0
        for m in _REF_RE.finditer(raw_text or ""):
            if m.start() > pos:
                piece = (raw_text[pos:m.start()] or "").strip()
                if piece: segs.append(("text", piece))
            segs.append(("card", (m.group(1), int(m.group(2)))))
            pos = m.end()
        if pos < len(raw_text or ""):
            rest = (raw_text[pos:] or "").strip()
            if rest: segs.append(("text", rest))
        if not segs and (raw_text or "").strip():
            segs.append(("text", raw_text.strip()))
        return segs

    def _finalize_bubble(self, container, label, raw_text):
        try:
            insert_idx = self.chat_page.msg_layout.indexOf(container)
        except Exception:
            insert_idx = -1
        if insert_idx < 0:
            clean = _strip_refs(raw_text)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setText(_md_to_html(clean) if clean else " ")
            return
        self.chat_page.msg_layout.removeWidget(container)
        container.setParent(None); container.deleteLater()
        turn = AssistantTurnBubble()
        for seg_type, payload in self._split_text_refs(raw_text):
            if seg_type == "text":
                turn.add_text(_md_to_html(payload))
            else:
                kind, rid = payload
                try:
                    card = self._make_embed_card(kind, rid)
                except Exception as e:
                    print(f"[Chat] embed card fail [{kind}:{rid}]: {e}"); continue
                if card is not None:
                    turn.add_card(card)
        self.chat_page.msg_layout.insertWidget(insert_idx, turn)

    def _make_embed_card(self, kind, rid):
        if kind == "ss":
            card = EmbedScreenshotCard(rid); card.clicked.connect(self._on_embed_ss_click); return card
        if kind == "au":
            card = EmbedAudioCard(rid); card.play_requested.connect(self._on_embed_audio_play); return card
        return None

    def _on_embed_ss_click(self, sid):
        try:
            from db import get_conn
            conn = get_conn()
            row = conn.cursor().execute("SELECT image, ts, app FROM screenshots WHERE id=?", (sid,)).fetchone()
            conn.close()
        except Exception as e:
            print(f"[Chat] embed ss click fail: {e}"); return
        if not row or not row[0]:
            return
        px = QPixmap(); px.loadFromData(row[0])
        ts = (row[1] or "")[:19].replace("T", " ")
        FullscreenViewer(px, f"{row[2] or '?'}   •   {ts}", self).exec()

    def _on_embed_audio_play(self, aid):
        import sounddevice as sd
        if self._chat_audio_playing is not None:
            prev_card, prev_aid = self._chat_audio_playing
            try: sd.stop()
            except Exception: pass
            try: prev_card.set_playing(False)
            except Exception: pass
            self._chat_audio_playing = None
            if prev_aid == aid:
                return
        try:
            from db import get_conn
            conn = get_conn()
            row = conn.cursor().execute("SELECT audio_data, audio_format FROM audio_segments WHERE id=?", (aid,)).fetchone()
            conn.close()
        except Exception as e:
            print(f"[Chat] embed audio fetch fail: {e}"); return
        if not row or not row[0]:
            return
        try:
            data = decode_audio(row[0], row[1] or "f32")
            sd.play(data, samplerate=16000)
        except Exception as e:
            print(f"[Chat] embed audio play fail: {e}")

    # ── Caricamento dati reali ──────────────────────────────────────
    def _load(self):
        """Avvia il caricamento della cronologia in background (no freeze UI)."""
        self._day_label.setText("Caricamento cronologia…")
        self._worker = TimelineWorker(limit=3000, offset=0)
        self._worker.done.connect(self._on_data)
        self._worker.start()

    def _on_data(self, records):
        self._records = records or []
        self._build_rows()
        n = len(self._records)
        self._day_label.setText(
            f"Cronologia   ·   {n:,} ricord{'o' if n == 1 else 'i'}".replace(",", ".")
            if n else "Nessun ricordo ancora"
        )
        n_shot = sum(1 for r in self._records if r.get("type") == "screenshot")
        self._archive_lbl.setText(f"{n_shot:,} schermate".replace(",", "."))
        # seleziona il primo evento (salta gli header) e carica le sue thumb
        for i in range(self.timeline.count()):
            it = self.timeline.item(i)
            if it and not it.data(TL_HOUR):
                self.timeline.setCurrentRow(i); break
        QTimer.singleShot(0, lambda: self._ensure_visible_thumbs(self.timeline))

    @staticmethod
    def _kind_of(r):
        t = r.get("type")
        return {"audio": "audio", "web": "note"}.get(t, "screen")

    @staticmethod
    def _clock(ts_iso):
        try:
            ts = datetime.fromisoformat(ts_iso)
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone().strftime("%H:%M")
        except Exception:
            return ""

    @staticmethod
    def _hour_header(ts_iso):
        """Etichetta header di gruppo (cambia per ogni ora/giorno)."""
        try:
            ts = datetime.fromisoformat(ts_iso)
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
            local = ts.astimezone()
        except Exception:
            return ("?", "?")
        days_ago = (datetime.now().date() - local.date()).days
        hour = local.strftime("%H:00")
        if days_ago == 0:   pref = ""
        elif days_ago == 1: pref = "ieri · "
        else:               pref = local.strftime("%d/%m · ")
        key = f"{local.date().isoformat()}|{local.hour}"
        return (key, f"{pref}{hour}")

    @staticmethod
    def _clean(s):
        """Toglie glyph non stampabili (tofu □) e spazi multipli dai titoli."""
        s = "".join(ch for ch in (s or "") if ch.isprintable())
        return " ".join(s.split()).strip()

    def _row_text(self, r, kind):
        if kind == "audio":
            tr = self._clean(r.get("transcript"))
            title = (tr[:48] + "…") if len(tr) > 48 else (tr or "Registrazione vocale")
            return title, ("registrazione · trascritta" if tr else "registrazione")
        if kind == "note":
            return (self._clean(r.get("title")) or self._clean(r.get("domain")) or "Pagina web"), \
                   (self._clean(r.get("domain")))
        return (self._clean(r.get("app")) or "Schermata"), ""  # screen: niente OCR (rumore)

    def _build_rows(self):
        self.timeline.blockSignals(True)
        self.timeline.clear()
        flt = getattr(self, "_tl_filter", "all")
        last_key = None
        for idx, r in enumerate(self._records):
            if flt != "all" and r.get("type") != flt:
                continue
            hkey, hlabel = self._hour_header(r.get("ts", ""))
            if hkey != last_key:
                hdr = QListWidgetItem(); hdr.setData(TL_HOUR, hlabel)
                hdr.setFlags(hdr.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.timeline.addItem(hdr)
                last_key = hkey
            kind = self._kind_of(r)
            title, sub = self._row_text(r, kind)
            it = QListWidgetItem()
            it.setData(TL_TITLE, title); it.setData(TL_SUB, sub)
            it.setData(TL_TIME, self._clock(r.get("ts", "")))
            it.setData(TL_KIND, kind); it.setData(TL_HUE, HUE.get(kind, theme.VIOLET_RGB))
            it.setData(TL_ID, r.get("id")); it.setData(TL_IDX, idx)
            self.timeline.addItem(it)
        self.timeline.blockSignals(False)

    def _ensure_visible_thumbs(self, lw=None):
        """Carica le miniature SOLO per le righe screenshot visibili, con UNA sola
        connessione DB (lezione da window.py: l'archivio ha migliaia di item)."""
        try:
            lw = lw if lw is not None else self.timeline
            n = lw.count()
            if n == 0:
                return
            vph = lw.viewport().rect().height()
            top_it = lw.itemAt(4, 4); bot_it = lw.itemAt(4, max(4, vph - 4))
            start = lw.row(top_it) if top_it is not None else 0
            end = lw.row(bot_it) if bot_it is not None else n - 1
            start = max(0, start - 2); end = min(n - 1, end + 3)
            need = []
            for i in range(start, end + 1):
                it = lw.item(i)
                if it is None or it.data(TL_HOUR):
                    continue
                if it.data(TL_KIND) != "screen" or it.data(TL_THUMB) is not None:
                    continue
                sid = it.data(TL_ID)
                if sid is not None:
                    need.append((it, sid))
            if not need:
                return
            from db import get_conn
            conn = get_conn()
            try:
                cur = conn.cursor()
                for it, sid in need:
                    if sid in _THUMB_CACHE:
                        pm = _THUMB_CACHE[sid]
                    else:
                        row = cur.execute("SELECT image FROM screenshots WHERE id=?", (sid,)).fetchone()
                        pm = _decode_thumb(row[0]) if row and row[0] else None
                        if len(_THUMB_CACHE) > 1500:
                            _THUMB_CACHE.clear()
                        _THUMB_CACHE[sid] = pm
                    it.setData(TL_THUMB, pm if pm is not None else False)
            finally:
                conn.close()
            lw.viewport().update()
        except Exception:
            pass

    def _make_pick_handler(self, list_getter, records_attr):
        """Handler currentRowChanged riusabile (timeline + cerca): legge la riga
        della lista e popola il detail dal record corrispondente."""
        def handler(row):
            lw = list_getter()
            it = lw.item(row)
            if not it or it.data(TL_HOUR):
                return
            idx = it.data(TL_IDX)
            recs = getattr(self, records_attr, [])
            r = recs[idx] if (idx is not None and idx < len(recs)) else {}
            self._populate_detail(r, it.data(TL_KIND), it.data(TL_TITLE), it.data(TL_ID))
        return handler

    def _populate_detail(self, r, kind, title, sid):
        # ferma audio precedente e azzera player
        if self._is_playing:
            self._stop_audio()
        self._reset_audio_player()

        self._cur_record = r; self._cur_kind = kind; self._cur_sid = sid

        # fade morbido del contenuto detail a ogni selezione
        self._fade_in(self._body_scroll)

        # elide su singola riga (il margine destro dell'header è riservato ai controlli finestra)
        fm = QFontMetrics(self._detail_title.font())
        self._detail_title.setText(fm.elidedText(title or "—", Qt.TextElideMode.ElideRight, 170))
        kindlbl = {"screen": "Schermo", "audio": "Registrazione vocale",
                   "note": "Pagina web"}.get(kind, "")
        when = self._detail_when(r.get("ts", ""))
        sub = f"{kindlbl} · {when}".strip(" ·").upper()
        fms = QFontMetrics(self._detail_sub.font())
        self._detail_sub.setText(fms.elidedText(sub, Qt.TextElideMode.ElideRight, 170))

        # badge colorato per tipo
        hue = {"screen": theme.EMERALD_RGB, "audio": theme.AMBER_RGB,
               "note": theme.VIOLET_RGB}.get(kind, theme.VIOLET_RGB)
        ic = {"screen": "screen", "audio": "audio", "note": "web"}.get(kind, "screen")
        hx = "#%02x%02x%02x" % hue
        self._detail_badge.setStyleSheet(
            f"background:rgba({hue[0]},{hue[1]},{hue[2]},0.14);"
            f" border:1px solid rgba({hue[0]},{hue[1]},{hue[2]},0.32); border-radius:8px;")
        self._detail_badge.setPixmap(_svg_pixmap(ic, hx, 16))

        # azioni per tipo
        self._act_open.setVisible(kind == "screen")
        self._act_link.setVisible(kind == "note")
        self._act_star.setVisible(kind in ("screen", "audio"))

        self._current_type = kind; self._current_pixmap = None; self._current_audio = None

        if kind == "audio":
            self._show_detail_sections(shot=False, body=True, audio=True)
            transcript = (r.get("transcript") or "").strip()
            self._detail_body.setTextFormat(Qt.TextFormat.PlainText)
            self._detail_body.setText(transcript or "(nessuna trascrizione)")
            self._load_audio(sid, r)
        elif kind == "note":
            self._show_detail_sections(shot=False, body=True, audio=False)
            import html as _html
            url = r.get("url") or ""; ttl = r.get("title") or url; text = r.get("text") or ""
            self._detail_body.setTextFormat(Qt.TextFormat.RichText)
            self._detail_body.setText(
                f"<b style='color:{theme.INK}'>{_html.escape(ttl)}</b><br>"
                f"<a href='{_html.escape(url)}' style='color:{theme.VIOLET}'>{_html.escape(url)}</a>"
                f"<br><br><span style='color:#cfcfd6'>{_html.escape(text)}</span>")
        else:  # screen — preview grande, NIENTE OCR (rumore)
            self._show_detail_sections(shot=True, body=False, audio=False)
            self._load_screenshot(sid)

        self._fill_context_chips(r)

    def _fill_context_chips(self, r):
        """Chip 'intorno a questo momento': tipi di ricordo entro ±5 min dal corrente."""
        # svuota (tieni lo stretch finale)
        while self._ctx_chips_l.count() > 1:
            it = self._ctx_chips_l.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        ts0 = r.get("ts", "")
        try:
            t0 = datetime.fromisoformat(ts0)
            if t0.tzinfo is None: t0 = t0.replace(tzinfo=timezone.utc)
        except Exception:
            self._ctx_wrap.setVisible(False); return
        seen = {}
        for o in self._records:
            if o is r:
                continue
            try:
                t1 = datetime.fromisoformat(o.get("ts", ""))
                if t1.tzinfo is None: t1 = t1.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if abs((t1 - t0).total_seconds()) <= 300:
                k = self._kind_of(o)
                seen[k] = seen.get(k, 0) + 1
        names = {"screen": ("schermo", theme.EMERALD_RGB), "audio": ("audio", theme.AMBER_RGB),
                 "note": ("web", theme.VIOLET_RGB)}
        if not seen:
            self._ctx_wrap.setVisible(False); return
        self._ctx_wrap.setVisible(True)
        for k, n in seen.items():
            label, hue = names.get(k, (k, theme.VIOLET_RGB))
            self._ctx_chips_l.insertWidget(self._ctx_chips_l.count() - 1,
                                           self._chip(f"{label} · {n}", hue))

    # ── Azioni detail ───────────────────────────────────────────────
    def _act_btn(self, label, icon, primary=False):
        icon_only = not label
        b = QPushButton(("  " + label) if label else ""); b.setFixedHeight(34)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setIcon(QIcon(_svg_pixmap(icon, theme.INK if primary else theme.INK_SOFT, 15)))
        if icon_only:
            b.setFixedWidth(34)
        pad = "0" if icon_only else "0 13px"
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:rgba(167,139,250,0.16); color:{theme.INK};"
                f" border:1px solid rgba(167,139,250,0.40); border-radius:9px; padding:{pad};"
                f" font-family:'{theme.SANS}'; font-size:12px; font-weight:600; text-align:center;}}"
                "QPushButton:hover{background:rgba(167,139,250,0.26);}")
        else:
            b.setStyleSheet(
                f"QPushButton{{background:rgba(255,255,255,0.04); color:{theme.INK_SOFT};"
                f" border:1px solid {theme.LINE}; border-radius:9px; padding:{pad};"
                f" font-family:'{theme.SANS}'; font-size:12px; font-weight:500; text-align:center;}}"
                f"QPushButton:hover{{background:rgba(255,255,255,0.08); color:{theme.INK};}}")
        return b

    def _detail_ask_ai(self):
        """Apre l'Assistente con una domanda precompilata sul ricordo corrente."""
        self._switch_page("assistant")
        try:
            t = self._detail_title.text()
            self.chat_page.input.setText(f"Parlami di questo ricordo: «{t}»")
            self.chat_page.input.setFocus()
        except Exception:
            pass

    def _detail_pin(self):
        """Pin/unpin del ricordo (★) via db.set_pinned."""
        r = getattr(self, "_cur_record", {}) or {}
        kind = getattr(self, "_cur_kind", "")
        sid = getattr(self, "_cur_sid", None)
        if sid is None or kind not in ("screen", "audio"):
            self.toast("Solo schermate e audio si possono fissare", level="info", duration_ms=1800); return
        try:
            from db import set_pinned
            new = not bool(r.get("pinned"))
            set_pinned("ss" if kind == "screen" else "au", sid, new)
            r["pinned"] = new
            self.toast("Fissato ★" if new else "Rimosso dai fissati", level="ok", duration_ms=1500)
        except Exception as e:
            self.toast(f"Pin non riuscito: {e}", level="error")

    @staticmethod
    def _chip(text, hue):
        c = QLabel(); c.setFixedHeight(24); c.setTextFormat(Qt.TextFormat.RichText)
        hx = "#%02x%02x%02x" % hue
        c.setText(f"<span style='color:{hx}; font-size:13px'>●</span>&nbsp; "
                  f"<span style='color:{theme.INK_SOFT}; font-size:11px'>{text}</span>")
        c.setStyleSheet(
            f"QLabel{{background:rgba(255,255,255,0.03); border:1px solid {theme.LINE};"
            f" border-radius:12px; padding:0 11px;}}")
        return c

    def _detail_open(self):
        if self._current_pixmap is not None and not self._current_pixmap.isNull():
            FullscreenViewer(self._current_pixmap, self._detail_sub.text(), self).exec()
        elif getattr(self, "_cur_sid", None) is not None:
            self._on_embed_ss_click(self._cur_sid)

    def _detail_open_link(self):
        url = (getattr(self, "_cur_record", {}) or {}).get("url")
        if url:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))

    def _detail_copy(self):
        r = getattr(self, "_cur_record", {}) or {}
        kind = getattr(self, "_cur_kind", "")
        when = self._detail_when(r.get("ts", ""))
        if kind == "audio":
            body = (r.get("transcript") or "").strip()
        elif kind == "note":
            body = r.get("url") or ""
        else:
            body = r.get("app") or ""
        text = f"{self._detail_title.text()}  ·  {when}\n{body}".strip()
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self.toast("Copiato", level="ok", duration_ms=1500)
        except Exception:
            pass

    def _show_detail_sections(self, shot, body, audio):
        self._shot_label.setVisible(shot)
        self._detail_body.setVisible(body)
        self._audio_bar.setVisible(audio)

    def _load_screenshot(self, sid):
        self._shot_label.clear()
        if sid is None:
            return
        try:
            from db import get_conn
            conn = get_conn()
            try:
                row = conn.cursor().execute(
                    "SELECT image FROM screenshots WHERE id=?", (sid,)).fetchone()
            finally:
                conn.close()
        except Exception:
            row = None
        if row and row[0]:
            px = QPixmap(); px.loadFromData(row[0])
            self._current_pixmap = px
            target_w = max(220, self.detail.width() - 36)
            scaled = px.scaled(target_w, 1200, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._shot_label.setPixmap(_rounded_pixmap(scaled, 12))
        else:
            self._shot_label.setText("Immagine non disponibile")
            self._shot_label.setStyleSheet(f"color:{theme.INK_FAINT}; font-size:12px;")

    def _load_audio(self, sid, r):
        """Recupera il blob audio on-demand, decodifica e arma il player."""
        blob, fmt = r.get("audio_data"), r.get("audio_format", "f32")
        if blob is None and sid is not None:
            try:
                from modules import search as search_module
                blob, fmt = search_module.get_audio_blob(sid)
            except Exception:
                blob = None
        self._current_audio = (blob, fmt)
        if not blob:
            self.play_btn.setEnabled(False)
            return
        self.play_btn.setEnabled(True)
        try:
            decoded = decode_audio(blob, fmt)
            self._audio_data = decoded
            total = len(decoded)
            self.audio_slider.blockSignals(True)
            self.audio_slider.setMaximum(max(1, total)); self.audio_slider.setValue(0)
            self.audio_slider.blockSignals(False)
            self.audio_time_cur.setText("0:00")
            self.audio_time_total.setText(_fmt_time(total / 16000))
            self.waveform.set_audio(decoded); self.waveform.set_progress(0.0)
        except Exception:
            self.play_btn.setEnabled(False)

    # ── Player audio (portato da window.py) ─────────────────────────
    def _reset_audio_player(self):
        self._playback_timer.stop(); self._is_playing = False
        self._audio_data = None; self._audio_offset = 0; self._playback_start = None
        self.audio_slider.blockSignals(True)
        self.audio_slider.setMaximum(100); self.audio_slider.setValue(0)
        self.audio_slider.blockSignals(False)
        self.audio_time_cur.setText("0:00"); self.audio_time_total.setText("0:00")
        self.waveform.clear()
        self.play_btn.setText("▶  Ascolta")

    def _play_audio(self):
        if self._audio_data is None:
            if not self._current_audio or not self._current_audio[0]:
                return
            blob, fmt = self._current_audio
            self._audio_data = decode_audio(blob, fmt)
            total = len(self._audio_data)
            self.audio_slider.blockSignals(True)
            self.audio_slider.setMaximum(max(1, total)); self.audio_slider.setValue(0)
            self.audio_slider.blockSignals(False)
            self.audio_time_total.setText(_fmt_time(total / 16000))
        self._play_from(self.audio_slider.value())

    def _play_from(self, offset_samples):
        import sounddevice as sd
        self._audio_offset = offset_samples
        self._playback_start = _time.time()
        self._is_playing = True
        sd.play(self._audio_data[offset_samples:], samplerate=16000)
        self._playback_timer.start()
        self.play_btn.setText("◼  Ferma")
        try: self.play_btn.clicked.disconnect()
        except Exception: pass
        self.play_btn.clicked.connect(self._stop_audio)

    def _stop_audio(self):
        import sounddevice as sd
        self._playback_timer.stop(); self._is_playing = False
        try: sd.stop()
        except Exception: pass
        self.play_btn.setText("▶  Ascolta")
        try: self.play_btn.clicked.disconnect()
        except Exception: pass
        self.play_btn.clicked.connect(self._play_audio)

    def _update_slider(self):
        if not self._is_playing or self._playback_start is None or self._audio_data is None:
            return
        elapsed = _time.time() - self._playback_start
        current_sample = self._audio_offset + int(elapsed * 16000)
        total = len(self._audio_data)
        if current_sample >= total:
            self._on_playback_finished(); return
        self.audio_slider.blockSignals(True)
        self.audio_slider.setValue(current_sample)
        self.audio_slider.blockSignals(False)
        self.audio_time_cur.setText(_fmt_time(current_sample / 16000))
        if total > 0: self.waveform.set_progress(current_sample / total)

    def _on_playback_finished(self):
        self._playback_timer.stop(); self._is_playing = False
        self.play_btn.setText("▶  Ascolta")
        try: self.play_btn.clicked.disconnect()
        except Exception: pass
        self.play_btn.clicked.connect(self._play_audio)
        self.audio_slider.blockSignals(True); self.audio_slider.setValue(0); self.audio_slider.blockSignals(False)
        self.audio_time_cur.setText("0:00"); self.waveform.set_progress(0.0)

    def _on_slider_pressed(self):
        self._playback_timer.stop()

    def _on_slider_moved(self, value):
        if self._audio_data is not None:
            self.audio_time_cur.setText(_fmt_time(value / 16000))

    def _on_slider_released(self):
        import sounddevice as sd
        if self._audio_data is None:
            return
        new_offset = self.audio_slider.value()
        sd.stop()
        self._play_from(new_offset)

    @staticmethod
    def _detail_when(ts_iso):
        try:
            ts = datetime.fromisoformat(ts_iso)
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone().strftime("%d/%m/%Y %H:%M")
        except Exception:
            return ""

    # ── Compat tray/hotkey ──────────────────────────────────────────
    def toggle(self):
        """Mostra/porta in primo piano (chiamato da hotkey Ctrl+Shift+D)."""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal(); self.raise_(); self.activateWindow()

    def hideEvent(self, e):
        if self._is_playing:
            self._stop_audio()
        super().hideEvent(e)

    def closeEvent(self, e):
        """X = torna nel tray (non chiude l'app). Quit vero dal menu tray.
        `setQuitOnLastWindowClosed(False)` in main.py tiene viva l'app."""
        e.ignore()
        self.hide()  # hideEvent ferma l'audio

    def toast(self, msg, level="info", duration_ms=3000):
        """Notifica transitoria in basso al centro (compat con DejaTray)."""
        try:
            color = {"ok": theme.EMERALD, "error": "#ef4444",
                     "info": theme.INK}.get(level, theme.INK)
            lbl = getattr(self, "_toast_lbl", None)
            if lbl is None:
                lbl = QLabel(self); self._toast_lbl = lbl
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"background:#1b1b21; color:{color}; border:1px solid {theme.LINE};"
                f" border-radius:10px; padding:10px 18px; font-family:'{theme.SANS}';"
                f" font-size:12px; font-weight:500;")
            lbl.setText(msg); lbl.adjustSize()
            lbl.move((self.width() - lbl.width()) // 2, self.height() - lbl.height() - 28)
            lbl.show(); lbl.raise_()
            t = getattr(self, "_toast_timer", None)
            if t is None:
                t = QTimer(self); t.setSingleShot(True)
                t.timeout.connect(lambda: self._toast_lbl.hide())
                self._toast_timer = t
            t.start(int(duration_ms))
        except Exception:
            print(f"[toast:{level}] {msg}")
