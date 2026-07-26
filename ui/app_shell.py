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
    QSlider, QScrollArea, QStackedWidget, QComboBox, QSpinBox, QDateEdit, QCheckBox,
    QDialog,
)
from PyQt6.QtCore import (
    Qt, QSize, QRectF, QPointF, QPoint, QRect, QThread, pyqtSignal, QTimer,
    QPropertyAnimation, QEasingCurve, pyqtProperty, QDate,
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
    AssistantTurnBubble, EmbedScreenshotCard, EmbedAudioCard, EmbedWebCard, FullscreenViewer,
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
    "sys": (96, 165, 250),
}

# etichette italiane per categoria evento di sistema/browser
SYS_CAT_LABEL = {
    "process": "App", "focus": "Primo piano", "file": "File",
    "install": "Programmi", "clock": "Orologio", "power": "Alimentazione",
    "session": "Sessione", "device": "Unità", "network": "Rete",
    "download": "Download", "tab": "Tab browser", "visit": "Visita web",
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


# ── Stato live (card sidebar + pannello) ───────────────────────────
def _fmt_bytes(n):
    if n is None:
        return "—"
    for unit, div in (("TB", 1024 ** 4), ("GB", 1024 ** 3), ("MB", 1024 ** 2), ("kB", 1024)):
        if n >= div:
            return f"{n / div:.1f} {unit}".replace(".", ",")
    return f"{int(n)} B"


def _fmt_num(n):
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _fmt_ago(ts_iso):
    """ISO UTC → '12s fa' / '5 min fa' / '2 h fa' / '3 g fa'. '—' se assente."""
    if not ts_iso:
        return "—"
    try:
        ts = datetime.fromisoformat(ts_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        d = (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return "—"
    if d < 0:
        d = 0
    if d < 10:
        return "ora"
    if d < 60:
        return f"{int(d)}s fa"
    if d < 3600:
        return f"{int(d // 60)} min fa"
    if d < 86400:
        return f"{int(d // 3600)} h fa"
    return f"{int(d // 86400)} g fa"


def _fmt_left(seconds):
    """Secondi residui di pausa → testo. Oltre un anno = incognito (pausa 'infinita')."""
    if seconds > 300 * 86400:
        return "incognito"
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)} min"
    return f"{int(seconds // 3600)} h"


def collect_status(full=True):
    """Fotografia dello stato di Déjà: cattura, archivio, spazio, indice, sicurezza.

    **Da chiamare fuori dal thread UI** (`StatusWorker`). Nessuna eccezione esce
    di qui: ogni pezzo che fallisce resta a None e la UI mostra '—'.

    `full=False` = giro ECONOMICO (~ms): stato cattura, dimensioni su disco,
    ultimo ricordo, flag sicurezza. Salta i COUNT(*), che su un archivio reale
    (600k+ righe) costano oltre un secondo: farli a ogni tick significherebbe
    tenere una connessione SQLCipher sotto sforzo in permanenza, in concorrenza
    con le scritture del capturer. I totali si aggiornano su cadenza lenta e il
    chiamante fonde le due fotografie.
    """
    import os
    import shutil
    import paths

    st = {"ts": _time.time()}

    # ── Disco (nessun accesso DB: sempre disponibile, anche se il DB è occupato) ──
    try:
        dbp = paths.db_path()
        st["db_bytes"] = os.path.getsize(dbp) if os.path.exists(dbp) else 0
        st["wal_bytes"] = sum(os.path.getsize(dbp + s) for s in ("-wal", "-shm")
                              if os.path.exists(dbp + s))
        st["db_path"] = dbp
    except Exception:
        st["db_bytes"] = st["wal_bytes"] = None
    try:
        st["data_dir"] = paths.data_dir()
        du = shutil.disk_usage(st["data_dir"])
        st["disk_free"] = du.free
        st["disk_total"] = du.total
    except Exception:
        st["disk_free"] = st["disk_total"] = None

    # ── Cattura (stato in-process: privacy è lo stesso modulo dei thread) ──
    try:
        from modules import privacy
        from db import get_setting
        st["cap_screens"] = (get_setting("capture_screenshots_enabled", "1") or "1") == "1"
        st["cap_audio"] = (get_setting("capture_audio_enabled", "1") or "1") == "1"
        st["paused"] = privacy.is_paused()
        st["pause_left"] = max(0.0, privacy.pause_until_ts() - _time.time()) if st["paused"] else 0.0
    except Exception:
        st["cap_screens"] = st["cap_audio"] = st["paused"] = None
        st["pause_left"] = 0.0

    # ── Archivio + indice (una sola connessione) ──
    try:
        from db import get_conn, db_encrypted, fts_available, fts_ready
        conn = get_conn()
        try:
            c = conn.cursor()

            def one(sql, default=None):
                try:
                    row = c.execute(sql).fetchone()
                    return row[0] if row else default
                except Exception:
                    return default

            # MAX/MIN(ts) usano idx_*_ts: costo trascurabile, stanno nel giro
            # economico. I COUNT(*) invece scandiscono l'indice per intero.
            st["last_ss"] = one("SELECT MAX(ts) FROM screenshots")
            st["last_au"] = one("SELECT MAX(ts) FROM audio_segments")
            if full:
                st["n_ss"] = one("SELECT COUNT(*) FROM screenshots", 0)
                st["n_au"] = one("SELECT COUNT(*) FROM audio_segments", 0)
                st["n_web"] = one("SELECT COUNT(*) FROM web_pages", 0)
                st["n_ev"] = one("SELECT COUNT(*) FROM system_events", 0)
                st["first_ts"] = one("SELECT MIN(ts) FROM screenshots")
                st["n_ss_emb"] = one("SELECT COUNT(*) FROM screenshot_embeddings", 0)
                st["n_au_emb"] = one("SELECT COUNT(*) FROM audio_embeddings", 0)
        finally:
            conn.close()
        st["encrypted"] = db_encrypted()
        st["fts"] = ("pronto" if fts_ready() else
                     ("in costruzione" if fts_available() else "non disponibile"))
    except Exception as e:
        st["db_error"] = str(e)[:120]

    # ── Sicurezza ──
    try:
        from modules import secrets as _secrets
        st["key_backend"] = ("DPAPI (Windows)" if _secrets.dpapi_available()
                             else ("Portachiavi di sistema" if _secrets.keyring_available()
                                   else "nessuno (in chiaro)"))
    except Exception:
        st["key_backend"] = None
    try:
        from modules import applock
        st["lock_on"] = applock.lock_enabled() and applock.has_usable_method()
    except Exception:
        st["lock_on"] = None

    # ── Ritmo di crescita: MB/giorno e giorni residui sul disco ──
    try:
        first = st.get("first_ts")
        if first and st.get("db_bytes"):
            t0 = datetime.fromisoformat(first)
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            days = max(0.5, (datetime.now(timezone.utc) - t0).total_seconds() / 86400.0)
            st["bytes_day"] = st["db_bytes"] / days
            st["days_span"] = days
            if st.get("disk_free") and st["bytes_day"] > 0:
                st["days_left"] = st["disk_free"] / st["bytes_day"]
    except Exception:
        pass
    return st


def status_headline(st):
    """(testo, colore) dello stato di cattura, dalla fotografia `collect_status`."""
    if not st:
        return "Stato sconosciuto", theme.INK_DIM
    if st.get("paused"):
        left = _fmt_left(st.get("pause_left", 0))
        if left == "incognito":
            return "Incognito", theme.AMBER
        return (f"In pausa · {left}" if left else "In pausa"), theme.AMBER
    ss, au = st.get("cap_screens"), st.get("cap_audio")
    if ss is None:
        return "Stato sconosciuto", theme.INK_DIM
    if ss and au:
        return "Cattura attiva", theme.EMERALD
    if ss:
        return "Solo schermate", theme.EMERALD
    if au:
        return "Solo audio", theme.AMBER
    return "Cattura disattivata", theme.INK_DIM


class StatusWorker(QThread):
    """Raccoglie la fotografia di stato fuori dal thread UI (vedi collect_status)."""
    done = pyqtSignal(dict)

    def __init__(self, full=True, parent=None):
        super().__init__(parent)
        self._full = full

    def run(self):
        try:
            self.done.emit(collect_status(full=self._full))
        except Exception as e:
            self.done.emit({"db_error": str(e)[:120]})


class StatusPoller:
    """Cadenza a due velocità per lo stato: giro economico a ogni tick, giro
    COMPLETO (i COUNT) solo ogni `full_every` secondi. Fonde le fotografie così
    i chiamanti vedono sempre un dict completo. Mai due worker in volo."""

    def __init__(self, on_update, full_every=60.0):
        self._on_update = on_update
        self._full_every = full_every
        self._last_full = 0.0
        self._worker = None
        self.state = {}

    def busy(self):
        return self._worker is not None and self._worker.isRunning()

    def tick(self, force_full=False):
        if self.busy():
            return   # niente accodamento: il prossimo tick riprova
        full = force_full or (_time.time() - self._last_full) >= self._full_every
        if full:
            self._last_full = _time.time()
        self._worker = StatusWorker(full=full)
        self._worker.done.connect(self._merge)
        self._worker.start()

    def _merge(self, st):
        self.state.update(st or {})
        try:
            self._on_update(self.state)
        except Exception:
            pass


class StatusDot(QWidget):
    """Pallino di stato che PULSA quando la cattura è attiva (feedback vivo:
    fermo = fermo). L'animazione gira solo se acceso, niente timer sprecati."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(9, 9)
        self._color = QColor(theme.INK_DIM)
        self._live = False
        self._phase = 0.0
        self._t = QTimer(self)
        self._t.setInterval(90)
        self._t.timeout.connect(self._step)

    def set_state(self, color, live):
        self._color = QColor(color)
        if live != self._live:
            self._live = live
            self._t.start() if live else self._t.stop()
            if not live:
                self._phase = 0.0
        self.update()

    def _step(self):
        self._phase = (self._phase + 0.09) % 1.0
        self.update()

    def paintEvent(self, _e):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if self._live:
            # alone che respira attorno al punto pieno
            halo = QColor(self._color)
            halo.setAlphaF(0.16 + 0.16 * (1 + math.cos(self._phase * 2 * math.pi)) / 2)
            p.setBrush(halo)
            p.drawEllipse(QRectF(0, 0, 9, 9))
            p.setBrush(self._color)
            p.drawEllipse(QRectF(2, 2, 5, 5))
        else:
            p.setBrush(self._color)
            p.drawEllipse(QRectF(2, 2, 5, 5))
        p.end()


class _ClickableRow(QWidget):
    """Riga cliccabile con hover (usata dal blocco profilo in sidebar)."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("clickrow")
        self._style(False)

    def _style(self, hover):
        bg = "rgba(255,255,255,0.04)" if hover else "transparent"
        self.setStyleSheet(f"QWidget#clickrow{{background:{bg}; border-radius:10px;}}"
                           " QWidget#clickrow QLabel{background:transparent;}")

    def enterEvent(self, e):
        self._style(True); super().enterEvent(e)

    def leaveEvent(self, e):
        self._style(False); super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class StatusCard(QFrame):
    """Card di stato in fondo alla sidebar. Prima era testo FISSO ('● Cattura
    attiva' + conteggio della sola pagina caricata); ora mostra dati reali e
    live, si clicca per aprire il pannello e ha il toggle pausa inline."""
    clicked = pyqtSignal()
    toggle_pause = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statuscard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._paint_style()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 13, 13, 14)
        lay.setSpacing(9)

        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(8)
        self._dot = StatusDot()
        self._state = QLabel("Lettura stato…")
        self._state.setStyleSheet(f"color:{theme.INK_DIM}; font-size:12px; font-weight:500;")
        head.addWidget(self._dot); head.addWidget(self._state); head.addStretch()
        self._pause_btn = QPushButton()
        self._pause_btn.setFixedSize(24, 24)
        self._pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_btn.setStyleSheet(
            "QPushButton{border:none; background:transparent; border-radius:7px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.09);}")
        self._pause_btn.clicked.connect(self.toggle_pause.emit)
        head.addWidget(self._pause_btn)
        lay.addLayout(head)

        self._rows = {}
        for key, label in (("archive", "Archivio"), ("disk", "Spazio"), ("last", "Ultima")):
            r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0)
            k = QLabel(label); k.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11.5px;")
            v = QLabel("—"); v.setFont(QFont(theme.MONO, 9))
            v.setStyleSheet(f"color:{theme.INK_SOFT};")
            r.addWidget(k); r.addStretch(); r.addWidget(v)
            self._rows[key] = v
            lay.addLayout(r)
        self._sync_pause_icon(False)

    def _paint_style(self):
        bg = "rgba(255,255,255,0.045)" if self._hover else "transparent"
        border = theme.LINE_STRONG if self._hover else theme.LINE
        self.setStyleSheet(
            f"QFrame#statuscard{{border:1px solid {border}; border-radius:12px; background:{bg};}}"
            " QFrame#statuscard QLabel{border:none; background:transparent;}")

    def enterEvent(self, e):
        self._hover = True; self._paint_style(); super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False; self._paint_style(); super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def _sync_pause_icon(self, paused):
        key, col = ("play", theme.AMBER) if paused else ("pause", theme.INK_DIM)
        self._pause_btn.setIcon(QIcon(_svg_pixmap(key, col, 13, sw=1.6)))
        self._pause_btn.setIconSize(QSize(13, 13))
        self._pause_btn.setToolTip("Riprendi la cattura" if paused else "Metti in pausa 15 minuti")

    def apply(self, st):
        """Aggiorna la card dalla fotografia di `collect_status`."""
        text, color = status_headline(st)
        live = bool(st.get("cap_screens") or st.get("cap_audio")) and not st.get("paused")
        self._dot.set_state(color, live)
        self._state.setText(text)
        self._state.setStyleSheet(f"color:{color}; font-size:12px; font-weight:500;")
        self._sync_pause_icon(bool(st.get("paused")))

        n = sum(st.get(k) or 0 for k in ("n_ss", "n_au", "n_web", "n_ev"))
        self._rows["archive"].setText(f"{_fmt_num(n)} ricordi" if n else "vuoto")
        db = st.get("db_bytes")
        self._rows["disk"].setText(_fmt_bytes((db or 0) + (st.get("wal_bytes") or 0))
                                   if db is not None else "—")
        last = max([t for t in (st.get("last_ss"), st.get("last_au")) if t], default=None)
        self._rows["last"].setText(_fmt_ago(last))
        self.setToolTip("Clic per i dettagli dello stato")


