<div align="center">

<img src="assets/icon.png" width="96" alt="Déjà">

# Déjà

**Your digital memory for Windows.**

Déjà captures in the background what you see and hear on your PC, indexes it locally, and lets you **find it again** with a semantic search — or **ask** an AI assistant about it. Like [Rewind AI](https://www.rewind.ai/), but open source and with data that stays on your computer.

</div>

---

## What it is

Déjà runs in the system tray and does three things:

1. **Capture** — periodic screenshots (default every 5s) + system audio and microphone.
2. **Index** — OCR on screenshots, Whisper transcription on audio, and multilingual embeddings of all text in a local SQLite DB.
3. **Retrieve** — an overlay (`Ctrl+Shift+D`) to search your memories with semantic + exact search, browse the timeline, or chat with an AI assistant that has access to your context (RAG).

The entire index lives locally. Capture/OCR/transcription models run offline; optional AI chat functions use an OpenAI-compatible endpoint of your choice — **even local** (Ollama / LM Studio), so nothing leaves the PC.

## Features

- 🖼️ **Screen capture + OCR** (`ita+eng`, Tesseract) with deduplication of identical frames.
- 🎙️ **Audio capture** — system loopback + microphone, transcription via `faster-whisper`.
- 🔎 **Hybrid search** — semantic (768-dim embeddings, cosine int8 via `sqlite-vec`) + exact match, with filters by date and type.
- 🗂️ **"Explore" Timeline** — browse everything by Today / Yesterday / 7 days / All.
- 💬 **AI Chat with RAG** — ask questions about your activity; the assistant retrieves relevant memories as context.
- 👁️ **Ask Screen** (`Ctrl+Shift+A`) — ask the AI what's on the screen right now (vision).
- 🌍 **Multilingual** — interface and search in `it` / `en` / `es`.
- 🔒 **Privacy-first** — local DB, onboarding with explicit consent, privacy filters.
- 🧯 **Robust degradation** — if ML models fail to load (e.g. missing VC++ redist), capture + OCR + text search continue to work.

## Tech Stack

| Layer | Technology |
|-------|------------|
| GUI | PyQt6 (system tray + overlay) |
| DB | SQLite WAL + [`sqlite-vec`](https://github.com/asg017/sqlite-vec) — cosine int8, 768-dim |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` (multilingual, 768-dim) |
| STT | `faster-whisper` (`large-v3-turbo`, CPU int8) |
| OCR | Tesseract (`ita+eng`) |
| Audio | `pyaudiowpatch` (loopback callback-based) |
| Chat AI | OpenAI SDK on any OpenAI-compatible endpoint (local or cloud) |
| Vision | Any OpenAI-compatible multimodal model (Ask Screen) |
| Hotkey | `keyboard` — `Ctrl+Shift+D` (overlay), `Ctrl+Shift+A` (ask screen) |

## Installation (user)

Download the Windows installer from the [Releases](https://github.com/5cr1p73d/deja/releases) section (`Deja-Setup-1.0.0.exe`, ~265 MB, includes the VC++ runtime) and run it. On first launch, the onboarding asks for consent before starting any capture.

> OCR requires [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
> Déjà looks for it automatically (env `TESSERACT_CMD` → `PATH` → known locations).

## Development

Requirements: **Windows**, **Python 3.11+**, [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki).

```powershell
git clone https://github.com/5cr1p73d/deja.git
cd deja
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

On first launch, models (embedding ~1 GB, Whisper) are downloaded from HuggingFace and cached.

### AI Configuration (optional)

Chat/vision features are optional. Without AI, capture, OCR, transcription and search still work.

Déjà works with **any OpenAI-compatible endpoint** — local or cloud. You're not tied to any provider: set Base URL + (optional) API Key + model in **Settings → AI**, and the **🔄 Detect** button lists available models on the endpoint. The model field is free-text: you can type any ID.

#### Local models (full privacy, no key needed)

Point the Base URL to your local server (presets already available in Settings):

| Server | Base URL | Start |
|--------|----------|-------|
| [Ollama](https://ollama.com) | `http://localhost:11434/v1` | `ollama serve` |
| [LM Studio](https://lmstudio.ai) | `http://localhost:1234/v1` | start the local server from the app |

With a local endpoint, **API Key is not needed** (leave blank).

**Chat — recommended models** (good multilingual capabilities + *tool calling* required, used to search memories):

- `llama3.1:8b` — good tool-calling, multilingual (recommended)
- `mistral-nemo` — lightweight, with tool-calling
- any model with *function calling* and good multilingual capabilities
- ⚠ Models without *function calling* support work for free chat but **cannot** automatically search memories.

**Vision (Ask Screen) — requires a multimodal model:**

- `llama3.2-vision:11b`
- `llava:13b` / `llava:7b`

Download with `ollama pull <model>`. Rule: bigger = better but slower; start with smaller sizes if you have limited VRAM.

#### Cloud providers

Any OpenAI-compatible service works (OpenAI, OpenRouter, Groq, Together, or self-hosted gateway). Paste the provider's Base URL + API Key and press **🔄 Detect**.

⚠ With a cloud provider for Vision, the screen image leaves your PC.

## Commands

| Hotkey | Action |
|--------|--------|
| `Ctrl+Shift+D` | Open/close the search overlay |
| `Ctrl+Shift+A` | Ask Screen — ask the AI what's on screen |

## Where data is stored

Everything in a writable user data dir (never in `Program Files`):

```
%LOCALAPPDATA%\Deja\
  deja.db           SQLite index (+ .wal, .shm)
  logs\deja.log     application log
  models\           HuggingFace model cache (consumer build)
```

When developing from source, if a `deja.db` already exists in the project folder, that one is reused.

## Build

```powershell
.\build.bat    # PyInstaller (onedir) → dist\
               # installer: Inno Setup on deja.iss
```

## Project Structure

```
main.py           entry point, error handling + torch degradation
config.py         runtime constants (models, intervals, endpoints)
paths.py          consumer-safe paths (user data dir)
db.py             SQLite schema + sqlite-vec + settings
modules/          capturer, indexer, audio, search, ai_assistant, ask_screen, privacy
ui/               window (overlay), tray, settings, hotkey, onboarding
i18n.py           it/en/es translations
obsidian/deja/    internal documentation vault
```

## Privacy

Déjà is designed to stay local: no automatic uploads, index only on your PC, explicit consent before capturing. The only network calls are the optional AI functions (chat/vision) to the endpoint you configure.

## License

See [`LICENSE`](LICENSE). Déjà captures potentially sensitive data: use it only on your own devices and in compliance with applicable laws.
