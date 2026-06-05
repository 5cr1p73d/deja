"""Render della nuova AppShell (fase 1 port)."""
import os, sys, traceback
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
try:
    from ui import theme
    theme.load_fonts(app)
    from ui.app_shell import AppShell
    w = AppShell(); w.resize(1180, 740); w.show()
    app.processEvents(); app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "_smoke_shell.png")
    w.grab().save(out); print("grab:", out)
    print("SHELL OK")
except Exception:
    traceback.print_exc(); print("SHELL FAIL"); sys.exit(1)
