# main.py
import sys
import os
import threading
import traceback
import logging

# Forza UTF-8 su stdout/stderr (evita UnicodeEncodeError su console cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Ambiente PRIMA di qualsiasi import che tiri torch ──────────────
# Deve venire prima di `import torch` (e degli import transitivi via
# sentence_transformers / faster_whisper). Su build frozen torch carica le sue
# DLL durante l'import: la dir va aggiunta PRIMA, non dopo.
#
# 1) Search path delle DLL di torch (onedir: _internal/torch/lib).
if getattr(sys, "frozen", False):
    _torch_lib = os.path.join(sys._MEIPASS, "torch", "lib")
    if os.path.isdir(_torch_lib):
        try:
            os.add_dll_directory(_torch_lib)
        except Exception:
            pass
# 2) Evita l'abort "OMP: Error #15" da runtime OpenMP duplicati (Intel libiomp5md
#    presente sia in torch/lib sia in ctranslate2). Mitigazione standard.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Logging su file + (nel bundle) cattura dei print. Prima di tutto il resto.
import paths
import applog
applog.setup()

# ── Import di torch tollerante ai fallimenti ───────────────────────
# Su una macchina pulita il caricamento delle DLL native di torch può fallire
# (WinError 1114 = init DLL fallita: VC++ redist mancante, OpenMP in conflitto,
# DLL corrotta da UPX, CPU senza l'ISA attesa...). NON deve essere un crash con
# traceback grezzo: prendiamo l'errore, lo logghiamo e proseguiamo in modalità
# ridotta (cattura + OCR + ricerca testuale esatta). I modelli ML restano
# disattivati finché torch non è disponibile.
TORCH_AVAILABLE = True
TORCH_IMPORT_ERROR = None
try:
    import torch  # noqa: F401  (forza il load anticipato per diagnosi early)
except Exception as e:  # OSError/WinError 1114, ImportError, ecc.
    TORCH_AVAILABLE = False
    TORCH_IMPORT_ERROR = e
    logging.getLogger("deja").error(
        "torch non caricabile: modalità ridotta (no embedding/trascrizione). %r", e
    )

from PyQt6.QtWidgets import QApplication
from db import (init_db, load_settings_into_config, ensure_encrypted,
                shutdown_db, stop_fts_backfill)
from modules import capturer, indexer, audio
from ui.window import open_ask_screen_dialog
from ui.app_shell import AppShell
from ui.tray import DejaTray
from ui.hotkey import HotkeyListener


def _show_torch_degraded_dialog():
    """Avvisa l'utente (una volta) che i modelli ML non sono disponibili.
    La cattura e la ricerca testuale funzionano comunque."""
    try:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None,
            "Déjà — funzioni AI non disponibili",
            "Le funzioni di intelligenza artificiale (ricerca semantica e "
            "trascrizione audio) non sono al momento disponibili su questo PC.\n\n"
            "Déjà continua a funzionare: cattura schermo, OCR e ricerca testuale "
            "restano attivi.\n\n"
            "Spesso si risolve installando il runtime Microsoft Visual C++ "
            "(vc_redist.x64) e riavviando.\n\n"
            f"Dettagli salvati in:\n{paths.log_file()}",
        )
    except Exception:
        pass


