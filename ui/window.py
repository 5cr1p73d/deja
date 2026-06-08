# ui/window.py
import time as _time
import re as _re
import html as _html
import numpy as np
from datetime import datetime, timezone, timedelta
from modules.audio import decode_audio

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QScrollArea, QDialog,
    QApplication, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QStackedWidget,
    QStyledItemDelegate, QStyle, QSlider,
    QTabWidget, QTextEdit, QFrame, QSizePolicy, QSpinBox, QComboBox
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve,
    QRect, QRectF, QTimer, QSize, QPointF
)
from PyQt6.QtGui import (
    QFont, QFontMetrics, QPixmap, QColor, QPainter, QPainterPath, QBrush,
    QRegion, QPen, QLinearGradient, QRadialGradient, QKeyEvent, QIcon, QPolygonF
)

from ui import theme
from ui.theme import INK, INK_SOFT, INK_DIM, INK_FAINT, EMERALD
from db import get_conn
from modules import search as search_module
from modules import ai_assistant
import i18n
from i18n import t
from modules.secrets import protect_secret as _protect
from modules import applock
from ui.framed import FramelessDialog, confirm as _confirm
try:
    import config as _cfg
except Exception:
    _cfg = None

# ── Font UI ────────────────────────────────────────────────────────
# Risolto a runtime sul font più elegante disponibile (resolve_ui_font),
# poi usato da tutti i QFont(UI_FONT, ...) e applicato all'app.
UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"


def resolve_ui_font(app=None):
    """Carica i font del design system (Geist + Geist Mono) e li applica all'app.
    Da chiamare dopo aver creato QApplication, prima di costruire la UI.

    Delega a ui.theme.load_fonts (single source of truth) e ne riflette il
    risultato in UI_FONT/MONO_FONT, usati dai QFont(UI_FONT, ...) sparsi qui."""
    global UI_FONT, MONO_FONT
    try:
        from ui import theme
        UI_FONT, MONO_FONT = theme.load_fonts(app)
    except Exception:
        # Fallback: vecchia euristica su font di sistema.
        try:
            from PyQt6.QtGui import QFontDatabase
            fams = set(QFontDatabase.families())
            for cand in ("Segoe UI Variable Text", "Segoe UI", "Selawik", "Arial"):
                if cand in fams:
                    UI_FONT = cand
                    break
            if app is not None:
                f = app.font(); f.setFamily(UI_FONT); app.setFont(f)
        except Exception:
            pass
    return UI_FONT


# ── Palette & Dimensioni ──────────────────────────────────────────
OVERLAY_W = 960
OVERLAY_H_COMPACT = 76
OVERLAY_H_EXPANDED = 720

BG_HEX = "#0e0e12"
TEXT_PRIMARY = "#f3f4f6"
TEXT_SECONDARY = "#8b8d98"
BORDER_STR = "rgba(255, 255, 255, 0.08)"

C_AUDIO_HEX = "#f59e0b"
C_AUDIO_RGB = (245, 158, 11)
C_SS_HEX = "#10b981"
C_SS_RGB = (16, 185, 129)
C_AI_HEX = "#a78bfa"
C_AI_RGB = (167, 139, 250)

# Palette colori per app hashing (avatar/accent automatici)
_APP_PALETTE = [
    (167, 139, 250),   # viola
    (251, 113, 133),   # rosa
    (52, 211, 153),    # verde
    (96, 165, 250),    # blu
    (251, 191, 36),    # ambra
    (244, 114, 182),   # fuchsia
    (94, 234, 212),    # teal
    (248, 113, 113),   # rosso
    (139, 92, 246),    # indaco
    (16, 185, 129),    # smeraldo
]

def _app_color_rgb(name):
    if not name: return (139, 141, 152)
    h = abs(hash(name)) % len(_APP_PALETTE)
    return _APP_PALETTE[h]

def _app_initial(name):
    if not name: return "?"
    s = name.strip()
    # Skippa emoji / leading non-alphanumeric
    for ch in s:
        if ch.isalnum(): return ch.upper()
    return "?"

SS_BTN_AUDIO_ON = (
    f"QPushButton{{background:rgba(245,158,11,0.15); color:{C_AUDIO_HEX}; "
    f"border:1px solid rgba(245,158,11,0.4); border-radius:8px; font-size:12px; font-weight:600; padding:6px 14px;}}"
    "QPushButton:hover{background:rgba(245,158,11,0.25);}"
)
SS_BTN_SS_ON = (
    f"QPushButton{{background:rgba(16,185,129,0.15); color:{C_SS_HEX}; "
    f"border:1px solid rgba(16,185,129,0.4); border-radius:8px; font-size:12px; font-weight:600; padding:6px 14px;}}"
    "QPushButton:hover{background:rgba(16,185,129,0.25);}"
)
SS_BTN_OFF = (
    "QPushButton{background:rgba(255,255,255,0.03); color:#8b8d98; "
    f"border:1px solid {BORDER_STR}; border-radius:8px; font-size:12px; font-weight:600; padding:6px 14px;}}"
    "QPushButton:hover{background:rgba(255,255,255,0.07); color:#ffffff;}"
)
SS_BTN_AI_ON = (
    f"QPushButton{{background:rgba(167,139,250,0.15); color:{C_AI_HEX}; "
    f"border:1px solid rgba(167,139,250,0.4); border-radius:8px; font-size:12px; font-weight:600; padding:6px 14px;}}"
    "QPushButton:hover{background:rgba(167,139,250,0.25);}"
)
SS_BTN_AI_PRIMARY = (
    f"QPushButton{{background:rgba(167,139,250,0.18); color:#ffffff; "
    f"border:1px solid rgba(167,139,250,0.55); border-radius:8px; font-size:12px; font-weight:600; padding:6px 14px;}}"
    "QPushButton:hover{background:rgba(167,139,250,0.32);}"
    "QPushButton:disabled{background:rgba(255,255,255,0.03); color:#5a5d6a; border:1px solid rgba(255,255,255,0.05);}"
)

SS_SLIDER_AUDIO = f"""
    QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(255,255,255,0.08);
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 rgba(245,158,11,0.85), stop:1 {C_AUDIO_HEX});
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        border: 2px solid {C_AUDIO_HEX};
        width: 12px;
        height: 12px;
        margin: -5px 0;
        border-radius: 7px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {C_AUDIO_HEX};
        border: 2px solid #ffffff;
        width: 16px;
        height: 16px;
        margin: -7px 0;
        border-radius: 9px;
    }}
"""

ITEM_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1
ITEM_HEADER_ROLE = Qt.ItemDataRole.UserRole + 2
ITEM_THUMB_ROLE = Qt.ItemDataRole.UserRole + 3   # QPixmap miniatura screenshot

# Cache miniature screenshot per id. Le thumbnail si caricano PIGRAMENTE solo
# per le righe visibili (vedi DejaWindow._ensure_visible_thumbs): in "Esplora"
# la lista può avere migliaia di item — decodificarle tutte freezerebbe la UI.
_THUMB_CACHE = {}            # id -> QPixmap | None (None = nessuna immagine)
_THUMB_PX = 96              # lato sorgente cache (downscale netto nel delegate)


def _decode_thumb(blob):
    """Decodifica un blob immagine in una QPixmap miniatura cover (o None).
    Nessun accesso DB: il chiamante fornisce i byte (batch con 1 sola conn)."""
    try:
        src = QPixmap()
        if blob and src.loadFromData(bytes(blob)) and not src.isNull():
            return src.scaled(_THUMB_PX, _THUMB_PX,
                              Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


def _rounded_pixmap(src, radius=12):
    """Ritorna una copia con angoli arrotondati + hairline (look 'card')."""
    try:
        if src is None or src.isNull():
            return src
        out = QPixmap(src.size()); out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(out.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath(); path.addRoundedRect(rect, radius, radius)
        p.setClipPath(path); p.drawPixmap(0, 0, src)
        p.setClipping(False); p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1.0)); p.drawPath(path)
        p.end()
        return out
    except Exception:
        return src