class StatusPanel(QDialog):
    """Pannello 'Stato di Déjà': tutto in tempo reale (si aggiorna da solo finché
    è aperto) più le azioni rapide. Aperto dalla card in sidebar."""

    def __init__(self, parent, on_pause, on_resume):
        super().__init__(parent)
        self._on_pause, self._on_resume = on_pause, on_resume
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(392)
        self._drag = None
        self._st = {}

        outer = QVBoxLayout(self); outer.setContentsMargins(16, 16, 16, 16); outer.setSpacing(0)
        card = QFrame(); card.setObjectName("stcard")
        card.setStyleSheet(
            f"QFrame#stcard{{background:{theme.SURFACE}; border:1px solid {theme.LINE_STRONG};"
            " border-radius:16px;} QFrame#stcard QLabel{background:transparent;}")
        outer.addWidget(card)
        try:
            from PyQt6.QtWidgets import QGraphicsDropShadowEffect
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(46); eff.setColor(QColor(0, 0, 0, 170)); eff.setOffset(0, 10)
            card.setGraphicsEffect(eff)
        except Exception:
            pass

        cl = QVBoxLayout(card); cl.setContentsMargins(20, 16, 20, 18); cl.setSpacing(0)
        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 4); head.setSpacing(9)
        self._dot = StatusDot()
        self._head_lbl = QLabel("Stato di Déjà")
        self._head_lbl.setFont(QFont(theme.SANS, 13, QFont.Weight.DemiBold))
        self._head_lbl.setStyleSheet(f"color:{theme.INK};")
        head.addWidget(self._dot); head.addWidget(self._head_lbl); head.addStretch()
        close = QPushButton("✕"); close.setFixedSize(26, 26)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"QPushButton{{border:none; background:transparent; color:{theme.INK_DIM};"
                            " font-size:13px; border-radius:8px;}"
                            "QPushButton:hover{background:rgba(255,255,255,0.09); color:#fff;}")
        close.clicked.connect(self.reject)
        head.addWidget(close)
        cl.addLayout(head)

        self._sub = QLabel("—")
        self._sub.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11.5px;")
        self._sub.setContentsMargins(18, 0, 0, 10)
        cl.addWidget(self._sub)

        self._val = {}
        for section, rows in (
            ("Cattura", (("cap_screens", "Schermate"), ("cap_audio", "Audio"),
                         ("last_ss", "Ultima schermata"), ("last_au", "Ultimo audio"))),
            ("Archivio", (("n_ss", "Schermate"), ("n_au", "Segmenti audio"),
                          ("n_web", "Pagine web"), ("n_ev", "Eventi"),
                          ("span", "Copre"))),
            ("Spazio", (("db", "Database"), ("wal", "Journal (WAL)"),
                        ("rate", "Crescita"), ("free", "Libero sul disco"),
                        ("left", "Autonomia stimata"))),
            ("Indice e sicurezza", (("index", "Indicizzazione"), ("fts", "Ricerca testuale"),
                                    ("enc", "Database"), ("key", "Chiave"),
                                    ("lock", "Blocco app"))),
        ):
            s = QLabel(section.upper())
            f = QFont(theme.MONO, 8); f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 116)
            s.setFont(f); s.setContentsMargins(0, 14, 0, 5)
            s.setStyleSheet(f"color:{theme.INK_FAINT};")
            cl.addWidget(s)
            for key, label in rows:
                r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0); r.setSpacing(12)
                k = QLabel(label); k.setStyleSheet(f"color:{theme.INK_DIM}; font-size:12px;")
                v = QLabel("—"); v.setFont(QFont(theme.MONO, 9))
                v.setStyleSheet(f"color:{theme.INK_SOFT};")
                v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                r.addWidget(k); r.addStretch(); r.addWidget(v)
                self._val[key] = v
                cl.addLayout(r)

        acts = QHBoxLayout(); acts.setContentsMargins(0, 18, 0, 0); acts.setSpacing(8)
        self._b_pause = self._btn("Pausa 15 min", self._pause_clicked, primary=True)
        acts.addWidget(self._b_pause)
        acts.addWidget(self._btn("Apri cartella dati", self._open_folder))
        acts.addStretch()
        cl.addLayout(acts)

        # Auto-refresh finché il pannello è aperto: tick da 2s (i numeri devono
        # muoversi sotto gli occhi) ma i COUNT solo ogni 20s — vedi StatusPoller.
        self._poller = StatusPoller(self.apply, full_every=20.0)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poller.tick)
        self._timer.start()
        self._poller.tick(force_full=True)

    @staticmethod
    def _btn(text, slot, primary=False):
        b = QPushButton(text); b.setFixedHeight(31)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:rgba(167,139,250,0.14); color:{theme.VIOLET};"
                f" border:1px solid rgba(167,139,250,0.28); border-radius:9px;"
                " padding:0 14px; font-size:12px; font-weight:600;}"
                "QPushButton:hover{background:rgba(167,139,250,0.22);}")
        else:
            b.setStyleSheet(
                f"QPushButton{{background:rgba(255,255,255,0.05); color:{theme.INK_SOFT};"
                f" border:1px solid {theme.LINE}; border-radius:9px;"
                " padding:0 14px; font-size:12px; font-weight:500;}"
                "QPushButton:hover{background:rgba(255,255,255,0.10); color:#fff;}")
        b.clicked.connect(slot)
        return b

    # ── Dati ────────────────────────────────────────────────────────
    def refresh(self, force_full=False):
        self._poller.tick(force_full=force_full)

    def apply(self, st):
        self._st = st
        text, color = status_headline(st)
        self._head_lbl.setText(text)
        self._head_lbl.setStyleSheet(f"color:{color};")
        self._dot.set_state(color, bool(st.get("cap_screens") or st.get("cap_audio"))
                            and not st.get("paused"))
        paused = bool(st.get("paused"))
        self._b_pause.setText("Riprendi" if paused else "Pausa 15 min")

        def on_off(v):
            return "attiva" if v else ("—" if v is None else "spenta")

        self._sub.setText(st.get("db_path") or st.get("data_dir") or "")
        self._val["cap_screens"].setText(on_off(st.get("cap_screens")))
        self._val["cap_audio"].setText(on_off(st.get("cap_audio")))
        self._val["last_ss"].setText(_fmt_ago(st.get("last_ss")))
        self._val["last_au"].setText(_fmt_ago(st.get("last_au")))
        for k in ("n_ss", "n_au", "n_web", "n_ev"):
            self._val[k].setText(_fmt_num(st.get(k)))
        days = st.get("days_span")
        self._val["span"].setText(f"{int(days)} giorni" if days else "—")

        self._val["db"].setText(_fmt_bytes(st.get("db_bytes")))
        self._val["wal"].setText(_fmt_bytes(st.get("wal_bytes")))
        rate = st.get("bytes_day")
        self._val["rate"].setText(f"{_fmt_bytes(rate)}/giorno" if rate else "—")
        self._val["free"].setText(_fmt_bytes(st.get("disk_free")))
        left = st.get("days_left")
        if left is None:
            self._val["left"].setText("—")
        elif left > 3650:
            self._val["left"].setText("oltre 10 anni")
        else:
            self._val["left"].setText(f"~{int(left)} giorni")
        self._val["left"].setStyleSheet(
            f"color:{theme.AMBER if (left is not None and left < 30) else theme.INK_SOFT};")

        # Indicizzazione: quanto dell'archivio ha già l'embedding semantico.
        n_items = (st.get("n_ss") or 0) + (st.get("n_au") or 0)
        n_emb = (st.get("n_ss_emb") or 0) + (st.get("n_au_emb") or 0)
        if not n_items:
            self._val["index"].setText("—")
        elif n_emb >= n_items:
            self._val["index"].setText("completa")
        else:
            self._val["index"].setText(f"{n_emb * 100 // n_items}% · {_fmt_num(n_items - n_emb)} in coda")
        self._val["fts"].setText(st.get("fts") or "—")
        enc = st.get("encrypted")
        self._val["enc"].setText("cifrato (SQLCipher)" if enc else
                                 ("—" if enc is None else "IN CHIARO"))
        self._val["enc"].setStyleSheet(f"color:{theme.INK_SOFT if enc else theme.AMBER};")
        self._val["key"].setText(st.get("key_backend") or "—")
        lock = st.get("lock_on")
        self._val["lock"].setText("attivo" if lock else ("—" if lock is None else "disattivato"))

    # ── Azioni ──────────────────────────────────────────────────────
    def _pause_clicked(self):
        if getattr(self, "_st", {}).get("paused"):
            self._on_resume()
        else:
            self._on_pause()
        self.refresh()

    def _open_folder(self):
        import os
        import subprocess
        import sys as _sys
        d = getattr(self, "_st", {}).get("data_dir")
        if not d:
            return
        try:
            if _sys.platform == "win32":
                os.startfile(d)  # noqa: S606 — apre Esplora risorse sulla cartella dati
            elif _sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception:
            pass

    # ── Frameless: trascinamento + stop timer ───────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept(); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag); e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    def resume(self):
        """Riavvia l'auto-refresh (il pannello viene riusato, non ricreato)."""
        if not self._timer.isActive():
            self._timer.start()
        self._poller.tick(force_full=True)

    def closeEvent(self, e):
        self._timer.stop()   # chiuso = zero query: nessun polling a vuoto
        super().closeEvent(e)

    def reject(self):
        self._timer.stop()
        super().reject()


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
        if kind in ("audio", "note", "sys"):
            fill = QColor(hue); fill.setAlpha(40)
            p.fillPath(mp, fill)
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(hue.red(), hue.green(), hue.blue(), 80), 1)); p.drawPath(mp)
            p.setPen(QPen(hue, 1.8, cap=Qt.PenCapStyle.RoundCap))
            if kind == "audio":
                hs = [5, 11, 16, 9, 14, 7, 4]; gi = 6.0
                cx = media.center().x(); cy = media.center().y(); sx = cx - (len(hs) - 1) * gi / 2
                for i, bh in enumerate(hs):
                    p.drawLine(QPointF(sx + i * gi, cy - bh / 2), QPointF(sx + i * gi, cy + bh / 2))
            elif kind == "sys":
                # fulmine (eventi di sistema)
                cx = media.center().x(); cy = media.center().y()
                bolt = QPainterPath(QPointF(cx + 2, cy - 9))
                bolt.lineTo(QPointF(cx - 6, cy + 2)); bolt.lineTo(QPointF(cx - 1, cy + 2))
                bolt.lineTo(QPointF(cx - 2, cy + 9)); bolt.lineTo(QPointF(cx + 6, cy - 2))
                bolt.lineTo(QPointF(cx + 1, cy - 2)); bolt.closeSubpath()
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(bolt)
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
    "sys": '<path d="M13 2L4 14h6l-1 8 9-12h-6z"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    "eyeoff": '<path d="M3 3l18 18"/><path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3.1 4M6.6 6.6A18 18 0 0 0 2 12s3.5 7 10 7a10.9 10.9 0 0 0 4.3-.9"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
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
    # stato / cattura
    "pause": '<rect x="8" y="6" width="3" height="12" rx="1"/><rect x="14" y="6" width="3" height="12" rx="1"/>',
    "play": '<path d="M8 5.5l10 6.5-10 6.5z"/>',
    "disk": '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
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

        # Stato cattura + archivio: card VIVA (dati reali dal DB/disco, clic →
        # pannello dettagliato, toggle pausa inline). Vedi StatusCard.
        self._status_card = StatusCard()
        self._status_card.clicked.connect(self._open_status_panel)
        self._status_card.toggle_pause.connect(self._toggle_pause)
        sl.addWidget(self._status_card)

        # Profilo — anche questo cliccabile: apre lo stesso pannello, e la riga
        # 'locale · cifrato' riflette lo STATO REALE della cifratura (prima era
        # una stringa fissa: mentiva se SQLCipher/DPAPI non erano disponibili).
        import getpass
        try:
            username = getpass.getuser() or "Utente"
        except Exception:
            username = "Utente"
        prof = _ClickableRow()
        prl = QHBoxLayout(prof); prl.setContentsMargins(8, 16, 8, 2); prl.setSpacing(11)
        av = QLabel(username[:1].upper()); av.setFixedSize(34, 34); av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet(f"background:#22222b; border:1px solid {theme.LINE}; border-radius:9px;"
                         f" color:{theme.INK_SOFT}; font-size:14px; font-weight:600;")
        pcol = QVBoxLayout(); pcol.setSpacing(1)
        pn = QLabel(username); pn.setStyleSheet(f"color:{theme.INK}; font-size:13px; font-weight:600;")
        self._profile_sub = QLabel("locale")
        self._profile_sub.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px; background:transparent;")
        pcol.addWidget(pn); pcol.addWidget(self._profile_sub)
        prl.addWidget(av); prl.addLayout(pcol); prl.addStretch()
        prof.clicked.connect(self._open_status_panel)
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
        self._current_page = "timeline"
        self._load()  # carica i dati reali dopo che il detail esiste

        # Quasi-realtime leggero: ogni pochi secondi controlla se sono arrivati
        # nuovi screenshot (query MAX(id), economica) e ricarica la timeline SOLO
        # se è cambiata e l'utente è in cima (non interrompe chi sta sfogliando).
        self._last_max_id = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(4000)
        self._refresh_timer.timeout.connect(self._maybe_refresh)
        self._refresh_timer.start()

        # Stato live della sidebar: raccolta SEMPRE su thread separato e a due
        # velocità (economico ogni 4s, totali ogni 60s) — vedi StatusPoller.
        self._status = StatusPoller(self._on_status, full_every=60.0)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(4000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()
        QTimer.singleShot(300, lambda: self._refresh_status(force_full=True))

    # ── Pagina Timeline ─────────────────────────────────────────────
    def _build_timeline_page(self):
        main = QWidget(); ml = QVBoxLayout(main); ml.setContentsMargins(0, 0, 0, 0); ml.setSpacing(0)
        top = QWidget(); top.setObjectName("hbar"); top.setFixedHeight(58); top.setStyleSheet(f"QWidget#hbar{{border-bottom:1px solid {theme.LINE};}}")
        # Riserva a destra per i controlli finestra (overlay) → il segmento/toggle non ci finisce sotto.
        tl = QHBoxLayout(top); tl.setContentsMargins(20, 0, 134, 0); tl.setSpacing(12)
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
                                ("audio", "Audio", theme.AMBER_RGB),
                                ("system", "Eventi", (96, 165, 250))):
            b = SegButton(label, dot=dot, on=(key == "all"))
            b.clicked.connect(lambda _=False, k=key: self._set_tl_filter(k))
            self._tl_seg[key] = b; self._tl_seg_keys.append(key); seg.add_button(b)
        self._seg_bar = seg
        tl.addWidget(seg)

        # Toggle "mostra nascosti": appare solo col filtro Eventi. Di default i
        # processi background/sistema/Déjà sono nascosti (no infodump); il
        # bottone rivela TUTTO ciò che è stato registrato.
        self._tl_show_hidden = False
        self._tl_hidebtn = QPushButton()
        self._tl_hidebtn.setCheckable(True)
        self._tl_hidebtn.setFixedHeight(36)
        self._tl_hidebtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tl_hidebtn.setVisible(False)
        self._tl_hidebtn.clicked.connect(self._toggle_show_hidden)
        self._sync_hidebtn()
        tl.addWidget(self._tl_hidebtn)
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
        # Cap larghezza = pannello fisso (366) − margini − scrollbar: senza, con un
        # transcript lungo il sizeHint del QLabel wordwrap diventa più largo del
        # pannello → niente scrollbar orizzontale → testo tagliato a destra.
        self._detail_body.setMaximumWidth(316)
        self._detail_body.setStyleSheet(f"color:{theme.INK_SOFT}; font-size:13px;")
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

        # ── Audio vicini (± N minuti) — solo per i ricordi audio ──
        self._nearby_wrap = QWidget()
        nv = QVBoxLayout(self._nearby_wrap); nv.setContentsMargins(0, 8, 0, 0); nv.setSpacing(7)
        nhead = QHBoxLayout(); nhead.setContentsMargins(0, 0, 0, 0); nhead.setSpacing(8)
        nlbl = QLabel("AUDIO VICINI"); nlbl.setFont(cf); nlbl.setStyleSheet(f"color:{theme.INK_FAINT};")
        self._nearby_min = QSpinBox(); self._nearby_min.setRange(1, 180); self._nearby_min.setValue(15)
        self._nearby_min.setPrefix("± "); self._nearby_min.setSuffix(" min"); self._nearby_min.setFixedHeight(26)
        self._nearby_min.setStyleSheet(
            f"QSpinBox{{background:rgba(255,255,255,0.05); color:{theme.INK}; border:1px solid {theme.LINE};"
            f" border-radius:7px; padding:1px 6px; font-size:11px;}}"
            f"QSpinBox::up-button,QSpinBox::down-button{{width:12px;}}")
        self._nearby_min.valueChanged.connect(lambda *_: self._refill_nearby())
        nhead.addWidget(nlbl); nhead.addStretch(); nhead.addWidget(self._nearby_min)
        nv.addLayout(nhead)
        self._nearby_list = QWidget()
        self._nearby_list_l = QVBoxLayout(self._nearby_list)
        self._nearby_list_l.setContentsMargins(0, 0, 0, 0); self._nearby_list_l.setSpacing(4)
        nv.addWidget(self._nearby_list)
        self._nearby_wrap.setVisible(False)
        bv.addWidget(self._nearby_wrap)

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
        # Data/ora assoluta del segmento (l'utente vuole sapere QUANDO è stato registrato).
        self._audio_when = QLabel("")
        self._audio_when.setFont(QFont(theme.MONO, 8))
        self._audio_when.setStyleSheet(f"color:{theme.INK_DIM}; background:transparent;")
        al.addWidget(self._audio_when)
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
        # il toggle "mostra nascosti" ha senso solo sugli Eventi
        if hasattr(self, "_tl_hidebtn"):
            self._tl_hidebtn.setVisible(key == "system")
        self._build_rows()
        for i in range(self.timeline.count()):
            it = self.timeline.item(i)
            if it and not it.data(TL_HOUR):
                self.timeline.setCurrentRow(i); break
        QTimer.singleShot(0, lambda: self._ensure_visible_thumbs(self.timeline))

    def _sync_hidebtn(self):
        """Aggiorna icona/testo/stile del toggle 'mostra nascosti'."""
        on = self._tl_show_hidden
        icon = "eye" if on else "eyeoff"
        label = "  Nascondi background" if on else "  Mostra nascosti"
        self._tl_hidebtn.setIcon(QIcon(_svg_pixmap(icon, theme.INK_SOFT, 15)))
        self._tl_hidebtn.setText(label)
        self._tl_hidebtn.setToolTip(
            "Sto mostrando anche i processi di sistema/Déjà" if on
            else "Mostro solo le app con finestra; clicca per vedere tutto")
        self._tl_hidebtn.setStyleSheet(
            f"QPushButton{{background:rgba(255,255,255,{'0.08' if on else '0.04'});"
            f" color:{theme.INK if on else theme.INK_SOFT}; border:1px solid {theme.LINE};"
            f" border-radius:10px; padding:0 12px; font-family:'{theme.SANS}'; font-size:12px;}}"
            "QPushButton:hover{background:rgba(255,255,255,0.10);}")

    def _toggle_show_hidden(self):
        self._tl_show_hidden = not self._tl_show_hidden
        self._sync_hidebtn()
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

        # ── Barra superiore: titolo + segmento Schermate/Audio ──
        top = QWidget(); top.setObjectName("hbar"); top.setFixedHeight(58)
        top.setStyleSheet(f"QWidget#hbar{{border-bottom:1px solid {theme.LINE};}}")
        # Margine destro ampio: lascia spazio ai controlli finestra (overlay top-right)
        # così il segmento Schermate/Audio non finisce sotto i pulsanti min/max/close.
        tl = QHBoxLayout(top); tl.setContentsMargins(20, 0, 134, 0); tl.setSpacing(12)
        head = QLabel("Galleria"); head.setFont(QFont(theme.SANS, 14, QFont.Weight.DemiBold))
        head.setStyleSheet(f"color:{theme.INK};")
        tl.addWidget(head); tl.addStretch()
        seg = _SegBar(); self._gal_seg = {}; self._gal_seg_keys = []
        for key, label, dot in (("screens", "Schermate", theme.EMERALD_RGB),
                                ("audio", "Audio", theme.AMBER_RGB)):
            b = SegButton(label, dot=dot, on=(key == "screens"))
            b.clicked.connect(lambda _=False, k=key: self._gallery_set_mode(k))
            self._gal_seg[key] = b; self._gal_seg_keys.append(key); seg.add_button(b)
        self._gal_seg_bar = seg
        tl.addWidget(seg)
        pl.addWidget(top)

        # ── Filtro data/ora (solo modalità Audio) ──
        self._gal_filter_bar = QWidget()
        self._gal_filter_bar.setStyleSheet(
            f"QLabel{{color:{theme.INK_DIM}; font-size:12px; background:transparent;}}"
            f"QDateEdit,QSpinBox{{background:rgba(255,255,255,0.05); color:{theme.INK};"
            f" border:1px solid {theme.LINE}; border-radius:8px; padding:4px 8px; font-size:12px;}}"
            f"QDateEdit::drop-down{{width:16px;}}"
            f"QSpinBox::up-button,QSpinBox::down-button{{width:14px;}}"
            f"QCheckBox{{color:{theme.INK_SOFT}; font-size:12px; spacing:6px;}}")
        fb = QHBoxLayout(self._gal_filter_bar); fb.setContentsMargins(20, 10, 20, 10); fb.setSpacing(9)
        self._gal_allaudio = QCheckBox("Tutti"); self._gal_allaudio.setChecked(True)
        self._gal_allaudio.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gal_allaudio.stateChanged.connect(lambda *_: self._reload_audio_gallery())
        self._gal_date = QDateEdit(); self._gal_date.setCalendarPopup(True)
        self._gal_date.setDisplayFormat("dd/MM/yyyy"); self._gal_date.setDate(QDate.currentDate())
        self._gal_date.dateChanged.connect(lambda *_: self._reload_audio_gallery())
        self._gal_h_from = QSpinBox(); self._gal_h_from.setRange(0, 23); self._gal_h_from.setValue(0); self._gal_h_from.setSuffix(":00")
        self._gal_h_to = QSpinBox(); self._gal_h_to.setRange(0, 23); self._gal_h_to.setValue(23); self._gal_h_to.setSuffix(":59")
        for w in (self._gal_h_from, self._gal_h_to):
            w.valueChanged.connect(lambda *_: self._reload_audio_gallery())
        fb.addWidget(self._gal_allaudio)
        sep = QLabel("·"); sep.setStyleSheet(f"color:{theme.INK_FAINT};"); fb.addWidget(sep)
        fb.addWidget(QLabel("Giorno")); fb.addWidget(self._gal_date)
        fb.addWidget(QLabel("dalle")); fb.addWidget(self._gal_h_from)
        fb.addWidget(QLabel("alle")); fb.addWidget(self._gal_h_to)
        fb.addStretch()
        self._gal_count = QLabel(""); self._gal_count.setStyleSheet(f"color:{theme.INK_FAINT}; font-size:11px;")
        fb.addWidget(self._gal_count)
        self._gal_filter_bar.setVisible(False)
        pl.addWidget(self._gal_filter_bar)

        # ── Stack: griglia schermate / lista audio ──
        self._gal_stack = QStackedWidget()
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
        self._gal_stack.addWidget(self.gallery)

        # Lista audio (stesso look della timeline, così il click apre il player nel detail)
        self.audio_list = QListWidget()
        self.audio_list.setStyleSheet(theme.results_list() + " QListWidget{padding:4px 12px;}")
        self.audio_list.setItemDelegate(TimelineDelegate(self.audio_list))
        self.audio_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.audio_list.currentRowChanged.connect(
            self._make_pick_handler(lambda: self.audio_list, "_audio_records"))
        self._gal_stack.addWidget(self.audio_list)

        pl.addWidget(self._gal_stack, stretch=1)
        self._gallery_mode = "screens"
        self._audio_records = []
        return page

    def _gallery_enter(self):
        """Chiamato entrando in Galleria: applica la modalità corrente (schermate
        di default) e carica i dati se serve."""
        self._gallery_set_mode(getattr(self, "_gallery_mode", "screens"))

    def _gallery_set_mode(self, mode):
        self._gallery_mode = mode
        audio = (mode == "audio")
        if mode in self._gal_seg_keys:
            self._gal_seg_bar.set_active(self._gal_seg_keys.index(mode), animate=True)
        self._gal_stack.setCurrentIndex(1 if audio else 0)
        self._gal_filter_bar.setVisible(audio)
        # Il detail (player) serve solo per l'audio; per le schermate resta nascosto.
        self.detail.setVisible(audio)
        if audio:
            if not getattr(self, "_audio_gal_loaded", False):
                self._reload_audio_gallery()
        else:
            if not self._gallery_loaded:
                self._load_gallery()

    def _reload_audio_gallery(self):
        from modules import search as search_module
        allaudio = self._gal_allaudio.isChecked()
        for w in (self._gal_date, self._gal_h_from, self._gal_h_to):
            w.setEnabled(not allaudio)
        if allaudio:
            day = None; hf, ht = 0, 23
        else:
            qd = self._gal_date.date()
            day = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
            hf = self._gal_h_from.value(); ht = max(self._gal_h_from.value(), self._gal_h_to.value())
        try:
            recs = search_module.list_audio(day_iso=day, hour_from=hf, hour_to=ht, limit=5000)
        except Exception as e:
            recs = []; print(f"[Gallery] list_audio fail: {e}")
        self._audio_records = recs
        self._audio_gal_loaded = True
        self.audio_list.blockSignals(True)
        self.audio_list.clear()
        for idx, r in enumerate(recs):
            title, sub = self._row_text(r, "audio")
            it = QListWidgetItem()
            it.setData(TL_TITLE, title); it.setData(TL_SUB, sub)
            it.setData(TL_TIME, self._clock(r.get("ts", "")))
            it.setData(TL_KIND, "audio"); it.setData(TL_HUE, HUE.get("audio", theme.VIOLET_RGB))
            it.setData(TL_ID, r.get("id")); it.setData(TL_IDX, idx)
            self.audio_list.addItem(it)
        self.audio_list.blockSignals(False)
        self._gal_count.setText(f"{len(recs)} audio" + ("  (max 5000)" if len(recs) >= 5000 else ""))
        if recs:
            self.audio_list.setCurrentRow(0)
        else:
            self._show_detail_sections(shot=False, body=True, audio=False)
            self._detail_title.setText("Nessun audio")
            self._detail_body.setTextFormat(Qt.TextFormat.PlainText)
            self._detail_body.setText("Nessuna registrazione per il filtro selezionato.")

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
        # header_right_pad: libera l'angolo in alto a dx dai controlli finestra overlay
        self.chat_page = ChatPage(header_right_pad=132)
        self.chat_page.send_clicked.connect(self._send_chat_message)
        self.chat_page.new_chat_btn.clicked.connect(self._reset_chat)
        self.chat_page.stop_btn.clicked.connect(self._stop_chat)
        self._chat_history = []
        self._chat_worker = None
        self._chat_activity = None
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
        self._current_page = key
        self._stack.setCurrentIndex(idx)
        self._fade_in(self._stack.currentWidget())
        for k, b in self._nav.items():
            b.setChecked(k == key)
        # Detail condiviso solo per Timeline e Cerca
        self.detail.setVisible(key in ("timeline", "search"))
        if key == "search":
            self.search_input.setFocus()
        elif key == "gallery":
            self._gallery_enter()
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
        subpages = (("general", "Generale", "sliders", self._build_set_general),
                    ("capture", "Cattura", "capture", self._build_set_capture),
                    ("events", "Eventi", "sys", self._build_set_events),
                    ("privacy", "Area & Privacy", "shield", self._build_set_privacy),
                    ("ai", "Assistente AI", "spark", self._build_set_ai),
                    ("vision", "Vision", "screen", self._build_set_vision),
                    ("models", "Modelli", "ai", self._build_set_models),
                    ("security", "Sicurezza", "lock", self._build_set_security))
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

    def _build_set_general(self, get_setting):
        import i18n
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Interfaccia", first=True))
        self._s_lang = self._set_combo(
            [(f"{i18n.LANG_FLAGS.get(c,'')} {n}", c) for c, n in i18n.LANGUAGES.items()],
            current=i18n.get_language(), width=180)
        self._s_lang_old = i18n.get_language()
        lay.addWidget(self._set_row("Lingua interfaccia", "Richiede riavvio per ridisegnare l'app.", self._s_lang))

        lay.addWidget(self._set_section("Archivio"))
        try:
            from db import get_conn
            conn = get_conn(); c = conn.cursor()
            n_ss = c.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
            n_au = c.execute("SELECT COUNT(*) FROM audio_segments").fetchone()[0]
            conn.close()
        except Exception:
            n_ss = n_au = "—"
        lay.addWidget(self._set_row("Schermate salvate", "Totale screenshot nell'archivio locale.", self._stat_value(n_ss)))
        lay.addWidget(self._set_row("Segmenti audio", "Totale registrazioni trascritte.", self._stat_value(n_au)))
        lay.addStretch()
        return w

    def _build_set_capture(self, get_setting):
        import config as _cfg
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Registrazione", first=True))
        self._s_cap_screens = ToggleSwitch((get_setting("capture_screenshots_enabled", "1") or "1") == "1")
        lay.addWidget(self._set_row("Cattura schermate", "Salva periodicamente schermate del desktop.", self._s_cap_screens))
        self._s_cap_audio = ToggleSwitch((get_setting("capture_audio_enabled", "1") or "1") == "1")
        lay.addWidget(self._set_row("Cattura audio", "Registra e trascrive microfono / audio di sistema.", self._s_cap_audio))
        self._s_interval = self._set_input(str(getattr(_cfg, "CAPTURE_INTERVAL", "")), "es. 4")
        self._s_interval.setFixedWidth(90)
        lay.addWidget(self._set_row("Intervallo schermate (s)", "Secondi tra una schermata e l'altra.", self._s_interval))
        self._s_audio_chunk = self._set_input(str(getattr(_cfg, "AUDIO_CHUNK_SECONDS", "")), "es. 30")
        self._s_audio_chunk.setFixedWidth(90)
        lay.addWidget(self._set_row("Durata segmento audio (s)", "Lunghezza di ogni spezzone audio registrato.", self._s_audio_chunk))

        lay.addWidget(self._set_section("Dispositivi audio"))
        intro = QLabel("Scegli una sorgente <b>Principale</b> e una di <b>Riserva</b>. "
                       "Déjà usa la Principale; se la scolleghi passa da solo alla "
                       "Riserva (es. cuffie → casse).")
        intro.setWordWrap(True); intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11.5px; background:transparent;")
        lay.addWidget(intro)

        try:
            from ui.settings import _get_all_devices
            _devs = _get_all_devices()
        except Exception:
            _devs = []
        # I device sono salvati per NOME (stabile tra riavvii), in ordine di
        # priorità: principale → riserva. A runtime si usa il primo collegato.
        mics  = [name for tp, idx, name in _devs if tp == "mic"]
        loops = [name for tp, idx, name in _devs if tp == "loopback"]

        import json as _json
        def _prio(key):
            raw = get_setting(key, None)
            if raw:
                try:
                    v = _json.loads(raw)
                    if isinstance(v, list):
                        return [str(x) for x in v if x]
                except Exception:
                    pass
            return []

        def _legacy_name(legacy_key, pool):
            li = get_setting(legacy_key, None)
            if li is None:
                return None
            try:
                li = int(li)
            except (ValueError, TypeError):
                return None
            for tp, idx, name in _devs:
                if idx == li and name in pool:
                    return name
            return None

        mic_prio = _prio("audio_mic_priority")
        out_prio = _prio("audio_out_priority")
        # Migrazione display: vecchio indice singolo → nome (poi riscritto al salvataggio).
        if not mic_prio:
            lm = _legacy_name("audio_mic_index", mics)
            if lm:
                mic_prio = [lm]
        if not out_prio:
            lo = _legacy_name("audio_out_index", loops)
            if lo:
                out_prio = [lo]

        # Combo vuote: popolamento (e refresh) in _populate_audio_combos.
        self._s_mic  = self._set_combo([], width=240)
        self._s_mic2 = self._set_combo([], width=240)
        self._s_out  = self._set_combo([], width=240)
        self._s_out2 = self._set_combo([], width=240)

        # Gruppo Microfono — header dedicato così è chiaro cosa controlla.
        lay.addWidget(self._set_section("🎙  Microfono — la tua voce"))
        lay.addWidget(self._set_row("1 · Principale", "Microfono che usi di solito (es. cuffie).", self._s_mic))
        lay.addWidget(self._set_row("2 · Riserva", "Solo se la Principale non è collegata. Opzionale.", self._s_mic2))

        # Gruppo Audio di sistema (loopback)
        lay.addWidget(self._set_section("🔊  Audio di sistema — ciò che esce dal PC"))
        lay.addWidget(self._set_row("1 · Principale", "Uscita audio preferita (es. cuffie).", self._s_out))
        lay.addWidget(self._set_row("2 · Riserva", "Solo se la Principale non è collegata (es. casse). Opzionale.", self._s_out2))

        self._populate_audio_combos(_devs, mic_prio, out_prio)

        # Rileva dispositivi: ri-enumera live (cuffie collegate dopo l'avvio).
        refresh = QPushButton("↻  Rileva dispositivi")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor); refresh.setFixedHeight(30)
        refresh.setStyleSheet(
            f"QPushButton{{background:transparent; color:{theme.INK_SOFT}; border:1px solid {theme.LINE};"
            f" border-radius:8px; padding:0 14px; font-family:'{theme.SANS}'; font-size:12px;}}"
            "QPushButton:hover{background:rgba(255,255,255,0.04);}")
        refresh.clicked.connect(self._refresh_audio_devices)
        rrow = QHBoxLayout(); rrow.setContentsMargins(2, 6, 2, 0)
        rrow.addWidget(refresh); rrow.addStretch()
        lay.addLayout(rrow)

        note = QLabel("Hai collegato le cuffie ora? Premi <b>Rileva dispositivi</b> per vederle in elenco. "
                      "Durante la registrazione il passaggio cuffie ⇄ casse è automatico.")
        note.setWordWrap(True); note.setTextFormat(Qt.TextFormat.RichText)
        note.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px; background:transparent;")
        lay.addWidget(note)
        lay.addStretch()
        return w

    def _populate_audio_combos(self, devs, mic_sel=None, out_sel=None):
        """(Ri)popola le 4 combo audio dai device enumerati. Se mic_sel/out_sel
        sono None → preserva la selezione corrente (refresh); altrimenti applica
        le liste priorità passate (primo build)."""
        mics  = [name for tp, idx, name in devs if tp == "mic"]
        loops = [name for tp, idx, name in devs if tp == "loopback"]
        mic_items = [("Non registrare", None)] + [(n, n) for n in mics]
        out_items = [("Non registrare", None)] + [(n, n) for n in loops]

        def _fill(cb, items, sel):
            prev = cb.currentData() if sel is None else sel
            cb.blockSignals(True); cb.clear()
            for label, data in items:
                cb.addItem(label, data)
            ix = cb.findData(prev) if prev is not None else -1
            cb.setCurrentIndex(ix if ix >= 0 else 0)
            cb.blockSignals(False)

        def _at(lst, i):
            return lst[i] if (lst is not None and i < len(lst)) else None

        _fill(self._s_mic,  mic_items, _at(mic_sel, 0))
        _fill(self._s_mic2, mic_items, _at(mic_sel, 1))
        _fill(self._s_out,  out_items, _at(out_sel, 0))
        _fill(self._s_out2, out_items, _at(out_sel, 1))

    def _refresh_audio_devices(self):
        """Ri-enumera i device (bypassa la cache) e ripopola le combo,
        preservando le scelte già fatte. Per device collegati dopo l'avvio."""
        try:
            from ui.settings import _get_all_devices
            devs = _get_all_devices(force=True)
        except Exception:
            devs = []
        self._populate_audio_combos(devs)

    def _build_set_events(self, get_setting):
        """Eventi di sistema + eventi browser. TUTTO OFF di default: ogni
        categoria parte a "0" e il collector la attiva live al salvataggio."""
        w, lay = self._set_body()

        def _tgl(key):
            return ToggleSwitch((get_setting(key, "0") or "0") == "1")

        lay.addWidget(self._set_section("Eventi di sistema", first=True))
        self._s_ev_process = _tgl("sysev_process_enabled")
        lay.addWidget(self._set_row("App aperte e chiuse", "Registra avvio e chiusura dei programmi (nome, percorso, durata).", self._s_ev_process))
        self._s_ev_focus = _tgl("sysev_focus_enabled")
        lay.addWidget(self._set_row("App in primo piano", "Registra quando passi da un'app all'altra (rispetta la blocklist privacy).", self._s_ev_focus))
        self._s_ev_file = _tgl("sysev_file_enabled")
        lay.addWidget(self._set_row("Attività sui file", "File creati, eliminati, spostati o rinominati nelle cartelle utente.", self._s_ev_file))
        self._s_ev_file_dirs = self._set_input(get_setting("sysev_file_dirs", "") or "",
                                               "vuoto = Desktop, Documenti, Download, …")
        lay.addWidget(self._set_row("Cartelle osservate", "Percorsi separati da ';'. Vuoto = cartelle utente standard.", self._s_ev_file_dirs))
        self._s_ev_install = _tgl("sysev_install_enabled")
        lay.addWidget(self._set_row("Programmi installati", "Installazioni, aggiornamenti e disinstallazioni (nome, versione, publisher).", self._s_ev_install))
        self._s_ev_device = _tgl("sysev_device_enabled")
        lay.addWidget(self._set_row("Unità e dispositivi", "Chiavette USB e dischi collegati o rimossi.", self._s_ev_device))
        self._s_ev_network = _tgl("sysev_network_enabled")
        lay.addWidget(self._set_row("Rete", "Interfacce di rete connesse o disconnesse.", self._s_ev_network))
        self._s_ev_power = _tgl("sysev_power_enabled")
        lay.addWidget(self._set_row("Sospensione e ripresa", "Quando il PC va in standby e quando riprende (con durata).", self._s_ev_power))
        self._s_ev_session = _tgl("sysev_session_enabled")
        lay.addWidget(self._set_row("Blocco sessione", "Blocco e sblocco della sessione Windows.", self._s_ev_session))
        self._s_ev_clock = _tgl("sysev_clock_enabled")
        lay.addWidget(self._set_row("Cambio orario", "Modifiche all'orario di sistema.", self._s_ev_clock))

        lay.addWidget(self._set_section("Eventi browser (estensione)"))
        note = QLabel("Richiedono l'estensione browser attiva (Area & Privacy → Estensione browser).")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px; background:transparent;")
        lay.addWidget(note)
        self._s_ev_download = _tgl("webev_download_enabled")
        lay.addWidget(self._set_row("Download", "File scaricati dal browser (nome, origine, dimensione).", self._s_ev_download))
        self._s_ev_tab = _tgl("webev_tab_enabled")
        lay.addWidget(self._set_row("Tab", "Apertura e chiusura delle schede.", self._s_ev_tab))
        self._s_ev_visit = _tgl("webev_visit_enabled")
        lay.addWidget(self._set_row("Pagine visitate", "Cronologia leggera delle visite (URL e titolo, senza contenuto).", self._s_ev_visit))
        lay.addStretch()
        return w

    def _build_set_privacy(self, get_setting):
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Area schermo & Privacy", first=True))
        # Area di cattura (region picker)
        self._s_region_lbl = QLabel(self._region_text())
        self._s_region_lbl.setStyleSheet(f"color:{theme.INK_SOFT}; font-size:12px; background:transparent;")
        reg_ctl = QWidget(); reg_ctl.setStyleSheet("background:transparent;")
        rcl = QHBoxLayout(reg_ctl); rcl.setContentsMargins(0, 0, 0, 0); rcl.setSpacing(8)
        rcl.addWidget(self._s_region_lbl)
        rcl.addWidget(self._accent_btn("Scegli area", self._choose_region))
        rcl.addWidget(self._ghost_btn("Reset", self._reset_region))
        lay.addWidget(self._set_row("Area di cattura", "Limita gli screenshot a una porzione di schermo.", reg_ctl))

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
            web_on = _wb.enabled(); web_conn = _wb.is_connected()
        except Exception:
            web_on = False; web_conn = False
        self._s_web_enabled = ToggleSwitch(web_on)
        lay.addWidget(self._set_row("Abilita estensione", "Cattura le pagine visitate (canale locale, nessuna porta di rete).", self._s_web_enabled))
        self._s_web_excluded = self._set_input(get_setting("web_excluded_domains", "") or "", "bank.com, mail.google.com")
        lay.addWidget(self._set_row("Domini da non catturare", "Uno o più domini separati da virgola.", self._s_web_excluded))
        self._s_web_extid = self._set_input(get_setting("web_ext_id", "") or "", "ID estensione Chrome / Edge")
        lay.addWidget(self._set_row("ID estensione", "Identificativo dell'estensione installata nel browser.", self._s_web_extid))
        host_ctl = QWidget(); host_ctl.setStyleSheet("background:transparent;")
        hcl = QHBoxLayout(host_ctl); hcl.setContentsMargins(0, 0, 0, 0); hcl.setSpacing(8)
        self._s_web_status = QLabel("● connessa" if web_conn else "○ non connessa")
        self._s_web_status.setStyleSheet(f"color:{theme.EMERALD if web_conn else theme.INK_DIM}; font-size:12px; background:transparent;")
        hcl.addWidget(self._s_web_status)
        hcl.addWidget(self._accent_btn("Installa host nativo", self._install_web_host))
        lay.addWidget(self._set_row("Host nativo", "Ponte locale tra browser e Déjà.", host_ctl))
        lay.addStretch()
        return w

    def _build_set_ai(self, get_setting):
        import config as _cfg
        w, lay = self._set_body()
        try: cfg = ai_assistant.get_ai_config()
        except Exception: cfg = {}
        lay.addWidget(self._set_section("Assistente AI", first=True))
        _def = getattr(_cfg, "AI_BASE_URL_DEFAULT", "")
        _url = cfg.get("base_url", "") or ""
        self._s_ai_url = self._set_input("" if _url == _def else _url, _def or "https://api.openai.com/v1")
        lay.addWidget(self._set_row("Endpoint (base URL)", "URL compatibile OpenAI per la chat.", self._s_ai_url))
        lay.addWidget(self._preset_chips(self._s_ai_url, [("Ollama", "http://localhost:11434/v1"), ("LM Studio", "http://localhost:1234/v1")]))
        self._s_ai_key = self._set_input("", "•••• (lascia vuoto per non cambiare)")
        self._s_ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._set_row("API key", "Salvata cifrata (DPAPI). Vuoto = invariata.", self._s_ai_key))
        self._s_ai_model = self._set_model_combo(getattr(_cfg, "AI_MODELS", []), cfg.get("model", ""))
        mctl, self._s_ai_detect = self._combo_with_button(self._s_ai_model, "Rileva", self._ai_detect)
        lay.addWidget(self._set_row("Modello chat", "Nome del modello sull'endpoint (o premi Rileva).", mctl))
        self._s_ai_inline = ToggleSwitch((get_setting("ai_inline_rag", "1") or "1") == "1")
        lay.addWidget(self._set_row("Cita i ricordi (RAG)", "L'assistente allega schermate/audio pertinenti alle risposte.", self._s_ai_inline))
        self._s_ai_agentic = ToggleSwitch((get_setting("ai_agentic_search", "0") or "0") == "1")
        lay.addWidget(self._set_row("Ricerca agentica", "Più ricerche in parallelo: più veloce e supera i limiti di token per risposta. Usa più chiamate (costo maggiore).", self._s_ai_agentic))
        self._s_ai_status = QLabel(""); self._s_ai_status.setWordWrap(True)
        self._s_ai_status.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px; background:transparent;")
        lay.addWidget(self._accent_btn("Prova connessione", self._ai_test), alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._s_ai_status)
        lay.addStretch()
        return w

    def _build_set_vision(self, get_setting):
        import config as _cfg
        w, lay = self._set_body()
        try:
            from modules import ask_screen as _ask
            vcfg = _ask.get_vision_config()
        except Exception:
            vcfg = {"enabled": False, "base_url": "", "api_key": "", "model": ""}
        lay.addWidget(self._set_section("Vision · Ask Screen", first=True))
        self._s_vis_enabled = ToggleSwitch(bool(vcfg.get("enabled")))
        lay.addWidget(self._set_row("Abilita Vision", "Interroga lo schermo con un modello multimodale.", self._s_vis_enabled))
        _vdef = getattr(_cfg, "AI_VISION_BASE_URL_DEFAULT", "")
        _vurl = vcfg.get("base_url", "") or ""
        self._s_vis_url = self._set_input("" if _vurl == _vdef else _vurl, _vdef)
        lay.addWidget(self._set_row("Endpoint (base URL)", "URL compatibile OpenAI per la vision.", self._s_vis_url))
        lay.addWidget(self._preset_chips(self._s_vis_url, [("Ollama", "http://localhost:11434/v1"), ("LM Studio", "http://localhost:1234/v1")]))
        self._s_vis_key = self._set_input("", "•••• (lascia vuoto per non cambiare)")
        self._s_vis_key.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._set_row("API key", "Salvata cifrata (DPAPI). Vuoto = invariata.", self._s_vis_key))
        self._s_vis_model = self._set_model_combo(getattr(_cfg, "AI_VISION_MODELS", []), vcfg.get("model", ""))
        vctl, self._s_vis_detect = self._combo_with_button(self._s_vis_model, "Rileva", self._vis_detect)
        lay.addWidget(self._set_row("Modello vision", "Nome del modello multimodale (o premi Rileva).", vctl))
        self._s_vis_status = QLabel(""); self._s_vis_status.setWordWrap(True)
        self._s_vis_status.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px; background:transparent;")
        lay.addWidget(self._accent_btn("Prova Vision", self._vis_test), alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._s_vis_status)
        lay.addStretch()
        return w

    def _build_set_models(self, get_setting):
        import config as _cfg
        from modules import model_catalog as _mc
        w, lay = self._set_body()
        self._adv_models = {}
        lay.addWidget(self._set_section("Modelli locali", first=True))
        cur_embed = str(getattr(_cfg, "EMBEDDING_MODEL", "") or "")
        emb = self._set_combo(
            [(f"{m['label']} · {_mc.human_size(m['size_mb'])}" + (f" · {m['dims']}d" if m.get("dims") else ""), m["id"])
             for m in _mc.EMBEDDING_MODELS], current=cur_embed)
        if cur_embed and emb.findData(cur_embed) < 0:
            emb.addItem(f"{cur_embed} (custom)", cur_embed); emb.setCurrentIndex(emb.count() - 1)
        self._adv_model_block(lay, "Embedding (ricerca)", emb, "embed")
        cur_wsp = str(getattr(_cfg, "WHISPER_MODEL", "") or "")
        wsp = self._set_combo(
            [(f"{m['label']} · {_mc.human_size(m['size_mb'])}", m["id"]) for m in _mc.WHISPER_MODELS],
            current=cur_wsp)
        if cur_wsp and wsp.findData(cur_wsp) < 0:
            wsp.addItem(f"{cur_wsp} (custom)", cur_wsp); wsp.setCurrentIndex(wsp.count() - 1)
        self._adv_model_block(lay, "Trascrizione (Whisper)", wsp, "whisper")
        cur_ocr = get_setting("ocr_lang", "ita+eng") or "ita+eng"
        ocr = self._set_combo(
            [(f"{m['label']} · {_mc.human_size(m['size_mb'])}", m["id"]) for m in _mc.OCR_MODELS],
            current=cur_ocr)
        if ocr.findData(cur_ocr) < 0:
            ocr.addItem(f"{cur_ocr} (custom)", cur_ocr); ocr.setCurrentIndex(ocr.count() - 1)
        self._adv_model_block(lay, "OCR (lingua testo)", ocr, "ocr", downloadable=False)
        try:
            _score0 = int(float(getattr(_cfg, "AUDIO_MIN_SCORE", 0.25)) * 100)
        except Exception:
            _score0 = 25
        self._s_audio_score = Stepper(_score0, 1, 99, step=1, suffix=" %")
        lay.addWidget(self._set_row("Soglia rilevanza audio", "Scarta i segmenti trascritti sotto questa confidenza.", self._s_audio_score))
        lay.addStretch()
        return w

    def _build_set_security(self, get_setting):
        w, lay = self._set_body()
        lay.addWidget(self._set_section("Sicurezza", first=True))
        try:
            from modules import applock
            lock_on = applock.lock_enabled(); hello = applock.hello_available()
        except Exception:
            lock_on = False; hello = False
        self._s_lock_enabled = ToggleSwitch(lock_on)
        lay.addWidget(self._set_row("Blocco app", "Richiede sblocco all'apertura e per dati sensibili.", self._s_lock_enabled))
        self._s_lock_relock = self._set_combo(
            [("Ogni accesso", "every_access"), ("Dopo inattività", "idle"), ("Solo manuale", "manual")],
            current=get_setting("lock_relock", "every_access") or "every_access", width=200)
        lay.addWidget(self._set_row("Ri-blocco", "Quando richiedere di nuovo lo sblocco.", self._s_lock_relock))
        method = "Sblocco con Windows Hello (volto/impronta/PIN)." if hello else "Sblocco con PIN dell'app."
        lay.addWidget(self._set_row("PIN di sblocco", method, self._accent_btn("Imposta / cambia PIN", self._change_pin)))
        lay.addStretch()
        return w

    # ── Helper controlli pagina settings ────────────────────────────
    @staticmethod
    def _stat_value(value):
        lb = QLabel(str(value))
        lb.setStyleSheet(f"color:{theme.INK}; font-size:15px; font-weight:700; background:transparent;")
        return lb

    def _accent_btn(self, text, slot=None, height=32):
        b = QPushButton(text); b.setFixedHeight(height); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{background:rgba(167,139,250,0.14); color:{theme.VIOLET};"
            f" border:1px solid rgba(167,139,250,0.30); border-radius:8px; padding:0 14px;"
            f" font-family:'{theme.SANS}'; font-size:12px; font-weight:600;}}"
            "QPushButton:hover{background:rgba(167,139,250,0.24);}"
            "QPushButton:disabled{background:transparent; color:rgba(255,255,255,0.3); border:1px solid rgba(255,255,255,0.08);}")
        if slot is not None:
            b.clicked.connect(slot)
        return b

    def _ghost_btn(self, text, slot=None, height=32):
        b = QPushButton(text); b.setFixedHeight(height); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{background:transparent; color:{theme.INK_SOFT}; border:1px solid {theme.LINE};"
            f" border-radius:8px; padding:0 14px; font-family:'{theme.SANS}'; font-size:12px;}}"
            "QPushButton:hover{background:rgba(255,255,255,0.04);}")
        if slot is not None:
            b.clicked.connect(slot)
        return b

    def _preset_chips(self, line_edit, presets):
        row = QWidget(); row.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(row); rl.setContentsMargins(2, 0, 2, 0); rl.setSpacing(7)
        hint = QLabel("Preset:"); hint.setStyleSheet(f"color:{theme.INK_FAINT}; font-size:11px; background:transparent;")
        rl.addWidget(hint)
        for name, url in presets:
            b = QPushButton(name); b.setFixedHeight(26); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:rgba(255,255,255,0.04); color:{theme.INK_SOFT}; border:1px solid {theme.LINE};"
                f" border-radius:7px; padding:0 11px; font-size:11px;}}"
                "QPushButton:hover{background:rgba(167,139,250,0.18); color:#fff; border:1px solid rgba(167,139,250,0.4);}")
            b.clicked.connect(lambda _=False, u=url, le=line_edit: le.setText(u))
            rl.addWidget(b)
        rl.addStretch()
        return row

    def _set_model_combo(self, items, current, width=210):
        cb = QComboBox(); cb.setEditable(True)
        for m in items:
            cb.addItem(m)
        if current:
            ix = cb.findText(current)
            cb.setCurrentIndex(ix) if ix >= 0 else cb.setCurrentText(current)
        cb.setFixedHeight(32); cb.setMinimumWidth(width)
        cb.setStyleSheet(
            f"QComboBox{{background:rgba(255,255,255,0.04); color:{theme.INK}; border:1px solid {theme.LINE};"
            f" border-radius:8px; padding:0 10px; font-size:12px;}}"
            f"QComboBox:hover{{border:1px solid rgba(167,139,250,0.4);}}"
            f"QComboBox::drop-down{{border:none; width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#1a1a20; color:{theme.INK}; border:1px solid {theme.LINE};"
            f" selection-background-color:rgba(167,139,250,0.25); outline:none;}}")
        if cb.lineEdit() is not None:
            cb.lineEdit().setStyleSheet(f"background:transparent; color:{theme.INK}; border:none;")
        return cb

    def _combo_with_button(self, combo, btn_text, slot):
        box = QWidget(); box.setStyleSheet("background:transparent;")
        bl = QHBoxLayout(box); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(8)
        bl.addWidget(combo, stretch=1)
        btn = self._accent_btn(btn_text, slot)
        bl.addWidget(btn)
        return box, btn

    @staticmethod
    def _populate_model_combo(combo, ids):
        cur = combo.currentText().strip()
        combo.blockSignals(True); combo.clear()
        for mid in ids:
            combo.addItem(mid)
        if cur:
            ix = combo.findText(cur)
            combo.setCurrentIndex(ix) if ix >= 0 else combo.setCurrentText(cur)
        combo.blockSignals(False)

    # ── Azioni settings: region / pin / web host / detect / test ────
    def _region_text(self):
        from db import get_setting as _gs
        raw = _gs("capture_region", "") or ""
        if raw and raw != "full":
            try:
                import json
                r = json.loads(raw)
                return f"Area {int(r['width'])}×{int(r['height'])} px"
            except Exception:
                pass
        return "Schermo intero"

    def _choose_region(self):
        try:
            from ui.region_select import select_region
            from db import save_setting
            self.hide()
            r = select_region(None)
            self.show(); self.raise_(); self.activateWindow()
            if r:
                import json
                save_setting("capture_region", json.dumps(r))
                self._s_region_lbl.setText(self._region_text())
        except Exception as e:
            self.toast(f"Selezione area non disponibile: {e}", level="error")

    def _reset_region(self):
        try:
            from db import save_setting
            save_setting("capture_region", "full")
            self._s_region_lbl.setText(self._region_text())
        except Exception as e:
            self.toast(f"Errore reset area: {e}", level="error")

    def _change_pin(self):
        try:
            from ui.lock import setup_pin
            setup_pin(self)
        except Exception as e:
            self.toast(f"Impostazione PIN non disponibile: {e}", level="error")

    def _install_web_host(self):
        try:
            from modules import web_bridge as _wb
            from db import save_setting
            save_setting("web_ext_id", self._s_web_extid.text().strip())
            ok, msg = _wb.install_native_host()
            self.toast("Host nativo installato" if ok else f"Installazione fallita: {msg}",
                       level=("ok" if ok else "error"))
        except Exception as e:
            self.toast(f"Errore host nativo: {e}", level="error")

    def _resolved_key(self, typed, getter):
        """Key digitata, o quella salvata se il campo è vuoto (placeholder)."""
        if typed:
            return typed
        try:
            return getter().get("api_key", "") or ""
        except Exception:
            return ""

    def _ai_detect(self):
        import config as _cfg
        base = self._s_ai_url.text().strip() or getattr(_cfg, "AI_BASE_URL_DEFAULT", "")
        key = self._resolved_key(self._s_ai_key.text().strip(), ai_assistant.get_ai_config)
        self._s_ai_detect.setEnabled(False); self._s_ai_status.setText("Rilevamento modelli…")
        from PyQt6.QtWidgets import QApplication; QApplication.processEvents()
        try:
            ok, res = ai_assistant.list_models(base_url=base, api_key=key or None)
        except Exception as e:
            ok, res = False, str(e)
        if ok and isinstance(res, list) and res:
            self._populate_model_combo(self._s_ai_model, res)
            self._s_ai_status.setText(f"✓ {len(res)} modelli disponibili")
        else:
            self._s_ai_status.setText("✗ " + (str(res) if not ok else "nessun modello"))
        self._s_ai_detect.setEnabled(True)

    def _ai_test(self):
        from db import save_setting
        from modules.secrets import protect_secret as _protect
        try:
            k = self._s_ai_key.text().strip()
            if k: save_setting("ai_api_key", _protect(k))
            save_setting("ai_base_url", self._s_ai_url.text().strip())
            save_setting("ai_model", self._s_ai_model.currentText().strip())
        except Exception:
            pass
        self._s_ai_status.setText("Test connessione in corso…")
        from PyQt6.QtWidgets import QApplication; QApplication.processEvents()
        try:
            ok, msg = ai_assistant.test_connection()
        except Exception as e:
            ok, msg = False, str(e)
        self._s_ai_status.setText(("✓ " if ok else "✗ ") + str(msg))

    def _vis_detect(self):
        import config as _cfg
        from modules import ask_screen as _ask
        base = self._s_vis_url.text().strip() or getattr(_cfg, "AI_VISION_BASE_URL_DEFAULT", "")
        key = self._resolved_key(self._s_vis_key.text().strip(), _ask.get_vision_config)
        self._s_vis_detect.setEnabled(False); self._s_vis_status.setText("Rilevamento modelli…")
        from PyQt6.QtWidgets import QApplication; QApplication.processEvents()
        try:
            ok, res = ai_assistant.list_models(base_url=base, api_key=key or None)
        except Exception as e:
            ok, res = False, str(e)
        if ok and isinstance(res, list) and res:
            self._populate_model_combo(self._s_vis_model, res)
            self._s_vis_status.setText(f"✓ {len(res)} modelli disponibili")
        else:
            self._s_vis_status.setText("✗ " + (str(res) if not ok else "nessun modello"))
        self._s_vis_detect.setEnabled(True)

    def _vis_test(self):
        from db import save_setting
        from modules.secrets import protect_secret as _protect
        try:
            save_setting("ai_vision_enabled", "1" if self._s_vis_enabled.isChecked() else "0")
            k = self._s_vis_key.text().strip()
            if k: save_setting("ai_vision_api_key", _protect(k))
            save_setting("ai_vision_base_url", self._s_vis_url.text().strip())
            save_setting("ai_vision_model", self._s_vis_model.currentText().strip())
        except Exception:
            pass
        self._s_vis_status.setText("Test Vision in corso…")
        from PyQt6.QtWidgets import QApplication; QApplication.processEvents()
        try:
            from modules import ask_screen as _ask
            ok, msg = _ask.test_vision_connection()
        except Exception as e:
            ok, msg = False, str(e)
        self._s_vis_status.setText(("✓ " if ok else "✗ ") + str(msg))

    # combo stilizzata come gli altri controlli della pagina settings
    def _set_combo(self, items, current=None, width=200):
        cb = QComboBox()
        for label, data in items:
            cb.addItem(label, data)
        if current is not None:
            ix = cb.findData(current)
            if ix >= 0:
                cb.setCurrentIndex(ix)
        cb.setFixedHeight(32); cb.setMinimumWidth(width)
        cb.setStyleSheet(
            f"QComboBox{{background:rgba(255,255,255,0.04); color:{theme.INK}; border:1px solid {theme.LINE};"
            f" border-radius:8px; padding:0 10px; font-size:12px;}}"
            f"QComboBox:hover{{border:1px solid rgba(167,139,250,0.4);}}"
            f"QComboBox::drop-down{{border:none; width:22px;}}"
            f"QComboBox QAbstractItemView{{background:#1a1a20; color:{theme.INK}; border:1px solid {theme.LINE};"
            f" selection-background-color:rgba(167,139,250,0.25); outline:none;}}")
        return cb

    def _adv_model_block(self, parent_lay, title, combo, kind, downloadable=True):
        """Riga modello: combo + pulsante Scarica + stato cache (porting da SettingsDialog)."""
        from modules import model_catalog as _mc
        box = QFrame(); box.setObjectName("frow")
        box.setStyleSheet(f"QFrame#frow{{border:none; border-bottom:1px solid {theme.LINE};}}"
                          " QFrame#frow QLabel{border:none; background:transparent;}")
        v = QVBoxLayout(box); v.setContentsMargins(2, 13, 2, 13); v.setSpacing(8)
        t = QLabel(title); t.setStyleSheet(f"color:{theme.INK}; font-size:13px; font-weight:500;")
        v.addWidget(t)
        row = QHBoxLayout(); row.setSpacing(8)
        row.addWidget(combo, stretch=1)
        dl = None
        if downloadable:
            dl = QPushButton("Scarica"); dl.setFixedHeight(32); dl.setCursor(Qt.CursorShape.PointingHandCursor)
            dl.setStyleSheet(
                f"QPushButton{{background:rgba(167,139,250,0.14); color:{theme.VIOLET};"
                f" border:1px solid rgba(167,139,250,0.30); border-radius:8px; padding:0 14px;"
                f" font-family:'{theme.SANS}'; font-size:12px; font-weight:600;}}"
                "QPushButton:hover{background:rgba(167,139,250,0.24);}"
                "QPushButton:disabled{background:transparent; color:rgba(255,255,255,0.3); border:1px solid rgba(255,255,255,0.08);}")
            dl.clicked.connect(lambda _=False, k=kind: self._adv_download(k))
            row.addWidget(dl)
        v.addLayout(row)
        cap = QLabel(""); cap.setWordWrap(True); cap.setStyleSheet(f"color:{theme.INK_DIM}; font-size:11px;")
        v.addWidget(cap)
        parent_lay.addWidget(box)
        catalog = {"embed": _mc.EMBEDDING_MODELS, "whisper": _mc.WHISPER_MODELS, "ocr": _mc.OCR_MODELS}[kind]
        self._adv_models[kind] = {"combo": combo, "catalog": catalog, "cap": cap, "dl": dl, "is_hf": downloadable}
        combo.currentIndexChanged.connect(lambda *_: self._adv_refresh_cap(kind))
        self._adv_refresh_cap(kind)

    def _adv_refresh_cap(self, kind):
        from modules import model_catalog as mc
        m = self._adv_models.get(kind)
        if not m:
            return
        combo, catalog, cap, dl, is_hf = m["combo"], m["catalog"], m["cap"], m["dl"], m["is_hf"]
        mid = combo.currentData() or combo.currentText()
        meta = mc.find(catalog, mid)
        note = meta.get("note", "") if meta else "Modello personalizzato"
        if is_hf:
            cached = mc.is_cached(mid)
            status = "scaricato ✓" if cached else "non scaricato"
            cap.setText(f"{note} — {status}" if note else status)
            if dl is not None:
                dl.setEnabled(not cached); dl.setText("Scaricato" if cached else "Scarica")
        else:
            installed = mc.ocr_installed(mid) if mid else False
            size = mc.human_size(meta["size_mb"]) if meta else "?"
            cap.setText(f"{size} — {'installato ✓' if installed else 'non installato'}")

    def _adv_download(self, kind):
        m = self._adv_models.get(kind)
        if not m or not m["is_hf"]:
            return
        combo, cap, dl = m["combo"], m["cap"], m["dl"]
        mid = combo.currentData() or combo.currentText()
        if not mid:
            return
        if dl is not None:
            dl.setEnabled(False)
        cap.setText("Scaricamento in corso…")
        from ui.window import ModelDownloadWorker
        self._adv_dl_worker = ModelDownloadWorker(kind, mid)
        self._adv_dl_worker.done.connect(lambda ok, msg, k=kind: self._adv_on_download(k, ok, msg))
        self._adv_dl_worker.start()

    def _adv_on_download(self, kind, ok, msg):
        m = self._adv_models.get(kind)
        if not m:
            return
        if ok:
            self._adv_refresh_cap(kind)
        else:
            m["cap"].setText("✗ " + msg)
            if m["dl"] is not None:
                m["dl"].setEnabled(True)

    def _save_settings(self):
        from db import save_setting, get_conn
        from modules.secrets import protect_secret as _protect
        import config as _cfg
        errs = 0; restart_lang = False

        # ── Generale: lingua interfaccia ──
        try:
            import i18n
            lang = self._s_lang.currentData()
            if lang and lang != self._s_lang_old:
                i18n.set_language(lang); restart_lang = True
        except Exception as e:
            errs += 1; print(f"[Set] lingua: {e}")

        # ── Cattura: toggle, intervalli, dispositivi ──
        try:
            save_setting("capture_screenshots_enabled", "1" if self._s_cap_screens.isChecked() else "0")
            save_setting("capture_audio_enabled", "1" if self._s_cap_audio.isChecked() else "0")
            for raw, key, attr in ((self._s_interval.text().strip(), "capture_interval", "CAPTURE_INTERVAL"),
                                   (self._s_audio_chunk.text().strip(), "audio_chunk_seconds", "AUDIO_CHUNK_SECONDS")):
                if not raw:
                    continue
                dv = getattr(_cfg, attr, None)
                try:
                    val = type(dv)(raw) if dv is not None else raw
                except (ValueError, TypeError):
                    continue
                save_setting(key, val); setattr(_cfg, attr, val)
            import json as _json
            def _collect(*combos):
                seq = []
                for cb in combos:
                    v = cb.currentData()
                    if v and v not in seq:
                        seq.append(v)
                return seq
            mic_seq = _collect(self._s_mic, self._s_mic2)
            out_seq = _collect(self._s_out, self._s_out2)
            conn = get_conn(); c = conn.cursor()
            for key, seq, legacy in (("audio_mic_priority", mic_seq, "audio_mic_index"),
                                     ("audio_out_priority", out_seq, "audio_out_index")):
                if seq:
                    c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, _json.dumps(seq)))
                else:
                    c.execute("DELETE FROM settings WHERE key=?", (key,))
                # Rimuovi il vecchio indice instabile: ora si usa il nome.
                c.execute("DELETE FROM settings WHERE key=?", (legacy,))
            conn.commit(); conn.close()
            try:
                from modules.audio import request_restart; request_restart()
            except Exception:
                pass
        except Exception as e:
            errs += 1; print(f"[Set] cattura: {e}")

        # ── Eventi di sistema + browser (tutto OFF di default) ──
        try:
            for key, tgl in (("sysev_process_enabled", self._s_ev_process),
                             ("sysev_focus_enabled", self._s_ev_focus),
                             ("sysev_file_enabled", self._s_ev_file),
                             ("sysev_install_enabled", self._s_ev_install),
                             ("sysev_device_enabled", self._s_ev_device),
                             ("sysev_network_enabled", self._s_ev_network),
                             ("sysev_power_enabled", self._s_ev_power),
                             ("sysev_session_enabled", self._s_ev_session),
                             ("sysev_clock_enabled", self._s_ev_clock),
                             ("webev_download_enabled", self._s_ev_download),
                             ("webev_tab_enabled", self._s_ev_tab),
                             ("webev_visit_enabled", self._s_ev_visit)):
                save_setting(key, "1" if tgl.isChecked() else "0")
            save_setting("sysev_file_dirs", self._s_ev_file_dirs.text().strip())
        except Exception as e:
            errs += 1; print(f"[Set] eventi: {e}")

        # ── Privacy + estensione browser ──
        try:
            save_setting("privacy_redact", "1" if self._s_redact.isChecked() else "0")
            save_setting("privacy_idle_min", str(self._s_idle.value()))
            save_setting("privacy_blocklist", self._s_blocklist.text().strip())
            save_setting("web_ext_id", self._s_web_extid.text().strip())
            from modules import web_bridge as _wb
            _wb.set_enabled(self._s_web_enabled.isChecked())
            _wb.set_excluded_domains(self._s_web_excluded.text().strip())
        except Exception as e:
            errs += 1; print(f"[Set] privacy: {e}")

        # ── Assistente AI ──
        try:
            k = self._s_ai_key.text().strip()
            if k:
                save_setting("ai_api_key", _protect(k))
            save_setting("ai_base_url", self._s_ai_url.text().strip())
            save_setting("ai_model", self._s_ai_model.currentText().strip())
            save_setting("ai_inline_rag", "1" if self._s_ai_inline.isChecked() else "0")
            save_setting("ai_agentic_search", "1" if self._s_ai_agentic.isChecked() else "0")
        except Exception as e:
            errs += 1; print(f"[Set] ai: {e}")

        # ── Vision (Ask Screen) ──
        try:
            save_setting("ai_vision_enabled", "1" if self._s_vis_enabled.isChecked() else "0")
            vk = self._s_vis_key.text().strip()
            if vk:
                save_setting("ai_vision_api_key", _protect(vk))
            save_setting("ai_vision_base_url", self._s_vis_url.text().strip())
            save_setting("ai_vision_model", self._s_vis_model.currentText().strip())
        except Exception as e:
            errs += 1; print(f"[Set] vision: {e}")

        # ── Modelli locali + soglia audio ──
        try:
            emb = self._adv_models["embed"]["combo"]
            v = emb.currentData() or emb.currentText().strip()
            if v:
                save_setting("embedding_model", v); setattr(_cfg, "EMBEDDING_MODEL", v)
            wsp = self._adv_models["whisper"]["combo"]
            v = wsp.currentData() or wsp.currentText().strip()
            if v:
                save_setting("whisper_model", v); setattr(_cfg, "WHISPER_MODEL", v)
            save_setting("ocr_lang", self._adv_models["ocr"]["combo"].currentData())
            sc = self._s_audio_score.value() / 100.0
            save_setting("audio_min_score", sc); setattr(_cfg, "AUDIO_MIN_SCORE", sc)
        except Exception as e:
            errs += 1; print(f"[Set] modelli: {e}")

        # ── Sicurezza ──
        try:
            from modules import applock
            applock.set_lock_enabled(self._s_lock_enabled.isChecked())
            save_setting("lock_relock", self._s_lock_relock.currentData())
        except Exception as e:
            errs += 1; print(f"[Set] sicurezza: {e}")

        self.toast("Impostazioni salvate" if not errs else f"Salvate con {errs} errori (vedi log)",
                   level=("ok" if not errs else "error"))
        if restart_lang:
            self.toast("Riavvia Déjà per applicare la nuova lingua.", level="info")

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
        try: self.chat_page.clear_attachment()
        except Exception: pass
        if not ai_assistant.is_configured():
            self.chat_page.add_notice("Configura una API key in Impostazioni → AI per usare l'Assistente.")
        else:
            self.chat_page.set_busy(False); self.chat_page.input.setFocus()

    def _send_chat_message(self, text):
        # Allegato corrente (chip sopra la barra): si invia con o senza testo.
        att = self.chat_page.take_attachment() if hasattr(self.chat_page, "take_attachment") else None
        text = (text or "").strip()
        if not text and not att:
            return
        if not ai_assistant.is_configured():
            self.chat_page.add_error("API key mancante. Apri Impostazioni → AI.")
            if att:
                self.chat_page.set_attachment(att)   # non perdere l'allegato
            return
        if self._chat_worker is not None and self._chat_worker.isRunning():
            if att:
                self.chat_page.set_attachment(att)
            return
        # Bolla visibile: chip allegato (se c'è) + testo. NIENTE dump del contenuto.
        self.chat_page.add_user(text, attachment=att)
        # Messaggio reale per l'AI: allegato (ref id univoco + contenuto) + domanda.
        ai_text = self._compose_ai_message(att, text)
        _, lbl = self.chat_page.add_thinking()
        self._chat_thinking = lbl
        self._chat_current_bubble = None; self._chat_current_text = ""
        self._chat_turn_bubbles = []
        self._chat_activity = None   # riquadro attività del turno (lazy)
        self.chat_page.set_busy(True)
        try: ai_assistant.save_chat_message("user", ai_text)
        except Exception as e: print(f"[Chat] save user fail: {e}")
        self._chat_worker = ChatWorker(self._chat_history, ai_text)
        self._chat_worker.chunk.connect(self._on_chat_chunk)
        self._chat_worker.finished_streaming.connect(lambda u=ai_text: self._on_chat_done(u))
        self._chat_worker.start()

    def _compose_ai_message(self, att, text):
        """Compone il messaggio inviato al modello: se c'è un allegato, include il
        riferimento UNIVOCO per id + il contenuto reale, poi la domanda dell'utente."""
        if not att:
            return text
        ref = att.get("ref", "")
        sub = att.get("subtitle", "")
        head = att.get("title", "questo ricordo")
        content = (att.get("content") or "").strip()
        if len(content) > 4000:
            content = content[:4000].rstrip() + "…"
        first = f"Allegato — {head} {ref}".strip()
        if sub:
            first += f" ({sub})"
        parts = [first]
        parts.append(f"Contenuto:\n«{content}»" if content else "(Nessun testo riconosciuto nel ricordo.)")
        parts.append(f"Domanda: {text}" if text else "Parlami di questo ricordo.")
        return "\n\n".join(parts)

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

    def _close_activity(self, failed=False, note=""):
        """Collassa il riquadro attività del turno in una riga di riepilogo."""
        act = getattr(self, "_chat_activity", None)
        if act is None:
            return
        try:
            act.fail(note or "interrotto") if failed else act.finish(note)
        except Exception:
            pass
        self._chat_activity = None

    def _stop_chat(self):
        """Ferma la risposta in corso (bottone Stop)."""
        w = self._chat_worker
        if w is None or not w.isRunning():
            return
        w.cancel()
        self._remove_thinking()
        self._close_activity(failed=True, note="fermato")
        self.chat_page.set_busy(False)

    def _on_chat_chunk(self, kind, content):
        if kind == "text":
            self._remove_thinking()
            self._close_activity()
            if self._chat_current_bubble is None:
                container, lbl = self.chat_page.add_assistant("")
                self._chat_current_bubble = lbl; self._chat_current_container = container
                self._chat_current_text = ""
                self._chat_turn_bubbles.append({"container": container, "label": lbl, "text": "", "finalized": False})
            self._chat_current_text += content
            self._chat_current_bubble.setText(self._chat_current_text)
            if self._chat_turn_bubbles:
                self._chat_turn_bubbles[-1]["text"] = self._chat_current_text
        elif kind == "tool":
            # Tutti i passi del turno finiscono in UN riquadro vivo, non in N
            # chip permanenti (in agentica erano 10-15 righe che restavano lì).
            self._remove_thinking()
            if self._chat_current_container is not None and self._chat_current_text:
                self._finalize_bubble(self._chat_current_container, self._chat_current_bubble, self._chat_current_text)
                # già finalizzato qui: non rifinalizzarlo in _on_chat_done (il container
                # è stato distrutto → setText su QLabel morto = crash "QLabel deleted").
                if self._chat_turn_bubbles:
                    self._chat_turn_bubbles[-1]["finalized"] = True
            self._chat_current_bubble = None; self._chat_current_container = None; self._chat_current_text = ""
            if getattr(self, "_chat_activity", None) is None:
                self._chat_activity = self.chat_page.add_activity()
            self._chat_activity.add_step(content)
        elif kind == "error":
            self._remove_thinking()
            self._close_activity(failed=True)
            self.chat_page.add_error(content)
            self._chat_current_bubble = None; self._chat_current_container = None; self._chat_current_text = ""

    def _on_chat_done(self, user_msg):
        self._remove_thinking()
        cancelled = bool(self._chat_worker is not None and self._chat_worker.cancelled())
        self._close_activity(failed=cancelled, note="fermato" if cancelled else "")
        for b in self._chat_turn_bubbles:
            if b["text"] and not b.get("finalized"):
                self._finalize_bubble(b["container"], b["label"], b["text"])
                b["finalized"] = True
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
        # Difensivo: container/label possono essere già stati distrutti (es. doppia
        # finalizzazione dopo un tool-call) → ogni accesso a un QObject morto solleva
        # "wrapped C/C++ object ... has been deleted". Non deve mai arrivare all'excepthook.
        try:
            from PyQt6 import sip
            if sip.isdeleted(container) or sip.isdeleted(label):
                return
        except Exception:
            pass
        try:
            insert_idx = self.chat_page.msg_layout.indexOf(container)
        except Exception:
            insert_idx = -1
        if insert_idx < 0:
            try:
                clean = _strip_refs(raw_text)
                label.setTextFormat(Qt.TextFormat.RichText)
                label.setText(_md_to_html(clean) if clean else " ")
            except (RuntimeError, Exception):
                pass
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
            card = EmbedAudioCard(rid)
            card.play_requested.connect(lambda a, c=card: self._on_embed_audio_play(a, c))
            return card
        if kind == "web":
            card = EmbedWebCard(rid); card.clicked.connect(self._on_embed_web_click); return card
        return None

    def _on_embed_web_click(self, url):
        if url:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))

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

    def _on_embed_audio_play(self, aid, card=None):
        import sounddevice as sd
        if self._chat_audio_playing is not None:
            prev_card, prev_aid = self._chat_audio_playing
            try: sd.stop()
            except Exception: pass
            try: prev_card.set_playing(False)
            except Exception: pass
            self._chat_audio_playing = None
            if prev_aid == aid:
                return  # toggle: stesso audio → ferma e basta
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
            # Traccia lo stato: serve a fermare/toggle e a non far interrompere
            # la riproduzione dal refresh della timeline.
            if card is not None:
                try: card.set_playing(True)
                except Exception: pass
                self._chat_audio_playing = (card, aid)
        except Exception as e:
            print(f"[Chat] embed audio play fail: {e}")

    # ── Stato live (sidebar + pannello) ─────────────────────────────
    def _refresh_status(self, force_full=False):
        """Aggiorna la StatusCard. A finestra nascosta si ferma: l'app vive nel
        tray per ore e non ha senso interrogare il DB per una UI invisibile."""
        if not self.isVisible():
            return
        self._status.tick(force_full=force_full)

    def _on_status(self, st):
        try:
            self._status_card.apply(st)
            enc = st.get("encrypted")
            self._profile_sub.setText("locale · cifrato" if enc else
                                      ("locale" if enc is None else "locale · NON cifrato"))
            self._profile_sub.setStyleSheet(
                f"color:{theme.INK_DIM if enc is not False else theme.AMBER};"
                " font-size:11px; background:transparent;")
        except Exception:
            pass

    def _toggle_pause(self):
        """Toggle rapido dalla card: pausa 15 min ↔ riprendi. Stessa semantica
        del menu tray (`privacy.pause_for` / `unpause`), stato condiviso."""
        try:
            from modules import privacy
            if privacy.is_paused():
                privacy.unpause()
                self.toast("Cattura ripresa.", level="ok")
            else:
                privacy.pause_for(15 * 60)
                self.toast("Cattura in pausa per 15 minuti.", level="info")
        except Exception as e:
            self.toast(f"Pausa non riuscita: {e}", level="error")
            return
        self._refresh_status()
        dlg = getattr(self, "_status_dlg", None)
        if dlg is not None and dlg.isVisible():
            dlg.refresh()

    def _open_status_panel(self):
        """Pannello di stato dettagliato. Riusa quello già aperto (niente copie)."""
        dlg = getattr(self, "_status_dlg", None)
        if dlg is not None:
            # Riapertura: stesso pannello (niente copie), timer ripreso.
            dlg.show(); dlg.resume(); dlg.raise_(); dlg.activateWindow(); return
        try:
            from modules import privacy
            dlg = StatusPanel(self,
                              on_pause=lambda: (privacy.pause_for(15 * 60), self._refresh_status()),
                              on_resume=lambda: (privacy.unpause(), self._refresh_status()))
        except Exception as e:
            self.toast(f"Stato non disponibile: {e}", level="error")
            return
        self._status_dlg = dlg
        # Ancorato al bordo della sidebar, accanto alla card che l'ha aperto.
        try:
            g = self._status_card.mapToGlobal(QPoint(self._status_card.width(), 0))
            dlg.adjustSize()
            dlg.move(g.x() + 6, max(40, g.y() - dlg.height() + self._status_card.height()))
        except Exception:
            pass
        dlg.show()

    # ── Caricamento dati reali ──────────────────────────────────────
    def _load(self):
        """Avvia il caricamento della cronologia in background (no freeze UI)."""
        self._day_label.setText("Caricamento cronologia…")
        self._worker = TimelineWorker(limit=3000, offset=0)
        self._worker.done.connect(self._on_data)
        self._worker.start()

    def _maybe_refresh(self):
        """Tick del refresh quasi-realtime. Condizioni per ricaricare (tutte
        leggere): finestra visibile, pagina Timeline, nessun caricamento in
        corso, ci sono screenshot nuovi rispetto all'ultimo visto, e l'utente è
        in cima alla lista (non interrompe chi sta scorrendo/leggendo)."""
        if not self.isVisible():
            return
        if getattr(self, "_current_page", "timeline") != "timeline":
            return
        # Riproduzione audio in corso: il reload ricostruisce la lista e cambia
        # selezione → _populate_detail fermerebbe l'audio a metà. Rimanda il
        # refresh (i dati nuovi verranno caricati al tick dopo la fine).
        if getattr(self, "_is_playing", False) or getattr(self, "_chat_audio_playing", None):
            return
        w = getattr(self, "_worker", None)
        if w is not None and w.isRunning():
            return
        try:
            from db import get_conn
            with get_conn() as conn:
                # Somma dei MAX(id) di tutte le sorgenti timeline: cresce a ogni
                # nuovo record (gli id sono AUTOINCREMENT) e resta una probe economica.
                row = conn.cursor().execute(
                    "SELECT (SELECT IFNULL(MAX(id),0) FROM screenshots)"
                    " + (SELECT IFNULL(MAX(id),0) FROM audio_segments)"
                    " + (SELECT IFNULL(MAX(id),0) FROM web_pages)"
                    " + (SELECT IFNULL(MAX(id),0) FROM system_events)").fetchone()
            mx = row[0] if row else None
        except Exception:
            return
        if mx is None:
            return
        if self._last_max_id is None:
            self._last_max_id = mx
            return
        if mx <= self._last_max_id:
            return
        sb = self.timeline.verticalScrollBar()
        if sb is not None and sb.value() > 4:
            return  # sta sfogliando: non strappargli la posizione sotto i piedi
        self._last_max_id = mx
        self._load()

    def _on_data(self, records):
        self._records = records or []
        self._build_rows()
        n = len(self._records)
        self._day_label.setText(
            f"Cronologia   ·   {n:,} ricord{'o' if n == 1 else 'i'}".replace(",", ".")
            if n else "Nessun ricordo ancora"
        )
        # (il conteggio archivio della sidebar non si legge più da qui: la
        # StatusCard mostra i TOTALI reali del DB, non la sola pagina caricata)
        # Audio in riproduzione: NON rubare la selezione (cambiarla ripopola il
        # detail → _stop_audio → audio interrotto). Lascia tutto com'è.
        if getattr(self, "_is_playing", False) or getattr(self, "_chat_audio_playing", None):
            QTimer.singleShot(0, lambda: self._ensure_visible_thumbs(self.timeline))
            return
        # seleziona il primo evento (salta gli header) e carica le sue thumb
        for i in range(self.timeline.count()):
            it = self.timeline.item(i)
            if it and not it.data(TL_HOUR):
                self.timeline.setCurrentRow(i); break
        QTimer.singleShot(0, lambda: self._ensure_visible_thumbs(self.timeline))

    @staticmethod
    def _kind_of(r):
        t = r.get("type")
        return {"audio": "audio", "web": "note", "system": "sys"}.get(t, "screen")

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
        if kind == "sys":
            cat = SYS_CAT_LABEL.get(r.get("category"), r.get("category") or "evento")
            title = self._clean(r.get("text")) or f"Evento: {cat}"
            return (title[:72] + "…") if len(title) > 72 else title, cat.lower()
        return (self._clean(r.get("app")) or "Schermata"), ""  # screen: niente OCR (rumore)

    def _build_rows(self):
        self.timeline.blockSignals(True)
        self.timeline.clear()
        flt = getattr(self, "_tl_filter", "all")
        last_key = None
        show_hidden = getattr(self, "_tl_show_hidden", False)
        for idx, r in enumerate(self._records):
            if flt != "all" and r.get("type") != flt:
                continue
            # Eventi background/sistema/Déjà: nascosti di default ovunque,
            # rivelati solo dal toggle "mostra nascosti".
            if r.get("hidden") and not show_hidden:
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
        # 'Audio vicini' è pertinente solo ai ricordi audio: nascondi di default.
        self._nearby_wrap.setVisible(False)

        # fade morbido del contenuto detail a ogni selezione
        self._fade_in(self._body_scroll)

        # elide su singola riga (il margine destro dell'header è riservato ai controlli finestra)
        fm = QFontMetrics(self._detail_title.font())
        self._detail_title.setText(fm.elidedText(title or "—", Qt.TextElideMode.ElideRight, 170))
        kindlbl = {"screen": "Schermo", "audio": "Registrazione vocale",
                   "note": "Pagina web", "sys": "Evento di sistema"}.get(kind, "")
        when = self._detail_when(r.get("ts", ""))
        sub = f"{kindlbl} · {when}".strip(" ·").upper()
        fms = QFontMetrics(self._detail_sub.font())
        self._detail_sub.setText(fms.elidedText(sub, Qt.TextElideMode.ElideRight, 170))

        # badge colorato per tipo
        hue = {"screen": theme.EMERALD_RGB, "audio": theme.AMBER_RGB,
               "note": theme.VIOLET_RGB, "sys": (96, 165, 250)}.get(kind, theme.VIOLET_RGB)
        ic = {"screen": "screen", "audio": "audio", "note": "web", "sys": "sys"}.get(kind, "screen")
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
            self._audio_when.setText("🕐  " + self._detail_when_full(r.get("ts", "")))
            self._load_audio(sid, r)
            self._fill_nearby_audio(r)
        elif kind == "note":
            self._show_detail_sections(shot=False, body=True, audio=False)
            import html as _html
            url = r.get("url") or ""; ttl = r.get("title") or url; text = r.get("text") or ""
            self._detail_body.setTextFormat(Qt.TextFormat.RichText)
            self._detail_body.setText(
                f"<b style='color:{theme.INK}'>{_html.escape(ttl)}</b><br>"
                f"<a href='{_html.escape(url)}' style='color:{theme.VIOLET}'>{_html.escape(url)}</a>"
                f"<br><br><span style='color:#cfcfd6'>{_html.escape(text)}</span>")
        elif kind == "sys":
            self._show_detail_sections(shot=False, body=True, audio=False)
            import html as _html, json as _json
            cat = SYS_CAT_LABEL.get(r.get("category"), r.get("category") or "evento")
            src = "estensione browser" if r.get("source") == "browser" else "sistema"
            rows = [f"<b style='color:{theme.INK}'>{_html.escape(r.get('text') or cat)}</b>",
                    f"<span style='color:{theme.INK_DIM}; font-size:11px'>"
                    f"{_html.escape(cat)} · {_html.escape(r.get('action') or '')} · {_html.escape(src)}</span>"]
            if r.get("subject"):
                rows.append(f"<span style='color:#cfcfd6'>{_html.escape(r.get('subject'))}</span>")
            try:
                det = _json.loads(r.get("detail") or "{}")
            except Exception:
                det = {}
            if det:
                kv = "<br>".join(
                    f"<span style='color:{theme.INK_DIM}'>{_html.escape(str(k))}:</span> "
                    f"<span style='color:#cfcfd6'>{_html.escape(str(v))}</span>"
                    for k, v in det.items())
                rows.append(kv)
            self._detail_body.setTextFormat(Qt.TextFormat.RichText)
            self._detail_body.setText("<br><br>".join(rows))
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
        show_hidden = getattr(self, "_tl_show_hidden", False)
        seen = {}
        for o in self._records:
            if o is r:
                continue
            # coerenza con la timeline: gli eventi nascosti non contano nei chip
            # finché non si è in modalità "mostra nascosti".
            if o.get("hidden") and not show_hidden:
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
                 "note": ("web", theme.VIOLET_RGB), "sys": ("eventi", (96, 165, 250))}
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
        """Apre l'Assistente e invia il ricordo corrente come allegato: riferimento
        univoco per id ([ss:ID]/[au:ID], così l'AI sa ESATTAMENTE quale ricordo anche
        se più screenshot hanno lo stesso titolo) + il contenuto reale (testo/trascrizione)."""
        self._switch_page("assistant")
        r = getattr(self, "_cur_record", {}) or {}
        kind = getattr(self, "_cur_kind", "")
        sid = getattr(self, "_cur_sid", None)
        when = self._detail_when(r.get("ts", "")) if r else ""

        if kind == "audio" and sid is not None:
            meta = {"kind": "audio", "ref": f"[au:{sid}]", "glyph": "🎙", "thumb": None,
                    "title": self._detail_title.text() or "Registrazione",
                    "subtitle": f"Registrazione · {when}".strip(" ·"),
                    "content": (r.get("transcript") or "").strip()}
        elif kind == "note":
            meta = {"kind": "note", "ref": "", "glyph": "🌐", "thumb": None,
                    "title": r.get("title") or self._detail_title.text() or "Pagina web",
                    "subtitle": f"Pagina web · {when}".strip(" ·"),
                    "content": "\n".join(p for p in (r.get("title"), r.get("url"), r.get("text")) if p).strip()}
        elif kind == "screen" and sid is not None:
            meta = {"kind": "screen", "ref": f"[ss:{sid}]", "glyph": "🖼",
                    "thumb": getattr(self, "_current_pixmap", None),
                    "title": self._detail_title.text() or "Schermata",
                    "subtitle": f"Schermata · {when}".strip(" ·"),
                    "content": (r.get("text") or "").strip()}
        elif kind == "sys":
            cat = SYS_CAT_LABEL.get(r.get("category"), r.get("category") or "evento")
            meta = {"kind": "sys", "ref": "", "glyph": "⚡", "thumb": None,
                    "title": r.get("text") or f"Evento: {cat}",
                    "subtitle": f"Evento di sistema · {when}".strip(" ·"),
                    "content": "\n".join(p for p in (r.get("text"), r.get("subject"),
                                                     r.get("detail")) if p).strip()}
        else:
            try: self.chat_page.input.setFocus()
            except Exception: pass
            return

        # Allega come "file" (chip sopra la barra), input vuoto: l'utente può poi
        # scrivere una domanda o inviare l'allegato così com'è.
        self.chat_page.set_attachment(meta)
        try:
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
        elif kind == "sys":
            body = "\n".join(p for p in (r.get("text"), r.get("subject"), r.get("detail")) if p)
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

    @staticmethod
    def _detail_when_full(ts_iso):
        """Data + ora complete (con giorno della settimana e secondi) per il detail audio."""
        try:
            ts = datetime.fromisoformat(ts_iso)
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
            local = ts.astimezone()
            g = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"][local.weekday()]
            return f"{g} {local.strftime('%d/%m/%Y · %H:%M:%S')}"
        except Exception:
            return ""

    # ── Audio vicini (navigazione ± N minuti) ───────────────────────
    def _refill_nearby(self):
        r = getattr(self, "_cur_record", None)
        if r and getattr(self, "_cur_kind", "") == "audio":
            self._fill_nearby_audio(r)

    def _fill_nearby_audio(self, r):
        # svuota la lista corrente
        while self._nearby_list_l.count():
            w = self._nearby_list_l.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        from modules import search as search_module
        ts = r.get("ts", "")
        try:
            near = search_module.list_audio_around(
                ts, minutes=self._nearby_min.value(), limit=14, exclude_id=r.get("id"))
        except Exception as e:
            near = []; print(f"[Detail] audio vicini fail: {e}")
        self._nearby_wrap.setVisible(True)
        if not near:
            empty = QLabel("Nessun altro audio in questa finestra.")
            empty.setStyleSheet(f"color:{theme.INK_FAINT}; font-size:11px; background:transparent;")
            self._nearby_list_l.addWidget(empty)
            return
        for nr in near:
            nts = nr.get("ts", "")
            after = nts >= ts            # ts UTC ISO stesso formato → confronto lessicale ok
            arrow = "↓" if after else "↑"
            snip = (nr.get("transcript") or "").replace("\n", " ").strip()
            snip = (snip[:38] + "…") if len(snip) > 38 else (snip or "—")
            src = "🎙️" if nr.get("source") == "mic" else "🔊"
            btn = QPushButton(f"{arrow} {self._clock(nts)}  {src}  {snip}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton{{text-align:left; background:rgba(255,255,255,0.03); color:{theme.INK_SOFT};"
                f" border:1px solid {theme.LINE}; border-radius:8px; padding:6px 10px; font-size:11px;"
                f" font-family:'{theme.SANS}';}}"
                "QPushButton:hover{background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.35);}")
            btn.clicked.connect(lambda _=False, rec=nr: self._open_nearby_audio(rec))
            self._nearby_list_l.addWidget(btn)

    def _open_nearby_audio(self, rec):
        title, _sub = self._row_text(rec, "audio")
        self._populate_detail(rec, "audio", title, rec.get("id"))

    # ── Compat tray/hotkey ──────────────────────────────────────────
    def toggle(self):
        """Mostra/porta in primo piano (chiamato da hotkey Ctrl+Shift+D)."""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            # Gate di sblocco prima di rivelare i dati (hotkey = stesso confine
            # di accesso del tray).
            from modules import applock
            if not applock.ensure_unlocked(self):
                return
            self.showNormal(); self.raise_(); self.activateWindow()

    def hideEvent(self, e):
        if self._is_playing:
            self._stop_audio()
        # Re-lock quando la finestra torna nel tray: con policy "every_access"
        # il prossimo accesso richiede di nuovo lo sblocco. Senza questo, uno
        # sblocco singolo restava valido per sempre.
        try:
            from modules import applock
            if applock.lock_enabled() and applock.relock_policy() == "every_access":
                applock.lock_now()
        except Exception:
            pass
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
