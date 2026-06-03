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
    QApplication, QGraphicsDropShadowEffect, QStackedWidget,
    QStyledItemDelegate, QStyle, QSlider,
    QTabWidget, QTextEdit, QFrame, QSizePolicy, QSpinBox, QComboBox
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve,
    QRect, QRectF, QTimer, QSize, QPointF
)
from PyQt6.QtGui import (
    QFont, QPixmap, QColor, QPainter, QPainterPath, QBrush,
    QRegion, QPen, QLinearGradient, QRadialGradient, QKeyEvent
)

from db import get_conn
from modules import search as search_module
from modules import ai_assistant
try:
    import config as _cfg
except Exception:
    _cfg = None

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
    if days_ago == 0: return ("oggi", "OGGI")
    if days_ago == 1: return ("ieri", "IERI")
    if days_ago < 7:  return (f"d{days_ago}", f"{days_ago} GIORNI FA")
    if days_ago < 30: return (f"w{days_ago // 7}", f"{days_ago // 7} SETTIMANE FA")
    # Mese
    return (f"m{local.year}{local.month:02d}",
            f"{_MONTHS_IT[local.month-1].upper()} {local.year}")

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
        return "ora"
    if secs < 3600:
        return f"{int(secs // 60)} min fa"
    local = ts.astimezone()
    today = datetime.now().date()
    d = local.date()
    if d == today:
        return f"oggi {local.strftime('%H:%M')}"
    if (today - d).days == 1:
        return f"ieri {local.strftime('%H:%M')}"
    if (today - d).days < 7:
        return f"{_DAYS_IT[local.weekday()]} {local.strftime('%H:%M')}"
    return f"{_DAYS_IT[local.weekday()]} {local.day} {_MONTHS_IT[local.month-1]}"

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
    QDialog { background:#17171c; }
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


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni — Déjà")
        self.setFixedSize(660, 720)
        # L'overlay di Déjà è WindowStaysOnTopHint|Tool: senza questo flag la finestra
        # impostazioni resta DIETRO l'overlay, il modal blocca l'input e sembra tutto
        # bloccato. Tenerla sopra (e portarla in primo piano in showEvent) risolve.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(SETTINGS_QSS)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        tabs = QTabWidget(); root.addWidget(tabs, stretch=1)

        # ── Tab Ricerca ─────────────────────────────────────────
        t_search = QWidget(); t_search.setStyleSheet("background:transparent;")
        tsl = QVBoxLayout(t_search); tsl.setContentsMargins(24, 22, 24, 20); tsl.setSpacing(14)
        srch_sec = QLabel("MODELLI"); srch_sec.setObjectName("section"); tsl.addWidget(srch_sec)
        for label, attr, placeholder in [
            ("Modello Embedding", "EMBEDDING_MODEL", "es. paraphrase-multilingual-mpnet-base-v2"),
            ("Modello Whisper",   "WHISPER_MODEL",   "tiny / base / small / medium"),
        ]:
            row = QHBoxLayout(); row.setSpacing(12)
            lbl = QLabel(label); lbl.setObjectName("field"); lbl.setFixedWidth(160)
            inp = QLineEdit(); inp.setPlaceholderText(placeholder)
            if _cfg: inp.setText(str(getattr(_cfg, attr, "")))
            inp.setObjectName(attr)
            row.addWidget(lbl); row.addWidget(inp); tsl.addLayout(row)

        row2 = QHBoxLayout(); row2.setSpacing(12)
        lbl2 = QLabel("Soglia audio"); lbl2.setObjectName("field"); lbl2.setFixedWidth(160)
        self._score_spin = QSpinBox()
        self._score_spin.setRange(1, 99); self._score_spin.setSuffix("%")
        try:
            from modules import search as _s
            self._score_spin.setValue(int(getattr(_s, "MIN_SCORE_AUDIO", 0.25) * 100))
        except Exception: self._score_spin.setValue(25)
        row2.addWidget(lbl2); row2.addWidget(self._score_spin); row2.addStretch()
        tsl.addLayout(row2); tsl.addStretch()
        tabs.addTab(t_search, "Ricerca")

        # ── Tab Cattura ─────────────────────────────────────────
        t_cap = QWidget(); t_cap.setStyleSheet("background:transparent;")
        tcl = QVBoxLayout(t_cap); tcl.setContentsMargins(24, 22, 24, 20); tcl.setSpacing(14)
        cap_sec = QLabel("INTERVALLI"); cap_sec.setObjectName("section"); tcl.addWidget(cap_sec)
        for label, attr, placeholder in [
            ("Intervallo screenshot (s)", "CAPTURE_INTERVAL", "es. 5"),
            ("Chunk audio (s)",           "AUDIO_CHUNK_SECONDS", "es. 30"),
        ]:
            row = QHBoxLayout(); row.setSpacing(12)
            lbl = QLabel(label); lbl.setObjectName("field"); lbl.setFixedWidth(180)
            inp = QLineEdit(); inp.setPlaceholderText(placeholder)
            if _cfg: inp.setText(str(getattr(_cfg, attr, "")))
            inp.setObjectName(attr)
            row.addWidget(lbl); row.addWidget(inp); tcl.addLayout(row)

        # ── Toggle cattura (screenshot / audio) ─────────────────
        from PyQt6.QtWidgets import QCheckBox as _QCheckBox
        from db import get_setting as _get_setting
        tcl.addSpacing(6)
        cap_sec2 = QLabel("REGISTRAZIONE"); cap_sec2.setObjectName("section"); tcl.addWidget(cap_sec2)
        self._cap_screens = _QCheckBox("Cattura gli screenshot dello schermo")
        self._cap_screens.setChecked((_get_setting("capture_screenshots_enabled", "1") or "1") == "1")
        tcl.addWidget(self._cap_screens)
        self._cap_audio = _QCheckBox("Registra e trascrivi l'audio (microfono e sistema)")
        self._cap_audio.setChecked((_get_setting("capture_audio_enabled", "1") or "1") == "1")
        tcl.addWidget(self._cap_audio)
        cap_hint = QLabel(
            "Puoi spegnere la registrazione senza chiudere l'app: il cambiamento è immediato."
        )
        cap_hint.setObjectName("caption"); cap_hint.setWordWrap(True); tcl.addWidget(cap_hint)

        tcl.addStretch(); tabs.addTab(t_cap, "Cattura")

        # ── Tab AI ──────────────────────────────────────────────
        t_ai = QWidget(); t_ai.setStyleSheet("background:transparent;")
        tail = QVBoxLayout(t_ai); tail.setContentsMargins(24, 20, 24, 20); tail.setSpacing(14)

        # carica valori correnti dal DB
        ai_cfg = ai_assistant.get_ai_config()

        ai_sec = QLabel("ASSISTENTE · CHAT"); ai_sec.setObjectName("section")
        tail.addWidget(ai_sec)

        row_key = QHBoxLayout(); row_key.setSpacing(12)
        lbl_key = QLabel("API Key"); lbl_key.setObjectName("field"); lbl_key.setFixedWidth(110)
        self._ai_key = QLineEdit(); self._ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_key.setPlaceholderText("Lascia vuoto se usi un modello locale")
        self._ai_key.setText(ai_cfg.get("api_key", ""))
        row_key.addWidget(lbl_key); row_key.addWidget(self._ai_key); tail.addLayout(row_key)

        row_url = QHBoxLayout(); row_url.setSpacing(12)
        lbl_url = QLabel("Base URL"); lbl_url.setObjectName("field"); lbl_url.setFixedWidth(110)
        self._ai_url = QLineEdit()
        self._ai_url.setPlaceholderText("es. http://localhost:11434/v1  oppure  https://tuo-provider/v1")
        url_val = ai_cfg.get("base_url", "")
        default_url = getattr(_cfg, "AI_BASE_URL_DEFAULT", "")
        if url_val and url_val != default_url:
            self._ai_url.setText(url_val)
        row_url.addWidget(lbl_url); row_url.addWidget(self._ai_url); tail.addLayout(row_url)
        tail.addLayout(self._build_preset_row(self._ai_url, [
            ("Ollama", "http://localhost:11434/v1"),
            ("LM Studio", "http://localhost:1234/v1"),
        ]))
        local_hint = QLabel(
            "Funziona con qualsiasi endpoint OpenAI-compatibile, locale o cloud. "
            "In locale avvia Ollama o LM Studio, scegli il preset e premi Rileva: "
            "l'API Key non serve. I modelli consigliati sono nel README."
        )
        local_hint.setObjectName("caption"); local_hint.setWordWrap(True); tail.addWidget(local_hint)

        row_model = QHBoxLayout(); row_model.setSpacing(12)
        lbl_model = QLabel("Modello"); lbl_model.setObjectName("field"); lbl_model.setFixedWidth(110)
        self._ai_model = QComboBox()
        self._ai_model.setEditable(True)  # qualsiasi modello, anche non in lista
        models = getattr(_cfg, "AI_MODELS", [])
        for m in models:
            self._ai_model.addItem(m)
        cur_model = ai_cfg.get("model", models[0])
        idx_match = self._ai_model.findText(cur_model)
        if idx_match >= 0:
            self._ai_model.setCurrentIndex(idx_match)
        else:
            self._ai_model.setCurrentText(cur_model)
        self._ai_detect_btn = QPushButton("Rileva"); self._ai_detect_btn.setObjectName("accent")
        self._ai_detect_btn.setFixedHeight(38); self._ai_detect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ai_detect_btn.setToolTip("Rileva i modelli disponibili sull'endpoint (richiede Base URL, e API Key se cloud)")
        self._ai_detect_btn.clicked.connect(self._detect_ai_models)
        row_model.addWidget(lbl_model); row_model.addWidget(self._ai_model, stretch=1)
        row_model.addWidget(self._ai_detect_btn); tail.addLayout(row_model)

        from PyQt6.QtWidgets import QCheckBox
        self._ai_inline = QCheckBox("Mostra risposta AI sopra i risultati di ricerca")
        self._ai_inline.setChecked(ai_cfg.get("inline", False))
        tail.addWidget(self._ai_inline)

        hint = QLabel(
            "La chat cerca da sola nei tuoi ricordi mentre le scrivi: chiedile pure "
            "in linguaggio naturale, capirà cosa cercare."
        )
        hint.setObjectName("caption"); hint.setWordWrap(True)
        tail.addWidget(hint)

        test_row = QHBoxLayout(); test_row.setSpacing(10)
        self._ai_test_btn = QPushButton("Prova connessione"); self._ai_test_btn.setObjectName("accent")
        self._ai_test_btn.setFixedHeight(34); self._ai_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ai_test_btn.clicked.connect(self._test_ai_connection)
        test_row.addWidget(self._ai_test_btn)

        self._ai_test_status = QLabel("")
        self._ai_test_status.setFont(QFont("Segoe UI", 10))
        self._ai_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        self._ai_test_status.setWordWrap(True)
        test_row.addWidget(self._ai_test_status, stretch=1)
        tail.addLayout(test_row)

        # ── Sub-section: Vision (Ask Screen) ────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:rgba(255,255,255,0.07); max-height:1px; min-height:1px; border:none;")
        tail.addSpacing(4); tail.addWidget(sep); tail.addSpacing(4)

        vis_title = QLabel("VISION · CHIEDI ALLO SCHERMO"); vis_title.setObjectName("section")
        tail.addWidget(vis_title)

        try:
            from modules import ask_screen as _ask_mod
            vis_cfg = _ask_mod.get_vision_config()
        except Exception:
            vis_cfg = {"enabled": False, "base_url": "", "api_key": "", "model": ""}

        self._vis_enabled = QCheckBox("Manda l'immagine dello schermo al modello (non solo il testo OCR)")
        self._vis_enabled.setChecked(vis_cfg.get("enabled", False))
        tail.addWidget(self._vis_enabled)

        row_vkey = QHBoxLayout(); row_vkey.setSpacing(12)
        lbl_vkey = QLabel("API Key"); lbl_vkey.setObjectName("field"); lbl_vkey.setFixedWidth(110)
        self._vis_key = QLineEdit(); self._vis_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._vis_key.setPlaceholderText("API key del provider (vuoto se locale)")
        self._vis_key.setText(vis_cfg.get("api_key", ""))
        row_vkey.addWidget(lbl_vkey); row_vkey.addWidget(self._vis_key); tail.addLayout(row_vkey)

        row_vurl = QHBoxLayout(); row_vurl.setSpacing(12)
        lbl_vurl = QLabel("Base URL"); lbl_vurl.setObjectName("field"); lbl_vurl.setFixedWidth(110)
        self._vis_url = QLineEdit()
        default_vurl = getattr(_cfg, "AI_VISION_BASE_URL_DEFAULT", "")
        self._vis_url.setPlaceholderText("es. http://localhost:11434/v1  oppure  https://tuo-provider/v1")
        vurl_val = vis_cfg.get("base_url", "")
        if vurl_val and vurl_val != default_vurl:
            self._vis_url.setText(vurl_val)
        row_vurl.addWidget(lbl_vurl); row_vurl.addWidget(self._vis_url); tail.addLayout(row_vurl)
        tail.addLayout(self._build_preset_row(self._vis_url, [
            ("Ollama", "http://localhost:11434/v1"),
            ("LM Studio", "http://localhost:1234/v1"),
        ]))

        row_vmodel = QHBoxLayout(); row_vmodel.setSpacing(12)
        lbl_vmodel = QLabel("Modello"); lbl_vmodel.setObjectName("field"); lbl_vmodel.setFixedWidth(110)
        self._vis_model = QComboBox()
        self._vis_model.setEditable(True)  # qualsiasi modello vision, anche non in lista
        vmodels = getattr(_cfg, "AI_VISION_MODELS", ["gemini-2.0-flash-exp"])
        for m in vmodels:
            self._vis_model.addItem(m)
        cur_vmodel = vis_cfg.get("model", vmodels[0])
        idx_vm = self._vis_model.findText(cur_vmodel)
        if idx_vm >= 0:
            self._vis_model.setCurrentIndex(idx_vm)
        else:
            self._vis_model.setCurrentText(cur_vmodel)
        self._vis_detect_btn = QPushButton("Rileva"); self._vis_detect_btn.setObjectName("accent")
        self._vis_detect_btn.setFixedHeight(38); self._vis_detect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vis_detect_btn.setToolTip("Rileva i modelli vision disponibili sull'endpoint")
        self._vis_detect_btn.clicked.connect(self._detect_vision_models)
        row_vmodel.addWidget(lbl_vmodel); row_vmodel.addWidget(self._vis_model, stretch=1)
        row_vmodel.addWidget(self._vis_detect_btn); tail.addLayout(row_vmodel)

        vis_hint = QLabel(
            "Richiede un modello multimodale su endpoint OpenAI-compatibile. "
            "In locale (es. llava o llama3.2-vision su Ollama) l'immagine non lascia il PC e "
            "l'API Key non serve; con un provider cloud l'immagine viene inviata online. "
            "I modelli consigliati sono nel README."
        )
        vis_hint.setObjectName("caption"); vis_hint.setWordWrap(True)
        vis_hint.setOpenExternalLinks(True)
        tail.addWidget(vis_hint)

        vtest_row = QHBoxLayout(); vtest_row.setSpacing(10)
        self._vis_test_btn = QPushButton("Prova Vision"); self._vis_test_btn.setObjectName("accent")
        self._vis_test_btn.setFixedHeight(34); self._vis_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vis_test_btn.clicked.connect(self._test_vision_connection)
        vtest_row.addWidget(self._vis_test_btn)

        self._vis_test_status = QLabel("")
        self._vis_test_status.setFont(QFont("Segoe UI", 10))
        self._vis_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        self._vis_test_status.setWordWrap(True)
        vtest_row.addWidget(self._vis_test_status, stretch=1)
        tail.addLayout(vtest_row)

        tail.addStretch()
        # Il tab AI ha molti campi (chat + vision): scroll area così nulla viene tagliato.
        ai_scroll = QScrollArea(); ai_scroll.setWidgetResizable(True)
        ai_scroll.setFrameShape(QFrame.Shape.NoFrame)
        ai_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ai_scroll.setStyleSheet(
            "QScrollArea{background:transparent; border:none;}"
            "QScrollBar:vertical{background:transparent; width:8px; margin:2px;}"
            "QScrollBar::handle:vertical{background:rgba(255,255,255,0.18); border-radius:4px; min-height:30px;}"
            "QScrollBar::handle:vertical:hover{background:rgba(255,255,255,0.30);}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        ai_scroll.setWidget(t_ai)
        tabs.addTab(ai_scroll, "AI")

        # ── Tab Info ────────────────────────────────────────────
        t_info = QWidget(); t_info.setStyleSheet("background:transparent;")
        til = QVBoxLayout(t_info); til.setContentsMargins(24, 22, 24, 20); til.setSpacing(14)
        try:
            conn = get_conn(); c = conn.cursor()
            n_ss = c.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
            n_au = c.execute("SELECT COUNT(*) FROM audio_segments").fetchone()[0]
            conn.close()
        except Exception: n_ss = n_au = "N/A"
        info_sec = QLabel("ARCHIVIO"); info_sec.setObjectName("section"); til.addWidget(info_sec)

        def _stat_row(name, value):
            row = QHBoxLayout(); row.setSpacing(12)
            k = QLabel(name); k.setObjectName("field")
            v = QLabel(str(value)); v.setStyleSheet("color:#f4f4f7; background:transparent; font-size:15px; font-weight:700;")
            row.addWidget(k); row.addStretch(); row.addWidget(v)
            return row
        til.addLayout(_stat_row("Screenshot salvati", n_ss))
        til.addLayout(_stat_row("Segmenti audio", n_au))
        til.addLayout(_stat_row("Database", "deja.db"))
        til.addStretch(); tabs.addTab(t_info, "Info")

        # ── Footer ──────────────────────────────────────────────
        foot_sep = QFrame(); foot_sep.setFrameShape(QFrame.Shape.HLine)
        foot_sep.setStyleSheet("background:rgba(255,255,255,0.07); max-height:1px; min-height:1px; border:none;")
        root.addWidget(foot_sep)
        footer = QHBoxLayout(); footer.setContentsMargins(24, 14, 24, 16); footer.setSpacing(10)
        close_btn = QPushButton("Annulla"); close_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Salva impostazioni"); save_btn.setObjectName("save_btn")
        save_btn.clicked.connect(self._save_and_close)
        footer.addStretch(); footer.addWidget(close_btn); footer.addWidget(save_btn)
        root.addLayout(footer)

        # Riempi le tendine dei modelli all'apertura (in background, non blocca).
        self._maybe_autodetect_models()

    def showEvent(self, e):
        super().showEvent(e)
        # Porta la finestra davanti all'overlay (anch'esso stays-on-top).
        self.raise_(); self.activateWindow()

    def _maybe_autodetect_models(self):
        """Se l'endpoint è configurato (key o locale), interroga i modelli disponibili
        e riempie la tendina. Silenzioso se fallisce (offline / key errata)."""
        base = self._ai_url.text().strip() or getattr(_cfg, "AI_BASE_URL_DEFAULT", "")
        key  = self._ai_key.text().strip()
        if key or ai_assistant.is_local_endpoint(base):
            self._ai_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
            self._ai_test_status.setText("rilevo modelli…")
            self._ai_models_worker = ModelsWorker(base, key)
            self._ai_models_worker.done.connect(self._on_ai_models_detected)
            self._ai_models_worker.start()
        if self._vis_enabled.isChecked():
            vbase = self._vis_url.text().strip() or getattr(_cfg, "AI_VISION_BASE_URL_DEFAULT", "")
            vkey  = self._vis_key.text().strip()
            if vkey or ai_assistant.is_local_endpoint(vbase):
                self._vis_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
                self._vis_test_status.setText("rilevo modelli…")
                self._vis_models_worker = ModelsWorker(vbase, vkey)
                self._vis_models_worker.done.connect(self._on_vis_models_detected)
                self._vis_models_worker.start()

    def _on_ai_models_detected(self, ok, res):
        try:
            if ok and isinstance(res, list) and res:
                self._populate_combo_models(self._ai_model, res)
                self._ai_test_status.setStyleSheet(f"color:{C_SS_HEX}; background:transparent;")
                self._ai_test_status.setText(f"✓ {len(res)} modelli disponibili")
            else:
                self._ai_test_status.setText("")  # fallimento silenzioso
        except RuntimeError:
            pass  # dialog già chiuso

    def _on_vis_models_detected(self, ok, res):
        try:
            if ok and isinstance(res, list) and res:
                self._populate_combo_models(self._vis_model, res)
                self._vis_test_status.setStyleSheet(f"color:{C_SS_HEX}; background:transparent;")
                self._vis_test_status.setText(f"✓ {len(res)} modelli disponibili")
            else:
                self._vis_test_status.setText("")
        except RuntimeError:
            pass

    def _test_ai_connection(self):
        # Salva prima i campi correnti così il test usa i valori attuali
        try:
            from db import save_setting
            save_setting("ai_api_key",  self._ai_key.text().strip())
            save_setting("ai_base_url", self._ai_url.text().strip())
            save_setting("ai_model",    self._ai_model.currentText().strip())
        except Exception:
            pass
        self._ai_test_btn.setEnabled(False)
        self._ai_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        self._ai_test_status.setText("⏳ test in corso…")
        QApplication.processEvents()
        try:
            ok, msg = ai_assistant.test_connection()
        except Exception as e:
            ok, msg = False, str(e)
        if ok:
            self._ai_test_status.setStyleSheet(f"color:{C_SS_HEX}; background:transparent;")
            self._ai_test_status.setText("✓ " + msg)
        else:
            self._ai_test_status.setStyleSheet("color:#ef4444; background:transparent;")
            self._ai_test_status.setText("✗ " + msg)
        self._ai_test_btn.setEnabled(True)

    def _test_vision_connection(self):
        # Persist vision fields prima del test
        try:
            from db import save_setting
            save_setting("ai_vision_api_key",  self._vis_key.text().strip())
            save_setting("ai_vision_base_url", self._vis_url.text().strip())
            save_setting("ai_vision_model",    self._vis_model.currentText().strip())
            save_setting("ai_vision_enabled",  "1" if self._vis_enabled.isChecked() else "0")
        except Exception:
            pass
        self._vis_test_btn.setEnabled(False)
        self._vis_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        self._vis_test_status.setText("⏳ test vision in corso…")
        QApplication.processEvents()
        try:
            from modules import ask_screen as _ask_mod
            ok, msg = _ask_mod.test_vision_connection()
        except Exception as e:
            ok, msg = False, str(e)
        if ok:
            self._vis_test_status.setStyleSheet(f"color:{C_SS_HEX}; background:transparent;")
            self._vis_test_status.setText("✓ " + msg)
        else:
            self._vis_test_status.setStyleSheet("color:#ef4444; background:transparent;")
            self._vis_test_status.setText("✗ " + msg)
        self._vis_test_btn.setEnabled(True)

    @staticmethod
    def _build_preset_row(line_edit, presets):
        """Riga di bottoni-preset che riempiono un QLineEdit di base URL.
        presets: list[(label, url)]. Usata per endpoint locali (Ollama/LM Studio) + cloud."""
        row = QHBoxLayout(); row.setSpacing(8)
        spacer = QLabel(""); spacer.setFixedWidth(110)
        row.addWidget(spacer)
        for name, url in presets:
            b = QPushButton(name); b.setObjectName("chip")
            b.setFixedHeight(28); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, u=url, le=line_edit: le.setText(u))
            row.addWidget(b)
        row.addStretch()
        return row

    @staticmethod
    def _populate_combo_models(combo, ids):
        """Riempi un combo editabile coi modelli rilevati, preservando la scelta corrente."""
        cur = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        for mid in ids:
            combo.addItem(mid)
        if cur:
            idx = combo.findText(cur)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText(cur)  # mantieni il modello scelto anche se non in lista
        combo.blockSignals(False)

    def _detect_ai_models(self):
        base = self._ai_url.text().strip() or getattr(_cfg, "AI_BASE_URL_DEFAULT", "")
        key  = self._ai_key.text().strip()
        self._ai_detect_btn.setEnabled(False)
        self._ai_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        self._ai_test_status.setText("⏳ rilevo modelli…")
        QApplication.processEvents()
        try:
            ok, res = ai_assistant.list_models(base_url=base, api_key=key)
        except Exception as e:
            ok, res = False, str(e)
        if ok:
            self._populate_combo_models(self._ai_model, res)
            self._ai_test_status.setStyleSheet(f"color:{C_SS_HEX}; background:transparent;")
            self._ai_test_status.setText(f"✓ {len(res)} modelli rilevati")
        else:
            self._ai_test_status.setStyleSheet("color:#ef4444; background:transparent;")
            self._ai_test_status.setText("✗ " + str(res))
        self._ai_detect_btn.setEnabled(True)

    def _detect_vision_models(self):
        base = self._vis_url.text().strip() or getattr(_cfg, "AI_VISION_BASE_URL_DEFAULT", "")
        key  = self._vis_key.text().strip()
        self._vis_detect_btn.setEnabled(False)
        self._vis_test_status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        self._vis_test_status.setText("⏳ rilevo modelli…")
        QApplication.processEvents()
        try:
            ok, res = ai_assistant.list_models(base_url=base, api_key=key)
        except Exception as e:
            ok, res = False, str(e)
        if ok:
            self._populate_combo_models(self._vis_model, res)
            self._vis_test_status.setStyleSheet(f"color:{C_SS_HEX}; background:transparent;")
            self._vis_test_status.setText(f"✓ {len(res)} modelli rilevati")
        else:
            self._vis_test_status.setStyleSheet("color:#ef4444; background:transparent;")
            self._vis_test_status.setText("✗ " + str(res))
        self._vis_detect_btn.setEnabled(True)

    def _save_and_close(self):
        from db import save_setting

        # 1. Settings ricerca/cattura — persistenza completa
        config_inputs = {
            "EMBEDDING_MODEL":     "embedding_model",
            "WHISPER_MODEL":       "whisper_model",
            "CAPTURE_INTERVAL":    "capture_interval",
            "AUDIO_CHUNK_SECONDS": "audio_chunk_seconds",
        }
        try:
            import config as _config_mod
            for attr, db_key in config_inputs.items():
                inp = self.findChild(QLineEdit, attr)
                if inp is None: continue
                raw = inp.text().strip()
                if not raw: continue
                # Conversione tipo basata sul default in config
                default_val = getattr(_config_mod, attr, None)
                try:
                    val = type(default_val)(raw) if default_val is not None else raw
                except (ValueError, TypeError):
                    continue
                save_setting(db_key, val)
                try: setattr(_config_mod, attr, val)
                except Exception: pass
        except Exception as e:
            print(f"[Settings] Errore persist ricerca/cattura: {e}")

        # 2. MIN_SCORE_AUDIO
        try:
            val = self._score_spin.value() / 100.0
            save_setting("audio_min_score", val)
            from modules import search as _s
            _s.MIN_SCORE_AUDIO = val
            import config as _config_mod
            _config_mod.AUDIO_MIN_SCORE = val
        except Exception as e:
            print(f"[Settings] Errore audio_min_score: {e}")

        # 3. Settings AI (text)
        try:
            save_setting("ai_api_key",    self._ai_key.text().strip())
            save_setting("ai_base_url",   self._ai_url.text().strip())
            save_setting("ai_model",      self._ai_model.currentText().strip())
            save_setting("ai_inline_rag", "1" if self._ai_inline.isChecked() else "0")
        except Exception as e:
            print(f"[Settings] Errore salvataggio AI: {e}")

        # 4. Settings Vision (Ask Screen)
        try:
            save_setting("ai_vision_enabled",  "1" if self._vis_enabled.isChecked() else "0")
            save_setting("ai_vision_api_key",  self._vis_key.text().strip())
            save_setting("ai_vision_base_url", self._vis_url.text().strip())
            save_setting("ai_vision_model",    self._vis_model.currentText().strip())
        except Exception as e:
            print(f"[Settings] Errore salvataggio Vision: {e}")

        # 5. Toggle cattura (screenshot / audio)
        try:
            save_setting("capture_screenshots_enabled", "1" if self._cap_screens.isChecked() else "0")
            save_setting("capture_audio_enabled", "1" if self._cap_audio.isChecked() else "0")
            # Notifica al thread audio di rivalutare subito (apri/chiudi stream).
            try:
                from modules.audio import request_restart
                request_restart()
            except Exception as e:
                print(f"[Settings] audio reload fail: {e}")
        except Exception as e:
            print(f"[Settings] Errore salvataggio toggle cattura: {e}")

        self.accept()


# ── Card Delegate (Sleek Modern Items) ─────────────────────────────
class MinimalItemDelegate(QStyledItemDelegate):
    CARD_H = 78
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
            rect = QRectF(option.rect).adjusted(8, 6, -8, -2)
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            # Linea sottile sotto label
            painter.setPen(QPen(QColor(255, 255, 255, 12), 1.0))
            painter.drawLine(int(rect.left()), int(rect.bottom()), int(rect.right()), int(rect.bottom()))
            painter.restore()
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(option.rect).adjusted(6, 4, -6, -4)
        path = QPainterPath(); path.addRoundedRect(rect, 11, 11)

        item_type = index.data(ITEM_TYPE_ROLE)
        is_audio = item_type == "audio"
        is_sel = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hov = bool(option.state & QStyle.StateFlag.State_MouseOver)

        cat_r, cat_g, cat_b = C_AUDIO_RGB if is_audio else C_SS_RGB

        # 1. Background — gradient verticale per profondità
        if is_sel:
            g = QLinearGradient(0, rect.top(), 0, rect.bottom())
            g.setColorAt(0.0, QColor(cat_r, cat_g, cat_b, 38))
            g.setColorAt(1.0, QColor(cat_r, cat_g, cat_b, 14))
            painter.fillPath(path, QBrush(g))
        elif is_hov:
            g = QLinearGradient(0, rect.top(), 0, rect.bottom())
            g.setColorAt(0.0, QColor(255, 255, 255, 14))
            g.setColorAt(1.0, QColor(255, 255, 255, 4))
            painter.fillPath(path, QBrush(g))
        else:
            g = QLinearGradient(0, rect.top(), 0, rect.bottom())
            g.setColorAt(0.0, QColor(28, 28, 34, 160))
            g.setColorAt(1.0, QColor(20, 20, 26, 160))
            painter.fillPath(path, QBrush(g))

        # 2. Top highlight — sottilissima riga chiara in alto
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 22 if not is_sel else 40), 1.0))
        painter.drawLine(QPointF(rect.left() + 12, rect.top() + 1),
                         QPointF(rect.right() - 12, rect.top() + 1))

        # 3. Border
        if is_sel:
            painter.setPen(QPen(QColor(cat_r, cat_g, cat_b, 180), 1.2))
        else:
            painter.setPen(QPen(QColor(255, 255, 255, 14), 1.0))
        painter.drawPath(path)

        # 4. Left accent bar (selezione)
        if is_sel:
            bar = QPainterPath()
            bar.addRoundedRect(QRectF(rect.left() + 1.5, rect.top() + 12,
                                      3.0, rect.height() - 24), 1.5, 1.5)
            grad_bar = QLinearGradient(0, rect.top(), 0, rect.bottom())
            grad_bar.setColorAt(0.0, QColor(cat_r, cat_g, cat_b, 255))
            grad_bar.setColorAt(1.0, QColor(cat_r, cat_g, cat_b, 140))
            painter.fillPath(bar, QBrush(grad_bar))

        # 5. Avatar: cerchio app color + lettera, oppure waveform per audio
        icon_cx = rect.left() + 30
        icon_cy = rect.center().y()

        # Estrai app name dal display (riga 1)
        display_full = index.data(Qt.ItemDataRole.DisplayRole) or ""
        first_line = display_full.split("\n", 1)[0] if display_full else ""
        if is_audio:
            # Mantieni waveform stilizzato + cerchio tinta categoria
            ic = QColor(cat_r, cat_g, cat_b, 255 if is_sel else 200)
            circ_bg = QColor(cat_r, cat_g, cat_b, 28 if is_sel else 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(circ_bg))
            painter.drawEllipse(QPointF(icon_cx, icon_cy), 15, 15)
            painter.setPen(QPen(ic, 1.7, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            hs = [4, 9, 13, 9, 4]; gi = 4.5
            sx = icon_cx - (len(hs) - 1) * gi / 2
            for i, bh in enumerate(hs):
                bx = sx + i * gi
                painter.drawLine(QPointF(bx, icon_cy - bh / 2), QPointF(bx, icon_cy + bh / 2))
        else:
            # Cerchio colore app + lettera iniziale
            app_r, app_g, app_b = _app_color_rgb(first_line)
            circ_bg = QColor(app_r, app_g, app_b, 60 if is_sel else 40)
            ring    = QColor(app_r, app_g, app_b, 220 if is_sel else 160)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(circ_bg))
            painter.drawEllipse(QPointF(icon_cx, icon_cy), 15, 15)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 1.4))
            painter.drawEllipse(QPointF(icon_cx, icon_cy), 14.5, 14.5)
            initial = _app_initial(first_line)
            painter.setPen(QColor(255, 255, 255, 240 if is_sel else 220))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.drawText(QRectF(icon_cx - 12, icon_cy - 12, 24, 24),
                             Qt.AlignmentFlag.AlignCenter, initial)

        # 6. Text
        tx = rect.left() + 60
        tw = rect.width() - 60 - 14
        content_h = self.TITLE_H + self.SUB_H
        gap = (rect.height() - content_h) / 3.0
        title_y = rect.top() + gap
        sub_y = title_y + self.TITLE_H + gap

        display = index.data(Qt.ItemDataRole.DisplayRole) or ""
        lines = display.split("\n", 1)

        painter.setPen(QColor("#ffffff") if is_sel else QColor("#e6e6ec"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        painter.drawText(QRectF(tx, title_y, tw, self.TITLE_H),
                         Qt.AlignmentFlag.AlignVCenter, lines[0] if lines else "")

        if len(lines) > 1:
            painter.setPen(QColor(cat_r, cat_g, cat_b, 245) if is_sel else QColor(TEXT_SECONDARY))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
            painter.drawText(QRectF(tx, sub_y, tw, self.SUB_H),
                             Qt.AlignmentFlag.AlignVCenter, lines[1])

        painter.restore()


# ── Workers ────────────────────────────────────────────────────────
class SearchWorker(QThread):
    done = pyqtSignal(list)
    error = pyqtSignal(str)
    def __init__(self, q): super().__init__(); self.q = q
    def run(self):
        try: self.done.emit(search_module.query(self.q))
        except Exception as e: self.error.emit(str(e))

class AllWorker(QThread):
    done = pyqtSignal(list)
    def run(self):
        try: self.done.emit(search_module.get_all())
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
        text_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
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
        self._badge.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
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

        self._text = QLabel("Sto leggendo i tuoi ricordi…")
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._text.setFont(QFont("Segoe UI", 11))
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
        self._text.setText("Sto leggendo i tuoi ricordi…" + (f"  «{query[:40]}»" if query else ""))
        self._badge.setText("✦  Déjà · elaborazione")
        if self._collapsed: self._expand()
        self._loading = True
        self._shimmer_pos = 0.0
        self._shimmer_timer.start()
        self.show()

    def set_answer(self, text):
        self._loading = False
        self._shimmer_timer.stop()
        self._badge.setText("✦  Déjà · sintesi")
        self._text.setText(text or "Nessuna risposta.")
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
    lbl.setFont(QFont("Segoe UI", 11))

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
        head = QLabel(f"📸  Screenshot")
        head.setStyleSheet(f"color:{C_SS_HEX}; background:transparent; font-size:9px; font-weight:700; letter-spacing:1px;")
        info_lay.addWidget(head)

        app_short = app if len(app) <= 36 else app[:33] + "…"
        app_lbl = QLabel(app_short)
        app_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        app_lbl.setStyleSheet("color:#e6e6ec; background:transparent;")
        info_lay.addWidget(app_lbl)

        ts_lbl = QLabel(_human_ago(ts))
        ts_lbl.setFont(QFont("Segoe UI", 9))
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
        src_lbl = QLabel(f"🎙️  {'Microfono' if src == 'mic' else 'Sistema'}  ·  {_human_ago(ts)}")
        src_lbl.setStyleSheet(f"color:{C_AUDIO_HEX}; background:transparent; font-size:9px; font-weight:700; letter-spacing:1px;")
        info_lay.addWidget(src_lbl)

        snippet = transcript.replace("\n", " ").strip()
        snippet = snippet if len(snippet) <= 80 else snippet[:77] + "…"
        tr_lbl = QLabel(snippet or "(senza testo)")
        tr_lbl.setFont(QFont("Segoe UI", 10))
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
        lbl.setFont(QFont("Segoe UI", 11))
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("color:#ebebef; background:transparent; border:none;")
        self.inner.addWidget(lbl)
        return lbl

    def add_card(self, card):
        self.inner.addWidget(card)


# ── Chat page ──────────────────────────────────────────────────────
class ChatPage(QWidget):
    send_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 6, 14, 14); root.setSpacing(10)

        # Header
        head = QHBoxLayout(); head.setSpacing(10)
        title = QLabel("Déjà · Assistente AI")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C_AI_HEX}; background:transparent; letter-spacing:1px;")
        head.addWidget(title); head.addStretch()
        self.new_chat_btn = QPushButton("Nuova chat")
        self.new_chat_btn.setFixedHeight(28); self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(SS_BTN_OFF)
        head.addWidget(self.new_chat_btn)
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
        es_icon.setFont(QFont("Segoe UI", 28))
        es_icon.setStyleSheet(f"color:{C_AI_HEX}; background:transparent;")
        es.addWidget(es_icon)
        es_t = QLabel("Chiedimi qualsiasi cosa sui tuoi ricordi")
        es_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_t.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
        es_t.setStyleSheet("color:#e5e7eb; background:transparent;")
        es.addWidget(es_t)
        es_s = QLabel("Cerco io nei tuoi screenshot e audio.\nProva: \"cosa ho fatto oggi?\" o \"di cosa ho parlato ieri?\"")
        es_s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        es_s.setFont(QFont("Segoe UI", 10))
        es_s.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; line-height:1.6;")
        es.addWidget(es_s)
        self.msg_layout.insertWidget(0, self.empty_state)

        # Input row
        input_row = QHBoxLayout(); input_row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Scrivi un messaggio…")
        self.input.setFont(QFont("Segoe UI", 11))
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
        self.mic_btn.setToolTip("Detta messaggio (Ctrl+M)")
        self.mic_btn.setCheckable(True)
        self._set_mic_style(False)
        input_row.addWidget(self.mic_btn)

        self.send_btn = QPushButton("Invia"); self.send_btn.setFixedHeight(38); self.send_btn.setFixedWidth(80)
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
        notice.setFont(QFont("Segoe UI", 11))
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
        self.send_btn.setText("…" if busy else "Invia")


