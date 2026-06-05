"""Render headless di SettingsDialog per verifica visiva."""
import os, sys, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
try:
    from ui.window import resolve_ui_font, SettingsDialog
    resolve_ui_font(app)
    dlg = SettingsDialog(None)
    try:
        dlg.select_page("privacy")
    except Exception as e:
        print("select_page warn:", e)
    dlg.show(); app.processEvents(); app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "_smoke_settings.png")
    dlg.grab().save(out); print("grab:", out, dlg.width(), "x", dlg.height())
    print("SETTINGS OK")
except Exception:
    traceback.print_exc(); print("SETTINGS FAIL"); sys.exit(1)
