"""Smoke test: l'overlay si costruisce senza errori con gli import REALI?
Non avvia cattura/indexer/tray/main-loop. Solo: QApplication -> font ->
import ui.window reale -> DejaWindow() -> grab a PNG.
Uso: QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe design/_smoke.py
"""
import os, sys, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

try:
    from ui.window import resolve_ui_font, DejaWindow
    resolve_ui_font(app)
    print("import + resolve_ui_font: OK")
    w = DejaWindow()
    print("DejaWindow() costruito: OK  size=", w.width(), "x", w.height())
    w.show()
    app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "_smoke.png")
    w.grab().save(out)
    print("grab salvato:", out)
    print("SMOKE OK")
except Exception:
    traceback.print_exc()
    print("SMOKE FAIL")
    sys.exit(1)
