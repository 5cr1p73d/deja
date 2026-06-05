"""Riproduce lo scenario 'Esplora' (3000 item) per verificare che NON freezi:
populate veloce (thumbnail lazy) + miniature solo per le righe visibili.
"""
import os, sys, time, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

import db
c = db.get_conn()
rows = c.execute("SELECT id, app, ts FROM screenshots ORDER BY ts DESC LIMIT 3000").fetchall()
c.close()
results = [{"id": r[0], "type": "screenshot", "app": (r[1] or "?"), "ts": r[2],
           "score": 1.0, "exact": False} for r in rows]
# qualche audio finto così appare anche il filtro tipo (Immagini/Audio)
for k in range(8):
    results.insert(k * 7, {"type": "audio", "transcript": "nota vocale di prova sul refactor",
                           "ts": results[0]["ts"]})
print("items:", len(results))

try:
    from ui.window import resolve_ui_font, DejaWindow, OVERLAY_H_EXPANDED, _THUMB_CACHE
    resolve_ui_font(app)
    w = DejaWindow()
    w._all_mode = True; w._all_results = results; w._active_date = "all"
    w._show_results_page()
    t0 = time.time()
    w._apply_date_filter("all")            # flusso Esplora reale: mostra barre + popola
    dt = time.time() - t0
    w.setFixedHeight(OVERLAY_H_EXPANDED); w.show()
    app.processEvents()
    w._ensure_visible_thumbs()
    app.processEvents()
    print(f"_apply_date_filter ~3000 item: {dt*1000:.0f} ms | thumb in cache: {len(_THUMB_CACHE)}")
    w.results_list.setCurrentRow(1); app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "_smoke_explore.png")
    w.grab().save(out); print("grab:", out)
    print("EXPLORE OK")
except Exception:
    traceback.print_exc(); print("EXPLORE FAIL"); sys.exit(1)
