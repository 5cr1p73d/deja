# applog.py
"""
Logging consumer-grade: scrive su file ruotante nella user data dir.

Nel build `--windowed` non esiste console, quindi i `print()` sparirebbero e
un crash sarebbe invisibile. Qui:
  - configuriamo un RotatingFileHandler su %LOCALAPPDATA%\\Deja\\logs\\deja.log
  - in build frozen redirigiamo stdout/stderr al log (cattura i print esistenti)
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

import paths

_configured = False


class _StreamToLog:
    """File-like che inoltra le righe scritte al logger (per i print())."""

    def __init__(self, level: int):
        self._level = level
        self._buf = ""
        self._log = logging.getLogger("stdio")

    def write(self, msg: str):
        try:
            self._buf += msg
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                if line.strip():
                    self._log.log(self._level, line)
        except Exception:
            pass

    def flush(self):
        if self._buf.strip():
            self._log.log(self._level, self._buf)
        self._buf = ""

    def isatty(self):
        return False


def setup() -> str:
    """Configura il logging. Ritorna il path del file di log."""
    global _configured
    if _configured:
        return paths.log_file()
    try:
        handler = RotatingFileHandler(
            paths.log_file(), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)

        # Solo nel bundle (no console) cattura anche i print() legacy.
        if paths.is_frozen():
            sys.stdout = _StreamToLog(logging.INFO)
            sys.stderr = _StreamToLog(logging.ERROR)

        logging.getLogger("deja").info("=== Avvio Déjà (frozen=%s) ===", paths.is_frozen())
    except Exception:
        pass
    _configured = True
    return paths.log_file()