def _date_bucket_label(ts_iso):
    """Ritorna bucket label e ordinamento (oggi/ieri/settimana/data)."""
    try:
        ts = datetime.fromisoformat(ts_iso)
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return ("?", "")
    local = ts.astimezone()
    today = datetime.now().date()
    d = local.date()
    days_ago = (today - d).days
    if days_ago == 0: return ("oggi", t("win.bkt_today"))
    if days_ago == 1: return ("ieri", t("win.bkt_yesterday"))
    if days_ago < 7:  return (f"d{days_ago}", t("win.bkt_days_ago", n=days_ago))
    if days_ago < 30: return (f"w{days_ago // 7}", t("win.bkt_weeks_ago", n=days_ago // 7))
    # Mese
    return (f"m{local.year}{local.month:02d}",
            f"{i18n.months()[local.month-1].upper()} {local.year}")

OVERLAY_W_FS = 1400        # larghezza fullscreen
OVERLAY_H_FS = 860         # altezza fullscreen
SIDEBAR_W = 220            # sidebar sinistra in fullscreen


def pill(active=False, kind="all"):
    if active:
        if kind == "audio":
            return (f"QPushButton{{background:rgba(245,158,11,0.15); color:{C_AUDIO_HEX}; "
                    f"border:1px solid rgba(245,158,11,0.3); border-radius:12px; font-size:11px; font-weight:600; padding:4px 14px;}}"
                    "QPushButton:hover{background:rgba(245,158,11,0.25);}")
        elif kind == "screenshot":
            return (f"QPushButton{{background:rgba(16,185,129,0.15); color:{C_SS_HEX}; "
                    f"border:1px solid rgba(16,185,129,0.3); border-radius:12px; font-size:11px; font-weight:600; padding:4px 14px;}}"
                    "QPushButton:hover{background:rgba(16,185,129,0.25);}")
        return ("QPushButton{background:rgba(255,255,255,0.12); color:#ffffff; "
                "border:1px solid rgba(255,255,255,0.25); border-radius:12px; font-size:11px; font-weight:600; padding:4px 14px;}"
                "QPushButton:hover{background:rgba(255,255,255,0.18);}")

    return (f"QPushButton{{background:transparent; color:{TEXT_SECONDARY}; "
            f"border:1px solid {BORDER_STR}; border-radius:12px; font-size:11px; font-weight:500; padding:4px 14px;}}"
            "QPushButton:hover{background:rgba(255,255,255,0.06); color:#ffffff;}")

def date_pill(active=False):
    if active:
        return ("QPushButton{background:transparent; color:#ffffff; "
                "border:none; border-bottom:2px solid #ffffff; border-radius:0px; font-size:12px; font-weight:600; padding:0 8px;}")
    return (f"QPushButton{{background:transparent; color:{TEXT_SECONDARY}; "
            "border:none; border-bottom:2px solid transparent; border-radius:0px; font-size:12px; font-weight:500; padding:0 8px;}}"
            "QPushButton:hover{color:#ffffff; border-bottom:2px solid rgba(255,255,255,0.2);}")

def force_style(btn, css):
    btn.setStyleSheet(css); btn.style().unpolish(btn); btn.style().polish(btn); btn.update()


def _fmt_time(secs):
    m, s = divmod(int(max(0, secs)), 60)
    return f"{m}:{s:02d}"

_MONTHS_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
_DAYS_IT = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

def _human_ago(ts_iso):
    """ISO timestamp → string relativo. 'ora', '5 min fa', 'oggi 14:30', 'ieri 09:15', 'lun 12 mag'."""
    try:
        ts = datetime.fromisoformat(ts_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return ts_iso[:16].replace("T", " ")
    now = datetime.now(timezone.utc)
    delta = now - ts
    secs = delta.total_seconds()
    if secs < 0:
        return ts.astimezone().strftime("%H:%M")
    if secs < 60:
        return t("win.rel_now")
    if secs < 3600:
        return t("win.rel_min_ago", n=int(secs // 60))
    local = ts.astimezone()
    today = datetime.now().date()
    d = local.date()
    if d == today:
        return t("win.rel_today_at", time=local.strftime('%H:%M'))
    if (today - d).days == 1:
        return t("win.rel_yesterday_at", time=local.strftime('%H:%M'))
    if (today - d).days < 7:
        return f"{i18n.days()[local.weekday()]} {local.strftime('%H:%M')}"
    return f"{i18n.days()[local.weekday()]} {local.day} {i18n.months()[local.month-1]}"


def _fmt_clock(ts_iso):
    """ISO → 'HH:MM' locale. Per la sotto-riga in Esplora (l'ago relativo
    sarebbe 'ora' identico su tutte le righe → rumore)."""
    try:
        ts = datetime.fromisoformat(ts_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone().strftime("%H:%M")
    except Exception:
        return ts_iso[11:16] if len(ts_iso) >= 16 else ts_iso


def _fmt_when(ts_iso):
    """ISO → 'oggi · 21:46' / 'ieri · 21:46' / '5 giu · 21:46' (header preview)."""
    try:
        ts = datetime.fromisoformat(ts_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local = ts.astimezone(); hm = local.strftime("%H:%M")
        today = datetime.now().date(); d = local.date()
        if d == today:
            return f"{t('win.sb_today').lower()} · {hm}"
        if (today - d).days == 1:
            return f"{t('win.sb_yesterday').lower()} · {hm}"
        return f"{local.day} {i18n.months()[local.month-1][:3].lower()} · {hm}"
    except Exception:
        return ts_iso[:16].replace("T", " ")


def _highlight_tokens(text, query):
    """HTML-escape + wrap matching tokens in <mark>."""
    import re as __re, html as __html
    if not text:
        return ""
    safe = __html.escape(text)
    if not query:
        return safe
    tokens = [t for t in __re.split(r"[^\w]+", query.lower()) if len(t) >= 2]
    if not tokens:
        return safe
    pattern = "|".join(__re.escape(t) for t in tokens)
    def repl(m):
        return f'<mark style="background:rgba(245,158,11,0.35); color:#fff; padding:0 2px; border-radius:3px;">{m.group(0)}</mark>'
    return __re.sub(f'({pattern})', repl, safe, flags=__re.IGNORECASE)


# ── Ref tag regex ──────────────────────────────────────────────────
_REF_RE = _re.compile(r"\[(ss|au):(\d+)\]")

def _extract_refs(text):
    """Estrae lista [(kind, id)] da testo. Dedup mantenendo ordine."""
    seen = set(); out = []
    for m in _REF_RE.finditer(text or ""):
        key = (m.group(1), int(m.group(2)))
        if key not in seen:
            seen.add(key); out.append(key)
    return out

def _strip_refs(text):
    return _REF_RE.sub("", text or "").replace("  ", " ").strip()


# ── Markdown → HTML (per QLabel rich text) ─────────────────────────
def _md_to_html(text):
    """Mini converter markdown → HTML per le bolle AI."""
    if not text:
        return ""
    s = _html.escape(text)

    # Code blocks (triple backtick) → <pre>
    def _block(m):
        code = m.group(1).strip("\n")
        return (
            '<pre style="background:rgba(0,0,0,0.35); color:#e5e7eb; '
            'padding:8px 10px; border-radius:6px; font-family:Consolas,monospace; '
            f'font-size:10pt;">{code}</pre>'
        )
    s = _re.sub(r'```(?:\w+)?\n?(.*?)```', _block, s, flags=_re.DOTALL)

    # Inline code
    s = _re.sub(
        r'`([^`\n]+)`',
        r'<code style="background:rgba(255,255,255,0.08); padding:1px 5px; '
        r'border-radius:3px; font-family:Consolas,monospace; font-size:10pt;">\1</code>',
        s,
    )

    # Bold **x**
    s = _re.sub(r'\*\*([^*\n]+)\*\*', r'<b>\1</b>', s)
    # Italic *x* (evita doppio asterisco)
    s = _re.sub(r'(?<![\*\w])\*([^*\n]+)\*(?![\*\w])', r'<i>\1</i>', s)

    # Headers
    s = _re.sub(r'^### (.+)$', r'<h4 style="margin:6px 0; color:#f3f4f6;">\1</h4>', s, flags=_re.MULTILINE)
    s = _re.sub(r'^## (.+)$',  r'<h3 style="margin:8px 0; color:#f3f4f6;">\1</h3>',  s, flags=_re.MULTILINE)
    s = _re.sub(r'^# (.+)$',   r'<h2 style="margin:10px 0; color:#f3f4f6;">\1</h2>', s, flags=_re.MULTILINE)

    # Lists — raggruppa righe consecutive
    out_lines = []; in_ul = False
    for line in s.split("\n"):
        m = _re.match(r'^\s*[\-\*] (.+)$', line)
        if m:
            if not in_ul:
                out_lines.append('<ul style="margin:4px 0 4px 18px; padding:0;">'); in_ul = True
            out_lines.append(f'<li>{m.group(1)}</li>')
        else:
            if in_ul: out_lines.append('</ul>'); in_ul = False
            out_lines.append(line)
    if in_ul: out_lines.append('</ul>')
    s = "\n".join(out_lines)

    # Newlines → <br> (evita di rovinare HTML già strutturato)
    s = _re.sub(r'\n(?![<])', '<br>', s)
    return s


# ── Settings Dialog ───────────────────────────────────────────────
# Foglio di stile coeso e sobrio: un solo accento (lavanda), superfici tenui,
# tipografia con gerarchia chiara. Classi via objectName: #section (titoletti),
# #caption (note), #chip (bottoncini preset), #accent (azioni), #save_btn (primario).
SETTINGS_QSS = """
    QDialog { background:transparent; }
    QLabel  { color:#e7e7ec; background:transparent; font-size:12px; }
    QLabel#section {
        color:#9a9aa6; font-size:10px; font-weight:700; letter-spacing:1.6px;
    }
    QLabel#caption { color:#82828e; font-size:11px; }
    QLabel#field   { color:#b9b9c4; font-size:12px; font-weight:600; }

    QLineEdit, QSpinBox, QComboBox {
        background:rgba(255,255,255,0.035); color:#e7e7ec;
        border:1px solid rgba(255,255,255,0.085); border-radius:9px;
        padding:9px 12px; font-size:12px;
        selection-background-color:rgba(167,139,250,0.35); selection-color:#fff;
    }
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {
        border:1px solid rgba(255,255,255,0.16);
    }
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QComboBox:on {
        border:1px solid rgba(167,139,250,0.55); background:rgba(255,255,255,0.06);
    }
    QComboBox::drop-down {
        subcontrol-origin:padding; subcontrol-position:center right;
        width:26px; border:none;
    }
    QComboBox::down-arrow {
        width:0; height:0; margin-right:9px;
        border-left:5px solid transparent; border-right:5px solid transparent;
        border-top:6px solid #9a9aa6;
    }
    QComboBox::down-arrow:on { border-top:none; border-bottom:6px solid #bcabff; }
    QComboBox QAbstractItemView {
        background:#1e1e26; color:#e7e7ec; border:1px solid rgba(255,255,255,0.10);
        border-radius:8px; padding:4px; outline:none;
        selection-background-color:rgba(167,139,250,0.22);
    }

    QSpinBox::up-button, QSpinBox::down-button {
        subcontrol-origin:border; width:20px; border:none; background:transparent;
    }
    QSpinBox::up-button { subcontrol-position:top right; }
    QSpinBox::down-button { subcontrol-position:bottom right; }
    QSpinBox::up-arrow {
        width:0; height:0; border-left:4px solid transparent; border-right:4px solid transparent;
        border-bottom:5px solid #9a9aa6;
    }
    QSpinBox::down-arrow {
        width:0; height:0; border-left:4px solid transparent; border-right:4px solid transparent;
        border-top:5px solid #9a9aa6;
    }
    QSpinBox::up-arrow:hover { border-bottom:5px solid #bcabff; }
    QSpinBox::down-arrow:hover { border-top:5px solid #bcabff; }

    QListWidget#nav {
        background:#131318; border:none; outline:none;
        border-right:1px solid rgba(255,255,255,0.06);
        border-bottom-left-radius:15px;
        padding:12px 8px; font-size:12.5px;
    }
    QListWidget#nav::item {
        color:#9a9aa6; padding:10px 12px; border-radius:8px; margin:2px 4px;
    }
    QListWidget#nav::item:hover { color:#d6d6dd; background:rgba(255,255,255,0.05); }
    QListWidget#nav::item:selected { color:#f4f4f7; background:rgba(167,139,250,0.16); }

    QTabWidget::pane { border:none; background:transparent; }
    QTabBar { qproperty-drawBase:0; }
    QTabBar::tab {
        background:transparent; color:#82828e; padding:11px 22px;
        font-size:12px; font-weight:600; border:none; border-bottom:2px solid transparent;
    }
    QTabBar::tab:hover { color:#c7c7d0; }
    QTabBar::tab:selected { color:#f4f4f7; border-bottom:2px solid #a78bfa; }

    QCheckBox { color:#e7e7ec; background:transparent; spacing:10px; font-size:12px; }
    QCheckBox::indicator {
        width:18px; height:18px; border-radius:5px;
        background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.22);
    }
    QCheckBox::indicator:hover { border:1px solid rgba(167,139,250,0.55); }
    QCheckBox::indicator:checked { background:#a78bfa; border:1px solid #a78bfa; }

    QPushButton {
        background:rgba(255,255,255,0.05); color:#d6d6dd;
        border:1px solid rgba(255,255,255,0.10); border-radius:9px;
        font-size:12px; font-weight:600; padding:9px 20px;
    }
    QPushButton:hover { background:rgba(255,255,255,0.10); color:#fff; }
    QPushButton:disabled { color:#56565f; background:rgba(255,255,255,0.025); }

    QPushButton#chip {
        background:rgba(255,255,255,0.04); color:#a6a6b2;
        border:1px solid rgba(255,255,255,0.09); border-radius:8px;
        font-size:11px; font-weight:600; padding:6px 13px;
    }
    QPushButton#chip:hover { background:rgba(255,255,255,0.09); color:#ededf1; }

    QPushButton#accent {
        background:rgba(167,139,250,0.12); color:#bcabff;
        border:1px solid rgba(167,139,250,0.30); border-radius:9px;
        font-size:11px; font-weight:600; padding:8px 16px;
    }
    QPushButton#accent:hover { background:rgba(167,139,250,0.20); color:#cdbfff; }
    QPushButton#accent:disabled {
        color:#56565f; background:rgba(255,255,255,0.025); border-color:rgba(255,255,255,0.07);
    }

    QPushButton#save_btn {
        background:#a78bfa; color:#1a1430; border:1px solid #a78bfa; font-weight:700;
    }
    QPushButton#save_btn:hover { background:#b9a4ff; border-color:#b9a4ff; }
"""


class ModelDownloadWorker(QThread):
    """Scarica (istanziando) un modello HuggingFace in background."""
    done = pyqtSignal(bool, str)

    def __init__(self, kind, model_id):
        super().__init__()
        self.kind = kind
        self.model_id = model_id

    def run(self):
        try:
            if self.kind == "embed":
                from sentence_transformers import SentenceTransformer
                m = SentenceTransformer(self.model_id); del m
            elif self.kind == "whisper":
                from faster_whisper import WhisperModel
                m = WhisperModel(self.model_id, device="cpu", compute_type="int8"); del m
            self.done.emit(True, "ok")
        except Exception as e:
            self.done.emit(False, str(e))


class _SelHighlight(QWidget):
    """Evidenziatore di selezione animato per la results list (Refined II).

    Vive sopra il viewport della lista: fill traslucido + barra viola a sinistra.
    Scorre da una riga all'altra con QPropertyAnimation invece di saltare —
    il feel "selezione che scivola" di Raycast. Trasparente al mouse: i click
    passano alla lista sotto.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._anim = None

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 3, -6, -3)
        path = QPainterPath(); path.addRoundedRect(r, 10, 10)
        p.fillPath(path, QColor(255, 255, 255, 16))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1.0)); p.drawPath(path)
        vr, vg, vb = C_AI_RGB
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(r.left() + 2, r.top() + 11, 2.5, r.height() - 22), 1.5, 1.5)
        p.fillPath(bar, QColor(vr, vg, vb, 255))

    def move_to(self, rect, animate=True):
        if rect is None or not rect.isValid() or rect.height() <= 0:
            self.hide(); return
        if self.isHidden() or not animate:
            self.setGeometry(rect); self.show(); self.raise_(); return
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(180); self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(self.geometry()); self._anim.setEndValue(rect)
        self._anim.start()
        self.raise_()


# ── Card Delegate (Sleek Modern Items) ─────────────────────────────
class MinimalItemDelegate(QStyledItemDelegate):
    CARD_H = 70
    TITLE_H = 18.0
    SUB_H = 14.0

    def sizeHint(self, option, index):
        if index.data(ITEM_HEADER_ROLE):
            return QSize(option.rect.width(), 28)
        return QSize(option.rect.width(), self.CARD_H)

    def paint(self, painter, option, index):
        # Header row: rendering separato
        if index.data(ITEM_HEADER_ROLE):
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = QRectF(option.rect).adjusted(12, 6, -12, -2)
            text = (index.data(Qt.ItemDataRole.DisplayRole) or "").upper()
            painter.setPen(QColor(INK_FAINT))
            hf = QFont(MONO_FONT, 8, QFont.Weight.Medium)
            hf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
            painter.setFont(hf)
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            # Linea sottile sotto label
            painter.setPen(QPen(QColor(255, 255, 255, 12), 1.0))
            painter.drawLine(int(rect.left()), int(rect.bottom()), int(rect.right()), int(rect.bottom()))
            painter.restore()
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(option.rect).adjusted(6, 3, -6, -3)
        path = QPainterPath(); path.addRoundedRect(rect, 10, 10)

        item_type = index.data(ITEM_TYPE_ROLE)
        is_audio = item_type == "audio"
        is_sel = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hov = bool(option.state & QStyle.StateFlag.State_MouseOver)

        VR, VG, VB = C_AI_RGB                       # viola = accento unico
        cat_r, cat_g, cat_b = C_AUDIO_RGB if is_audio else C_SS_RGB  # tinta tipo (badge)

        # 1. Background — solo hover qui. La SELEZIONE è disegnata da _SelHighlight
        #    (overlay animato sopra il viewport) per lo scorrimento fluido stile Raycast.
        if is_hov and not is_sel:
            painter.fillPath(path, QColor(255, 255, 255, 8))

        # 2. Media box — MINIATURA reale della cattura (screenshot) o waveform (audio).
        #    È ciò che rende la lista "memoria visiva" invece di una rubrica.
        MW, MH = 52.0, 36.0
        media = QRectF(rect.left() + 12, rect.center().y() - MH / 2, MW, MH)
        mpath = QPainterPath(); mpath.addRoundedRect(media, 8, 8)

        display_full = index.data(Qt.ItemDataRole.DisplayRole) or ""
        first_line = display_full.split("\n", 1)[0] if display_full else ""
        thumb = index.data(ITEM_THUMB_ROLE)

        if is_audio:
            fill = QColor(cat_r, cat_g, cat_b); fill.setAlpha(70 if is_sel else 48)
            painter.setPen(Qt.PenStyle.NoPen); painter.fillPath(mpath, fill)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(cat_r, cat_g, cat_b, 90), 1.0)); painter.drawPath(mpath)
            painter.setPen(QPen(QColor(cat_r, cat_g, cat_b, 255), 1.8, cap=Qt.PenCapStyle.RoundCap))
            hs = [5, 10, 15, 9, 13, 7, 4]; gi = 4.6
            cx = media.center().x(); cy = media.center().y()
            sx = cx - (len(hs) - 1) * gi / 2
            for i, bh in enumerate(hs):
                painter.drawLine(QPointF(sx + i * gi, cy - bh / 2), QPointF(sx + i * gi, cy + bh / 2))
        elif isinstance(thumb, QPixmap) and not thumb.isNull():
            painter.save(); painter.setClipPath(mpath)
            sc = thumb.scaled(int(MW), int(MH), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(QPointF(media.left() - (sc.width() - MW) / 2,
                                       media.top() - (sc.height() - MH) / 2), sc)
            painter.restore()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 40 if not is_sel else 70), 1.0))
            painter.drawPath(mpath)
            # pallino colore-app nell'angolo (identifica la sorgente)
            ar, ag, ab = _app_color_rgb(first_line)
            dcx, dcy = media.right() - 7, media.bottom() - 7
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(14, 14, 18, 235)); painter.drawEllipse(QPointF(dcx, dcy), 5.4, 5.4)
            painter.setBrush(QColor(ar, ag, ab)); painter.drawEllipse(QPointF(dcx, dcy), 3.0, 3.0)
        else:
            # fallback (nessuna miniatura): fill colore app + iniziale
            ar, ag, ab = _app_color_rgb(first_line)
            fill = QColor(ar, ag, ab); fill.setAlpha(220 if is_sel else 195)
            painter.setPen(Qt.PenStyle.NoPen); painter.fillPath(mpath, fill)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 36), 1.0)); painter.drawPath(mpath)
            painter.setPen(QColor(14, 14, 18, 240))
            painter.setFont(QFont(UI_FONT, 13, QFont.Weight.Bold))
            painter.drawText(media, Qt.AlignmentFlag.AlignCenter, _app_initial(first_line))

        # 4. Testo — titolo + sotto-riga; score a destra in mono
        display = index.data(Qt.ItemDataRole.DisplayRole) or ""
        lines = display.split("\n", 1)
        score_txt = ""
        sub_txt = lines[1] if len(lines) > 1 else ""
        if "•" in sub_txt:
            left, right = sub_txt.split("•", 1)
            sub_txt = left.strip(); score_txt = right.strip()

        tx = media.right() + 14
        score_w = 56.0
        tw = rect.right() - 14 - score_w - tx
        content_h = self.TITLE_H + self.SUB_H
        gap = (rect.height() - content_h) / 3.0
        title_y = rect.top() + gap
        sub_y = title_y + self.TITLE_H + gap

        fm_title = QFontMetrics(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        elided = fm_title.elidedText(lines[0] if lines else "", Qt.TextElideMode.ElideRight, int(tw))
        painter.setPen(QColor(INK) if is_sel else QColor("#dcdce4"))
        painter.setFont(QFont(UI_FONT, 11, QFont.Weight.DemiBold))
        painter.drawText(QRectF(tx, title_y, tw, self.TITLE_H),
                         Qt.AlignmentFlag.AlignVCenter, elided)

        if sub_txt:
            painter.setPen(QColor(INK_DIM))
            painter.setFont(QFont(UI_FONT, 9, QFont.Weight.Normal))
            painter.drawText(QRectF(tx, sub_y, tw, self.SUB_H),
                             Qt.AlignmentFlag.AlignVCenter, sub_txt)

        if score_txt:
            exact = "✓" in score_txt or "esatt" in score_txt.lower()
            sb = QRectF(rect.right() - 14 - score_w, rect.top(), score_w, rect.height())
            if exact:
                # check vettoriale (Geist Mono non ha ✓) + "esatto"
                painter.setFont(QFont(MONO_FONT, 9, QFont.Weight.Medium))
                painter.setPen(QColor(EMERALD))
                painter.drawText(sb, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "esatto")
                cy = sb.center().y()
                cx = sb.right() - QFontMetrics(QFont(MONO_FONT, 9, QFont.Weight.Medium)).horizontalAdvance("esatto") - 9
                painter.setPen(QPen(QColor(EMERALD), 1.4, cap=Qt.PenCapStyle.RoundCap,
                                    join=Qt.PenJoinStyle.RoundJoin))
                painter.drawPolyline(QPolygonF([QPointF(cx, cy + 0.5),
                                                QPointF(cx + 2.4, cy + 2.8),
                                                QPointF(cx + 6.2, cy - 3.0)]))
            else:
                painter.setPen(QColor(INK_FAINT))
                painter.setFont(QFont(MONO_FONT, 9, QFont.Weight.Medium))
                painter.drawText(sb, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, score_txt)

        painter.restore()


# ── Workers ────────────────────────────────────────────────────────
class SearchWorker(QThread):
    done = pyqtSignal(list)
    error = pyqtSignal(str)
    def __init__(self, q): super().__init__(); self.q = q
    def run(self):
        try: self.done.emit(search_module.query(self.q))
        except Exception as e: self.error.emit(str(e))

# Dimensione pagina di "Esplora" (scroll-infinito): si carica così, a blocchi.
EXPLORE_PAGE = 3000


class AllWorker(QThread):
    done = pyqtSignal(list)
    def __init__(self, offset=0, limit=EXPLORE_PAGE):
        super().__init__(); self._offset = offset; self._limit = limit
    def run(self):
        try: self.done.emit(search_module.get_all(limit=self._limit, offset=self._offset))
        except Exception: self.done.emit([])

class ModelsWorker(QThread):
    """Interroga l'endpoint (chat o vision) per i modelli disponibili, in background,
    così il combo si riempie da solo all'apertura delle Impostazioni senza bloccare la UI."""
    done = pyqtSignal(bool, object)  # (ok, list[str] | str errore)
    def __init__(self, base, key):
        super().__init__(); self._base = base; self._key = key
    def run(self):
        try:
            ok, res = ai_assistant.list_models(base_url=self._base, api_key=self._key)
        except Exception as e:
            ok, res = False, str(e)
        self.done.emit(ok, res)

class ChatWorker(QThread):
    chunk = pyqtSignal(str, str)         # (kind, content)
    finished_streaming = pyqtSignal()

    def __init__(self, history, message):
        super().__init__()
        self._history = list(history)
        self._message = message

    def run(self):
        try:
            for kind, content in ai_assistant.chat_stream(self._history, self._message):
                if kind == "done":
                    break
                self.chunk.emit(kind, content or "")
        except Exception as e:
            self.chunk.emit("error", str(e))
        self.finished_streaming.emit()

class VoiceWorker(QThread):
    """Registra dal mic, trascrive con Whisper. Emette (text, log)."""
    started_transcribe = pyqtSignal()
    done = pyqtSignal(str, str)

    def __init__(self, stop_event):
        super().__init__()
        self._stop_event = stop_event

    def run(self):
        text, log = "", ""
        try:
            from modules.audio import record_and_transcribe
            # Hook: notifica fase trascrizione
            class _StopProxy:
                def __init__(self, ev, cb):
                    self._ev = ev; self._cb = cb; self._fired = False
                def is_set(self):
                    if self._ev.is_set() and not self._fired:
                        self._fired = True
                        try: self._cb()
                        except Exception: pass
                    return self._ev.is_set()
                def set(self): self._ev.set()
            proxy = _StopProxy(self._stop_event, lambda: self.started_transcribe.emit())
            text, log = record_and_transcribe(proxy, max_seconds=120)
        except Exception as e:
            log = f"worker_exc={e}"
            print(f"[VoiceWorker] errore: {e}")
        print(f"[VoiceWorker] log: {log}")
        self.done.emit(text or "", log or "")


class RagWorker(QThread):
    done = pyqtSignal(str)

    def __init__(self, query, results):
        super().__init__()
        self._q = query
        self._results = results

    def run(self):
        try:
            ans = ai_assistant.rag_inline(self._q, self._results)
            self.done.emit(ans or "")
        except Exception as e:
            self.done.emit(f"⚠ {e}")

class ClickableLabel(QLabel):
    dbl = pyqtSignal()
    def mouseDoubleClickEvent(self, _): self.dbl.emit()


# ── Loading page ───────────────────────────────────────────────────
class _SpinnerRing(QWidget):
    """Anello rotante premium con arc gradient."""
    def __init__(self, parent=None, color=C_AI_HEX):
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self.setStyleSheet("background:transparent;")
        self._angle = 0
        self._color = QColor(color)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self): self._timer.start(16)
    def stop(self):  self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(cx, cy) - 5
        # Track sottile
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 18), 3, cap=Qt.PenCapStyle.RoundCap))
        p.drawEllipse(QPointF(cx, cy), r, r)
        # Arco rotante
        p.setPen(QPen(self._color, 3, cap=Qt.PenCapStyle.RoundCap))
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        p.drawArc(rect, int(-self._angle * 16), int(120 * 16))

class WaveformWidget(QWidget):
    """Disegna forma onda audio da array float32. Cursor playback opzionale."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet("background:transparent;")
        self._samples = None      # ndarray float32
        self._cursor = 0.0        # 0..1 progress
        self._bars = None         # cached peaks

    def set_audio(self, samples, max_bars=140):
        import numpy as _np
        if samples is None or len(samples) == 0:
            self._samples = None; self._bars = None; self.update(); return
        self._samples = samples
        # Downsample a max_bars peak bars
        n = len(samples); bw = max(1, n // max_bars)
        bars = []
        for i in range(0, n, bw):
            chunk = samples[i:i+bw]
            if len(chunk) > 0:
                bars.append(float(_np.max(_np.abs(chunk))))
        # Normalize
        m = max(bars) if bars else 1.0
        if m > 0:
            bars = [b / m for b in bars]
        self._bars = bars
        self.update()

    def set_progress(self, p):
        self._cursor = max(0.0, min(1.0, p))
        self.update()

    def clear(self):
        self._samples = None; self._bars = None; self._cursor = 0.0; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self._bars:
            # Placeholder line
            p.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
            p.drawLine(0, h // 2, w, h // 2)
            return
        n = len(self._bars)
        gap = max(1, int(w / n)) if n > 0 else 1
        bar_w = max(1, gap - 1)
        cx_progress = int(w * self._cursor)
        cy = h / 2.0
        for i, v in enumerate(self._bars):
            x = int(i * w / n)
            bh = max(2, int(v * (h - 6)))
            y0 = cy - bh / 2; y1 = cy + bh / 2
            # Color: played vs unplayed
            if x <= cx_progress:
                p.setPen(QPen(QColor(*C_AUDIO_RGB, 230), bar_w))
            else:
                p.setPen(QPen(QColor(255, 255, 255, 55), bar_w))
            p.drawLine(x, int(y0), x, int(y1))
        # Cursor line
        if self._cursor > 0:
            p.setPen(QPen(QColor(255, 255, 255, 200), 1.0))
            p.drawLine(cx_progress, 0, cx_progress, h)


class _SkeletonCard(QWidget):
    """Card placeholder con shimmer band."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)
        self.setStyleSheet("background:transparent;")
        self._phase = 0.0

    def tick(self, phase):
        self._phase = phase
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(6, 4, -6, -4)
        path = QPainterPath(); path.addRoundedRect(rect, 11, 11)
        p.fillPath(path, QBrush(QColor(28, 28, 34, 140)))
        # Shimmer band scorrevole
        band_w = self.width() * 0.45
        x = -band_w + (self.width() + band_w) * self._phase
        sh = QLinearGradient(x, 0, x + band_w, 0)
        sh.setColorAt(0.0, QColor(255, 255, 255, 0))
        sh.setColorAt(0.5, QColor(255, 255, 255, 28))
        sh.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(sh))
        # Ghost icona circle
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(255, 255, 255, 22)))
        p.drawEllipse(QPointF(rect.left() + 30, rect.center().y()), 14, 14)
        # Ghost text bars
        p.setBrush(QBrush(QColor(255, 255, 255, 26)))
        p.drawRoundedRect(QRectF(rect.left() + 60, rect.center().y() - 14, rect.width() * 0.50, 9), 4, 4)
        p.setBrush(QBrush(QColor(255, 255, 255, 16)))
        p.drawRoundedRect(QRectF(rect.left() + 60, rect.center().y() + 2, rect.width() * 0.30, 7), 3, 3)
        # Border subtle
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1.0))
        p.drawPath(path)


