# modules/capturer.py
import time, hashlib, io, logging
from datetime import datetime, timezone
import mss
from PIL import Image
import pytesseract
import pygetwindow as gw
from db import get_conn, get_setting
from modules import privacy
from modules import web_bridge
import config
from config import OCR_LANG, TESSERACT_CMD
# NB: CAPTURE_INTERVAL si legge come config.CAPTURE_INTERVAL (dinamico): un
# `from config import CAPTURE_INTERVAL` catturerebbe il default all'import,
# ignorando il valore salvato applicato da load_settings_into_config.

# Imposta il path solo se trovato; altrimenti pytesseract prova "tesseract" su PATH
# e _ocr() degrada (ritorna "") senza far crashare la cattura.
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

_OCR_AVAILABLE = bool(TESSERACT_CMD)

def _image_to_compressed_bytes(img):
    new_w = int(img.width * 0.75); new_h = int(img.height * 0.75)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=70, optimize=True)
    return buf.getvalue()

def _hash_bytes(data): return hashlib.sha256(data).hexdigest()

def _last_hash(conn):
    row = conn.cursor().execute("SELECT hash FROM screenshots ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None

def _get_active_app():
    try:
        win = gw.getActiveWindow()
        return win.title if win else "Sconosciuta"
    except: return "Sconosciuta"

def _get_active_monitor(sct):
    try:
        win = gw.getActiveWindow()
        if not win: return sct.monitors[1]
        win_cx = win.left + win.width // 2
        win_cy = win.top + win.height // 2
        for m in sct.monitors[1:]:
            if m["left"] <= win_cx <= m["left"]+m["width"] and m["top"] <= win_cy <= m["top"]+m["height"]:
                return m
    except: pass
    return sct.monitors[1]

def _ocr(img, lang=OCR_LANG):
    try: return pytesseract.image_to_string(img, lang=lang).strip()
    except Exception as e: print(f"[Capturer] Errore OCR: {e}"); return ""

def _save(conn, compressed, h, text, app):
    conn.cursor().execute(
        "INSERT INTO screenshots (ts, app, hash, image, text) VALUES (?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), app, h, compressed, text))
    conn.commit()

def _should_skip_app(app):
    raw = get_setting("privacy_blocklist", "")
    patterns = privacy.parse_blocklist(raw or "")
    return privacy.is_app_blocked(app, patterns)

def _capture_target(sct):
    """Area da catturare: regione fissa salvata dall'utente (se valida) altrimenti
    il monitor della finestra attiva. Letta a ogni ciclo (cambio immediato)."""
    raw = get_setting("capture_region", "") or ""
    if raw and raw != "full":
        try:
            import json
            r = json.loads(raw)
            if int(r["width"]) > 0 and int(r["height"]) > 0:
                return {"left": int(r["left"]), "top": int(r["top"]),
                        "width": int(r["width"]), "height": int(r["height"])}
        except Exception:
            pass
    return _get_active_monitor(sct)

_log = logging.getLogger("deja.capturer")

def run(stop_event):
    conn = get_conn()
    print("[Capturer] Avviato.")
    if not _OCR_AVAILABLE:
        print("[Capturer] Tesseract non trovato: cattura attiva ma senza OCR (testo vuoto).")
        _log.warning("Tesseract assente: OCR disattivato.")
    while not stop_event.is_set():
        start = time.time()
        try:
            # Toggle utente: cattura screenshot disattivabile da Impostazioni → Cattura.
            # Letta a ogni ciclo così il cambio è immediato senza riavvio.
            if (get_setting("capture_screenshots_enabled", "1") or "1") != "1":
                stop_event.wait(timeout=2); continue
            # Privacy gates
            if privacy.is_paused():
                stop_event.wait(timeout=2); continue
            idle_threshold = int(get_setting("privacy_idle_min", "5") or 5) * 60
            if idle_threshold > 0 and privacy.idle_seconds() > idle_threshold:
                stop_event.wait(timeout=5); continue
            if privacy.is_workstation_locked():
                stop_event.wait(timeout=5); continue
            # Estensione browser: salta se la tab attiva è login o sito escluso.
            # No-op se la feature è OFF o l'estensione non sta inviando stato.
            try:
                if web_bridge.should_skip():
                    print("[Capturer] Skip: tab browser login/esclusa (estensione)")
                    stop_event.wait(timeout=2); continue
            except Exception:
                pass

            with mss.mss() as sct:
                monitor = _capture_target(sct)
                app = _get_active_app()
                if _should_skip_app(app):
                    stop_event.wait(timeout=max(0, config.CAPTURE_INTERVAL - (time.time()-start)))
                    continue
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                compressed = _image_to_compressed_bytes(img)
                h = _hash_bytes(compressed)
                if h != _last_hash(conn):
                    ocr_lang = get_setting("ocr_lang", "") or OCR_LANG
                    text = _ocr(img, ocr_lang)
                    # Redaction PII
                    redact_on = (get_setting("privacy_redact", "1") or "1") == "1"
                    text = privacy.redact_pii(text, enabled=redact_on)
                    _save(conn, compressed, h, text, app)
                    print(f"[Capturer] Screenshot -- App={app} OCR len={len(text)}")
        except Exception as e:
            # Errore transitorio (MSS/PIL/DB): logga e continua, non uccidere il thread.
            _log.exception("Errore nel ciclo capturer")
            print(f"[Capturer] Errore ciclo (continuo): {e}")
        stop_event.wait(timeout=max(0, config.CAPTURE_INTERVAL - (time.time()-start)))
    conn.close()
    print("[Capturer] Fermato.")
