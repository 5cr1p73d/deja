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
    # NB: NON escludere "unittest": torch (torch.testing) e pygetwindow
    # (pyrect→doctest→unittest) lo importano; escluderlo causa
    # ModuleNotFoundError all'avvio del bundle.
    excludes=["matplotlib", "tkinter", "test"],
    cipher=block_cipher,
)

# ── Fix WinError 1114 (init di c10.dll) ────────────────────────────
# PyQt6 (Qt6/bin), sklearn e numpy includono copie VECCHIE del runtime MSVC
# (es. msvcp140 14.26 di Qt). Se Qt viene caricato PRIMA di torch (nel bundle
# accade via il runtime-hook pyqt6), quel runtime obsoleto resta residente e
# l'inizializzazione di c10.dll (torch 2.10 richiede un VC++ più recente)
# fallisce con WinError 1114 "DLL initialization routine failed". Soluzione:
# sostituire OGNI copia del runtime MSVC nel bundle con quella corrente di
# System32 (retro-compatibile: Qt costruito su 14.26 gira con 14.5x).
_sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
_vc_names = {
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll", "vcomp140.dll",
}
_patched_binaries = []
for _dest, _src, _kind in a.binaries:
    if os.path.basename(_dest).lower() in _vc_names:
        _cur = os.path.join(_sys32, os.path.basename(_dest))
        if os.path.exists(_cur):
            _patched_binaries.append((_dest, _cur, _kind))
            continue
    _patched_binaries.append((_dest, _src, _kind))
a.binaries = _patched_binaries

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# UPX corrompe spesso le DLL native con init non banale (torch/c10, OpenMP,
# runtime VC++, pyd) → WinError 1114 "DLL initialization routine failed" sulla
# macchina dell'utente anche se la DLL è presente. Escludiamole dalla
# compressione UPX (PyInstaller le copia non compresse). Pattern case-insensitive.
upx_exclude = [
    "c10.dll", "torch_cpu.dll", "torch_python.dll", "torch_global_deps.dll",
    "fbgemm.dll", "asmjit.dll", "uv.dll", "shm.dll",
    "libiomp5md.dll", "libiompstubs5md.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll",
    "msvcp140_1.dll", "msvcp140_2.dll", "concrt140.dll", "vcomp140.dll",
    "python3.dll", "python314.dll",
    "onnxruntime*.dll", "ctranslate2*.dll", "cublas*.dll", "cudnn*.dll",
    "torch*.dll", "*.pyd",
]

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Deja",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=upx_exclude,
    console=False,                 # niente console nera
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,
    upx=True,
    upx_exclude=upx_exclude,
    name="Deja",
)
