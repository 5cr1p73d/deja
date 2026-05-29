# ui/hotkey.py
import threading
import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


class HotkeyListener(QObject):
    """Listener globale per uno o più hotkey.

    Backward compat: `HotkeyListener("ctrl+shift+d")` espone `triggered` come prima.
    Multi-hotkey: passare dict {name: shortcut}, esposto come segnali dinamici.
    Es: HotkeyListener(shortcuts={"toggle": "ctrl+shift+d", "ask": "ctrl+shift+a"})
        → connetti a listener.signal("toggle") / listener.signal("ask")
    """
    triggered = pyqtSignal()
    triggered_named = pyqtSignal(str)

    def __init__(self, shortcut="ctrl+shift+d", shortcuts=None):
        super().__init__()
        if shortcuts:
            self._shortcuts = dict(shortcuts)
        else:
            self._shortcuts = {"_default": shortcut}

    def signal(self, name):
        """Ritorna callable che emette triggered_named(name) — wrap segnale."""
        def _emit():
            self.triggered_named.emit(name)
        return _emit

    def start(self):
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        for name, shortcut in self._shortcuts.items():
            if not shortcut:
                continue
            try:
                if name == "_default":
                    keyboard.add_hotkey(shortcut, self.triggered.emit)
                else:
                    keyboard.add_hotkey(shortcut, self.signal(name))
                print(f"[Hotkey] registrato {name!r} → {shortcut!r}")
            except Exception as e:
                print(f"[Hotkey] errore registrazione {name!r} ({shortcut!r}): {e}")
        keyboard.wait()
