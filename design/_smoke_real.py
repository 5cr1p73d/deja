"""Render overlay con DATI REALI dal DB buono (LOCALAPPDATA): righe + preview
con immagine screenshot vera. Per giudicare il redesign sul reale.
Uso: QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe design/_smoke_real.py
"""
import os, sys, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

import db
c = db.get_conn()
# una riga per app distinta, piu recenti
rows = c.execute("""
    SELECT id, app, ts FROM screenshots
    WHERE app IS NOT NULL AND app != ''
    GROUP BY app ORDER BY MAX(ts) DESC LIMIT 6
""").fetchall()
c.close()
fake = [{"id": r[0], "type": "screenshot", "app": r[1], "ts": r[2],
         "score": 0.96 - i*0.05, "exact": (i == 1)} for i, r in enumerate(rows)]
print("righe reali:", len(fake))

try:
    from ui.window import resolve_ui_font, DejaWindow, OVERLAY_H_EXPANDED
    resolve_ui_font(app)
    w = DejaWindow()
    w.search_input.setText("déjà")
    w._on_search_done(fake)
    w.setFixedHeight(OVERLAY_H_EXPANDED)
    w.show()
    app.processEvents(); app.processEvents()
    w.results_list.setCurrentRow(1)  # screenshot reale → preview carica immagine vera
    app.processEvents(); app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "_smoke_real.png")
    w.grab().save(out)
    print("grab:", out)
    print("SMOKE-REAL OK")
except Exception:
    traceback.print_exc()
    print("SMOKE-REAL FAIL")
    sys.exit(1)