class _SkeletonBlock(QWidget):
    """Blocco rettangolare con shimmer per preview panel placeholder."""
    def __init__(self, height=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        if height: self.setFixedHeight(height)
        self._phase = 0.0
        self._radius = 10

    def tick(self, phase):
        self._phase = phase; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath(); path.addRoundedRect(rect, self._radius, self._radius)
        p.fillPath(path, QBrush(QColor(28, 28, 34, 140)))
        band_w = self.width() * 0.40
        x = -band_w + (self.width() + band_w) * self._phase
        sh = QLinearGradient(x, 0, x + band_w, 0)
        sh.setColorAt(0.0, QColor(255, 255, 255, 0))
        sh.setColorAt(0.5, QColor(255, 255, 255, 24))
        sh.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(sh))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1.0))
        p.drawPath(path)


class LoadingPage(QWidget):
    """Skeleton split layout: cards a sx, preview placeholder a dx."""
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:transparent;")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 6, 14, 16); outer.setSpacing(12)

        # Left column — skeleton cards (mimica results_list)
        self._left_col = QWidget(); self._left_col.setFixedWidth(320)
        self._left_col.setStyleSheet("background:transparent;")
        lcol = QVBoxLayout(self._left_col)
        lcol.setContentsMargins(0, 0, 0, 0); lcol.setSpacing(6)
        lcol.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cards = []
        for _ in range(7):
            c = _SkeletonCard(); lcol.addWidget(c); self._cards.append(c)
        lcol.addStretch()
        outer.addWidget(self._left_col)

        # Right column — preview panel placeholder
        right = QWidget(); right.setStyleSheet("background:transparent;")
        rcol = QVBoxLayout(right)
        rcol.setContentsMargins(16, 12, 16, 16); rcol.setSpacing(12)
        # 3 ghost buttons (Espandi / Ascolta / Contesto)
        btn_row = QHBoxLayout(); btn_row.setSpacing(10)
        self._ghost_btns = []
        for _ in range(3):
            b = _SkeletonBlock(height=34); btn_row.addWidget(b); self._ghost_btns.append(b)
        rcol.addLayout(btn_row)
        # Big ghost block per preview content
        self._big = _SkeletonBlock(height=420); self._big._radius = 12
        rcol.addWidget(self._big, stretch=1)
        outer.addWidget(right, stretch=1)

        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._phase = (self._phase + 0.025) % 1.0
        for i, c in enumerate(self._cards):
            c.tick((self._phase + i * 0.06) % 1.0)
        for i, b in enumerate(self._ghost_btns):
            b.tick((self._phase + 0.15 + i * 0.05) % 1.0)
        self._big.tick((self._phase + 0.3) % 1.0)

    def start(self):
        self._phase = 0.0; self._timer.start()

    def stop(self):
        self._timer.stop()