# ── Diary dialog (daily summaries AI) ─────────────────────────────
class DiaryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diario — Déjà")
        self.setMinimumSize(720, 560)
        # Sopra l'overlay stays-on-top, altrimenti finisce dietro.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(f"QDialog{{background:{BG_HEX};}}")

        root = QVBoxLayout(self); root.setContentsMargins(20, 18, 20, 16); root.setSpacing(12)

        head = QHBoxLayout(); head.setSpacing(8)
        title = QLabel("📖  Diario")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
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
        self.content_label.setFont(QFont("Segoe UI", 11))
        self.content_label.setStyleSheet("color:#e6e6ec; background:transparent; padding:18px;")
        self.content_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.content_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_scroll.setWidget(self.content_label)
        body.addWidget(self.content_scroll, stretch=1)

        root.addLayout(body, stretch=1)

        foot = QHBoxLayout(); foot.addStretch()
        close_btn = QPushButton("Chiudi"); close_btn.setFixedHeight(34); close_btn.setStyleSheet(SS_BTN_OFF)
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
            self.content_label.setText(
                "<i style='color:#8b8d98;'>Nessun diario salvato.<br><br>"
                "Clicca <b>✨ Genera oggi</b> per creare il riepilogo della giornata.</i>"
            )

    def _on_day_changed(self, row):
        item = self.day_list.item(row)
        if not item: return
        day = item.text()
        try:
            s = ai_assistant.load_daily_summary(day)
        except Exception as e:
            self.content_label.setText(f"⚠ {e}"); return
        if not s:
            self.content_label.setText("⚠ Diario non trovato"); return
        self.content_label.setText(_md_to_html(s["content"]))

    def _generate_selected(self):
        if self._gen_thread is not None and self._gen_thread.isRunning(): return
        day = self.gen_date.date().toString("yyyy-MM-dd")
        self.gen_btn.setEnabled(False); self.gen_btn.setText("⏳ Generazione…")
        self._gen_thread = _DailySummaryWorker(day)
        self._gen_thread.done.connect(self._on_gen_done)
        self._gen_thread.start()

    def _on_gen_done(self, ok, content_or_err, day_iso):
        self.gen_btn.setEnabled(True); self.gen_btn.setText("✨ Genera")
        if ok:
            try:
                ai_assistant.save_daily_summary(day_iso, content_or_err)
            except Exception as e:
                self.content_label.setText(f"⚠ Errore salvataggio: {e}"); return
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
class ContextDialog(QDialog):
    """Mostra ricordi ±N min attorno a un timestamp pivot."""
    def __init__(self, pivot_ts, pivot_label, parent=None, window_min=5):
        super().__init__(parent)
        self.setWindowTitle("Contesto temporale — Déjà")
        self.setMinimumSize(520, 520)
        self.setStyleSheet(f"QDialog{{background:{BG_HEX};}}")

        root = QVBoxLayout(self); root.setContentsMargins(20, 18, 20, 16); root.setSpacing(10)

        title = QLabel(f"🔗  Contesto ±{window_min} min")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C_AI_HEX}; background:transparent; letter-spacing:0.5px;")
        root.addWidget(title)

        sub = QLabel(f"Intorno a: {pivot_label}")
        sub.setFont(QFont("Segoe UI", 10))
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
            empty = QLabel("Nessun evento in questa finestra temporale.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color:{TEXT_SECONDARY}; padding:30px;")
            v.addWidget(empty)
        else:
            for kind, rid, ts, src, snippet in events:
                v.addWidget(self._make_item(kind, rid, ts, src, snippet))
            v.addStretch()

        # Footer close
        close_btn = QPushButton("Chiudi"); close_btn.setFixedHeight(34)
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
        head = QLabel(f"<b style='color:{accent_hex};'>{('Audio' if is_audio else 'Screenshot')}</b>  "
                      f"<span style='color:#8b8d98;'>· {_human_ago(ts)} · {(src if not is_audio else ('Microfono' if src == 'mic' else 'Sistema'))}</span>")
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

        for txt, size, color in [(info, 12, "#ffffff"), ("Premi ESC per chiudere", 9, TEXT_SECONDARY)]:
            lbl = QLabel(txt)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(QFont("Segoe UI", size, QFont.Weight.Medium))
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


