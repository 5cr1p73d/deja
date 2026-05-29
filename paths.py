# paths.py
"""
Percorsi consumer-safe per Déjà.

Problema: con DB/log relativi alla CWD l'app crasha quando installata in
`C:\\Program Files\\...` (non scrivibile). Qui centralizziamo tutti i percorsi
in una user data dir scrivibile (%LOCALAPPDATA%\\Deja), con un fallback che
NON disturba lo sviluppo da sorgente (se esiste gia un deja.db nella cartella
del progetto lo riusiamo).
"""
import os
import sys
import shutil

APP_NAME = "Deja"


def is_frozen() -> bool:
    """True se in esecuzione dentro un bundle PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def _project_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Cartella dati scrivibile dell'utente. Creata se manca."""
    base = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or os.path.expanduser("~")
    )
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def db_path() -> str:
    """
    Percorso del DB SQLite.

    - Sviluppo da sorgente (non-frozen) con un `deja.db` gia presente nel
      progetto → riusa quello (non perdere i dati esistenti del dev).
    - Altrimenti (build consumer o prima esecuzione) → user data dir.
    """
    legacy = os.path.join(_project_dir(), "deja.db")
    if not is_frozen() and os.path.exists(legacy):
        return legacy
    return os.path.join(data_dir(), "deja.db")


def logs_dir() -> str:
    d = os.path.join(data_dir(), "logs")
    os.makedirs(d, exist_ok=True)
    return d


def log_file() -> str:
    return os.path.join(logs_dir(), "deja.log")


def models_dir() -> str:
    d = os.path.join(data_dir(), "models")
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(rel: str) -> str:
    """Percorso di un asset, compatibile con bundle PyInstaller (_MEIPASS)."""
    base = getattr(sys, "_MEIPASS", _project_dir())
    return os.path.join(base, rel)


def find_tesseract() -> str | None:
    """
    Trova l'eseguibile Tesseract senza path hardcoded.

    Ordine: env TESSERACT_CMD → PATH → posizioni note → copia bundlata.
    Ritorna None se non trovato (l'app deve degradare, non crashare).
    """
    candidates: list[str] = []
    env = os.environ.get("TESSERACT_CMD")
    if env:
        candidates.append(env)
    which = shutil.which("tesseract")
    if which:
        candidates.append(which)
    local = os.environ.get("LOCALAPPDATA", "")
    candidates += [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(local, "Programs", "Tesseract-OCR", "tesseract.exe") if local else "",
        resource_path(os.path.join("tesseract", "tesseract.exe")),  # eventuale copia bundlata
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def configure_model_cache() -> None:
    """
    Nel bundle consumer, contieni la cache dei modelli HuggingFace dentro la
    user data dir (cosi la disinstallazione/pulizia e prevedibile). In dev
    lascia la cache di default per non riscaricare i modelli gia presenti.
    """
    if not is_frozen():
        return
    mdir = models_dir()
    os.environ.setdefault("HF_HOME", mdir)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(mdir, "hub"))
