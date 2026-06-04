# modules/model_catalog.py
"""
Cataloghi dei modelli selezionabili da UI (embedding / Whisper / OCR) con
dimensione su disco e RAM stimata, più utilità per lo stato della cache.

Numeri di peso/RAM sono **stime** indicative (variano per quantizzazione e
piattaforma), servono a far scegliere l'utente in modo informato.

VINCOLO: gli embedding devono essere **768-dim** perché la tabella vettoriale
sqlite-vec è `int8[768]` (vedi `db.EMBED_DIM`). Modelli con dim diversa
romperebbero la ricerca, quindi il catalogo embedding è solo 768-dim.
"""
import os


# ── Cataloghi ──────────────────────────────────────────────────────
# size_mb / ram_mb = stime (MB). dims solo per embedding.
EMBEDDING_MODELS = [
    {
        "id": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        "label": "Multilingual MPNet base", "size_mb": 1040, "ram_mb": 1300,
        "dims": 768, "note": "Qualità alta, 50+ lingue (default)",
    },
    {
        "id": "intfloat/multilingual-e5-base",
        "label": "Multilingual E5 base", "size_mb": 1110, "ram_mb": 1300,
        "dims": 768, "note": "Ottimo per ricerca, 100 lingue",
    },
    {
        "id": "sentence-transformers/LaBSE",
        "label": "LaBSE", "size_mb": 1880, "ram_mb": 2100,
        "dims": 768, "note": "109 lingue, pesante",
    },
    {
        "id": "sentence-transformers/all-mpnet-base-v2",
        "label": "All-MPNet base (EN)", "size_mb": 420, "ram_mb": 700,
        "dims": 768, "note": "Solo inglese, leggero e veloce",
    },
    {
        "id": "sentence-transformers/paraphrase-mpnet-base-v2",
        "label": "Paraphrase MPNet (EN)", "size_mb": 420, "ram_mb": 700,
        "dims": 768, "note": "Solo inglese",
    },
]

WHISPER_MODELS = [
    {"id": "Systran/faster-whisper-tiny",   "label": "Whisper tiny",   "size_mb": 75,   "ram_mb": 1000, "note": "Velocissimo, qualità bassa"},
    {"id": "Systran/faster-whisper-base",   "label": "Whisper base",   "size_mb": 145,  "ram_mb": 1000, "note": "Veloce"},
    {"id": "Systran/faster-whisper-small",  "label": "Whisper small",  "size_mb": 480,  "ram_mb": 2000, "note": "Buon compromesso"},
    {"id": "Systran/faster-whisper-medium", "label": "Whisper medium", "size_mb": 1500, "ram_mb": 5000, "note": "Qualità alta"},
    {"id": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "label": "Whisper large-v3 turbo", "size_mb": 1600, "ram_mb": 6000, "note": "Qualità top, veloce (default)"},
    {"id": "Systran/faster-whisper-large-v3", "label": "Whisper large-v3", "size_mb": 3100, "ram_mb": 10000, "note": "Massima qualità, pesante"},
    {"id": "Systran/faster-distil-whisper-large-v3", "label": "Distil large-v3", "size_mb": 1500, "ram_mb": 6000, "note": "Veloce, qualità quasi large"},
]

# OCR = pacchetti lingua Tesseract (*.traineddata). size_mb ~ somma lingue.
OCR_MODELS = [
    {"id": "ita+eng", "label": "Italiano + Inglese", "size_mb": 30, "langs": ["ita", "eng"]},
    {"id": "eng",     "label": "Inglese",            "size_mb": 15, "langs": ["eng"]},
    {"id": "ita",     "label": "Italiano",           "size_mb": 15, "langs": ["ita"]},
    {"id": "spa+eng", "label": "Spagnolo + Inglese", "size_mb": 30, "langs": ["spa", "eng"]},
    {"id": "fra+eng", "label": "Francese + Inglese",  "size_mb": 30, "langs": ["fra", "eng"]},
    {"id": "deu+eng", "label": "Tedesco + Inglese",   "size_mb": 30, "langs": ["deu", "eng"]},
    {"id": "por+eng", "label": "Portoghese + Inglese","size_mb": 30, "langs": ["por", "eng"]},
]


# ── Utilità ────────────────────────────────────────────────────────
def human_size(mb) -> str:
    try:
        mb = float(mb)
    except (TypeError, ValueError):
        return "?"
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB".replace(".0 GB", " GB")
    return f"{int(mb)} MB"


def human_ram(mb) -> str:
    return "~" + human_size(mb) + " RAM"


def _hub_dir() -> str:
    h = os.environ.get("HUGGINGFACE_HUB_CACHE")
    if h:
        return h
    hf = os.environ.get("HF_HOME")
    if hf:
        return os.path.join(hf, "hub")
    return os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")


def is_cached(repo_id: str) -> bool:
    """True se il repo HuggingFace è già in cache locale (scaricato)."""
    if not repo_id:
        return False
    folder = "models--" + repo_id.replace("/", "--")
    path = os.path.join(_hub_dir(), folder)
    if not os.path.isdir(path):
        return False
    # Considera scaricato solo se c'è almeno uno snapshot con file.
    snap = os.path.join(path, "snapshots")
    if os.path.isdir(snap):
        for d in os.listdir(snap):
            sub = os.path.join(snap, d)
            if os.path.isdir(sub) and os.listdir(sub):
                return True
        return False
    return True


def tessdata_dir() -> str:
    """Cartella tessdata di Tesseract (per verificare i pacchetti lingua)."""
    try:
        import config
        cmd = getattr(config, "TESSERACT_CMD", "") or ""
    except Exception:
        cmd = ""
    cands = []
    if cmd:
        cands.append(os.path.join(os.path.dirname(cmd), "tessdata"))
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        cands.append(env)
        cands.append(os.path.join(env, "tessdata"))
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return ""


def ocr_installed(preset_id: str) -> bool:
    """True se tutti i .traineddata del preset sono presenti."""
    d = tessdata_dir()
    if not d:
        return False
    langs = preset_id.split("+")
    return all(os.path.exists(os.path.join(d, f"{l}.traineddata")) for l in langs)


def find(catalog, model_id):
    for m in catalog:
        if m["id"] == model_id:
            return m
    return None
