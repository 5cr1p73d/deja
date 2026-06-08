"""Smoke espanso: costruisce DejaWindow reale, inietta risultati FINTI via
_on_search_done e cattura l'overlay espanso in PNG. No cattura/DB reale.
Uso: QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe design/_smoke_expanded.py
"""
import os, sys, traceback
from datetime import datetime, timezone, timedelta
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

def iso(h):
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()

fake = [
    {"id": 1, "type": "screenshot", "app": "Figma",   "ts": iso(2),  "score": 0.94, "exact": False, "path": ""},
    {"id": 2, "type": "screenshot", "app": "Slack",   "ts": iso(3),  "score": 1.0,  "exact": True,  "path": ""},
    {"id": 3, "type": "audio", "transcript": "Riunione design — portiamo il layout a qualita Raycast", "ts": iso(4), "score": 0.88, "exact": False},
    {"id": 4, "type": "screenshot", "app": "Mail",    "ts": iso(26), "score": 0.76, "exact": False, "path": ""},
    {"id": 5, "type": "screenshot", "app": "VS Code", "ts": iso(27), "score": 0.82, "exact": False, "path": ""},
    {"id": 6, "type": "audio", "transcript": "note vocali sul refactor dei token e del delegate", "ts": iso(28), "score": 0.91, "exact": False},
]

try:
    from ui.window import resolve_ui_font, DejaWindow, OVERLAY_W, OVERLAY_H_EXPANDED
    resolve_ui_font(app)
    w = DejaWindow()
    w.search_input.setText("design")
    w._on_search_done(fake)
    w.setFixedHeight(OVERLAY_H_EXPANDED)
    w.show()
    app.processEvents(); app.processEvents()
    # Il DB reale qui e cifrato e non decifrabile da questo processo: evita il
    # load preview (_on_row_changed) staccando i slot, poi mostra solo l'overlay
    # selezione manualmente. Nell'app vera il DB si decifra e il preview carica.
    try:
        w.results_list.currentRowChanged.disconnect()
    except Exception:
        pass
    w.results_list.setCurrentRow(1)  # Figma (riga 0 = header OGGI)
    w._move_sel_highlight(False)
    w._fade_preview()  # esercita il cross-fade (no DB)
    app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "_smoke_expanded.png")
    w.grab().save(out)
    print("grab:", out, "| size", w.width(), "x", w.height())
    print("SMOKE-EXPANDED OK")
except Exception:
    traceback.print_exc()
    print("SMOKE-EXPANDED FAIL")
    sys.exit(1)
