# config.py
import os
import paths

# Contieni la cache modelli nella user data dir nei build consumer.
paths.configure_model_cache()

# Versione app (mostrata in About / log / installer).
APP_VERSION        = "1.2.0"
APP_NAME           = "Déjà"

# Percorsi consumer-safe (user data dir scrivibile, non la CWD).
DB_PATH            = paths.db_path()
CAPTURE_INTERVAL   = 5
OCR_LANG           = "ita+eng"
# Auto-discovery di Tesseract (env → PATH → posizioni note → bundle). "" se assente.
TESSERACT_CMD      = paths.find_tesseract() or ""
EMBEDDING_MODEL    = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
INDEXER_BATCH      = 20
INDEXER_INTERVAL   = 10
TOP_K_RESULTS      = 10
WHISPER_MODEL      = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
AUDIO_CHUNK_SECONDS    = 30
AUDIO_SEMANTIC_PENALTY = 0.6
AUDIO_MIN_SCORE = 0.15
SCREENSHOT_MIN_SCORE = 0.18

# ── AI Assistant ───────────────────────────────────────────────────
AI_BASE_URL_DEFAULT   = "https://api.gonkagate.com/v1"
# Nessun modello preimpostato: lo sceglie l'utente (combo editabile +
# "Rileva modelli" in Impostazioni → AI). Endpoint OpenAI-compatibile.
AI_MODELS             = []
AI_MODEL_DEFAULT      = ""
AI_MAX_TOKENS         = 2048
AI_CONTEXT_TOKENS     = 128_000
AI_RAG_TOP_K          = 10
AI_INLINE_RAG_DEFAULT = "0"

# ── Vision (solo Ask Screen) ──────────────────────────────────────
# Google Gemini free tier: limiti per modello (vedi ai.google.dev/pricing)
# Endpoint OpenAI-compatibile ufficiale Google.
AI_VISION_BASE_URL_DEFAULT = "https://generativelanguage.googleapis.com/v1beta/openai/"
AI_VISION_MODEL_DEFAULT    = "gemini-2.5-flash"
AI_VISION_MODELS = [
    "gemini-2.5-flash",        # stable, 250 req/giorno free
    "gemini-2.5-flash-lite",   # più veloce, 1000 req/giorno free
    "gemini-2.5-pro",          # più capace, 50 req/giorno free
    "gemini-2.0-flash",        # gen precedente stable
    "gemini-2.0-flash-lite",
]
AI_VISION_MAX_TOKENS = 2048
AI_VISION_IMAGE_MAX_W = 1280  # downscale per ridurre token immagine