# ── Toast notification ────────────────────────────────────────────
class Toast(QWidget):
    """Toast overlay top-right del parent. Auto-dismiss con fade."""
    LEVELS = {
        "info":  ("#a78bfa", "rgba(167,139,250,0.18)", "rgba(167,139,250,0.45)"),
        "ok":    ("#10b981", "rgba(16,185,129,0.18)",  "rgba(16,185,129,0.45)"),
        "error": ("#ef4444", "rgba(239,68,68,0.18)",   "rgba(239,68,68,0.45)"),
        "warn":  ("#f59e0b", "rgba(245,158,11,0.18)",  "rgba(245,158,11,0.45)"),
    }
    ICONS = {"info": "ℹ", "ok": "✓", "error": "⚠", "warn": "!"}

    def __init__(self, parent, message, level="info", duration_ms=3000):
        super().__init__(parent, Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        color_hex, bg_rgba, border_rgba = self.LEVELS.get(level, self.LEVELS["info"])
        icon = self.ICONS.get(level, "ℹ")

        lay = QHBoxLayout(self); lay.setContentsMargins(14, 10, 14, 10); lay.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color:{color_hex}; background:transparent; font-size:14px; font-weight:700;")
        lay.addWidget(icon_lbl)

        text_lbl = QLabel(message)
        text_lbl.setWordWrap(True)
        text_lbl.setFont(QFont(UI_FONT, 10, QFont.Weight.Medium))
        text_lbl.setStyleSheet("color:#f3f4f6; background:transparent;")
        lay.addWidget(text_lbl)

        self._color_hex = color_hex
        self._bg_rgba = bg_rgba
        self._border_rgba = border_rgba

        self.setStyleSheet("background:transparent;")
        self.setFixedHeight(44)
        # Position top-right
        if parent:
            pw = parent.width()
            self.adjustSize()
            w = min(max(self.sizeHint().width() + 24, 220), 420)
            self.setFixedWidth(w)
            self.move(pw - w - 16, 16)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        # Fade-in
        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0); self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in.start()

        # Auto dismiss
        QTimer.singleShot(duration_ms, self._dismiss)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath(); path.addRoundedRect(rect, 10, 10)
        # bg
        from PyQt6.QtGui import QColor as _QC
        def parse_rgba(s):
            v = s[s.index("(")+1:s.index(")")].split(",")
            return _QC(int(float(v[0])), int(float(v[1])), int(float(v[2])), int(float(v[3])*255))
        p.fillPath(path, QBrush(parse_rgba(self._bg_rgba)))
        # bg base dark for opacity
        p.fillPath(path, QBrush(_QC(18, 18, 22, 240)))
        p.fillPath(path, QBrush(parse_rgba(self._bg_rgba)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(parse_rgba(self._border_rgba), 1.0))
        p.drawPath(path)

    def _dismiss(self):
        try:
            self._fade_out = QPropertyAnimation(self, b"windowOpacity")
            self._fade_out.setDuration(220)
            self._fade_out.setStartValue(self.windowOpacity()); self._fade_out.setEndValue(0.0)
            self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
            self._fade_out.finished.connect(self.deleteLater)
            self._fade_out.start()
        except Exception:
            self.deleteLater()


# ── AI Answer Card (inline RAG above search results) ──────────────
class AIAnswerCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._collapsed = False
        self._loading = False
        self._shimmer_pos = 0.0

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 14); v.setSpacing(8)

        head = QHBoxLayout(); head.setSpacing(8)
        # Badge con punto pulsante
        self._badge = QLabel("✦  Déjà · sintesi")
        self._badge.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
        self._badge.setStyleSheet(f"color:{C_AI_HEX}; background:transparent; letter-spacing:0.6px;")
        head.addWidget(self._badge); head.addStretch()
        self._toggle = QPushButton("−")
        self._toggle.setFixedSize(22, 22); self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setStyleSheet(
            f"QPushButton{{background:rgba(167,139,250,0.08); color:{C_AI_HEX}; "
            f"border:1px solid rgba(167,139,250,0.30); border-radius:6px; "
            f"font-size:14px; font-weight:600; padding-bottom:2px;}}"
            "QPushButton:hover{background:rgba(167,139,250,0.22);}"
        )
        self._toggle.clicked.connect(self._toggle_collapse)
        head.addWidget(self._toggle)
        v.addLayout(head)

        self._text = QLabel(t("win.sum_reading"))
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._text.setFont(QFont(UI_FONT, 11))
        self._text.setStyleSheet("color:#ebebef; background:transparent;")
        v.addWidget(self._text)

        # Shimmer timer (loading anim)
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(40)
        self._shimmer_timer.timeout.connect(self._on_shimmer_tick)

        self.hide()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath(); path.addRoundedRect(rect, 12, 12)

        # Gradient base
        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0.0, QColor(167, 139, 250, 30))
        bg.setColorAt(1.0, QColor(139, 92, 246, 14))
        p.fillPath(path, QBrush(bg))

        # Shimmer band durante loading
        if self._loading:
            band_w = self.width() * 0.35
            x = -band_w + (self.width() + band_w) * self._shimmer_pos
            sh = QLinearGradient(x, 0, x + band_w, 0)
            sh.setColorAt(0.0, QColor(255, 255, 255, 0))
            sh.setColorAt(0.5, QColor(255, 255, 255, 26))
            sh.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillPath(path, QBrush(sh))

        # Border doppio: gradient diagonale + inner
        bg_b = QLinearGradient(0, 0, self.width(), self.height())
        bg_b.setColorAt(0.0, QColor(167, 139, 250, 130))
        bg_b.setColorAt(1.0, QColor(167, 139, 250, 60))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(bg_b, 1.0))
        p.drawPath(path)

    def _on_shimmer_tick(self):
        self._shimmer_pos = (self._shimmer_pos + 0.04) % 1.0
        self.update()

    def show_loading(self, query=""):
        self._text.setText(t("win.sum_reading") + (f"  «{query[:40]}»" if query else ""))
        self._badge.setText(t("win.sum_proc"))
        if self._collapsed: self._expand()
        self._loading = True
        self._shimmer_pos = 0.0
        self._shimmer_timer.start()
        self.show()

    def set_answer(self, text):
        self._loading = False
        self._shimmer_timer.stop()
        self._badge.setText(t("win.sum_synth"))
        self._text.setText(text or t("win.sum_no_answer"))
        self.update()

    def reset(self):
        self._loading = False
        self._shimmer_timer.stop()
        self._text.setText("")
        self.hide()

    def _toggle_collapse(self):
        if self._collapsed: self._expand()
        else: self._collapse()

    def _collapse(self):
        self._collapsed = True
        self._text.hide(); self._toggle.setText("+")

    def _expand(self):
        self._collapsed = False
        self._text.show(); self._toggle.setText("−")


