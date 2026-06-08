import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = ["x"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QEventLoop
app = QApplication(sys.argv)
from ui import theme; theme.load_fonts(app)
from ui.app_shell import AppShell
from modules import search as search_module
w = AppShell(); w.resize(1180, 740); w.show()
w._on_data(search_module.get_all(limit=400))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(OUT, exist_ok=True)
def pump(ms=350):
    loop=QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()
def grab(n): pump(); w.grab().save(os.path.join(OUT, n)); print("saved", n)
pump(400); grab("01_timeline.png")
w._set_tl_filter("audio"); grab("01b_audio.png")
w._switch_page("settings"); w._set_select("privacy"); grab("04_settings.png")
print("done")