def _relaunch():
    """Riavvia l'app (stesso eseguibile). Usato dopo il cambio lingua.
    Chiamato solo dopo lo shutdown pulito (thread fermati, WAL checkpointato)."""
    import subprocess
    try:
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable])
        else:
            subprocess.Popen([sys.executable, *sys.argv])
    except Exception as e:
        logging.getLogger("deja").error("relaunch fallito: %r", e)


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
    # Entry per l'host native messaging dell'estensione browser (build frozen:
    # il browser lancia `deja.exe --web-host`). In dev si usa python sul file.
    if "--web-host" in sys.argv:
        import runpy
        runpy.run_path(
            paths.resource_path(os.path.join("extension", "host", "web_host.py")),
            run_name="__main__",
        )
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Istanza singola: se Déjà è già in esecuzione, esci subito (evita doppio
    # tray, doppio onboarding e DOPPI prompt di Windows Hello). Su Windows il
    # segmento si libera da solo alla chiusura del processo (anche se crasha).
    try:
        from PyQt6.QtCore import QSharedMemory
        _single = QSharedMemory("Deja_SingleInstance_v1")
        if _single.attach():
            if sys.platform == "win32":
                logging.getLogger("deja").info("Istanza già attiva: esco.")
                return
            # Unix: un crash lascia il segmento orfano (non viene ripulito dal
            # kernel come su Windows). attach+detach lo distrugge se nessun
            # altro processo lo tiene; se create() poi fallisce, l'istanza è
            # davvero viva.
            _single.detach()
            if not _single.create(1):
                logging.getLogger("deja").info("Istanza già attiva: esco.")
                return
        else:
            _single.create(1)
        app._single_instance = _single  # mantieni vivo per tutta la durata
    except Exception:
        logging.getLogger("deja").exception("single-instance check fallito (proseguo)")

    # Font UI elegante applicato a tutta l'app (prima di costruire la UI).
    try:
        from ui.window import resolve_ui_font
        resolve_ui_font(app)
    except Exception:
        logging.getLogger("deja").exception("resolve_ui_font fallita (proseguo)")

    # Cifratura a riposo: migra un eventuale deja.db in chiaro a SQLCipher
    # PRIMA di aprire qualsiasi connessione. Degrada in silenzio se non
    # disponibile (DPAPI/SQLCipher assenti).
    try:
        ensure_encrypted()
    except Exception:
        logging.getLogger("deja").exception("ensure_encrypted fallita (proseguo)")

    # Difesa in profondità: restringe la ACL della cartella dati al solo utente.
    try:
        paths.harden_data_dir_acl()
    except Exception:
        logging.getLogger("deja").exception("harden ACL fallita (proseguo)")

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

    # Se torch non è caricabile, avvisa una volta e prosegui in modalità ridotta.
    if not TORCH_AVAILABLE:
        _show_torch_degraded_dialog()

    # Déjà ora è un'APP a finestra (pivot da overlay): si avvia visibile e resta
    # in taskbar. Il tray sopravvive alla chiusura finestra (riapri da tray/hotkey).
    window = AppShell()
    # Gate di sblocco all'avvio: se il blocco è attivo, NON mostrare la finestra
    # (e i suoi dati) finché l'utente non si autentica. Altrimenti il PIN era
    # aggirabile semplicemente all'avvio o dalla nav in-app. Se annulla, resta
    # in tray: riaprendo da tray/hotkey verrà richiesto lo sblocco.
    from modules import applock
    if applock.ensure_unlocked(window):
        window.show(); window.raise_(); window.activateWindow()
    else:
        logging.getLogger("deja").info("Avvio bloccato: finestra in tray fino allo sblocco.")
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

    # La cattura + OCR non dipende da torch: parte sempre.
    threads = []
    t_capture = threading.Thread(target=capturer.run, args=(stop_event,), daemon=True)
    t_capture.start(); threads.append(t_capture)
    # Watcher dell'estensione browser: ingerisce le pagine visitate dallo spool.
    # Leggero, nessun ML; gira sempre (no-op se la feature è OFF).
    try:
        from modules import web_ingest
        t_webingest = threading.Thread(target=web_ingest.run, args=(stop_event,), daemon=True)
        t_webingest.start(); threads.append(t_webingest)
    except Exception:
        logging.getLogger("deja").exception("avvio web_ingest fallito (proseguo)")
    # Eventi di sistema (processi/file/install/...): tutto OFF di default,
    # toggle per categoria in Impostazioni → Eventi. No ML, no admin; il loop
    # è un no-op economico finché ogni categoria resta disattivata.
    try:
        from modules import system_events
        t_sysev = threading.Thread(target=system_events.run, args=(stop_event,), daemon=True)
        t_sysev.start(); threads.append(t_sysev)
    except Exception:
        logging.getLogger("deja").exception("avvio system_events fallito (proseguo)")
    # Indexer (embedding) e Audio (Whisper) richiedono torch/ML: avviali solo se
    # disponibile. I loro run() degradano comunque da soli, ma evitiamo retry
    # inutili quando sappiamo già che torch non c'è.
    if TORCH_AVAILABLE:
        t_indexer = threading.Thread(target=indexer.run, args=(stop_event,), daemon=True)
        t_audio   = threading.Thread(target=audio.run,   args=(stop_event,), daemon=True)
        t_indexer.start(); t_audio.start()
        threads += [t_indexer, t_audio]
    else:
        print("[INFO] Modalità ridotta: indexer e trascrizione audio disattivati (torch non disponibile).")
    exit_code = app.exec()
    # Togli subito l'icona dal tray: lo shutdown può richiedere 1-2 secondi
    # e l'utente non deve vedere un'icona "morta".
    try:
        tray.hide()
        app.processEvents()
    except Exception:
        pass
    stop_event.set()
    # Ferma il backfill FTS (se in corso) PRIMA del checkpoint: esce al confine
    # del batch (~ms) e riprende al prossimo avvio, niente contesa sul lock.
    stop_fts_backfill(3.0)
    # Join con DEADLINE GLOBALE (~6s totali), non 5s CIASCUNO: i thread sono
    # daemon, chi non risponde in tempo viene abbandonato (SQLite in WAL regge
    # l'interruzione; al peggio si perde il chunk in corso).
    import time as _time
    _deadline = _time.time() + 6.0
    for t in threads:
        t.join(timeout=max(0.2, _deadline - _time.time()))
    # Manutenzione rapida (checkpoint WAL + optimize). Il VECCHIO vacuum_db()
    # riscriveva l'INTERO file a ogni chiusura: su un DB da decine di GB erano
    # minuti di attesa per recuperare ~0 byte (qui non si cancella quasi nulla).
    shutdown_db()
    # Riavvio richiesto (es. cambio lingua): rilancia dopo lo shutdown pulito.
    if app.property("restart_requested"):
        _relaunch()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