# ── Chat bubble factory ────────────────────────────────────────────
def _make_bubble(text, kind):
    """kind: 'user' | 'assistant' | 'tool' | 'error' | 'thinking'"""
    container = QWidget()
    container.setStyleSheet("background:transparent;")
    h = QHBoxLayout(container)
    h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)

    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setMaximumWidth(580)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setFont(QFont(UI_FONT, 11))

    if kind == "user":
        lbl.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 rgba(167,139,250,0.28), stop:1 rgba(139,92,246,0.18)); "
            "color:#ffffff; border:1px solid rgba(167,139,250,0.42); "
            "border-radius:14px; padding:11px 15px; }"
        )
        h.addStretch(); h.addWidget(lbl)
    elif kind == "tool":
        lbl.setFont(QFont("Consolas", 9))
        lbl.setStyleSheet(
            "QLabel{background:rgba(255,255,255,0.035); color:#9ca0ac; "
            "border:1px solid rgba(255,255,255,0.06); border-radius:11px; "
            "padding:5px 12px; letter-spacing:0.3px;}"
        )
        h.addStretch(1); h.addWidget(lbl); h.addStretch(1)
    elif kind == "error":
        lbl.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 rgba(239,68,68,0.12), stop:1 rgba(220,38,38,0.06)); "
            "color:#fca5a5; border:1px solid rgba(239,68,68,0.30); "
            "border-radius:12px; padding:11px 15px; }"
        )
        h.addWidget(lbl); h.addStretch()
    elif kind == "thinking":
        lbl.setStyleSheet(
            f"QLabel{{background:rgba(167,139,250,0.05); color:{C_AI_HEX}; "
            f"border:1px solid rgba(167,139,250,0.22); border-radius:14px; "
            "padding:11px 16px; letter-spacing:6px; font-size:13px;}}"
        )
        h.addWidget(lbl); h.addStretch()
    else:  # assistant
        lbl.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 rgba(255,255,255,0.055), stop:1 rgba(255,255,255,0.025)); "
            "color:#ebebef; border:1px solid rgba(255,255,255,0.08); "
            "border-radius:14px; padding:11px 15px; }"
        )
        h.addWidget(lbl); h.addStretch()

    return container, lbl


# ── Embed source cards (inserite sotto risposta AI) ───────────────
class _EmbedCardBase(QWidget):
    """Card cliccabile premium per fonte citata da AI nella chat."""
    HEIGHT = 78

    def __init__(self, accent_rgb, parent=None):
        super().__init__(parent)
        self._accent = QColor(*accent_rgb)
        self._hover = False
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background:transparent;")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def enterEvent(self, _): self._hover = True; self.update()
    def leaveEvent(self, _): self._hover = False; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath(); path.addRoundedRect(rect, 10, 10)

        a = self._accent
        # Gradient bg sottile
        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0.0, QColor(a.red(), a.green(), a.blue(), 26 if self._hover else 16))
        bg.setColorAt(1.0, QColor(a.red(), a.green(), a.blue(), 10 if self._hover else 4))
        p.fillPath(path, QBrush(bg))

        # Border tinta
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(a.red(), a.green(), a.blue(), 130 if self._hover else 70), 1.0))
        p.drawPath(path)

        # Left accent bar
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(rect.left() + 1.5, rect.top() + 12, 3.0, rect.height() - 24), 1.5, 1.5)
        p.fillPath(bar, QBrush(QColor(a.red(), a.green(), a.blue(), 255)))


class EmbedScreenshotCard(_EmbedCardBase):
    """Card screenshot citato: thumbnail + app + ts. Click → fullscreen."""
    clicked = pyqtSignal(int)

    def __init__(self, row_id, parent=None):
        super().__init__(C_SS_RGB, parent)
        self._id = row_id
        self._pixmap = None

        conn = get_conn(); c = conn.cursor()
        row = c.execute("SELECT ts, app, image FROM screenshots WHERE id=?", (row_id,)).fetchone()
        conn.close()
        ts = row[0] if row else ""
        app = (row[1] if row else "?") or "?"
        img_blob = row[2] if row else None

        h = QHBoxLayout(self); h.setContentsMargins(12, 8, 12, 8); h.setSpacing(12)

        # Thumb
        thumb = QLabel(); thumb.setFixedSize(60, 60)
        thumb.setStyleSheet("background:rgba(0,0,0,0.3); border-radius:6px;")
        if img_blob:
            px = QPixmap(); px.loadFromData(img_blob)
            self._pixmap = px
            thumb.setPixmap(px.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation))
            thumb.setScaledContents(False)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(thumb)

        # Info
        info_lay = QVBoxLayout(); info_lay.setContentsMargins(0, 4, 0, 4); info_lay.setSpacing(2)
        head = QLabel(f"📸  {t('win.card_screenshot')}")
        head.setStyleSheet(f"color:{C_SS_HEX}; background:transparent; font-size:9px; font-weight:700; letter-spacing:1px;")
        info_lay.addWidget(head)

        app_short = app if len(app) <= 36 else app[:33] + "…"
        app_lbl = QLabel(app_short)
        app_lbl.setFont(QFont(UI_FONT, 10, QFont.Weight.DemiBold))
        app_lbl.setStyleSheet("color:#e6e6ec; background:transparent;")
        info_lay.addWidget(app_lbl)

        ts_lbl = QLabel(_human_ago(ts))
        ts_lbl.setFont(QFont(UI_FONT, 9))
        ts_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        info_lay.addWidget(ts_lbl)
        h.addLayout(info_lay, stretch=1)

        # Hint icon
        hint = QLabel("↗")
        hint.setStyleSheet(f"color:{C_SS_HEX}; background:transparent; font-size:14px;")
        h.addWidget(hint)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._id)