class AskScreenDialog(QDialog):
    """Popup 'Chiedi allo schermo ora'. Cattura istantanea + AI streaming.

    Si apre via hotkey Ctrl+Shift+A. Mostra thumbnail dello screen + input
    domanda + risposta AI in streaming markdown.
    """
    def __init__(self, snap, parent=None):
        super().__init__(parent)
        self._snap = snap
        self._worker = None
        self._answer_buf = []
        self._closing = False

        self.setWindowTitle("Chiedi allo schermo — Déjà")
        self.setMinimumSize(720, 620)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Container con bordo arrotondato
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setStyleSheet(
            f"QFrame{{background:{BG_HEX}; border:1px solid {BORDER_STR}; "
            f"border-radius:14px;}}"
        )
        outer.addWidget(card)

        root = QVBoxLayout(card); root.setContentsMargins(20, 16, 20, 16); root.setSpacing(12)

        # Header
        head = QHBoxLayout(); head.setSpacing(8)
        title = QLabel("👁  Chiedi allo schermo")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
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
            self.thumb_label.setText("[anteprima non disponibile]")
            self.thumb_label.setFixedHeight(60)
        root.addWidget(self.thumb_label)

        # OCR preview info
        ocr_len = len((snap.get("text") or "").strip())
        info = QLabel(f"OCR: {ocr_len} caratteri estratti")
        info.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; font-size:9pt;")
        root.addWidget(info)

        # Question input
        in_row = QHBoxLayout(); in_row.setSpacing(8)
        self.question = QLineEdit()
        self.question.setPlaceholderText("Cosa vuoi sapere? (es. spiega questo errore, riassumi, traduci…)")
        self.question.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.04); color:#f3f4f6; "
            "border:1px solid rgba(255,255,255,0.10); border-radius:8px; "
            "padding:10px 12px; font-size:11pt;}"
            "QLineEdit:focus{border:1px solid rgba(167,139,250,0.55);}"
        )
        self.question.returnPressed.connect(self._on_send)
        in_row.addWidget(self.question, stretch=1)

        self.send_btn = QPushButton("Chiedi")
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
        self.answer_label.setFont(QFont("Segoe UI", 11))
        self.answer_label.setStyleSheet("color:#e6e6ec; background:transparent; padding:14px;")
        self.answer_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.answer_label.setTextFormat(Qt.TextFormat.RichText)
        self.answer_label.setText(
            "<i style='color:#8b8d98;'>Scrivi una domanda e premi Invio. "
            "L'AI risponderà basandosi su ciò che vedi adesso.</i>"
        )
        self.answer_scroll.setWidget(self.answer_label)
        root.addWidget(self.answer_scroll, stretch=1)

        # Footer
        foot = QHBoxLayout(); foot.setSpacing(8)
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; font-size:9pt;")
        foot.addWidget(self.status_lbl); foot.addStretch()
        hint = QLabel("Esc per chiudere · Invio per chiedere")
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
            self.answer_label.setText(
                "<span style='color:#ef4444;'>⚠ Nessuna AI configurata. "
                "Vai in Impostazioni → AI (text o Vision).</span>"
            )
            return
        self.send_btn.setEnabled(False); self.send_btn.setText("⏳")
        self.question.setEnabled(False)
        self.status_lbl.setText("AI sta pensando…")
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
        self.send_btn.setEnabled(True); self.send_btn.setText("Chiedi")
        self.question.setEnabled(True); self.question.setFocus()
        self.status_lbl.setText("✓ Risposta completa")

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
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    return dlg


