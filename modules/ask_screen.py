# modules/ask_screen.py
"""
"Chiedi allo schermo ora" — cattura istantanea schermo + OCR (e/o Vision) + AI streaming.

Flusso:
  1. capture_now() → screenshot del monitor attivo + OCR + app name
  2. ask_stream(question, snap) → generator (kind, content) verso AI
     - se vision enabled (Gemini) → invia immagine base64 (no OCR text)
     - else → fallback OCR text-only
  3. save_snapshot() → opzionale, salva in screenshots table

Independent dal capturer loop. Usa stessa pipeline OCR/redaction.
"""
import io
import base64
import hashlib
import time
from datetime import datetime, timezone

import mss
from PIL import Image
import pytesseract
import pygetwindow as gw

from db import get_conn, get_setting
from modules import privacy, ai_assistant
import i18n
from config import (
    OCR_LANG, TESSERACT_CMD, AI_MAX_TOKENS, AI_CONTEXT_TOKENS,
    AI_VISION_BASE_URL_DEFAULT, AI_VISION_MODEL_DEFAULT,
    AI_VISION_MAX_TOKENS, AI_VISION_IMAGE_MAX_W,
)

# Imposta il path solo se Tesseract è stato trovato (altrimenti _ocr degrada,
# e con Vision attiva l'OCR non serve comunque).
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


# ── Capture ────────────────────────────────────────────────────────
def _active_app():
    try:
        win = gw.getActiveWindow()
        return win.title if win else "Sconosciuta"
    except Exception:
        return "Sconosciuta"


def _active_monitor(sct):
    try:
        win = gw.getActiveWindow()
        if not win:
            return sct.monitors[1]
        cx = win.left + win.width // 2
        cy = win.top + win.height // 2
        for m in sct.monitors[1:]:
            if m["left"] <= cx <= m["left"] + m["width"] and m["top"] <= cy <= m["top"] + m["height"]:
                return m
    except Exception:
        pass
    return sct.monitors[1]


