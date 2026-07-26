# ui/hotkey.py
import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal

# Backend per piattaforma:
# - Windows: lib `keyboard` (hook globale, come sempre).
# - Linux: `pynput` (X11; `keyboard` su Linux richiede root). Se manca o siamo
#   su Wayland puro, gli hotkey degradano a non-disponibili senza crash.
try:
    if sys.platform == "win32":
        import keyboard
        _pynput_keyboard = None
    else:
        keyboard = None
        from pynput import keyboard as _pynput_keyboard
except Exception:
    keyboard = None
    _pynput_keyboard = None


def _to_pynput(shortcut: str) -> str:
    """'ctrl+shift+d' → '<ctrl>+<shift>+d' (formato GlobalHotKeys)."""
    parts = [p.strip().lower() for p in shortcut.split("+") if p.strip()]
    out = []
    for p in parts:
        if len(p) == 1:
            out.append(p)
        else:
            out.append(f"<{p}>")
    return "+".join(out)


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
        if keyboard is not None:
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
            return
        if _pynput_keyboard is not None:
            mapping = {}
            for name, shortcut in self._shortcuts.items():
                if not shortcut:
                    continue
                cb = self.triggered.emit if name == "_default" else self.signal(name)
                try:
                    mapping[_to_pynput(shortcut)] = cb
                    print(f"[Hotkey] registrato {name!r} → {shortcut!r} (pynput)")
                except Exception as e:
                    print(f"[Hotkey] errore registrazione {name!r}: {e}")
            if not mapping:
                return
            try:
                with _pynput_keyboard.GlobalHotKeys(mapping) as h:
                    h.join()
            except Exception as e:
                # Tipico: Wayland puro senza X11 → niente hook globali (fase 2).
                print(f"[Hotkey] hotkey globali non disponibili: {e}")
            return
        print("[Hotkey] nessun backend hotkey disponibile su questa piattaforma.")