# ── Main window ────────────────────────────────────────────────────
class DejaWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Déjà")
        self.setFixedWidth(OVERLAY_W)
        self.setFixedHeight(OVERLAY_H_COMPACT)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._worker = self._all_worker = None
        self._results = []; self._filtered = []; self._all_results = []
        self._all_mode = False; self._all_loading = False
        self._active_date = self._active_filter = "all"
        self._current_pixmap = self._current_audio = self._current_type = None
        self._drag_pos = self._anim = None; self._busy = False
        self._fullscreen_mode = False
        self._prev_geom = None

        # ── Chat state ──
        self._chat_mode = False
        self._chat_history = []           # list of {role, content} — sent to AI
        self._chat_worker = None
        self._chat_current_bubble = None  # active assistant QLabel being streamed
        self._chat_current_text = ""
        self._chat_current_container = None  # container widget bolla corrente
        self._chat_thinking = None        # thinking bubble widget (to remove on first chunk)
        self._chat_turn_bubbles = []      # list of {container, label, text} per turno
        self._chat_loaded = False         # cronologia DB caricata?
        self._chat_audio_playing = None   # (card_widget, audio_id) attivo
        self._voice_worker = None
        self._voice_stop_event = None

        # ── Inline RAG ──
        self._rag_worker = None

        # ── Audio player state ──────────────────────────────────
        self._audio_data = None
        self._audio_offset = 0
        self._playback_start = None
        self._is_playing = False
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(80)
        self._playback_timer.timeout.connect(self._update_slider)
        self._build_ui()
        self._update_mask()
        self._center_on_screen()

        # Premium drop shadow
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(110); sh.setOffset(0, 28); sh.setColor(QColor(0, 0, 0, 220))
        self.setGraphicsEffect(sh)

        # Drag & drop image → OCR → search
        self.setAcceptDrops(True)

        # Particle background (subtle drift)
        import random as _rnd
        self._particles = []
        for _ in range(28):
            self._particles.append([
                _rnd.uniform(0, OVERLAY_W),                # x
                _rnd.uniform(0, OVERLAY_H_EXPANDED),       # y
                _rnd.uniform(0.05, 0.15),                  # vx
                _rnd.uniform(0.05, 0.12),                  # vy
                _rnd.uniform(0.6, 2.0),                    # radius
                _rnd.uniform(5, 14),                       # alpha (0-255 max ~14)
            ])
        self._particle_timer = QTimer(self)
        self._particle_timer.setInterval(60)
        self._particle_timer.timeout.connect(self._tick_particles)
        self._particle_timer.start()

    def _tick_particles(self):
        w = self.width() or OVERLAY_W
        h = self.height() or OVERLAY_H_COMPACT
        for p in self._particles:
            p[0] += p[2]
            p[1] -= p[3]
            if p[0] > w: p[0] = 0
            if p[1] < 0: p[1] = h
        # Solo redraw se visibile
        if self.isVisible(): self.update()

    def _update_mask(self):
        path = QPainterPath(); path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 18, 18)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, e): super().resizeEvent(e); self._update_mask()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath(); path.addRoundedRect(rect, 18, 18)

        # Base background — gradient verticale sottile (depth)
        base = QLinearGradient(0, 0, 0, self.height())
        base.setColorAt(0.0, QColor(20, 20, 26, 248))
        base.setColorAt(1.0, QColor(12, 12, 16, 248))
        p.fillPath(path, QBrush(base))

        # Spotlight superiore (luce)
        spot = QRadialGradient(self.width() / 2, -20, self.width() * 0.8)
        spot.setColorAt(0.0, QColor(255, 255, 255, 18))
        spot.setColorAt(0.6, QColor(255, 255, 255, 4))
        spot.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(spot))

        # Vignetta angoli (subtle)
        vig = QRadialGradient(self.width() / 2, self.height() / 2, max(self.width(), self.height()) * 0.7)
        vig.setColorAt(0.7, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 40))
        p.fillPath(path, QBrush(vig))

        # Particle layer (drift sottile)
        if hasattr(self, "_particles"):
            p.setClipPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            for px, py, _vx, _vy, r, a in self._particles:
                p.setBrush(QBrush(QColor(167, 139, 250, int(a))))
                p.drawEllipse(QPointF(px, py), r, r)
            p.setClipping(False)

        # Bordo doppio: esterno chiaro + interno sottile
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1.0))
        p.drawPath(path)
        inner = QPainterPath(); inner.addRoundedRect(rect.adjusted(1, 1, -1, -1), 17, 17)
        p.setPen(QPen(QColor(255, 255, 255, 8), 1.0))
        p.drawPath(inner)

        # Accent top — sottile linea evidenziata in alto
        top_grad = QLinearGradient(0, 0, self.width(), 0)
        top_grad.setColorAt(0.0, QColor(167, 139, 250, 0))
        top_grad.setColorAt(0.5, QColor(167, 139, 250, 60))
        top_grad.setColorAt(1.0, QColor(167, 139, 250, 0))
        p.setPen(QPen(QBrush(top_grad), 1.0))
        p.drawLine(int(rect.left() + 14), int(rect.top() + 1), int(rect.right() - 14), int(rect.top() + 1))

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── Search bar ─────────────────────────────────────────────
        sw = QWidget(); sw.setFixedHeight(OVERLAY_H_COMPACT); sw.setStyleSheet("background:transparent;")
        sl = QHBoxLayout(sw); sl.setContentsMargins(24, 0, 20, 0); sl.setSpacing(14)

        ic = _SearchIcon(); ic.setFixedSize(28, 28); sl.addWidget(ic)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca nei tuoi ricordi…")
        self.search_input.setFont(QFont("Segoe UI", 16, QFont.Weight.Normal))
        self.search_input.setStyleSheet(
            f"QLineEdit{{border:none; background:transparent; color:{TEXT_PRIMARY}; "
            f"selection-background-color:rgba(167,139,250,0.35); selection-color:#ffffff;}}"
        )
        self.search_input.returnPressed.connect(self._do_search)
        self.search_input.textChanged.connect(self._on_text_changed)
        # History completer
        from PyQt6.QtWidgets import QCompleter
        from PyQt6.QtCore import QStringListModel
        self._search_history_model = QStringListModel()
        self._search_completer = QCompleter(self._search_history_model, self.search_input)
        self._search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._search_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        popup = self._search_completer.popup()
        popup.setStyleSheet(
            "background:#1a1a1f; color:#f3f4f6; border:1px solid rgba(255,255,255,0.10); "
            "border-radius:8px; padding:4px; font-size:11px;"
            " selection-background-color: rgba(167,139,250,0.30);"
        )
        self.search_input.setCompleter(self._search_completer)
        self._refresh_search_completer()
        sl.addWidget(self.search_input)

        self.kbd = QLabel("↵  Invio"); self.kbd.setFixedHeight(24)
        self.kbd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.kbd.setContentsMargins(8, 0, 8, 0)
        self.kbd.setStyleSheet(
            f"QLabel{{color:{TEXT_SECONDARY}; background:rgba(255,255,255,0.04); "
            f"border:1px solid rgba(255,255,255,0.10); border-radius:6px; "
            f"font-size:10px; font-weight:600; letter-spacing:0.8px;}}"
        )
        self.kbd.hide(); sl.addWidget(self.kbd)

        self.all_btn = QPushButton("Esplora"); self.all_btn.setFixedHeight(30); self.all_btn.setFixedWidth(84)
        self.all_btn.setStyleSheet(SS_BTN_OFF)
        self.all_btn.clicked.connect(self._show_all); self.all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sl.addWidget(self.all_btn)

        self.chat_btn = QPushButton("Chat"); self.chat_btn.setFixedHeight(30); self.chat_btn.setFixedWidth(72)
        self.chat_btn.setStyleSheet(SS_BTN_OFF); self.chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chat_btn.clicked.connect(self._show_chat)
        sl.addWidget(self.chat_btn)

        root.addWidget(sw)

        self.sep = QWidget(); self.sep.setFixedHeight(1); self.sep.setStyleSheet(f"background:{BORDER_STR};"); self.sep.hide()
        root.addWidget(self.sep)

        # ── Status ─────────────────────────────────────────────────
        self.status = QLabel(); self.status.setFixedHeight(22)
        self.status.setContentsMargins(24, 6, 0, 0)
        self.status.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.status.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; letter-spacing:1px;")
        self.status.hide(); root.addWidget(self.status)

        # ── Date Filter ────────────────────────────────────────────
        self.date_bar = QWidget(); self.date_bar.setFixedHeight(34); self.date_bar.setStyleSheet("background:transparent;")
        dl = QHBoxLayout(self.date_bar); dl.setContentsMargins(24, 0, 24, 0); dl.setSpacing(12)
        self._dbtn = {}
        for lbl, key in [("Oggi", "today"), ("Ieri", "yesterday"), ("7 giorni", "week"), ("Tutto", "all")]:
            b = QPushButton(lbl); b.setFixedHeight(28); b.setCursor(Qt.CursorShape.PointingHandCursor)
            force_style(b, date_pill(key == "all")); b.clicked.connect(lambda _, k=key: self._apply_date_filter(k))
            self._dbtn[key] = b; dl.addWidget(b)
        dl.addStretch(); self.date_bar.hide(); root.addWidget(self.date_bar)

        # ── Category Filter ────────────────────────────────────────
        self.filter_bar = QWidget(); self.filter_bar.setFixedHeight(36); self.filter_bar.setStyleSheet("background:transparent;")
        fl = QHBoxLayout(self.filter_bar); fl.setContentsMargins(24, 0, 24, 0); fl.setSpacing(10)
        self._fbtn = {}
        for key, lbl in [("all", "Tutto"), ("screenshot", "Immagini"), ("audio", "Audio")]:
            b = QPushButton(lbl); b.setFixedHeight(28); b.setCursor(Qt.CursorShape.PointingHandCursor)
            force_style(b, pill(key == "all", key)); b.clicked.connect(lambda _, k=key: self._set_filter(k))
            self._fbtn[key] = b; fl.addWidget(b)
        fl.addStretch(); self.filter_bar.hide(); root.addWidget(self.filter_bar)

        # ── Sidebar (visibile solo in fullscreen) ─────────────
        self._sidebar = QWidget(); self._sidebar.setFixedWidth(SIDEBAR_W)
        self._sidebar.setStyleSheet("background:transparent;"); self._sidebar.hide()
        sb_layout = QVBoxLayout(self._sidebar); sb_layout.setContentsMargins(10, 8, 10, 16); sb_layout.setSpacing(10)

        # Titolo sidebar
        sb_title = QLabel("DÉJÀ"); sb_title.setFont(QFont("Segoe UI", 19, QFont.Weight.Bold))
        sb_title.setStyleSheet(f"color:#f3f4f6; background:transparent; letter-spacing:5px;")
        sb_title.setAlignment(Qt.AlignmentFlag.AlignCenter); sb_layout.addWidget(sb_title)

        sb_sub = QLabel("memoria digitale"); sb_sub.setFont(QFont("Segoe UI", 8))
        sb_sub.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; letter-spacing:3px;")
        sb_sub.setAlignment(Qt.AlignmentFlag.AlignCenter); sb_layout.addWidget(sb_sub)

        # Accent line viola sotto titolo
        accent = QFrame(); accent.setFixedHeight(2); accent.setFixedWidth(40)
        accent.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                              f"stop:0 transparent, stop:0.5 {C_AI_HEX}, stop:1 transparent); border-radius:1px;")
        wrap_acc = QHBoxLayout(); wrap_acc.setAlignment(Qt.AlignmentFlag.AlignCenter); wrap_acc.addWidget(accent)
        sb_layout.addLayout(wrap_acc)

        sep_sb = QFrame(); sep_sb.setFrameShape(QFrame.Shape.HLine)
        sep_sb.setStyleSheet("background:rgba(255,255,255,0.06); max-height:1px;"); sb_layout.addWidget(sep_sb)

        # Stats live (in card subtle)
        stats_wrap = QWidget()
        stats_wrap.setStyleSheet(
            "QWidget{background:rgba(255,255,255,0.02); "
            "border:1px solid rgba(255,255,255,0.05); border-radius:10px;}"
        )
        stats_lay = QVBoxLayout(stats_wrap); stats_lay.setContentsMargins(12, 10, 12, 10)
        self._sb_stats = QLabel("—"); self._sb_stats.setFont(QFont("Segoe UI", 10))
        self._sb_stats.setStyleSheet(f"color:#d1d5db; background:transparent; border:none;")
        self._sb_stats.setWordWrap(True); stats_lay.addWidget(self._sb_stats)
        sb_layout.addWidget(stats_wrap)

        sep_sb2 = QFrame(); sep_sb2.setFrameShape(QFrame.Shape.HLine)
        sep_sb2.setStyleSheet("background:rgba(255,255,255,0.06); max-height:1px;"); sb_layout.addWidget(sep_sb2)

        # Pulsanti sidebar
        def _sb_btn(label, icon="", tooltip=""):
            b = QPushButton(f"{icon}  {label}" if icon else label)
            b.setFixedHeight(36); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tooltip)
            b.setStyleSheet(
                f"QPushButton{{background:rgba(255,255,255,0.04); color:#d1d5db; "
                f"border:1px solid {BORDER_STR}; border-radius:9px; font-size:12px; font-weight:500; text-align:left; padding:0 14px;}}"
                "QPushButton:hover{background:rgba(255,255,255,0.10); color:#ffffff;}")
            return b

        self._sb_export_btn = _sb_btn("Esporta ricordi", "📤", "Esporta tutto in JSON")
        self._sb_export_btn.clicked.connect(self._export_memories)
        sb_layout.addWidget(self._sb_export_btn)

        self._sb_clear_btn = _sb_btn("Svuota database", "🗑️", "Elimina tutti i dati")
        self._sb_clear_btn.clicked.connect(self._confirm_clear)
        self._sb_clear_btn.setStyleSheet(
            "QPushButton{background:rgba(239,68,68,0.08); color:#f87171; "
            f"border:1px solid rgba(239,68,68,0.25); border-radius:9px; font-size:12px; font-weight:500; text-align:left; padding:0 14px;}}"
            "QPushButton:hover{background:rgba(239,68,68,0.18);}")
        sb_layout.addWidget(self._sb_clear_btn)

        self._sb_pinned_btn = _sb_btn("Pinned", "⭐", "Mostra solo ricordi marcati con stella")
        self._sb_pinned_btn.clicked.connect(self._show_pinned)
        sb_layout.addWidget(self._sb_pinned_btn)

        self._sb_date_btn = _sb_btn("Filtra date", "📅", "Range data custom")
        self._sb_date_btn.clicked.connect(self._open_date_filter)
        sb_layout.addWidget(self._sb_date_btn)

        # Separator + Apps section
        sb_sep_apps = QFrame(); sb_sep_apps.setFrameShape(QFrame.Shape.HLine)
        sb_sep_apps.setStyleSheet("background:rgba(255,255,255,0.06); max-height:1px;")
        sb_layout.addWidget(sb_sep_apps)
        apps_lbl = QLabel("APP")
        apps_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        apps_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; letter-spacing:2px; padding-left:2px;")
        sb_layout.addWidget(apps_lbl)

        # Lista app scrollabile
        self._sb_apps_list = QListWidget()
        self._sb_apps_list.setStyleSheet(f"""
            QListWidget {{ background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); border-radius:8px; outline:none; padding:4px; }}
            QListWidget::item {{ color:#d1d5db; padding:5px 8px; border-radius:4px; font-size:10pt; }}
            QListWidget::item:hover {{ background:rgba(255,255,255,0.05); }}
            QListWidget::item:selected {{ background:rgba(167,139,250,0.20); color:#ffffff; }}
            QScrollBar:vertical {{ background:transparent; width:6px; }}
            QScrollBar::handle:vertical {{ background:rgba(255,255,255,0.10); border-radius:3px; min-height:24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        self._sb_apps_list.itemClicked.connect(self._on_app_filter)
        sb_layout.addWidget(self._sb_apps_list, stretch=1)

        sb_layout.addStretch()

        # ── Stack & Splitter ───────────────────────────────────────
        self.stack = QStackedWidget(); self.stack.setStyleSheet("background:transparent;"); self.stack.hide()
        self.loading_page = LoadingPage(); self.stack.addWidget(self.loading_page)

        split_container = QWidget(); split_container.setStyleSheet("background:transparent;")
        split_layout = QHBoxLayout(split_container); split_layout.setContentsMargins(14, 6, 14, 16); split_layout.setSpacing(12)

        split_layout.addWidget(self._sidebar)

        # ── Results column (AI card + results list) ──
        self._results_col = QWidget(); self._results_col.setStyleSheet("background:transparent;")
        self._results_col.setFixedWidth(320)
        results_col_lay = QVBoxLayout(self._results_col)
        results_col_lay.setContentsMargins(0, 0, 0, 0); results_col_lay.setSpacing(8)

        self.ai_card = AIAnswerCard()
        results_col_lay.addWidget(self.ai_card)

        self.results_list = QListWidget()
        self.results_list.setSpacing(4)
        self.results_list.setWordWrap(True); self.results_list.setUniformItemSizes(True)
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_list.setMouseTracking(True)
        self.results_list.setStyleSheet(f"""
            QListWidget {{ background:transparent; border:none; outline:none; }}
            QListWidget::item {{ background:transparent; border:none; }}
            QScrollBar:vertical {{ background:transparent; width:8px; margin:6px 2px; }}
            QScrollBar::handle:vertical {{
                background:rgba(255,255,255,0.10); border-radius:3px; min-height:30px;
            }}
            QScrollBar::handle:vertical:hover {{ background:rgba(167,139,250,0.40); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
        """)
        self.results_list.setItemDelegate(MinimalItemDelegate(self.results_list))
        self.results_list.currentRowChanged.connect(self._on_row_changed)
        self.results_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.results_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(self._on_results_context_menu)
        results_col_lay.addWidget(self.results_list, stretch=1)
        split_layout.addWidget(self._results_col)

        self._preview_panel = PreviewPanel()
        pv_layout = QVBoxLayout(self._preview_panel); pv_layout.setContentsMargins(16, 12, 16, 16); pv_layout.setSpacing(12)

        self.preview_info = QLabel(); self.preview_info.setFixedHeight(18)
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_info.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.preview_info.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent; letter-spacing:0.5px;")
        pv_layout.addWidget(self.preview_info)

        top_br = QHBoxLayout(); top_br.setSpacing(10)
        self.fs_btn = QPushButton("Espandi"); self.fs_btn.setFixedHeight(34)
        self.fs_btn.setEnabled(False); self.fs_btn.setStyleSheet(SS_BTN_OFF); self.fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fs_btn.clicked.connect(self._open_fullscreen); top_br.addWidget(self.fs_btn)

        self.play_btn = QPushButton("Ascolta"); self.play_btn.setFixedHeight(34)
        self.play_btn.setEnabled(False); self.play_btn.setStyleSheet(SS_BTN_OFF); self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self._play_audio); top_br.addWidget(self.play_btn)

        self.ctx_btn = QPushButton("🔗 Contesto"); self.ctx_btn.setFixedHeight(34)
        self.ctx_btn.setEnabled(False)
        self.ctx_btn.setStyleSheet(SS_BTN_OFF); self.ctx_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ctx_btn.setToolTip("Mostra cosa accadeva intorno a questo ricordo (±5 min)")
        self.ctx_btn.clicked.connect(self._show_context)
        top_br.addWidget(self.ctx_btn)

        self.pin_btn = QPushButton("☆"); self.pin_btn.setFixedHeight(34); self.pin_btn.setFixedWidth(40)
        self.pin_btn.setEnabled(False); self.pin_btn.setStyleSheet(SS_BTN_OFF)
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.setToolTip("Pinna/spinna ricordo")
        self.pin_btn.clicked.connect(self._toggle_pin)
        top_br.addWidget(self.pin_btn)

        pv_layout.addLayout(top_br)

        # Tag row
        tag_row = QHBoxLayout(); tag_row.setSpacing(6)
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Aggiungi tag (Enter)")
        self.tag_input.setFixedHeight(28)
        self.tag_input.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,0.03); color:#e5e7eb; "
            f"border:1px solid {BORDER_STR}; border-radius:7px; padding:0 10px; font-size:10pt;}}"
            f"QLineEdit:focus{{border:1px solid rgba(167,139,250,0.4);}}"
        )
        self.tag_input.returnPressed.connect(self._on_add_tag)
        self.tag_input.setEnabled(False)
        tag_row.addWidget(self.tag_input)
        self.tags_label = QLabel("")
        self.tags_label.setStyleSheet("color:#a78bfa; background:transparent; font-size:9pt;")
        self.tags_label.setTextFormat(Qt.TextFormat.RichText)
        self.tags_label.setWordWrap(True)
        tag_row.addWidget(self.tags_label, stretch=1)
        pv_layout.addLayout(tag_row)

        # ── Audio Player Bar (slider + time) ──────────────────────
        self.audio_player_bar = QWidget()
        self.audio_player_bar.setStyleSheet("background:transparent;")
        ap_layout = QVBoxLayout(self.audio_player_bar)
        ap_layout.setContentsMargins(0, 4, 0, 0); ap_layout.setSpacing(4)
        self.waveform = WaveformWidget()
        ap_layout.addWidget(self.waveform)
        self.audio_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_slider.setMinimum(0); self.audio_slider.setValue(0)
        self.audio_slider.setStyleSheet(SS_SLIDER_AUDIO)
        self.audio_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audio_slider.sliderPressed.connect(self._on_slider_pressed)
        self.audio_slider.sliderReleased.connect(self._on_slider_released)
        self.audio_slider.sliderMoved.connect(self._on_slider_moved)
        ap_layout.addWidget(self.audio_slider)
        time_row = QHBoxLayout(); time_row.setContentsMargins(2, 0, 2, 0)
        self.audio_time_cur = QLabel("0:00")
        self.audio_time_cur.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.audio_time_cur.setStyleSheet(f"color:{C_AUDIO_HEX}; background:transparent;")
        self.audio_time_total = QLabel("0:00")
        self.audio_time_total.setFont(QFont("Segoe UI", 9))
        self.audio_time_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.audio_time_total.setStyleSheet(f"color:{TEXT_SECONDARY}; background:transparent;")
        time_row.addWidget(self.audio_time_cur); time_row.addStretch(); time_row.addWidget(self.audio_time_total)
        ap_layout.addLayout(time_row)
        self.audio_player_bar.hide()
        pv_layout.addWidget(self.audio_player_bar)

        self.preview_scroll = QScrollArea(); self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet(f"background:transparent; border:none; QScrollBar:vertical{{background:transparent; width:5px;}} QScrollBar::handle:vertical{{background:{BORDER_STR}; border-radius:2px;}}")
        self.preview_lbl = ClickableLabel(); self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("background:transparent;")
        self.preview_lbl.dbl.connect(self._open_fullscreen)
        self.preview_scroll.setWidget(self.preview_lbl); pv_layout.addWidget(self.preview_scroll, stretch=1)

        split_layout.addWidget(self._preview_panel, stretch=1)
        self.stack.addWidget(split_container)

        # ── Chat page (stack index 2) ──
        self.chat_page = ChatPage()
        self.chat_page.send_clicked.connect(self._send_chat_message)
        self.chat_page.new_chat_btn.clicked.connect(self._reset_chat)
        self.chat_page.mic_btn.clicked.connect(self._toggle_voice_input)
        self.stack.addWidget(self.chat_page)

        root.addWidget(self.stack, stretch=1)

    # ── Helpers ─────────────────────────────────────────────────────
    def _set_action_btns(self, kind="neutral"):
        if kind == "audio":
            self.fs_btn.setEnabled(False); self.fs_btn.setStyleSheet(SS_BTN_OFF)
            self.play_btn.setEnabled(True); self.play_btn.setStyleSheet(SS_BTN_AUDIO_ON)
            self.ctx_btn.setEnabled(True); self.ctx_btn.setStyleSheet(SS_BTN_AI_ON)
        elif kind == "screenshot":
            self.fs_btn.setEnabled(True); self.fs_btn.setStyleSheet(SS_BTN_SS_ON)
            self.play_btn.setEnabled(False); self.play_btn.setStyleSheet(SS_BTN_OFF)
            self.ctx_btn.setEnabled(True); self.ctx_btn.setStyleSheet(SS_BTN_AI_ON)
        else:
            self.fs_btn.setEnabled(False); self.fs_btn.setStyleSheet(SS_BTN_OFF)
            self.play_btn.setEnabled(False); self.play_btn.setStyleSheet(SS_BTN_OFF)
            self.ctx_btn.setEnabled(False); self.ctx_btn.setStyleSheet(SS_BTN_OFF)
            if hasattr(self, "pin_btn"):
                self.pin_btn.setEnabled(False); self.pin_btn.setStyleSheet(SS_BTN_OFF)
                self.pin_btn.setText("☆")
            if hasattr(self, "tag_input"):
                self.tag_input.setEnabled(False); self.tag_input.clear()
            if hasattr(self, "tags_label"):
                self.tags_label.setText("")

    def _center_on_screen(self):
        g = QApplication.primaryScreen().availableGeometry()
        self.move((g.width() - OVERLAY_W) // 2, int(g.height() * 0.22))

    def _animate_height(self, h):
        # Stop animazione precedente per evitare race
        if self._anim is not None:
            try: self._anim.stop()
            except Exception: pass
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(260); self._anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        g = self.geometry()
        self._anim.setStartValue(g); self._anim.setEndValue(QRect(g.x(), g.y(), OVERLAY_W, h))
        self._anim.finished.connect(self._update_mask)
        self._anim.start()

    def _redraw(self):
        self.layout().activate()
        for w in self.findChildren(QWidget):
            if w.isVisible(): w.update(); w.repaint()
        self.update(); self.repaint(); QApplication.processEvents()

    def _style_dpills(self):
        for k, b in self._dbtn.items(): force_style(b, date_pill(k == self._active_date))
    def _style_fpills(self):
        for k, b in self._fbtn.items(): force_style(b, pill(k == self._active_filter, k))

    def _set_input(self, placeholder="Cerca nei tuoi ricordi...", ro=False, color=TEXT_PRIMARY):
        self.search_input.blockSignals(True)
        self.search_input.setReadOnly(ro)
        self.search_input.setPlaceholderText(placeholder)
        self.search_input.setStyleSheet(f"border:none; background:transparent; color:{color};")
        if not ro: self.search_input.clear()
        self.search_input.blockSignals(False)

    def _reset_all_btn(self):
        self.all_btn.setText("Esplora"); self.all_btn.setFixedWidth(84); self.all_btn.setStyleSheet(SS_BTN_OFF)
        try: self.all_btn.clicked.disconnect()
        except Exception: pass
        self.all_btn.clicked.connect(self._show_all)

    def _show_loading(self):
        self.stack.setCurrentIndex(0); self.stack.show(); self.loading_page.start()

    def _show_results_page(self):
        self.loading_page.stop(); self.stack.setCurrentIndex(1); self.stack.show()
        self.stack.currentWidget().update(); self.stack.currentWidget().repaint()
        self.stack.update(); self.stack.repaint()

    def toggle(self):
        if self.isVisible(): self.hide()
        else: self._center_on_screen(); self.show(); self.raise_(); self.activateWindow(); self.search_input.setFocus()

    def _on_text_changed(self, text):
        if self._all_mode or self.search_input.isReadOnly(): return
        self.kbd.setVisible(bool(text.strip()))
        if not text.strip(): self._collapse()


    def dragEnterEvent(self, e):
        urls = e.mimeData().urls() if e.mimeData() else []
        if any(u.toLocalFile().lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")) for u in urls):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        urls = e.mimeData().urls() if e.mimeData() else []
        for u in urls:
            path = u.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                self._search_from_image(path)
                e.acceptProposedAction()
                return
        e.ignore()

    def _search_from_image(self, path):
        try:
            self.toast(f"OCR su {path.split('/')[-1].split(chr(92))[-1]}…", level="info", duration_ms=2000)
            QApplication.processEvents()
            import pytesseract
            from PIL import Image
            from config import OCR_LANG
            img = Image.open(path)
            text = pytesseract.image_to_string(img, lang=OCR_LANG).strip()
        except Exception as e:
            self.toast(f"OCR fallito: {e}", level="error", duration_ms=4500)
            return
        if not text:
            self.toast("Nessun testo estratto dall'immagine", level="warn", duration_ms=3500)
            return
        # Prendi prime parole significative come query (max 80 char)
        snippet = " ".join(text.split())[:80]
        self.toast(f"Cerco: {snippet[:50]}{'…' if len(snippet) > 50 else ''}", level="ok", duration_ms=2500)
        if not self.isVisible():
            self._center_on_screen(); self.show(); self.raise_(); self.activateWindow()
        self.search_input.setText(snippet)
        self._do_search()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton: self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _): self._drag_pos = None

    def _collapse(self):
        # Idempotente: niente _busy guard (causa layout overflow se saltato)
        try:
            # Stop animazioni pendenti per evitare race con fixed height
            if self._anim is not None:
                try: self._anim.stop()
                except Exception: pass
                self._anim = None
            self.loading_page.stop()
            for w in (self.sep, self.status, self.date_bar, self.filter_bar, self.stack): w.hide()
            self.results_list.blockSignals(True); self.results_list.clear(); self.results_list.blockSignals(False)
            self.preview_lbl.clear(); self.preview_lbl.setPixmap(QPixmap()); self.preview_info.setText("")
            self._set_action_btns("neutral"); self._preview_panel.set_border_kind("neutral")
            self.ai_card.reset()
            self._results = []; self._filtered = []; self._all_results = []; self._all_mode = False
            self._all_loading = False
            self._chat_mode = False
            self._active_date = self._active_filter = "all"; self._current_pixmap = self._current_audio = self._current_type = None
            self.kbd.hide(); self._set_input(); self._reset_all_btn(); self._reset_chat_btn()
            self.setFixedHeight(OVERLAY_H_COMPACT)
            self._animate_height(OVERLAY_H_COMPACT)
            self._redraw()
        finally:
            self._busy = False

    def _reset_chat_btn(self):
        self.chat_btn.setText("Chat"); self.chat_btn.setFixedWidth(72); self.chat_btn.setStyleSheet(SS_BTN_OFF)
        try: self.chat_btn.clicked.disconnect()
        except Exception: pass
        self.chat_btn.clicked.connect(self._show_chat)

    def _do_search(self):
        q = self.search_input.text().strip()
        if not q: return
        # Salva in history
        try:
            from db import save_search_query
            save_search_query(q)
            self._refresh_search_completer()
        except Exception as e: print(f"[Search] save history fail: {e}")
        self._all_mode = False; self._all_loading = False; self._chat_mode = False; self._active_filter = "all"
        self._reset_chat_btn(); self.ai_card.reset()
        self.sep.show()
        self.status.setStyleSheet(f"color:{TEXT_SECONDARY};background:transparent;font-size:10px;font-weight:600;letter-spacing:1px;")
        self.status.setText("RICERCA IN CORSO..."); self.status.show()
        self.date_bar.hide(); self.filter_bar.hide()
        self.results_list.blockSignals(True); self.results_list.clear(); self.results_list.blockSignals(False)
        self.preview_lbl.clear(); self.preview_lbl.setPixmap(QPixmap()); self.preview_info.setText("")
        self._set_action_btns("neutral"); self._preview_panel.set_border_kind("neutral")
        self._results = []; self._filtered = []; self._current_pixmap = self._current_audio = None
        self.setFixedHeight(OVERLAY_H_EXPANDED); self._animate_height(OVERLAY_H_EXPANDED)
        self._show_loading(); self._redraw()
        self._worker = SearchWorker(q)
        self._worker.done.connect(self._on_search_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_search_done(self, results):
        self._results = results; self._active_filter = "all"
        self.ai_card.reset()
        if not results:
            self.loading_page.stop(); self.stack.hide()
            self.results_list.blockSignals(True); self.results_list.clear(); self.results_list.blockSignals(False)
            self.preview_lbl.clear(); self.preview_lbl.setPixmap(QPixmap()); self.preview_info.setText("")
            self._set_action_btns("neutral"); self.sep.show(); self.status.show()
            self.status.setStyleSheet(f"color:#ef4444;background:transparent;font-size:10px;font-weight:600;letter-spacing:1px;")
            self.status.setText("NESSUN RISULTATO TROVATO")
            self.setFixedHeight(OVERLAY_H_COMPACT); self._animate_height(OVERLAY_H_COMPACT); self._redraw()
            return
        has_a = any(r.get("type") == "audio" for r in results); has_s = any(r.get("type") == "screenshot" for r in results)
        if has_a and has_s: self._style_fpills(); self.filter_bar.show(); self.filter_bar.repaint()
        else: self.filter_bar.hide()
        self.status.setStyleSheet(f"color:{TEXT_SECONDARY};background:transparent;font-size:10px;font-weight:600;")
        self.status.setText(f"{len(results)} RISULTATI")
        self._apply_filter(); self._show_results_page(); self._redraw()
        # Trigger AI inline summary if enabled
        try:
            q = self.search_input.text().strip()
            self._maybe_trigger_inline_rag(q, results)
        except Exception as e:
            print(f"[RAG inline] errore trigger: {e}")

    def _show_all(self):
        self._all_mode = True; self._chat_mode = False; self._all_results = []; self._active_date = self._active_filter = "all"
        self._all_loading = True  # AllWorker in corso: i click sui filtri non devono mostrare "NESSUN ELEMENTO"
        self._reset_chat_btn(); self.ai_card.reset()
        self._set_input(placeholder="Esplora la timeline...", ro=True, color=TEXT_SECONDARY)
        self.kbd.hide()
        self.all_btn.setText("Chiudi"); self.all_btn.setFixedWidth(84)
        self.all_btn.setStyleSheet(f"QPushButton{{background:rgba(255,255,255,0.1); color:#ffffff; border:1px solid {BORDER_STR}; border-radius:8px; font-size:12px; font-weight:600; padding:6px 14px;}} QPushButton:hover{{background:rgba(255,255,255,0.15);}}")
        try: self.all_btn.clicked.disconnect()
        except Exception: pass
        self.all_btn.clicked.connect(self._collapse)
        self.sep.show(); self.status.setStyleSheet(f"color:{TEXT_SECONDARY};background:transparent;font-size:10px;font-weight:600;letter-spacing:1px;")
        self.status.setText("CARICAMENTO TIMELINE..."); self.status.show(); self.date_bar.show(); self._style_dpills()
        self.filter_bar.hide(); self.results_list.blockSignals(True); self.results_list.clear(); self.results_list.blockSignals(False)
        self.preview_lbl.clear(); self.preview_lbl.setPixmap(QPixmap()); self.preview_info.setText("")
        self._set_action_btns("neutral"); self._preview_panel.set_border_kind("neutral")
        self._results = []; self._filtered = []; self._current_pixmap = self._current_audio = None
        self.setFixedHeight(OVERLAY_H_EXPANDED); self._animate_height(OVERLAY_H_EXPANDED)
        self._show_loading(); self._redraw()
        self._all_worker = AllWorker(); self._all_worker.done.connect(self._on_all_done); self._all_worker.start()

    def _on_all_done(self, results):
        # Guard contro race: l'utente può chiudere l'overlay (o premere "Chiudi",
        # o cambiare modalità) mentre AllWorker gira in un thread. Con un DB grande
        # get_all() è lento e la callback può arrivare tardi: senza questo guard
        # ridisegnerebbe la UI "Esplora" (status + date_bar) sopra un overlay già
        # collassato a 76px, causando l'overlap del testo (issue #2).
        if not self._all_mode:
            return
        self._all_loading = False  # dati arrivati: i filtri possono valutare l'esito reale
        self._all_results = results
        # Riafferma l'altezza espansa: se l'animazione di _show_all è stata
        # interrotta o la finestra è tornata compatta, i risultati avrebbero
        # un'altezza insufficiente e si sovrapporrebbero alla barra di ricerca.
        if self.height() < OVERLAY_H_EXPANDED:
            self.setFixedHeight(OVERLAY_H_EXPANDED); self._animate_height(OVERLAY_H_EXPANDED)
        self._apply_date_filter(self._active_date)

    def _apply_date_filter(self, key):
        self._active_date = key; self._style_dpills()
        # Se l'AllWorker sta ancora caricando, NON valutare l'esito: il filtro è solo
        # registrato (active_date + stile pillole) e lo spinner resta. Quando arrivano
        # i dati, _on_all_done richiama _apply_date_filter con l'active_date corrente.
        # Senza questo, cambiare filtro durante il load mostrava "NESSUN ELEMENTO" e
        # interrompeva lo spinner, lasciando la schermata bloccata su DB grandi.
        if getattr(self, "_all_loading", False):
            self.status.setStyleSheet(f"color:{TEXT_SECONDARY};background:transparent;font-size:10px;font-weight:600;letter-spacing:1px;")
            self.status.setText("CARICAMENTO TIMELINE..."); self.status.show()
            self._show_loading(); self._redraw()
            return
        if not self._all_results:
            self.loading_page.stop(); self.stack.hide()
            self.status.setStyleSheet(f"color:{TEXT_SECONDARY};background:transparent;font-size:10px;font-weight:600;letter-spacing:1px;")
            self.status.setText("NESSUN ELEMENTO"); self._redraw()
            return
        now = datetime.now(timezone.utc)
        if key == "today": cut = now.replace(hour=0, minute=0, second=0, microsecond=0); cut_end = None
        elif key == "yesterday": cut = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0); cut_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif key == "week": cut = now - timedelta(days=7); cut_end = None
        else: cut = cut_end = None
        filtered = []
        for r in self._all_results:
            ts = datetime.fromisoformat(r["ts"])
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
            if cut is None: filtered.append(r)
            elif key == "yesterday":
                if cut <= ts < cut_end: filtered.append(r)
            else:
                if ts >= cut: filtered.append(r)
        self._results = filtered; self._filtered = filtered; self._active_filter = "all"
        has_a = any(r.get("type") == "audio" for r in filtered); has_s = any(r.get("type") == "screenshot" for r in filtered)
        if has_a and has_s: self._style_fpills(); self.filter_bar.show(); self.filter_bar.repaint()
        else: self.filter_bar.hide()
        self.sep.show(); self.status.show(); self.date_bar.show(); self.date_bar.repaint(); self.status.repaint()
        self.status.setText(f"{len(filtered)} ELEMENTI")
        self._apply_filter(); self._show_results_page(); self._redraw()

    def _set_filter(self, key):
        self._active_filter = key; self._style_fpills(); self._apply_filter(); self._redraw()

    def _update_filter_pill_counts(self):
        try:
            n_all   = len(self._results)
            n_ss    = sum(1 for r in self._results if r.get("type") == "screenshot")
            n_au    = sum(1 for r in self._results if r.get("type") == "audio")
            labels  = {"all": f"Tutto ({n_all})", "screenshot": f"Immagini ({n_ss})", "audio": f"Audio ({n_au})"}
            for k, b in self._fbtn.items():
                b.setText(labels.get(k, k))
        except Exception:
            pass

    def _apply_filter(self):
        self._filtered = (self._results if self._active_filter == "all" else [r for r in self._results if r.get("type") == self._active_filter])
        self.results_list.blockSignals(True); self.results_list.clear(); self.results_list.blockSignals(False)
        last_bucket = None
        for i, r in enumerate(self._filtered):
            # Sticky date header se bucket cambia
            bucket_key, bucket_label = _date_bucket_label(r.get("ts", ""))
            if bucket_key != last_bucket:
                hdr = QListWidgetItem(bucket_label)
                hdr.setData(ITEM_HEADER_ROLE, True)
                hdr.setFlags(hdr.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
                self.results_list.addItem(hdr)
                last_bucket = bucket_key
            ts_rel = _human_ago(r["ts"])
            is_audio = r.get("type") == "audio"
            if is_audio:
                transcript = r.get("transcript", "").strip()
                title = (transcript[:40] + "…") if len(transcript) > 40 else (transcript or "Registrazione Audio")
            else:
                app = r.get("app", "?")
                title = app if len(app) <= 38 else app[:35] + "…"
            tag = "✓ esatto" if r.get("exact") else f"{int(r['score'] * 100)}%"
            item = QListWidgetItem(f"{title}\n{ts_rel}   •   {tag}")
            item.setData(Qt.ItemDataRole.UserRole, i); item.setData(ITEM_TYPE_ROLE, "audio" if is_audio else "screenshot")
            self.results_list.addItem(item)
        # Aggiorna count badges
        self._update_filter_pill_counts()

    def _on_row_changed(self, row):
        item = self.results_list.item(row)
        if not item: return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._filtered): return
        r = self._filtered[idx]
        self.preview_info.setText(f"{r.get('app', '?')}   •   {r['ts'][:19].replace('T', ' ')}")
        # Ferma audio precedente
        self._stop_audio() if self._is_playing else None
        self._reset_audio_player()

        # Pin + tags state per item corrente
        kind = "ss" if r.get("type") == "screenshot" else "au"
        try:
            from db import get_conn as _gc
            _cn = _gc(); _row = _cn.cursor().execute(
                f"SELECT pinned FROM {'screenshots' if kind=='ss' else 'audio_segments'} WHERE id=?",
                (r["id"],)
            ).fetchone(); _cn.close()
            pinned_state = bool(_row and _row[0])
            r["pinned"] = pinned_state
            self.pin_btn.setEnabled(True)
            self._update_pin_btn(pinned_state)
            self.tag_input.setEnabled(True)
            self._refresh_tags_label(kind, r["id"])
        except Exception as e:
            print(f"[Preview] pin/tag load fail: {e}")

        if r.get("type") == "audio":
            self._current_type = "audio"; self._current_pixmap = None; self.preview_lbl.clear()
            query = self.search_input.text().strip() if not self._all_mode else ""
            transcript = r.get("transcript", "")
            if query:
                self.preview_lbl.setTextFormat(Qt.TextFormat.RichText)
                self.preview_lbl.setText(_highlight_tokens(transcript, query))
            else:
                self.preview_lbl.setTextFormat(Qt.TextFormat.PlainText)
                self.preview_lbl.setText(transcript)
            self.preview_lbl.setWordWrap(True)
            self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            self.preview_lbl.setStyleSheet(f"background:transparent; color:{TEXT_PRIMARY}; font-size:14px; padding:16px; line-height: 1.6;")

            audio_blob = r.get("audio_data"); audio_fmt = r.get("audio_format", "f32")
            self._current_audio = (audio_blob, audio_fmt)
            if audio_blob:
                decoded = decode_audio(audio_blob, audio_fmt)
                self._audio_data = decoded
                total_samples = len(decoded)
                self.audio_slider.blockSignals(True)
                self.audio_slider.setMaximum(total_samples); self.audio_slider.setValue(0)
                self.audio_slider.blockSignals(False)
                self.audio_time_cur.setText("0:00")
                self.audio_time_total.setText(_fmt_time(total_samples / 16000))
                self.waveform.set_audio(decoded)
                self.waveform.set_progress(0.0)
                self.audio_player_bar.show()
            self._preview_panel.set_border_kind("audio"); self._set_action_btns("audio")
            if not audio_blob: self.play_btn.setEnabled(False); self.play_btn.setStyleSheet(SS_BTN_OFF)
        else:
            self._current_type = "screenshot"; self._current_audio = None
            self.preview_lbl.setWordWrap(False); self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_lbl.setStyleSheet("background:transparent;")
            self.audio_player_bar.hide()

            conn = get_conn()
            row_db = conn.cursor().execute("SELECT image FROM screenshots WHERE id=?", (r["id"],)).fetchone()
            conn.close()

            if row_db and row_db[0]:
                px = QPixmap(); px.loadFromData(row_db[0])
                self._current_pixmap = px
                target_w = self.preview_lbl.width() or 560
                self.preview_lbl.setPixmap(px.scaled(target_w, 500, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self._preview_panel.set_border_kind("screenshot"); self._set_action_btns("screenshot")
            else:
                self._current_pixmap = None; self.preview_lbl.setText("Immagine non disponibile")
                self._preview_panel.set_border_kind("neutral"); self._set_action_btns("neutral")

        if self._all_mode: self.sep.show(); self.status.show(); self.date_bar.show()

    def _open_fullscreen(self):
        if self._current_pixmap: FullscreenViewer(self._current_pixmap, self.preview_info.text(), self).exec()

    def _on_results_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        selected = self.results_list.selectedItems()
        if not selected:
            cur = self.results_list.currentItem()
            if cur: selected = [cur]
        if not selected:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#1a1a1f; color:#f3f4f6; border:1px solid rgba(255,255,255,0.10); border-radius:8px; padding:4px;}"
            "QMenu::item{padding:6px 16px; border-radius:5px;}"
            "QMenu::item:selected{background:rgba(167,139,250,0.25);}"
        )
        act_copy = menu.addAction(f"📋 Copia come Markdown ({len(selected)})")
        chosen = menu.exec(self.results_list.mapToGlobal(pos))
        if chosen is act_copy:
            self._copy_selection_md(selected)

    def _copy_selection_md(self, items):
        parts = []
        for it in items:
            idx = it.data(Qt.ItemDataRole.UserRole)
            if idx is None or idx >= len(self._filtered): continue
            r = self._filtered[idx]
            ts = r.get("ts", "")[:19].replace("T", " ")
            if r.get("type") == "audio":
                src = "Microfono" if r.get("source") == "mic" else "Sistema"
                body = (r.get("transcript") or "").strip()
                parts.append(f"### 🎙️ {src} · {ts} `[au:{r['id']}]`\n\n> {body}\n")
            else:
                app = r.get("app") or "?"
                body = (r.get("text") or "").strip()
                parts.append(f"### 📸 {app} · {ts} `[ss:{r['id']}]`\n\n```\n{body}\n```\n")
        md = "\n---\n\n".join(parts)
        try:
            QApplication.clipboard().setText(md)
            self.toast(f"Copiati {len(items)} ricordi come markdown", level="ok")
        except Exception as e:
            self.toast(f"Errore copia: {e}", level="error")

    def _toggle_pin(self):
        if not self._filtered: return
        row = self.results_list.currentRow()
        if row < 0: return
        item = self.results_list.item(row)
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._filtered): return
        r = self._filtered[idx]
        kind = "ss" if r.get("type") == "screenshot" else "au"
        try:
            from db import set_pinned
            new_state = not r.get("pinned", False)
            set_pinned(kind, r["id"], new_state)
            r["pinned"] = new_state
            self._update_pin_btn(new_state)
            self.toast(("⭐ Pinned" if new_state else "Unpinned"), level="ok", duration_ms=2000)
        except Exception as e:
            self.toast(f"Errore pin: {e}", level="error")

    def _update_pin_btn(self, pinned):
        if pinned:
            self.pin_btn.setText("★")
            self.pin_btn.setStyleSheet(
                f"QPushButton{{background:rgba(245,158,11,0.18); color:{C_AUDIO_HEX}; "
                f"border:1px solid rgba(245,158,11,0.4); border-radius:8px; font-size:18px; font-weight:600;}}"
                "QPushButton:hover{background:rgba(245,158,11,0.30);}"
            )
        else:
            self.pin_btn.setText("☆"); self.pin_btn.setStyleSheet(SS_BTN_OFF)

    def _on_add_tag(self):
        if not self._filtered: return
        row = self.results_list.currentRow()
        if row < 0: return
        item = self.results_list.item(row)
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._filtered): return
        r = self._filtered[idx]
        kind = "ss" if r.get("type") == "screenshot" else "au"
        name = self.tag_input.text().strip()
        if not name: return
        try:
            from db import add_tag
            add_tag(kind, r["id"], name)
            self.tag_input.clear()
            self._refresh_tags_label(kind, r["id"])
            self.toast(f"Tag aggiunto: {name}", level="ok", duration_ms=1800)
        except Exception as e:
            self.toast(f"Errore tag: {e}", level="error")

    def _refresh_tags_label(self, kind, item_id):
        try:
            from db import get_tags
            tags = get_tags(kind, item_id)
            if tags:
                html = "  ".join(f"<span style='background:rgba(167,139,250,0.15); padding:1px 7px; border-radius:8px; color:#c4b5fd;'>#{t}</span>" for t in tags)
                self.tags_label.setText(html)
            else:
                self.tags_label.setText("<span style='color:#5a5d6a;'>nessun tag</span>")
        except Exception:
            self.tags_label.setText("")

    def _show_context(self):
        row = self.results_list.currentRow()
        if row < 0: return
        item = self.results_list.item(row)
        if not item: return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._filtered): return
        r = self._filtered[idx]
        pivot_ts = r["ts"]
        pivot_label = f"{r.get('app', '?')} · {_human_ago(pivot_ts)}"
        ContextDialog(pivot_ts, pivot_label, self, window_min=5).exec()

    # ── Audio Player Logic ──────────────────────────────────────
    def _play_from(self, offset_samples):
        import sounddevice as sd
        self._audio_offset = offset_samples
        self._playback_start = _time.time()
        self._is_playing = True
        sd.play(self._audio_data[offset_samples:], samplerate=16000)
        self._playback_timer.start()
        self.play_btn.setText("⏹  Stop"); self.play_btn.setStyleSheet(SS_BTN_AUDIO_ON)
        try: self.play_btn.clicked.disconnect()
        except Exception: pass
        self.play_btn.clicked.connect(self._stop_audio)

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
        self.play_btn.setText("▶  Ascolta"); self.play_btn.setStyleSheet(SS_BTN_AUDIO_ON)
        try: self.play_btn.clicked.disconnect()
        except Exception: pass
        self.play_btn.clicked.connect(self._play_audio)
        if self._audio_data is not None:
            self.audio_slider.blockSignals(True)
            self.audio_slider.setValue(0)
            self.audio_slider.blockSignals(False)
            self.audio_time_cur.setText("0:00")

    def _on_slider_pressed(self):
        self._playback_timer.stop()

    def _on_slider_moved(self, value):
        if self._audio_data is not None:
            self.audio_time_cur.setText(_fmt_time(value / 16000))

    def _on_slider_released(self):
        import sounddevice as sd
        new_offset = self.audio_slider.value()
        sd.stop()
        self._is_playing = True
        self._play_from(new_offset)

    def _reset_audio_player(self):
        self._playback_timer.stop(); self._is_playing = False
        self._audio_data = None; self._audio_offset = 0; self._playback_start = None
        self.audio_slider.blockSignals(True)
        self.audio_slider.setMaximum(100); self.audio_slider.setValue(0)
        self.audio_slider.blockSignals(False)
        self.audio_time_cur.setText("0:00"); self.audio_time_total.setText("0:00")
        if hasattr(self, "waveform"): self.waveform.clear()
        self.audio_player_bar.hide()

    def _play_audio(self):
        if self._audio_data is None:
            if not self._current_audio: return
            blob, fmt = self._current_audio
            self._audio_data = decode_audio(blob, fmt)
            total = len(self._audio_data)
            self.audio_slider.blockSignals(True)
            self.audio_slider.setMaximum(total); self.audio_slider.setValue(0)
            self.audio_slider.blockSignals(False)
            self.audio_time_total.setText(_fmt_time(total / 16000))
            self.audio_player_bar.show()
        self._play_from(self.audio_slider.value())

    def _stop_audio(self):
        import sounddevice as sd
        self._playback_timer.stop(); self._is_playing = False
        try: sd.stop()
        except Exception: pass
        self.play_btn.setText("▶  Ascolta"); self.play_btn.setStyleSheet(SS_BTN_AUDIO_ON)
        try: self.play_btn.clicked.disconnect()
        except Exception: pass
        self.play_btn.clicked.connect(self._play_audio)

    def _on_error(self, msg):
        self.loading_page.stop(); self.stack.hide(); self.status.setText(f"ERRORE: {msg}"); self._redraw()

    # ── Chat mode ───────────────────────────────────────────────────
    def _show_chat(self):
        if self._chat_mode:
            self._collapse(); return
        self._chat_mode = True; self._all_mode = False; self._all_loading = False
        self.ai_card.reset()
        self._set_input(placeholder="Modalità chat AI…", ro=True, color=TEXT_SECONDARY)
        self.kbd.hide()

        self.chat_btn.setText("Chiudi"); self.chat_btn.setFixedWidth(80)
        self.chat_btn.setStyleSheet(SS_BTN_AI_ON)
        try: self.chat_btn.clicked.disconnect()
        except Exception: pass
        self.chat_btn.clicked.connect(self._collapse)
        self._reset_all_btn()

        for w in (self.sep, self.status, self.date_bar, self.filter_bar):
            w.hide()
        self.stack.setCurrentWidget(self.chat_page); self.stack.show()
        self.setFixedHeight(OVERLAY_H_EXPANDED); self._animate_height(OVERLAY_H_EXPANDED)

        if not self._chat_loaded:
            self._load_chat_from_db()
            self._chat_loaded = True

        if not ai_assistant.is_configured():
            self.chat_page.add_notice(
                "Configura la tua API key in Impostazioni → AI per iniziare a chattare."
            )
            self.chat_page.set_busy(True)
        else:
            self.chat_page.set_busy(False)
            self.chat_page.input.setFocus()
        self._redraw()

    def _load_chat_from_db(self):
        try:
            history = ai_assistant.load_chat_history()
        except Exception as e:
            print(f"[Chat] Errore caricamento storia: {e}"); history = []
        self.chat_page.clear_messages()
        self._chat_history = []
        for m in history:
            role = m["role"]; content = m["content"]
            if role == "user":
                # User msg potrebbero contenere ref se utente li scrive ma raro — render plain
                self.chat_page.add_user(content)
            elif role == "assistant":
                container, lbl = self.chat_page.add_assistant("")
                self._finalize_bubble(container, lbl, content)
            self._chat_history.append({"role": role, "content": content})

    def _reset_chat(self):
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return
        try: ai_assistant.clear_chat_history()
        except Exception as e: print(f"[Chat] Errore clear: {e}")
        self._chat_history = []
        self._chat_turn_bubbles = []
        self.chat_page.clear_messages()
        if not ai_assistant.is_configured():
            self.chat_page.add_notice("Configura la tua API key in Impostazioni → AI.")
            self.chat_page.set_busy(True)
        else:
            self.chat_page.set_busy(False)
            self.chat_page.input.setFocus()

    def _send_chat_message(self, text):
        if not text.strip(): return
        if not ai_assistant.is_configured():
            self.chat_page.add_error("API key mancante. Apri Impostazioni → AI.")
            return
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return

        self.chat_page.add_user(text)
        _, lbl = self.chat_page.add_thinking()
        self._chat_thinking = lbl
        self._chat_current_bubble = None
        self._chat_current_text = ""
        self._chat_turn_bubbles = []
        self.chat_page.set_busy(True)

        # Persist user message
        try: ai_assistant.save_chat_message("user", text)
        except Exception as e: print(f"[Chat] save user fail: {e}")

        self._chat_worker = ChatWorker(self._chat_history, text)
        self._chat_worker.chunk.connect(self._on_chat_chunk)
        self._chat_worker.finished_streaming.connect(
            lambda user_msg=text: self._on_chat_done(user_msg)
        )
        self._chat_worker.start()

    def _remove_thinking(self):
        if self._chat_thinking is None: return
        try:
            parent = self._chat_thinking.parentWidget()
            if parent is not None:
                self.chat_page.msg_layout.removeWidget(parent)
                parent.deleteLater()
        except Exception:
            pass
        self._chat_thinking = None

    def _on_chat_chunk(self, kind, content):
        if kind == "text":
            self._remove_thinking()
            if self._chat_current_bubble is None:
                container, lbl = self.chat_page.add_assistant("")
                self._chat_current_bubble = lbl
                self._chat_current_container = container
                self._chat_current_text = ""
                self._chat_turn_bubbles.append({
                    "container": container, "label": lbl, "text": "",
                })
            self._chat_current_text += content
            self._chat_current_bubble.setText(self._chat_current_text)
            if self._chat_turn_bubbles:
                self._chat_turn_bubbles[-1]["text"] = self._chat_current_text
        elif kind == "tool":
            self._remove_thinking()
            # finalizza bolla corrente con markdown + embed cards
            if self._chat_current_container is not None and self._chat_current_text:
                self._finalize_bubble(self._chat_current_container,
                                      self._chat_current_bubble,
                                      self._chat_current_text)
            self._chat_current_bubble = None
            self._chat_current_container = None
            self._chat_current_text = ""
            self.chat_page.add_tool(content)
            _, lbl = self.chat_page.add_thinking()
            self._chat_thinking = lbl
        elif kind == "error":
            self._remove_thinking()
            self.chat_page.add_error(content)
            self._chat_current_bubble = None
            self._chat_current_container = None
            self._chat_current_text = ""

    def _on_chat_done(self, user_msg):
        self._remove_thinking()
        # Finalizza ogni bolla (markdown + embed cards)
        for b in self._chat_turn_bubbles:
            if b["text"]:
                self._finalize_bubble(b["container"], b["label"], b["text"])
        # Concat full assistant text (refs incluse — utili a AI per memoria)
        full_assistant = "\n\n".join(b["text"] for b in self._chat_turn_bubbles if b["text"])
        self._chat_history.append({"role": "user", "content": user_msg})
        if full_assistant:
            self._chat_history.append({"role": "assistant", "content": full_assistant})
            try: ai_assistant.save_chat_message("assistant", full_assistant)
            except Exception as e: print(f"[Chat] save assistant fail: {e}")
        self._chat_current_bubble = None
        self._chat_current_container = None
        self._chat_current_text = ""
        self._chat_turn_bubbles = []
        self.chat_page.set_busy(False)
        self.chat_page.input.setFocus()

    # ── Finalize bubble: split text on refs + render inline sequence ──
    def _split_text_refs(self, raw_text):
        """Yield ('text', str) | ('card', (kind, id)) segmenti, in ordine."""
        segs = []
        pos = 0
        for m in _REF_RE.finditer(raw_text or ""):
            if m.start() > pos:
                piece = (raw_text[pos:m.start()] or "").strip()
                if piece:
                    segs.append(("text", piece))
            segs.append(("card", (m.group(1), int(m.group(2)))))
            pos = m.end()
        if pos < len(raw_text or ""):
            rest = (raw_text[pos:] or "").strip()
            if rest:
                segs.append(("text", rest))
        if not segs and (raw_text or "").strip():
            segs.append(("text", raw_text.strip()))
        return segs

    def _finalize_bubble(self, container, label, raw_text):
        # Posizione del container originale nel layout chat
        try:
            insert_idx = self.chat_page.msg_layout.indexOf(container)
        except Exception:
            insert_idx = -1
        if insert_idx < 0:
            clean = _strip_refs(raw_text)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setText(_md_to_html(clean) if clean else " ")
            return

        # Rimuove bolla streaming-temporanea
        self.chat_page.msg_layout.removeWidget(container)
        container.setParent(None); container.deleteLater()

        # Crea UNA singola bolla assistant che contiene testo + card inline
        turn = AssistantTurnBubble()
        for seg_type, payload in self._split_text_refs(raw_text):
            if seg_type == "text":
                turn.add_text(_md_to_html(payload))
            else:
                kind, rid = payload
                try:
                    card = self._make_embed_card(kind, rid)
                except Exception as e:
                    print(f"[Chat] embed card fail [{kind}:{rid}]: {e}")
                    continue
                if card is not None:
                    turn.add_card(card)
        self.chat_page.msg_layout.insertWidget(insert_idx, turn)

    def _make_embed_card(self, kind, rid):
        if kind == "ss":
            card = EmbedScreenshotCard(rid)
            card.clicked.connect(self._on_embed_ss_click)
            return card
        if kind == "au":
            card = EmbedAudioCard(rid)
            card.play_requested.connect(self._on_embed_audio_play)
            return card
        return None

    def _on_embed_ss_click(self, sid):
        try:
            conn = get_conn()
            row = conn.cursor().execute(
                "SELECT image, ts, app FROM screenshots WHERE id=?", (sid,)
            ).fetchone()
            conn.close()
        except Exception as e:
            print(f"[Chat] embed ss click fail: {e}"); return
        if not row or not row[0]: return
        px = QPixmap(); px.loadFromData(row[0])
        ts = (row[1] or "")[:19].replace("T", " ")
        info = f"{row[2] or '?'}   •   {ts}"
        FullscreenViewer(px, info, self).exec()

    def _on_embed_audio_play(self, aid):
        # Stop precedente se diverso
        if self._chat_audio_playing is not None:
            prev_card, prev_aid = self._chat_audio_playing
            try:
                import sounddevice as sd
                sd.stop()
            except Exception: pass
            try: prev_card.set_playing(False)
            except Exception: pass
            self._chat_audio_playing = None
            if prev_aid == aid:
                # toggle stop
                return
        try:
            conn = get_conn()
            row = conn.cursor().execute(
                "SELECT audio_data, audio_format FROM audio_segments WHERE id=?", (aid,)
            ).fetchone()
            conn.close()
        except Exception as e:
            print(f"[Chat] embed audio fetch fail: {e}"); return
        if not row or not row[0]: return
        try:
            data = decode_audio(row[0], row[1] or "f32")
            import sounddevice as sd
            sd.play(data, samplerate=16000)
        except Exception as e:
            print(f"[Chat] embed audio play fail: {e}"); return
        # Trova card sender
        sender = self.sender()
        if isinstance(sender, EmbedAudioCard):
            sender.set_playing(True)
            self._chat_audio_playing = (sender, aid)

    # ── Voice input ─────────────────────────────────────────────────
    def _toggle_voice_input(self):
        if self._voice_worker is not None and self._voice_worker.isRunning():
            # Stop record → entra fase trascrizione
            if self._voice_stop_event is not None:
                self._voice_stop_event.set()
            return
        import threading
        self._voice_stop_event = threading.Event()
        self.chat_page._set_mic_style(True)
        self.chat_page.input.setPlaceholderText("🎙 In ascolto… clicca ⏹ per stop")
        self._voice_worker = VoiceWorker(self._voice_stop_event)
        self._voice_worker.started_transcribe.connect(self._on_voice_transcribing)
        self._voice_worker.done.connect(self._on_voice_done)
        self._voice_worker.start()

    def _on_voice_transcribing(self):
        # Stop ricezione → mostra stato trascrizione
        self.chat_page.input.setPlaceholderText("✨ Trascrizione in corso…")
        self.chat_page.mic_btn.setEnabled(False)

    def _on_voice_done(self, text, log):
        self.chat_page._set_mic_style(False)
        self.chat_page.mic_btn.setEnabled(True)
        if text:
            self.chat_page.input.setPlaceholderText("Scrivi un messaggio…")
            current = self.chat_page.input.text()
            self.chat_page.input.setText((current + " " + text).strip() if current else text)
            self.toast(f"Trascritto: {text[:40]}{'…' if len(text) > 40 else ''}", level="ok")
        else:
            self.chat_page.input.setPlaceholderText("Scrivi un messaggio…")
            self.toast(f"Niente trascritto", level="warn")
        self.chat_page.input.setFocus()
        self._voice_stop_event = None
        self._voice_worker = None

    # ── Inline RAG ──────────────────────────────────────────────────
    def _maybe_trigger_inline_rag(self, query, results):
        if not results: return
        cfg = ai_assistant.get_ai_config()
        if not cfg["inline"] or not ai_assistant.is_configured():
            self.ai_card.reset(); return
        self.ai_card.show_loading(query)
        self._rag_worker = RagWorker(query, results)
        self._rag_worker.done.connect(self._on_rag_done)
        self._rag_worker.start()

    def _on_rag_done(self, text):
        self.ai_card.set_answer(text)


    # ── Fullscreen & Settings ─────────────────────────────────────
    def keyPressEvent(self, e):
        k = e.key()
        # Navigazione lista risultati con ↑↓ anche se focus su search_input
        if self.results_list.isVisible() and self.results_list.count() > 0:
            if k == Qt.Key.Key_Down:
                row = min(self.results_list.currentRow() + 1, self.results_list.count() - 1)
                if row < 0: row = 0
                self.results_list.setCurrentRow(row); return
            if k == Qt.Key.Key_Up:
                row = max(self.results_list.currentRow() - 1, 0)
                self.results_list.setCurrentRow(row); return
        if k == Qt.Key.Key_Escape:
            if self._fullscreen_mode: self._toggle_fullscreen(); return
            self._collapse(); self.hide()
        elif k == Qt.Key.Key_F11:
            self._toggle_fullscreen()

    def _toggle_fullscreen(self):
        if not self._fullscreen_mode: self._enter_fullscreen()
        else: self._exit_fullscreen()

    def _enter_fullscreen(self):
        self._prev_geom = self.geometry()
        self._fullscreen_mode = True
        g = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(0, 0); self.setMaximumSize(99999, 99999)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.show()
        self.setGeometry(g)
        self._results_col.setFixedWidth(420)
        self._sidebar.show()
        self.fs_toggle_btn.setText("⊡")
        self.fs_toggle_btn.setToolTip("Esci da schermo intero (F11/ESC)")
        self._update_sidebar_stats()
        self._refresh_sidebar_apps()
        self._update_mask()

    def _exit_fullscreen(self):
        self._fullscreen_mode = False
        self.setMinimumSize(0, 0); self.setMaximumSize(99999, 99999)
        self._results_col.setFixedWidth(320)
        self._sidebar.hide()
        self.fs_toggle_btn.setText("⛶")
        self.fs_toggle_btn.setToolTip("Schermo intero (F11)")
        if self._prev_geom:
            self.setGeometry(self._prev_geom)
        else:
            self.setFixedWidth(OVERLAY_W); self.setFixedHeight(OVERLAY_H_COMPACT)
            self._center_on_screen()
        self._update_mask()

    def _refresh_sidebar_apps(self):
        try:
            from db import get_distinct_apps
            apps = get_distinct_apps(40)
            self._sb_apps_list.blockSignals(True); self._sb_apps_list.clear()
            for a in apps:
                name = a["app"]
                display = name if len(name) <= 26 else name[:23] + "…"
                self._sb_apps_list.addItem(f"{display}  ({a['count']})")
                self._sb_apps_list.item(self._sb_apps_list.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, name)
            self._sb_apps_list.blockSignals(False)
        except Exception as e:
            print(f"[Sidebar] apps refresh fail: {e}")

    def _on_app_filter(self, item):
        app = item.data(Qt.ItemDataRole.UserRole)
        if not app: return
        # Filtra _all_results se in esplora mode, altrimenti _results
        source = self._all_results if self._all_mode else self._results
        if not source:
            self.toast(f"Nessun risultato per filtrare", level="warn"); return
        self._filtered = [r for r in source if r.get("type") == "screenshot" and r.get("app") == app]
        self.results_list.blockSignals(True); self.results_list.clear(); self.results_list.blockSignals(False)
        for i, r in enumerate(self._filtered):
            ts_rel = _human_ago(r["ts"])
            app_t = r.get("app", "?")
            title = app_t if len(app_t) <= 38 else app_t[:35] + "…"
            tag = "✓ esatto" if r.get("exact") else f"{int(r['score'] * 100)}%"
            it = QListWidgetItem(f"{title}\n{ts_rel}   •   {tag}")
            it.setData(Qt.ItemDataRole.UserRole, i)
            it.setData(ITEM_TYPE_ROLE, "screenshot")
            self.results_list.addItem(it)
        self.status.setText(f"{len(self._filtered)} · APP: {app[:40]}")
        self.toast(f"Filtrato per app: {app[:40]}", level="info")

    def _open_date_filter(self):
        from PyQt6.QtWidgets import QDialog, QDateEdit, QDialogButtonBox
        from PyQt6.QtCore import QDate
        dlg = QDialog(self)
        dlg.setWindowTitle("Range date custom — Déjà")
        dlg.setFixedSize(380, 200)
        dlg.setStyleSheet(f"QDialog{{background:{BG_HEX}; color:#f3f4f6;}}"
                          " QDateEdit{background:rgba(255,255,255,0.05); color:#f3f4f6;"
                          " border:1px solid rgba(255,255,255,0.10); border-radius:7px; padding:5px 10px; font-size:11pt;}"
                          " QLabel{color:#f3f4f6; background:transparent;}")
        v = QVBoxLayout(dlg); v.setContentsMargins(22, 18, 22, 16); v.setSpacing(10)
        title = QLabel("📅  Filtra ricordi per range date")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color:{C_AI_HEX};"); v.addWidget(title)
        from_row = QHBoxLayout(); from_row.addWidget(QLabel("Da:"))
        d_from = QDateEdit(); d_from.setCalendarPopup(True); d_from.setDate(QDate.currentDate().addDays(-7))
        from_row.addWidget(d_from); v.addLayout(from_row)
        to_row = QHBoxLayout(); to_row.addWidget(QLabel("A:"))
        d_to = QDateEdit(); d_to.setCalendarPopup(True); d_to.setDate(QDate.currentDate())
        to_row.addWidget(d_to); v.addLayout(to_row)
        v.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(SS_BTN_AI_PRIMARY)
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(SS_BTN_OFF)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); v.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        start_iso = d_from.date().toString("yyyy-MM-dd") + "T00:00:00+00:00"
        end_iso = d_to.date().toString("yyyy-MM-dd") + "T23:59:59+00:00"
        # Query DB
        from db import get_conn
        conn = get_conn(); c = conn.cursor()
        results = []
        for row in c.execute("SELECT id, ts, app, text FROM screenshots WHERE ts>=? AND ts<=? ORDER BY ts DESC LIMIT 500",
                             (start_iso, end_iso)):
            results.append({"id": row[0], "ts": row[1], "app": row[2] or "?", "text": row[3],
                            "type": "screenshot", "score": 1.0, "exact": False})
        for row in c.execute("SELECT id, ts, source, transcript, audio_data, audio_format FROM audio_segments WHERE ts>=? AND ts<=? ORDER BY ts DESC LIMIT 500",
                             (start_iso, end_iso)):
            results.append({"id": row[0], "ts": row[1], "source": row[2], "transcript": row[3],
                            "audio_data": row[4], "audio_format": row[5] or "f32",
                            "type": "audio", "score": 1.0, "exact": False,
                            "app": "🎙️ " + ("Microfono" if row[2] == "mic" else "Sistema"),
                            "text": row[3]})
        conn.close()
        results.sort(key=lambda x: x["ts"], reverse=True)
        self._all_results = results; self._results = results
        self._all_mode = True
        self._apply_filter(); self._show_results_page()
        self.status.setText(f"📅 {len(results)} · {d_from.date().toString('dd MMM')} → {d_to.date().toString('dd MMM')}")
        self.status.show(); self.sep.show()
        self.toast(f"{len(results)} ricordi in range", level="info")

    def _show_pinned(self):
        try:
            from db import get_pinned
            pins = get_pinned()
        except Exception as e:
            self.toast(f"Errore pinned: {e}", level="error"); return
        if not pins:
            self.toast("Nessun ricordo pinned. Clicca ⭐ in preview per marcare.", level="info"); return
        self._results = pins; self._all_results = pins
        self._filtered = pins; self._active_filter = "all"
        self.status.setText(f"⭐ {len(pins)} PINNED"); self.status.show()
        self.results_list.blockSignals(True); self.results_list.clear(); self.results_list.blockSignals(False)
        for i, r in enumerate(pins):
            ts_rel = _human_ago(r["ts"])
            is_audio = r.get("type") == "audio"
            if is_audio:
                title = (r.get("transcript", "")[:40] + "…") if len(r.get("transcript", "")) > 40 else (r.get("transcript", "") or "Audio")
            else:
                app_t = r.get("app", "?")
                title = app_t if len(app_t) <= 38 else app_t[:35] + "…"
            it = QListWidgetItem(f"⭐ {title}\n{ts_rel}")
            it.setData(Qt.ItemDataRole.UserRole, i)
            it.setData(ITEM_TYPE_ROLE, "audio" if is_audio else "screenshot")
            self.results_list.addItem(it)
        self._show_results_page(); self._redraw()

    def _update_sidebar_stats(self):
        try:
            conn = get_conn(); c = conn.cursor()
            n_ss     = c.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
            n_ss_emb = c.execute("SELECT COUNT(*) FROM screenshot_embeddings").fetchone()[0]
            n_ss_empty = c.execute("SELECT COUNT(*) FROM screenshots WHERE text IS NULL OR text=''").fetchone()[0]
            n_au     = c.execute("SELECT COUNT(*) FROM audio_segments").fetchone()[0]
            n_au_emb = c.execute("SELECT COUNT(*) FROM audio_embeddings").fetchone()[0]
            conn.close()
            ss_pending = max(0, n_ss - n_ss_emb - n_ss_empty)
            au_pending = max(0, n_au - n_au_emb)
            parts = [
                f"📸  {n_ss} screenshot",
                f"🎙️  {n_au} audio",
            ]
            if ss_pending or au_pending:
                queue = []
                if ss_pending: queue.append(f"{ss_pending} screenshot")
                if au_pending: queue.append(f"{au_pending} audio")
                parts.append(f"\n⏳  In coda: {', '.join(queue)}")
            if n_ss_empty:
                parts.append(f"⚠  {n_ss_empty} screen senza testo OCR")
            parts.append(f"\n📂  Risultati: {len(self._filtered)}")
            self._sb_stats.setText("\n".join(parts))
        except Exception: pass

    def _open_settings(self):
        dlg = SettingsDialog(self); dlg.exec()

    def _export_memories(self):
        import json, os
        try:
            conn = get_conn(); c = conn.cursor()
            data = {"screenshots": [], "audio": []}
            for row in c.execute("SELECT id, ts, app, text FROM screenshots ORDER BY ts DESC"):
                data["screenshots"].append({"id": row[0], "ts": row[1], "app": row[2], "text": row[3]})
            for row in c.execute("SELECT id, ts, source, transcript FROM audio_segments ORDER BY ts DESC"):
                data["audio"].append({"id": row[0], "ts": row[1], "source": row[2], "transcript": row[3]})
            conn.close()
            path = os.path.expanduser("~/deja_export.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.toast(f"Esportato in {path}", level="ok", duration_ms=4000)
        except Exception as e:
            self.toast(f"Errore export: {e}", level="error", duration_ms=4500)

    def _confirm_clear(self):
        self._sb_clear_btn.setText("⚠️  Conferma? (clicca ancora)")
        try: self._sb_clear_btn.clicked.disconnect()
        except Exception: pass
        self._sb_clear_btn.clicked.connect(self._do_clear)
        QTimer.singleShot(4000, self._reset_clear_btn)

    def _do_clear(self):
        try:
            conn = get_conn()
            conn.execute("DELETE FROM screenshots"); conn.execute("DELETE FROM audio_segments")
            conn.execute("DELETE FROM screenshot_embeddings"); conn.execute("DELETE FROM audio_embeddings")
            conn.commit(); conn.close()
            self._collapse(); self._reset_clear_btn()
        except Exception: pass

    def _reset_clear_btn(self):
        self._sb_clear_btn.setText("🗑️  Svuota database")
        try: self._sb_clear_btn.clicked.disconnect()
        except Exception: pass
        self._sb_clear_btn.clicked.connect(self._confirm_clear)

    def update_status(self, msg):
        self.status.setText(msg)

    def _refresh_search_completer(self):
        try:
            from db import load_search_history
            self._search_history_model.setStringList(load_search_history(20))
        except Exception: pass

    def toast(self, message, level="info", duration_ms=3000):
        """Mostra toast overlay nell'angolo top-right della window."""
        try:
            Toast(self, message, level=level, duration_ms=duration_ms)
        except Exception as e:
            print(f"[Toast] {message} ({e})")