class EmbedAudioCard(_EmbedCardBase):
    """Card audio citato: play inline + transcript + ts. Click play toggle."""
    play_requested = pyqtSignal(int)

    def __init__(self, row_id, parent=None):
        super().__init__(C_AUDIO_RGB, parent)
        self._id = row_id

        conn = get_conn(); c = conn.cursor()
        row = c.execute(
            "SELECT ts, source, transcript FROM audio_segments WHERE id=?", (row_id,)
        ).fetchone()
        conn.close()
        ts = row[0] if row else ""
        src = (row[1] if row else "?") or "?"
        transcript = (row[2] if row else "") or ""

        h = QHBoxLayout(self); h.setContentsMargins(12, 8, 12, 8); h.setSpacing(12)

        # Play button (circular)
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(40, 40)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setStyleSheet(
            f"QPushButton{{background:rgba(245,158,11,0.20); color:{C_AUDIO_HEX}; "
            f"border:1px solid rgba(245,158,11,0.45); border-radius:20px; "
            f"font-size:14px; font-weight:700; padding-bottom:1px;}}"
            "QPushButton:hover{background:rgba(245,158,11,0.35);}"
        )
        self._play_btn.clicked.connect(lambda: self.play_requested.emit(self._id))
        h.addWidget(self._play_btn)

        # Info
        info_lay = QVBoxLayout(); info_lay.setContentsMargins(0, 4, 0, 4); info_lay.setSpacing(2)
        src_lbl = QLabel(f"🎙️  {t('win.card_mic') if src == 'mic' else t('win.card_system')}  ·  {_human_ago(ts)}")
        src_lbl.setStyleSheet(f"color:{C_AUDIO_HEX}; background:transparent; font-size:9px; font-weight:700; letter-spacing:1px;")
        info_lay.addWidget(src_lbl)

        snippet = transcript.replace("\n", " ").strip()
        snippet = snippet if len(snippet) <= 80 else snippet[:77] + "…"
        tr_lbl = QLabel(snippet or t("win.card_no_text"))
        tr_lbl.setFont(QFont(UI_FONT, 10))
        tr_lbl.setStyleSheet("color:#e6e6ec; background:transparent;")
        tr_lbl.setWordWrap(False)
        info_lay.addWidget(tr_lbl)
        h.addLayout(info_lay, stretch=1)

    def set_playing(self, playing):
        self._play_btn.setText("⏹" if playing else "▶")


# ── Assistant turn bubble (contiene testo + embed cards inline) ───
class AssistantTurnBubble(QWidget):
    """Bolla unica AI: paintEvent gradient + border. Dentro stack di text labels + cards."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        # Layout root: hbox per allineamento sx + max width
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        self._bubble = QWidget()
        self._bubble.setMaximumWidth(620)
        # paint custom su _bubble
        self._bubble.paintEvent = self._paint_bubble
        outer.addWidget(self._bubble)
        outer.addStretch()

        self.inner = QVBoxLayout(self._bubble)
        self.inner.setContentsMargins(14, 12, 14, 12)
        self.inner.setSpacing(10)

    def _paint_bubble(self, _):
        from PyQt6.QtGui import QPainter, QPainterPath, QBrush, QPen, QColor, QLinearGradient
        b = self._bubble
        p = QPainter(b); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(b.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath(); path.addRoundedRect(rect, 14, 14)
        bg = QLinearGradient(0, 0, 0, b.height())
        bg.setColorAt(0.0, QColor(255, 255, 255, 14))
        bg.setColorAt(1.0, QColor(255, 255, 255, 6))
        p.fillPath(path, QBrush(bg))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1.0))
        p.drawPath(path)

    def add_text(self, html):
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setFont(QFont(UI_FONT, 11))
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("color:#ebebef; background:transparent; border:none;")
        self.inner.addWidget(lbl)
        return lbl

    def add_card(self, card):
        self.inner.addWidget(card)


# ── Chat page ──────────────────────────────────────────────────────
class ChatPage(QWidget):
    send_clicked = pyqtSignal(str)

    def __init__(self, parent=None, header_right_pad=0):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 6, 14, 14); root.setSpacing(10)

        # Header
        head = QHBoxLayout(); head.setSpacing(10)
        title = QLabel(t("win.chat_title"))
        title.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C_AI_HEX}; background:transparent; letter-spacing:1px;")
        head.addWidget(title); head.addStretch()
        self.new_chat_btn = QPushButton(t("win.chat_new"))
        self.new_chat_btn.setFixedHeight(28); self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(SS_BTN_OFF)
        head.addWidget(self.new_chat_btn)
        # Riserva spazio a destra: nell'AppShell i controlli finestra (min/max/chiudi)
        # galleggiano in alto a destra sopra questa pagina → senza riserva coprono il
        # bottone "Nuova chat" e lo rendono non cliccabile.
        if header_right_pad:
            head.addSpacing(header_right_pad)
        root.addLayout(head)

        # Messages scroll area
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background:transparent; border:none; }}
            QScrollBar:vertical {{ background:transparent; width:8px; margin:6px 2px; }}
            QScrollBar::handle:vertical {{
                background:rgba(255,255,255,0.10); border-radius:3px; min-height:30px;
            }}
            QScrollBar::handle:vertical:hover {{ background:rgba(167,139,250,0.40); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
        """)

        self._msg_holder = QWidget(); self._msg_holder.setStyleSheet("background:transparent;")
        self.msg_layout = QVBoxLayout(self._msg_holder)
        self.msg_layout.setContentsMargins(4, 4, 4, 4); self.msg_layout.setSpacing(8)
        self.msg_layout.addStretch()
        self.scroll.setWidget(self._msg_holder)
        root.addWidget(self.scroll, stretch=1)

        # Empty state
        self.empty_state = QWidget(); self.empty_state.setStyleSheet("background:transparent;")
        es = QVBoxLayout(self.empty_state); es.setAlignment(Qt.AlignmentFlag.AlignCenter); es.setSpacing(10)
        es_icon = QLabel("◆"); es_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_icon.setFont(QFont(UI_FONT, 28))
        es_icon.setStyleSheet(f"color:{C_AI_HEX}; background:transparent;")
        es.addWidget(es_icon)
        es_t = QLabel(t("win.chat_empty_title"))
        es_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_t.setFont(QFont(UI_FONT, 13, QFont.Weight.Medium))
        es_t.setStyleSheet("color:#e5e7eb; background:transparent;")
        es.addWidget(es_t)
        es_s = QLabel(t("win.chat_empty_sub"))
        es_s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_s.setFont(QFont(UI_FONT, 10))
        es_s.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; line-height:1.6;")
        es.addWidget(es_s)
        self.msg_layout.insertWidget(0, self.empty_state)

        # Input row
        input_row = QHBoxLayout(); input_row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText(t("win.chat_placeholder"))
        self.input.setFont(QFont(UI_FONT, 11))
        self.input.setFixedHeight(38)
        self.input.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.04); color:#f3f4f6; "
            f"border:1px solid {BORDER_STR}; border-radius:10px; padding:0 14px; }}"
            f"QLineEdit:focus{{border:1px solid rgba(167,139,250,0.5);}}"
        )
        self.input.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input, stretch=1)

        # Mic button (voice input)
        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setFixedSize(38, 38); self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setToolTip(t("win.chat_mic_tip"))
        self.mic_btn.setCheckable(True)
        self._set_mic_style(False)
        input_row.addWidget(self.mic_btn)

        self.send_btn = QPushButton(t("win.chat_send")); self.send_btn.setFixedHeight(38); self.send_btn.setFixedWidth(80)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(SS_BTN_AI_PRIMARY)
        self.send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self.send_btn)
        root.addLayout(input_row)

    def _set_mic_style(self, recording):
        if recording:
            self.mic_btn.setStyleSheet(
                f"QPushButton{{background:rgba(239,68,68,0.25); color:#fff; "
                f"border:1px solid rgba(239,68,68,0.55); border-radius:10px; font-size:16px;}}"
                "QPushButton:hover{background:rgba(239,68,68,0.40);}"
            )
            self.mic_btn.setText("⏹")
        else:
            self.mic_btn.setStyleSheet(
                f"QPushButton{{background:rgba(255,255,255,0.04); color:#d1d5db; "
                f"border:1px solid {BORDER_STR}; border-radius:10px; font-size:14px;}}"
                "QPushButton:hover{background:rgba(167,139,250,0.18); color:#fff;}"
            )
            self.mic_btn.setText("🎙")

        # Auto-scroll trigger
        self.scroll.verticalScrollBar().rangeChanged.connect(self._auto_scroll)

    def _on_send(self):
        text = self.input.text().strip()
        if not text: return
        self.input.clear()
        self.send_clicked.emit(text)

    def _auto_scroll(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _hide_empty(self):
        if self.empty_state.isVisible():
            self.empty_state.hide()

    def add_user(self, text):
        self._hide_empty()
        w, _ = _make_bubble(text, "user")
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
        return w

    def add_thinking(self):
        self._hide_empty()
        w, lbl = _make_bubble("● ○ ○", "thinking")
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
        return w, lbl

    def add_assistant(self, text=""):
        self._hide_empty()
        w, lbl = _make_bubble(text or " ", "assistant")
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
        return w, lbl

    def add_tool(self, label):
        w, _ = _make_bubble(f"🔧  {label}", "tool")
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
        return w

    def add_error(self, msg):
        w, _ = _make_bubble(f"⚠  {msg}", "error")
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
        return w

    def add_notice(self, text):
        """Centered notice (e.g. 'configura API key')."""
        self._hide_empty()
        notice = QLabel(text); notice.setWordWrap(True)
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notice.setFont(QFont(UI_FONT, 11))
        notice.setStyleSheet(
            f"color:{TEXT_SECONDARY}; background:rgba(255,255,255,0.02); "
            f"border:1px dashed {BORDER_STR}; border-radius:10px; padding:14px;"
        )
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, notice)
        return notice

    def clear_messages(self):
        # raccogli widget da rimuovere (tranne empty_state)
        to_remove = []
        for i in range(self.msg_layout.count()):
            item = self.msg_layout.itemAt(i)
            if item is None: continue
            w = item.widget()
            if w is None or w is self.empty_state: continue
            to_remove.append(w)
        for w in to_remove:
            self.msg_layout.removeWidget(w)
            w.deleteLater()
        self.empty_state.show()

    def set_busy(self, busy):
        self.input.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.send_btn.setText("…" if busy else t("win.chat_send"))