def _compress(img, quality=80, scale=0.85):
    new_w = int(img.width * scale)
    new_h = int(img.height * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _thumbnail(img, max_w=520):
    if img.width <= max_w:
        thumb = img
    else:
        ratio = max_w / img.width
        thumb = img.resize((max_w, int(img.height * ratio)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    thumb.convert("RGB").save(buf, format="JPEG", quality=78, optimize=True)
    return buf.getvalue()


def _vision_image_bytes(img, max_w=AI_VISION_IMAGE_MAX_W, quality=85):
    """Resize+encode immagine per invio vision API. JPEG ~80-150KB tipico."""
    if img.width > max_w:
        ratio = max_w / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_w, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _ocr(img):
    try:
        lang = get_setting("ocr_lang", "") or OCR_LANG
        return pytesseract.image_to_string(img, lang=lang).strip()
    except Exception as e:
        print(f"[AskScreen] OCR error: {e}")
        return ""


def _lang_line() -> str:
    """Istruzione per far rispondere l'AI nella lingua UI scelta."""
    return f"\n\nIMPORTANTE: rispondi sempre in {i18n.ai_language_name()}."


def capture_now():
    """Cattura istantanea. Ritorna dict:
       { 'image': bytes(JPEG full), 'thumb': bytes(JPEG small),
         'vision': bytes(JPEG resized per vision API),
         'text': str(OCR), 'app': str, 'ts': str(ISO), 'hash': str }
    """
    t0 = time.time()
    with mss.mss() as sct:
        monitor = _active_monitor(sct)
        app = _active_app()
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
    image_bytes = _compress(img)
    thumb_bytes = _thumbnail(img)
    vision_bytes = _vision_image_bytes(img)
    text = _ocr(img)
    redact_on = (get_setting("privacy_redact", "1") or "1") == "1"
    text = privacy.redact_pii(text, enabled=redact_on)
    h = hashlib.sha256(image_bytes).hexdigest()
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[AskScreen] capture {app!r} OCR={len(text)}ch vision={len(vision_bytes)//1024}KB t={time.time()-t0:.2f}s")
    return {
        "image": image_bytes,
        "thumb": thumb_bytes,
        "vision": vision_bytes,
        "text": text,
        "app": app,
        "ts": ts,
        "hash": h,
    }


def save_snapshot(snap):
    """Persiste come screenshot normale (così appare in search/timeline)."""
    try:
        conn = get_conn()
        conn.cursor().execute(
            "INSERT INTO screenshots (ts, app, hash, image, text) VALUES (?, ?, ?, ?, ?)",
            (snap["ts"], snap["app"], snap["hash"], snap["image"], snap["text"]),
        )
        conn.commit()
        sid = conn.cursor().execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return sid
    except Exception as e:
        print(f"[AskScreen] save fail: {e}")
        return None


# ── Vision config ──────────────────────────────────────────────────
def _get_setting(key, default=""):
    conn = get_conn()
    row = conn.cursor().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def get_vision_config():
    """Ritorna config vision (Gemini default). Indipendente da AI text config."""
    enabled = (_get_setting("ai_vision_enabled", "0") or "0") == "1"
    base = (_get_setting("ai_vision_base_url", AI_VISION_BASE_URL_DEFAULT)
            or AI_VISION_BASE_URL_DEFAULT).strip()
    key = (_get_setting("ai_vision_api_key", "") or "").strip()
    model = (_get_setting("ai_vision_model", AI_VISION_MODEL_DEFAULT)
             or AI_VISION_MODEL_DEFAULT).strip()
    return {
        "enabled": enabled,
        "base_url": base,
        "api_key": key,
        "model": model,
    }


def vision_is_configured():
    cfg = get_vision_config()
    # Abilitato + (key presente OPPURE endpoint locale, che non richiede key).
    return cfg["enabled"] and (bool(cfg["api_key"]) or ai_assistant.is_local_endpoint(cfg["base_url"]))


def _vision_client():
    """Client OpenAI-compat dedicato vision (Gemini)."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai SDK non installato. Esegui: pip install openai") from e
    cfg = get_vision_config()
    key = cfg["api_key"]
    if not key:
        if ai_assistant.is_local_endpoint(cfg["base_url"]):
            key = "local"  # endpoint vision locale (es. llava su Ollama): chiave fittizia
        else:
            raise RuntimeError("Vision API key mancante. Configura in Impostazioni → AI → Vision.")
    try:
        print(f"[AskScreen] vision client url={cfg['base_url']} model={cfg['model']} "
              f"key={key[:6]}...{key[-4:]} (len={len(key)})")
    except Exception:
        pass
    return OpenAI(base_url=cfg["base_url"], api_key=key), cfg["model"]


def test_vision_connection():
    """Ping vision endpoint. Ritorna (ok, msg)."""
    try:
        client, model = _vision_client()
    except Exception as e:
        return False, str(e)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        text = (resp.choices[0].message.content or "").strip()[:60]
        return True, f"OK · modello: {model}" + (f" · risposta: {text}" if text else "")
    except Exception as e:
        return False, str(e)[:200]


# ── AI streaming ───────────────────────────────────────────────────
ASK_SYSTEM_PROMPT_OCR = (
    "Sei Déjà, assistente AI personale. L'utente ti chiede qualcosa "
    "sullo schermo che STA GUARDANDO IN QUESTO MOMENTO. Hai accesso a:\n"
    "- testo OCR estratto dallo schermo corrente (potrebbe contenere errori OCR)\n"
    "- nome dell'app/finestra attiva\n"
    "- timestamp cattura\n\n"
    "REGOLE:\n"
    "1. Concentrati su ciò che è visibile ORA — non cercare in memoria storica.\n"
    "2. Rispondi in italiano, conciso e diretto.\n"
    "3. Se l'utente chiede 'cosa fa questo errore', 'spiega', 'riassumi', "
    "'traduci' → focus sul contenuto OCR fornito.\n"
    "4. Se l'OCR è rumoroso o incompleto, dillo brevemente e prova lo stesso.\n"
    "5. Formattazione markdown ammessa (code, bold, liste).\n"
    "6. NON citare [ss:ID] o [au:ID] — qui non ci sono ID, è cattura istantanea.\n"
)

ASK_SYSTEM_PROMPT_VISION = (
    "Sei Déjà, assistente AI personale. L'utente ti chiede qualcosa "
    "sullo schermo che STA GUARDANDO IN QUESTO MOMENTO. "
    "Hai accesso DIRETTO all'immagine dello schermo (vision), oltre a:\n"
    "- nome dell'app/finestra attiva\n"
    "- timestamp cattura\n\n"
    "REGOLE:\n"
    "1. Concentrati su ciò che è visibile ORA — non cercare in memoria storica.\n"
    "2. Rispondi in italiano, conciso e diretto.\n"
    "3. Puoi descrivere elementi visivi (grafici, icone, layout, colori, immagini), "
    "leggere testo, identificare errori, spiegare interfacce.\n"
    "4. Formattazione markdown ammessa (code, bold, liste).\n"
    "5. NON citare [ss:ID] o [au:ID] — cattura istantanea, no ID persistente.\n"
)


def _format_ocr_context(snap, max_ocr=8000):
    ocr = (snap.get("text") or "").strip()
    if len(ocr) > max_ocr:
        ocr = ocr[:max_ocr] + "\n…[OCR troncato]"
    app = snap.get("app", "?")
    ts = snap.get("ts", "")[:19].replace("T", " ")
    return (
        f"# Cattura schermo\n"
        f"- App attiva: {app}\n"
        f"- Timestamp: {ts}\n\n"
        f"# Testo OCR\n```\n{ocr or '[nessun testo rilevato]'}\n```"
    )


def _format_vision_context(snap):
    app = snap.get("app", "?")
    ts = snap.get("ts", "")[:19].replace("T", " ")
    return f"App attiva: {app}\nTimestamp: {ts}\n\n"


def _encode_image_b64(image_bytes):
    return base64.b64encode(image_bytes).decode("ascii")


def ask_stream(question, snap):
    """Generator yields (kind, content):
         ("text", chunk)  - chunk testuale streaming
         ("info", msg)    - notifica info (es. "Vision attiva")
         ("error", msg)   - errore
         ("done", None)   - fine

    Strategia:
      - se vision_is_configured() → Gemini con image_url base64
      - else → AI text config (Gonkagate) con OCR text-only
    """
    use_vision = vision_is_configured()

    # Branch 1: Vision (Gemini)
    if use_vision:
        try:
            client, model = _vision_client()
        except Exception as e:
            yield ("error", str(e))
            yield ("done", None)
            return

        image_bytes = snap.get("vision") or snap.get("image")
        if not image_bytes:
            yield ("error", "Snapshot senza immagine.")
            yield ("done", None)
            return

        b64 = _encode_image_b64(image_bytes)
        prefix = _format_vision_context(snap)
        user_content = [
            {"type": "text", "text": f"{prefix}Domanda: {question.strip()}"},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{b64}"
            }},
        ]
        messages = [
            {"role": "system", "content": ASK_SYSTEM_PROMPT_VISION + _lang_line()},
            {"role": "user", "content": user_content},
        ]
        yield ("info", f"vision · {model}")

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                max_tokens=AI_VISION_MAX_TOKENS,
                temperature=0.5,
            )
        except Exception as e:
            yield ("error", f"API error: {e}")
            yield ("done", None)
            return

        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and getattr(delta, "content", None):
                    yield ("text", delta.content)
        except Exception as e:
            yield ("error", f"Stream error: {e}")
            yield ("done", None)
            return

        yield ("done", None)
        return

    # Branch 2: OCR text-only (fallback, usa AI text config esistente)
    try:
        client, model = ai_assistant._client()
    except Exception as e:
        yield ("error", str(e))
        yield ("done", None)
        return

    user_content = (
        f"{_format_ocr_context(snap)}\n\n"
        f"# Domanda utente\n{question.strip()}"
    )
    messages = [
        {"role": "system", "content": ASK_SYSTEM_PROMPT_OCR + _lang_line()},
        {"role": "user", "content": user_content},
    ]
    yield ("info", f"ocr · {model}")

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=AI_MAX_TOKENS,
            temperature=0.5,
        )
    except Exception as e:
        yield ("error", f"API error: {e}")
        yield ("done", None)
        return

    try:
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                yield ("text", delta.content)
    except Exception as e:
        yield ("error", f"Stream error: {e}")
        yield ("done", None)
        return

    yield ("done", None)
