# ui/theme.py
"""
Design system centrale per l'overlay Déjà — direzione "Refined II"
(Raycast × Linear). Single source of truth per colori, font, raggi e fogli QSS.

Nasce dal redesign overlay (vedi obsidian/deja/UI/Redesign-Overlay-progress.md).
Sostituisce gli stili inline sparsi in ui/window.py: i moduli UI importano da
qui invece di ridefinire hex e CSS a mano.

Palette = quella storica di Déjà (bg #0e0e12, viola #a78bfa accento unico,
hash app per gli avatar). Font = Geist + Geist Mono (Vercel, OFL), caricati a
runtime da assets/fonts/ con fallback a Segoe UI / system.
"""
from __future__ import annotations

import logging

import paths

log = logging.getLogger("deja")

# ── Font ────────────────────────────────────────────────────────────
# Riempiti da load_fonts(); fallback sensati finché non è chiamata.
SANS = "Segoe UI"
MONO = "Consolas"

_FALLBACK_SANS = ("Segoe UI Variable Text", "Segoe UI", "Selawik", "Arial")
_FALLBACK_MONO = ("Cascadia Code", "Consolas", "Courier New")


def _first_available(families: set[str], candidates) -> str | None:
    for c in candidates:
        if c in families:
            return c
    return None


def load_fonts(app=None) -> tuple[str, str]:
    """Registra Geist + Geist Mono da assets/fonts/ e li applica all'app.

    Idempotente-ish: ricaricare lo stesso file aggiunge solo un id duplicato,
    innocuo. Da chiamare dopo QApplication, prima di costruire la UI.
    Ritorna (sans_family, mono_family) effettivamente disponibili.
    """
    global SANS, MONO
    try:
        from PyQt6.QtGui import QFontDatabase
    except Exception:
        return SANS, MONO

    # Carica i file imbarcati (best-effort).
    for rel in ("assets/fonts/Geist.ttf", "assets/fonts/GeistMono.ttf"):
        try:
            path = paths.resource_path(rel)
            fid = QFontDatabase.addApplicationFont(path)
            if fid < 0:
                log.warning("theme: font non caricato: %s", rel)
        except Exception as e:  # pragma: no cover - difensivo
            log.warning("theme: errore caricando %s: %r", rel, e)

    fams = set(QFontDatabase.families())
    SANS = ("Geist" if "Geist" in fams else None) or _first_available(fams, _FALLBACK_SANS) or SANS
    MONO = ("Geist Mono" if "Geist Mono" in fams else None) or _first_available(fams, _FALLBACK_MONO) or MONO

    if app is not None:
        try:
            f = app.font(); f.setFamily(SANS); app.setFont(f)
        except Exception:
            pass
    log.info("theme: font UI=%s mono=%s", SANS, MONO)
    return SANS, MONO


# ── Colori (palette storica Déjà) ───────────────────────────────────
BG          = "#0e0e12"   # sfondo overlay
SURFACE     = "#131319"   # superficie pannelli
SURFACE_2   = "#101015"   # superficie incassata (preview pane)
RAISE       = "#17171e"   # elemento sollevato (chip attivo)

INK         = "#f4f4f6"   # testo primario
INK_SOFT    = "#9a9aa6"   # testo secondario
INK_DIM     = "#6c6c78"   # testo terziario
INK_FAINT   = "#4c4c56"   # label/etichette deboli

VIOLET      = "#a78bfa"   # accento unico (AI / selezione / highlight)
VIOLET_RGB  = (167, 139, 250)
AMBER       = "#f59e0b"   # audio
AMBER_RGB   = (245, 158, 11)
EMERALD     = "#10b981"   # screenshot
EMERALD_RGB = (16, 185, 129)
RED         = "#ef4444"

# Linee / bordi (su sfondo scuro)
LINE        = "rgba(255,255,255,0.07)"
LINE_SOFT   = "rgba(255,255,255,0.04)"
LINE_STRONG = "rgba(255,255,255,0.12)"
SEL_FILL    = "rgba(255,255,255,0.055)"

# Raggi
R_SM = 7
R_MD = 9
R_LG = 12
R_XL = 15

# ── QSS riusabili ───────────────────────────────────────────────────
def btn(active: bool = False) -> str:
    """Bottone/segment in stile Raycast. active = pillola selezionata."""
    if active:
        return (
            f"QPushButton{{color:{INK}; background:{RAISE}; "
            f"border:1px solid {LINE}; border-radius:{R_SM}px; "
            f"font-family:'{SANS}'; font-size:12px; font-weight:600; padding:0 12px;}}"
            f"QPushButton:hover{{background:#1d1d26;}}"
        )
    return (
        f"QPushButton{{color:{INK_DIM}; background:transparent; border:none; "
        f"border-radius:{R_SM}px; font-family:'{SANS}'; font-size:12px; "
        f"font-weight:500; padding:0 12px;}}"
        f"QPushButton:hover{{color:{INK_SOFT}; background:rgba(255,255,255,0.03);}}"
    )


def btn_action(primary: bool = False) -> str:
    """Bottone azione del pannello preview. Un solo accento (primary=viola)
    per l'azione principale; gli altri neutri. Include stato :disabled."""
    if primary:
        return (
            f"QPushButton{{background:rgba(167,139,250,0.16); color:{INK}; "
            f"border:1px solid rgba(167,139,250,0.45); border-radius:{R_MD}px; "
            f"font-family:'{SANS}'; font-size:12px; font-weight:600; padding:6px 14px;}}"
            f"QPushButton:hover{{background:rgba(167,139,250,0.26);}}"
            f"QPushButton:disabled{{background:rgba(255,255,255,0.03); color:{INK_FAINT}; "
            f"border:1px solid {LINE_SOFT};}}"
        )
    return (
        f"QPushButton{{background:rgba(255,255,255,0.05); color:{INK}; "
        f"border:1px solid {LINE}; border-radius:{R_MD}px; "
        f"font-family:'{SANS}'; font-size:12px; font-weight:500; padding:6px 14px;}}"
        f"QPushButton:hover{{background:rgba(255,255,255,0.09);}}"
        f"QPushButton:disabled{{background:transparent; color:{INK_FAINT}; "
        f"border:1px solid {LINE_SOFT};}}"
    )


def line_edit() -> str:
    return (
        f"QLineEdit{{border:none; background:transparent; color:{INK}; "
        f"font-family:'{SANS}'; "
        f"selection-background-color:rgba(167,139,250,0.35); selection-color:#ffffff;}}"
    )


def tag_input() -> str:
    return (
        f"QLineEdit{{background:rgba(255,255,255,0.03); color:{INK}; "
        f"border:1px solid {LINE}; border-radius:{R_SM}px; padding:0 10px; "
        f"font-family:'{SANS}'; font-size:12px;}}"
        f"QLineEdit:focus{{border:1px solid rgba(167,139,250,0.45);}}"
    )


def scrollbar() -> str:
    return (
        "QScrollBar:vertical{background:transparent; width:8px; margin:6px 2px;}"
        "QScrollBar::handle:vertical{background:rgba(255,255,255,0.07); "
        "border-radius:4px; min-height:30px;}"
        "QScrollBar::handle:vertical:hover{background:rgba(167,139,250,0.40);}"
        "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
    )


def results_list() -> str:
    return (
        "QListWidget{background:transparent; border:none; outline:none;}"
        "QListWidget::item{background:transparent; border:none;}"
        + scrollbar()
    )
