# main.py
import sys
import threading
import traceback
import logging

# Forza UTF-8 su stdout/stderr (evita UnicodeEncodeError su console cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Logging su file + (nel bundle) cattura dei print. Prima di tutto il resto.
import paths
import applog
applog.setup()

import torch

from PyQt6.QtWidgets import QApplication
from db import init_db, load_settings_into_config, vacuum_db
from modules import capturer, indexer, audio
from ui.window import DejaWindow, open_ask_screen_dialog
from ui.tray import DejaTray
from ui.hotkey import HotkeyListener

import sys
import os

if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
    torch_lib = os.path.join(base, 'torch', 'lib')
    if os.path.exists(torch_lib):
        os.add_dll_directory(torch_lib)

def _handle_exception(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.getLogger("deja").critical(
        "Eccezione non gestita", exc_info=(exc_type, exc_value, exc_tb)
    )
    traceback.print_exception(exc_type, exc_value, exc_tb)
    # Mostra un dialog se la GUI è viva (niente input(): in build --windowed
    # non c'è console e l'app morirebbe in silenzio).
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                "Déjà — errore inatteso",
                f"Si è verificato un errore.\n\n{exc_value}\n\n"
                f"Dettagli salvati in:\n{paths.log_file()}",
            )
    except Exception:
        pass

def _thread_exception(args):
    logging.getLogger("deja").error(
        "Eccezione in thread %s", getattr(args.thread, "name", "?"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )

sys.excepthook = _handle_exception
threading.excepthook = _thread_exception

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Init DB con gestione errori (mai crash silenzioso per il consumer).
    try:
        init_db()
    except Exception as e:
        logging.getLogger("deja").exception("init_db fallito")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None, "Déjà — errore database",
            f"Impossibile inizializzare il database.\n\n{e}\n\nDettagli: {paths.log_file()}",
        )
        return
    load_settings_into_config()

    # Onboarding + consenso esplicito PRIMA di avviare qualsiasi cattura.
    from ui.onboarding import run_onboarding
    if not run_onboarding():
        logging.getLogger("deja").info("Onboarding non completato: uscita senza cattura.")
        return

    window = DejaWindow()
    stop_event = threading.Event()
    tray = DejaTray(window, stop_event, app)
    tray.show()

    print("[INFO] Hotkey avviando...")

    # Multi-hotkey: toggle overlay + ask screen
    hotkey = HotkeyListener(shortcuts={
        "toggle": "ctrl+shift+d",
        "ask":    "ctrl+shift+a",
    })

    def _on_hotkey(name):
        if name == "toggle":
            window.toggle()
        elif name == "ask":
            # Singleton per evitare dialog duplicati su hotkey ripetuti
            existing = getattr(window, "_ask_dialog", None)
            if existing is not None:
                try:
                    if existing.isVisible():
                        existing.raise_(); existing.activateWindow()
                        return
                except RuntimeError:
                    pass  # widget Qt deleted
            try:
                dlg = open_ask_screen_dialog(parent=None)
                window._ask_dialog = dlg
            except Exception as e:
                print(f"[Hotkey] ask_screen fail: {e}")

    hotkey.triggered_named.connect(_on_hotkey)
    hotkey.start()

    t_capture = threading.Thread(target=capturer.run, args=(stop_event,), daemon=True)
    t_indexer = threading.Thread(target=indexer.run, args=(stop_event,), daemon=True)
    t_audio   = threading.Thread(target=audio.run,   args=(stop_event,), daemon=True)
    t_capture.start(); t_indexer.start(); t_audio.start()
    exit_code = app.exec()
    stop_event.set()
    t_capture.join(timeout=5); t_indexer.join(timeout=5); t_audio.join(timeout=5)
    vacuum_db()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
