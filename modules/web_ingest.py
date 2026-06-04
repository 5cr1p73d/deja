# modules/web_ingest.py
"""
Watcher dello spool dell'estensione browser. L'host scrive le pagine visitate
in `%LOCALAPPDATA%\\Deja\\web_inbox\\*.json`; qui le leggiamo (UNICO writer del
DB = l'app), applichiamo i gate privacy e le inseriamo in `web_pages`.

Gate prima di inserire:
- feature abilitata (`web_bridge.enabled()`)
- non in pausa/incognito (`privacy.is_paused()`)
- dominio non escluso
- redazione PII applicata su titolo+testo
- dedupe: stessa URL inserita di recente → scartata
"""
import os
import glob
import json
import time
import logging
from datetime import datetime, timezone, timedelta

import paths
from db import get_conn, get_setting
from modules import privacy
from modules import web_bridge

_log = logging.getLogger("deja.web_ingest")

_DEDUPE_MIN = 10      # stessa URL entro N minuti → non re-inserire
_STALE_HOURS = 6      # file in coda più vecchi di così → scartati (no crescita infinita)


def _inbox_dir() -> str:
    d = os.path.join(paths.data_dir(), "web_inbox")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _purge_stale():
    cutoff = time.time() - _STALE_HOURS * 3600
    for p in glob.glob(os.path.join(_inbox_dir(), "*.json")):
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
        except Exception:
            pass


def _process_file(conn, path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            rec = json.load(f)
    except Exception:
        try: os.remove(path)
        except Exception: pass
        return

    url = (rec.get("url") or "").strip()
    domain = (rec.get("domain") or "").strip().lower()
    if not url:
        os.remove(path); return

    # Dominio escluso → scarta in silenzio.
    if web_bridge._domain_excluded(domain):
        os.remove(path); return

    # Dedupe: stessa URL inserita negli ultimi N minuti.
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=_DEDUPE_MIN)).isoformat()
    dup = conn.execute(
        "SELECT 1 FROM web_pages WHERE url=? AND ts>=? LIMIT 1", (url[:2048], cutoff_iso)
    ).fetchone()
    if dup:
        os.remove(path); return

    redact_on = (get_setting("privacy_redact", "1") or "1") == "1"
    title = privacy.redact_pii(rec.get("title") or "", enabled=redact_on)
    text = privacy.redact_pii(rec.get("text") or "", enabled=redact_on)
    links = rec.get("links") if isinstance(rec.get("links"), list) else []

    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO web_pages (ts,url,domain,title,text,links) VALUES (?,?,?,?,?,?)",
        (ts, url[:2048], domain[:255], title[:512], text[:20000], json.dumps(links[:100])),
    )
    conn.commit()
    os.remove(path)
    print(f"[WebIngest] Pagina salvata: {domain} (testo {len(text)} char)")


def run(stop_event):
    conn = get_conn()
    print("[WebIngest] Avviato.")
    while not stop_event.is_set():
        try:
            _purge_stale()
            if web_bridge.enabled() and not privacy.is_paused():
                for path in sorted(glob.glob(os.path.join(_inbox_dir(), "*.json"))):
                    if stop_event.is_set():
                        break
                    _process_file(conn, path)
        except Exception:
            _log.exception("Errore ciclo web_ingest")
        stop_event.wait(timeout=3)
    conn.close()
    print("[WebIngest] Fermato.")