# ── Diary dialog (daily summaries AI) ─────────────────────────────
class DiaryDialog(FramelessDialog):
    def __init__(self, parent=None):
        super().__init__(parent, title=t("win.diary_title"))
        self.setMinimumSize(740, 580)
        self.setStyleSheet("QDialog{background:transparent;}")

        root = self.body; root.setContentsMargins(20, 6, 20, 16); root.setSpacing(12)

        head = QHBoxLayout(); head.setSpacing(8)
        title = QLabel(t("win.diary_header"))
        title.setFont(QFont(UI_FONT, 14, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C_AI_HEX}; background:transparent; letter-spacing:1px;")
        head.addWidget(title); head.addStretch()

        # Date picker per scegliere giorno da riassumere
        from PyQt6.QtWidgets import QDateEdit
        from PyQt6.QtCore import QDate
        self.gen_date = QDateEdit()
        self.gen_date.setCalendarPopup(True)
        self.gen_date.setDate(QDate.currentDate())
        self.gen_date.setDisplayFormat("dd MMM yyyy")
        self.gen_date.setStyleSheet(
            "QDateEdit{background:rgba(255,255,255,0.05); color:#f3f4f6; "
            "border:1px solid rgba(255,255,255,0.10); border-radius:7px; "
            "padding:4px 10px; font-size:11pt;}"
        )
        head.addWidget(self.gen_date)

        self.gen_btn = QPushButton("✨ Genera")
        self.gen_btn.setFixedHeight(32); self.gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gen_btn.setStyleSheet(SS_BTN_AI_PRIMARY)
        self.gen_btn.clicked.connect(self._generate_selected)
        head.addWidget(self.gen_btn)
        root.addLayout(head)

        # Split: list left, content right
        body = QHBoxLayout(); body.setSpacing(12)

        self.day_list = QListWidget()
        self.day_list.setFixedWidth(220)
        self.day_list.setStyleSheet(f"""
            QListWidget {{ background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:10px; outline:none; padding:6px; }}
            QListWidget::item {{ color:#d1d5db; padding:8px 10px; border-radius:6px; }}
            QListWidget::item:hover {{ background:rgba(255,255,255,0.05); }}
            QListWidget::item:selected {{ background:rgba(167,139,250,0.20); color:#ffffff; }}
        """)
        self.day_list.currentRowChanged.connect(self._on_day_changed)
        body.addWidget(self.day_list)

        self.content_scroll = QScrollArea(); self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setStyleSheet(f"""
            QScrollArea {{ background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:10px; }}
            QScrollBar:vertical {{ background:transparent; width:8px; margin:6px 2px; }}
            QScrollBar::handle:vertical {{ background:rgba(255,255,255,0.10); border-radius:3px; min-height:30px; }}
            QScrollBar::handle:vertical:hover {{ background:rgba(167,139,250,0.40); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        self.content_label = QLabel()
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.content_label.setFont(QFont(UI_FONT, 11))
        self.content_label.setStyleSheet("color:#e6e6ec; background:transparent; padding:18px;")
        self.content_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.content_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_scroll.setWidget(self.content_label)
        body.addWidget(self.content_scroll, stretch=1)

        root.addLayout(body, stretch=1)

        foot = QHBoxLayout(); foot.addStretch()
        close_btn = QPushButton(t("win.diary_close")); close_btn.setFixedHeight(34); close_btn.setStyleSheet(SS_BTN_OFF)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor); close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

        self._gen_thread = None
        self._refresh_list()

    def _refresh_list(self):
        self.day_list.blockSignals(True); self.day_list.clear()
        try:
            summaries = ai_assistant.list_daily_summaries()
        except Exception as e:
            summaries = []; print(f"[Diary] list fail: {e}")
        for s in summaries:
            self.day_list.addItem(s["day_iso"])
        self.day_list.blockSignals(False)
        if summaries:
            self.day_list.setCurrentRow(0)
        else:
            self.content_label.setText(t("win.diary_empty"))

    def _on_day_changed(self, row):
        item = self.day_list.item(row)
        if not item: return
        day = item.text()
        try:
            s = ai_assistant.load_daily_summary(day)
        except Exception as e:
            self.content_label.setText(f"⚠ {e}"); return
        if not s:
            self.content_label.setText(t("win.diary_not_found")); return
        self.content_label.setText(_md_to_html(s["content"]))

    def _generate_selected(self):
        if self._gen_thread is not None and self._gen_thread.isRunning(): return
        day = self.gen_date.date().toString("yyyy-MM-dd")
        self.gen_btn.setEnabled(False); self.gen_btn.setText("⏳ Generazione…")
        self._gen_thread = _DailySummaryWorker(day)
        self._gen_thread.done.connect(self._on_gen_done)
        self._gen_thread.start()

    def _on_gen_done(self, ok, content_or_err, day_iso):
        self.gen_btn.setEnabled(True); self.gen_btn.setText(t("win.diary_generate"))
        if ok:
            try:
                ai_assistant.save_daily_summary(day_iso, content_or_err)
            except Exception as e:
                self.content_label.setText(t("win.diary_save_error", e=e)); return
            self._refresh_list()
            # Seleziona quello appena generato
            for i in range(self.day_list.count()):
                if self.day_list.item(i).text() == day_iso:
                    self.day_list.setCurrentRow(i); break
        else:
            self.content_label.setText(f"<span style='color:#ef4444;'>⚠ {content_or_err}</span>")


class _DailySummaryWorker(QThread):
    done = pyqtSignal(bool, str, str)  # (ok, content_or_error, day_iso)

    def __init__(self, day_iso):
        super().__init__()
        self._day = day_iso

    def run(self):
        ok, msg = ai_assistant.generate_daily_summary(self._day)
        self.done.emit(ok, msg, self._day)


# ── Context dialog (cross-reference ±N min) ───────────────────────
class ContextDialog(FramelessDialog):
    """Mostra ricordi ±N min attorno a un timestamp pivot."""
    def __init__(self, pivot_ts, pivot_label, parent=None, window_min=5):
        super().__init__(parent, title=t("win.ctx_title"))
        self.setMinimumSize(540, 540)
        self.setStyleSheet("QDialog{background:transparent;}")

        root = self.body; root.setContentsMargins(20, 6, 20, 16); root.setSpacing(10)

        title = QLabel(t("win.ctx_header", min=window_min))
        title.setFont(QFont(UI_FONT, 12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C_AI_HEX}; background:transparent; letter-spacing:0.5px;")
        root.addWidget(title)

        sub = QLabel(t("win.ctx_around", label=pivot_label))
        sub.setFont(QFont(UI_FONT, 10))
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:rgba(255,255,255,0.06); max-height:1px;")
        root.addWidget(sep)

        # Lista risultati
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background:transparent; border:none; }}
            QScrollBar:vertical {{ background:transparent; width:8px; margin:6px 2px; }}
            QScrollBar::handle:vertical {{ background:rgba(255,255,255,0.10); border-radius:3px; min-height:30px; }}
            QScrollBar::handle:vertical:hover {{ background:rgba(167,139,250,0.40); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        holder = QWidget(); holder.setStyleSheet("background:transparent;")
        v = QVBoxLayout(holder); v.setContentsMargins(2, 2, 2, 2); v.setSpacing(6)
        scroll.setWidget(holder)
        root.addWidget(scroll, stretch=1)

        # Fetch
        try:
            pivot_dt = datetime.fromisoformat(pivot_ts)
            if pivot_dt.tzinfo is None:
                pivot_dt = pivot_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pivot_dt = datetime.now(timezone.utc)
        delta = timedelta(minutes=window_min)
        start_iso = (pivot_dt - delta).isoformat()
        end_iso = (pivot_dt + delta).isoformat()

        conn = get_conn(); c = conn.cursor()
        events = []
        for row in c.execute(
            "SELECT id, ts, app, text FROM screenshots WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
            (start_iso, end_iso),
        ):
            events.append(("screenshot", row[0], row[1], row[2] or "?", (row[3] or "")[:120]))
        for row in c.execute(
            "SELECT id, ts, source, transcript FROM audio_segments WHERE ts >= ? AND ts <= ? ORDER BY ts ASC",
            (start_iso, end_iso),
        ):
            events.append(("audio", row[0], row[1], row[2] or "?", (row[3] or "")[:120]))
        conn.close()
        events.sort(key=lambda e: e[2])

        if not events:
            empty = QLabel(t("win.ctx_empty"))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color:{TEXT_SECONDARY}; padding:30px;")
            v.addWidget(empty)
        else:
            for kind, rid, ts, src, snippet in events:
                v.addWidget(self._make_item(kind, rid, ts, src, snippet))
            v.addStretch()

        # Footer close
        close_btn = QPushButton(t("win.ctx_close")); close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(SS_BTN_OFF); close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        foot = QHBoxLayout(); foot.addStretch(); foot.addWidget(close_btn)
        root.addLayout(foot)

    def _make_item(self, kind, rid, ts, src, snippet):
        is_audio = (kind == "audio")
        accent_rgb = C_AUDIO_RGB if is_audio else C_SS_RGB
        accent_hex = C_AUDIO_HEX if is_audio else C_SS_HEX
        w = QWidget()
        w.setStyleSheet(
            f"QWidget{{background:rgba({accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]},0.06); "
            f"border:1px solid rgba({accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]},0.20); "
            "border-radius:10px;}}"
        )
        h = QHBoxLayout(w); h.setContentsMargins(12, 8, 12, 8); h.setSpacing(10)

        icon_lbl = QLabel("🎙️" if is_audio else "📸")
        icon_lbl.setStyleSheet("background:transparent; font-size:16px; border:none;")
        h.addWidget(icon_lbl)

        info = QVBoxLayout(); info.setContentsMargins(0, 0, 0, 0); info.setSpacing(2)
        head = QLabel(f"<b style='color:{accent_hex};'>{(t('win.card_audio') if is_audio else t('win.card_screenshot'))}</b>  "
                      f"<span style='color:#8b8d98;'>· {_human_ago(ts)} · {(src if not is_audio else (t('win.card_mic') if src == 'mic' else t('win.card_system')))}</span>")
        head.setStyleSheet("background:transparent; border:none; font-size:10px;")
        head.setTextFormat(Qt.TextFormat.RichText)
        info.addWidget(head)

        body = QLabel(snippet)
        body.setStyleSheet("color:#e6e6ec; background:transparent; border:none; font-size:10pt;")
        body.setWordWrap(True)
        info.addWidget(body)
        h.addLayout(info, stretch=1)
        return w


# ── Fullscreen viewer ──────────────────────────────────────────────
class FullscreenViewer(QDialog):
    def __init__(self, pixmap, info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Déjà")
        self.setStyleSheet(f"background:{BG_HEX};")
        self.showFullScreen()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24); lay.setSpacing(8)

        for txt, size, color in [(info, 12, "#ffffff"), (t("win.fs_press_esc"), 9, TEXT_SECONDARY)]:
            lbl = QLabel(txt)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(QFont(UI_FONT, size, QFont.Weight.Medium))
            lbl.setStyleSheet(f"color:{color}; background:transparent;")
            lay.addWidget(lbl)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setStyleSheet("background:transparent;border:none;")
        img = ClickableLabel()
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setStyleSheet("background:transparent;")
        img.dbl.connect(self.close)

        g = self.screen().availableGeometry()
        img.setPixmap(pixmap.scaled(
            g.width() - 80, g.height() - 140,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        sc.setWidget(img); lay.addWidget(sc)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape: self.close()


# ── Icons & Panels ─────────────────────────────────────────────────
class _SearchIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 13, 13, 7

        # Halo sottile
        halo = QRadialGradient(cx, cy, r * 2.2)
        halo.setColorAt(0.0, QColor(167, 139, 250, 24))
        halo.setColorAt(1.0, QColor(167, 139, 250, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), r * 2.2, r * 2.2)

        # Icona lente
        p.setPen(QPen(QColor(180, 182, 195, 230), 1.8, cap=Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.drawLine(QPointF(cx + r * 0.707, cy + r * 0.707),
                   QPointF(cx + r * 0.707 + 5, cy + r * 0.707 + 5))

class PreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._border_color = QColor(255, 255, 255, 20)

    def set_border_kind(self, kind="neutral"):
        if kind == "audio": self._border_color = QColor(*C_AUDIO_RGB)
        elif kind == "screenshot": self._border_color = QColor(*C_SS_RGB)
        else: self._border_color = QColor(255, 255, 255, 20)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        # Surface fill — gradient verticale per profondità
        base = QLinearGradient(0, 0, 0, self.height())
        base.setColorAt(0.0, QColor(26, 26, 32, 255))
        base.setColorAt(1.0, QColor(18, 18, 22, 255))
        p.fillPath(path, QBrush(base))

        # Subtle inner top highlight
        glow = QRadialGradient(self.width() / 2, -10, self.width() * 0.5)
        bc = self._border_color
        glow.setColorAt(0.0, QColor(bc.red(), bc.green(), bc.blue(), 30))
        glow.setColorAt(1.0, QColor(bc.red(), bc.green(), bc.blue(), 0))
        p.fillPath(path, QBrush(glow))

        # Subtle dot grid (più fine)
        gap, radius = 22, 1.0
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(255, 255, 255, 5)))
        for x in range(gap, self.width(), gap):
            for y in range(gap, self.height(), gap):
                p.drawEllipse(QPointF(x, y), radius, radius)

        # Border gradient diagonale tinta categoria
        border_grad = QLinearGradient(0, 0, self.width(), self.height())
        border_grad.setColorAt(0.0, QColor(bc.red(), bc.green(), bc.blue(), 120))
        border_grad.setColorAt(0.5, QColor(bc.red(), bc.green(), bc.blue(), 40))
        border_grad.setColorAt(1.0, QColor(bc.red(), bc.green(), bc.blue(), 100))

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(border_grad, 1.0))
        p.drawPath(path)

        # Inner stroke sottilissimo
        inner = QPainterPath()
        inner.addRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 13, 13)
        p.setPen(QPen(QColor(255, 255, 255, 6), 1.0))
        p.drawPath(inner)


# ── Ask Screen Now ─────────────────────────────────────────────────
class _AskScreenWorker(QThread):
    """Worker streaming AI per AskScreenDialog. snap già catturato."""
    chunk = pyqtSignal(str, str)        # (kind, content)
    finished_streaming = pyqtSignal()

    def __init__(self, question, snap):
        super().__init__()
        self._q = question
        self._snap = snap

    def run(self):
        try:
            from modules import ask_screen
            for kind, content in ask_screen.ask_stream(self._q, self._snap):
                if kind == "done":
                    break
                self.chunk.emit(kind, content or "")
        except Exception as e:
            self.chunk.emit("error", str(e))
        self.finished_streaming.emit()


class AskScreenDialog(FramelessDialog):
    """Popup 'Chiedi allo schermo ora'. Cattura istantanea + AI streaming.

    Si apre via hotkey Ctrl+Shift+A. Mostra thumbnail dello screen + input
    domanda + risposta AI in streaming markdown.
    """
    def __init__(self, snap, parent=None):
        super().__init__(parent, stays_on_top=True)
        self.hide_titlebar()  # ha un suo header con titolo + ✕
        self._snap = snap
        self._worker = None
        self._answer_buf = []
        self._closing = False

        self.setMinimumSize(720, 620)

        root = self.body; root.setContentsMargins(20, 12, 20, 16); root.setSpacing(12)

        # Header
        head = QHBoxLayout(); head.setSpacing(8)
        title = QLabel(t("win.ask_header"))
        title.setFont(QFont(UI_FONT, 13, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C_AI_HEX}; background:transparent; letter-spacing:0.5px;")
        head.addWidget(title)

        app_label = QLabel(f"· {snap.get('app','?')[:60]}")
        app_label.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; font-size:10pt;")
        head.addWidget(app_label)
        head.addStretch()

        close_x = QPushButton("✕")
        close_x.setFixedSize(28, 28); close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.setStyleSheet(
            "QPushButton{background:transparent; color:#8b8d98; border:none; "
            "font-size:14pt; font-weight:600;}"
            "QPushButton:hover{color:#ffffff;}"
        )
        close_x.clicked.connect(self.accept)
        head.addWidget(close_x)
        root.addLayout(head)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet(
            "background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); "
            "border-radius:8px; padding:6px;"
        )
        pix = QPixmap()
        if snap.get("thumb"):
            pix.loadFromData(snap["thumb"])
        if not pix.isNull():
            scaled = pix.scaledToWidth(520, Qt.TransformationMode.SmoothTransformation)
            if scaled.height() > 220:
                scaled = pix.scaledToHeight(220, Qt.TransformationMode.SmoothTransformation)
            self.thumb_label.setPixmap(scaled)
            self.thumb_label.setFixedHeight(min(scaled.height() + 16, 240))
        else:
            self.thumb_label.setText(t("win.ask_preview_unavail"))
            self.thumb_label.setFixedHeight(60)
        root.addWidget(self.thumb_label)

        # OCR preview info
        ocr_len = len((snap.get("text") or "").strip())
        info = QLabel(t("win.ask_ocr_chars", n=ocr_len))
        info.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; font-size:9pt;")
        root.addWidget(info)

        # Question input
        in_row = QHBoxLayout(); in_row.setSpacing(8)
        self.question = QLineEdit()
        self.question.setPlaceholderText(t("win.ask_question_ph"))
        self.question.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.04); color:#f3f4f6; "
            "border:1px solid rgba(255,255,255,0.10); border-radius:8px; "
            "padding:10px 12px; font-size:11pt;}"
            "QLineEdit:focus{border:1px solid rgba(167,139,250,0.55);}"
        )
        self.question.returnPressed.connect(self._on_send)
        in_row.addWidget(self.question, stretch=1)

        self.send_btn = QPushButton(t("win.ask_ask"))
        self.send_btn.setFixedHeight(38); self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(SS_BTN_AI_PRIMARY)
        self.send_btn.clicked.connect(self._on_send)
        in_row.addWidget(self.send_btn)
        root.addLayout(in_row)

        # Answer area (scroll)
        self.answer_scroll = QScrollArea(); self.answer_scroll.setWidgetResizable(True)
        self.answer_scroll.setStyleSheet(f"""
            QScrollArea {{ background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:10px; }}
            QScrollBar:vertical {{ background:transparent; width:8px; margin:6px 2px; }}
            QScrollBar::handle:vertical {{ background:rgba(255,255,255,0.10); border-radius:3px; min-height:30px; }}
            QScrollBar::handle:vertical:hover {{ background:rgba(167,139,250,0.40); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        self.answer_label = QLabel()
        self.answer_label.setWordWrap(True)
        self.answer_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.answer_label.setFont(QFont(UI_FONT, 11))
        self.answer_label.setStyleSheet("color:#e6e6ec; background:transparent; padding:14px;")
        self.answer_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.answer_label.setTextFormat(Qt.TextFormat.RichText)
        self.answer_label.setText(t("win.ask_answer_ph"))
        self.answer_scroll.setWidget(self.answer_label)
        root.addWidget(self.answer_scroll, stretch=1)

        # Footer
        foot = QHBoxLayout(); foot.setSpacing(8)
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; font-size:9pt;")
        foot.addWidget(self.status_lbl); foot.addStretch()
        hint = QLabel(t("win.ask_hint"))
        hint.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; font-size:9pt;")
        foot.addWidget(hint)
        root.addLayout(foot)

        # Drag-to-move
        self._drag_pos = None

        self.question.setFocus()

    # Drag
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.accept(); return
        super().keyPressEvent(e)

    def _on_send(self):
        q = self.question.text().strip()
        if not q:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        # Vision (Gemini) o text AI: almeno uno deve essere configurato
        try:
            from modules import ask_screen as _ask
            vision_ok = _ask.vision_is_configured()
        except Exception:
            vision_ok = False
        if not vision_ok and not ai_assistant.is_configured():
            self.answer_label.setText(t("win.ask_no_ai"))
            return
        self.send_btn.setEnabled(False); self.send_btn.setText("⏳")
        self.question.setEnabled(False)
        self.status_lbl.setText(t("win.ask_thinking"))
        self._answer_buf = []
        self.answer_label.setText("")
        self._worker = _AskScreenWorker(q, self._snap)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished_streaming.connect(self._on_done)
        self._worker.start()

    def _on_chunk(self, kind, content):
        if kind == "text":
            self._answer_buf.append(content)
            self.answer_label.setText(_md_to_html("".join(self._answer_buf)))
            # Autoscroll bottom
            bar = self.answer_scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
        elif kind == "info":
            # Badge modalità: "vision · gemini-..." / "ocr · model-..."
            self.status_lbl.setText(f"⚡ {content}")
        elif kind == "error":
            self.answer_label.setText(
                f"<span style='color:#ef4444;'>⚠ {_html.escape(content)}</span>"
            )

    def _on_done(self):
        self.send_btn.setEnabled(True); self.send_btn.setText(t("win.ask_ask"))
        self.question.setEnabled(True); self.question.setFocus()
        self.status_lbl.setText(t("win.ask_complete"))

    def closeEvent(self, e):
        self._closing = True
        try:
            if self._worker is not None and self._worker.isRunning():
                self._worker.requestInterruption()
                self._worker.wait(500)
        except Exception:
            pass
        super().closeEvent(e)


def open_ask_screen_dialog(parent=None, save_to_history=True):
    """Helper: cattura istantanea + apre dialog. Chiamato dall'hotkey."""
    if not applock.ensure_unlocked(parent):
        return None
    try:
        from modules import ask_screen
    except Exception as e:
        print(f"[AskScreen] import fail: {e}")
        return None
    try:
        snap = ask_screen.capture_now()
    except Exception as e:
        print(f"[AskScreen] capture fail: {e}")
        return None
    if save_to_history:
        try:
            ask_screen.save_snapshot(snap)
        except Exception as e:
            print(f"[AskScreen] save fail: {e}")
    dlg = AskScreenDialog(snap, parent=parent)
    def _relock_ask():
        try:
            if applock.lock_enabled() and applock.relock_policy() == "every_access":
                applock.lock_now()
        except Exception:
            pass
    dlg.finished.connect(_relock_ask)
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    return dlg


# ── NOTE (F6, 2026-06-06) ──────────────────────────────────────────
# La god class `DejaWindow` (overlay Spotlight, ~1900 righe) è stata RIMOSSA:
# l'app ora si avvia da `ui/app_shell.py` (AppShell) via main.py. Questo modulo
# resta come libreria di COMPONENTI riusati da app_shell e tray:
#   dialoghi  : SettingsDialog, DiaryDialog, ContextDialog, AskScreenDialog,
#               FullscreenViewer, open_ask_screen_dialog
#   chat      : ChatPage, ChatWorker, AssistantTurnBubble, Embed*Card
#   ricerca   : SearchWorker, AllWorker
#   widget/UI : WaveformWidget, Toast, LoadingPage, PreviewPanel, MinimalItemDelegate
#   helper    : resolve_ui_font, _rounded_pixmap, _fmt_time, _md_to_html, _strip_refs, ...
# Backup pre-rimozione: window.py.bak (cancellabile dopo verifica).
