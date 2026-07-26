# autostart.py
"""
Avvio automatico al login. Niente privilegi admin.
- Windows: HKCU\\...\\Run.
- Linux: file .desktop in ~/.config/autostart (XDG Autostart, standard per
  GNOME/KDE/XFCE/...).
"""
import os
import sys

import paths

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Deja"


def _command() -> str:
    if paths.is_frozen():
        return f'"{sys.executable}"'
    # Dev: avvia main.py con l'interprete corrente.
    py = sys.executable
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{py}" "{main_py}"'


def _desktop_file() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, "autostart", "deja.desktop")


def is_supported() -> bool:
    return sys.platform in ("win32", "linux")


def is_enabled() -> bool:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                val, _ = winreg.QueryValueEx(k, _VALUE_NAME)
                return bool(val)
        except FileNotFoundError:
            return False
        except OSError:
            return False
    if sys.platform == "linux":
        return os.path.exists(_desktop_file())
    return False


def _set_enabled_linux(enabled: bool) -> bool:
    p = _desktop_file()
    try:
        if enabled:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            # Exec senza doppi apici stile shell: il formato .desktop usa il
            # proprio quoting; il comando qui è già quotato correttamente.
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Déjà\n"
                "Comment=Memoria personale del PC\n"
                f"Exec={_command()}\n"
                "X-GNOME-Autostart-enabled=true\n"
                "Terminal=false\n"
            )
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            if os.path.exists(p):
                os.remove(p)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Attiva/disattiva l'autostart. Ritorna True se riuscito."""
    if sys.platform == "linux":
        return _set_enabled_linux(enabled)
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            if enabled:
                winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, _VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
