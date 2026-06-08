"""Harness offscreen: renderizza la lista risultati col nuovo MinimalItemDelegate
in un PNG, senza avviare l'app (stub dei moduli pesanti). Solo per verifica visiva.
Uso: QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe design/_render_rows.py
"""
import os, sys, types
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Stub moduli pesanti che ui.window importa (evita torch/db reali) ──
def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

_stub("db", get_conn=lambda *a, **k: None)
pkg = sys.modules.get("modules") or _stub("modules")
pkg.__path__ = []
_stub("modules.audio", decode_audio=lambda *a, **k: None)
_stub("modules.search")
_stub("modules.ai_assistant", chat_stream=None)
_stub("modules.secrets", protect_secret=lambda x: x)
_stub("modules.applock", is_locked=lambda: False)

from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor

app = QApplication(sys.argv)
from ui import theme
theme.load_fonts(app)
import ui.window as W
W.UI_FONT, W.MONO_FONT = theme.SANS, theme.MONO

lw = QListWidget()
lw.setSpacing(4)
lw.setFixedSize(320, 520)
lw.setStyleSheet(theme.results_list() + f" QListWidget{{background:{theme.BG};}}")
lw.setItemDelegate(W.MinimalItemDelegate(lw))

def header(txt):
    it = QListWidgetItem(txt); it.setData(W.ITEM_HEADER_ROLE, True)
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)
    lw.addItem(it)

def row(title, ago, score, kind):
    it = QListWidgetItem(f"{title}\n{ago}   •   {score}")
    it.setData(W.ITEM_TYPE_ROLE, kind)
    lw.addItem(it)

header("OGGI")
row("Figma", "2h fa", "94%", "screenshot")
row("Slack", "3h fa", "✓ esatto", "screenshot")
row("Riunione design — portiamo il layout a…", "4h fa", "88%", "audio")
header("IERI")
row("Mail", "1g fa", "76%", "screenshot")
row("VS Code", "1g fa", "82%", "screenshot")
row("note vocali sul refactor dei token e…", "1g fa", "91%", "audio")

lw.setCurrentRow(1)  # mostra selezione
hl = W._SelHighlight(lw.viewport())
lw.show()
app.processEvents()
# posiziona l'evidenziatore animato sulla riga corrente (Refined II)
it = lw.currentItem()
from PyQt6.QtCore import QRect
hl.move_to(QRect(lw.visualItemRect(it)), animate=False)
app.processEvents()
out = os.path.join(os.path.dirname(__file__), "_rows.png")
lw.grab().save(out)
print("saved", out)
