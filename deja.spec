# deja.spec — PyInstaller (onedir, windowed). Unica fonte di verità per il build.
#   build:  pyinstaller --noconfirm deja.spec
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Dati da includere ──────────────────────────────────────────────
datas = []
datas += collect_data_files("faster_whisper")
datas += collect_data_files("sentence_transformers")
datas += collect_data_files("torch")
datas += collect_data_files("tokenizers")
datas += collect_data_files("transformers")
# Asset dell'app (icona, ecc.)
if os.path.isdir("assets"):
    datas += [("assets", "assets")]
# Eventuale Tesseract bundlato: copia la cartella "tesseract/" se presente
# accanto allo spec (tesseract.exe + tessdata). Opzionale.
if os.path.isdir("tesseract"):
    datas += [("tesseract", "tesseract")]

# ── Hidden imports ─────────────────────────────────────────────────
hiddenimports = []
hiddenimports += collect_submodules("torch")
hiddenimports += collect_submodules("sentence_transformers")
hiddenimports += [
    "encodings", "encodings.utf_8", "encodings.ascii", "encodings.latin_1",
    "encodings.cp1252", "encodings.idna", "codecs",
    "pyaudiowpatch", "sounddevice", "mss", "pytesseract", "pygetwindow",
    "keyboard", "numpy", "PIL", "ctypes", "ctypes.util",
    # moduli app caricati in modo lazy (PyInstaller potrebbe non vederli)
    "ui.onboarding", "paths", "applog", "autostart",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],          # PyInstaller rileva da solo la python3xx.dll corretta
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "unittest", "test"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Deja",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                 # niente console nera
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,
    upx=True,
    name="Deja",
)
