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
import re
import glob
import json
import time
import logging
from datetime import datetime, timezone, timedelta

import paths
from db import get_conn, get_setting, log_system_event
from modules import privacy
from modules import web_bridge

_log = logging.getLogger("deja.web_ingest")

_DEDUPE_MIN = 10      # stessa URL entro N minuti → non re-inserire
_STALE_HOURS = 6      # file in coda più vecchi di così → scartati (no crescita infinita)

# Difesa extra: scarta pagine di login/auth anche se arrivassero (privacy).
_LOGIN_URL_RE = re.compile(
    r"(/login|/log[_-]?in|/signin|/sign[_-]?in|/signup|/sign[_-]?up|/register|"
    r"/create[_-]?account|/auth(/|$|\?)|/account/login|/sessions/new|"
    r"accounts\.google\.|login\.microsoftonline|appleid\.apple\.|oauth|/sso)",
    re.I,
)


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


def _process_event(conn, path, rec, ev_flags):
    """Evento browser dallo spool (kind=event) → system_events, se la sua
    categoria è attiva (webev_*_enabled, tutto OFF di default)."""
    cat = (rec.get("category") or "").strip().lower()
    action = (rec.get("action") or "").strip().lower()[:32]
    if cat not in ("download", "tab", "visit") or not ev_flags.get(cat):
        os.remove(path); return

    url = (rec.get("url") or "").strip()
    domain = (rec.get("domain") or "").strip().lower()
    if domain and web_bridge._domain_excluded(domain):
        os.remove(path); return
    if url and _LOGIN_URL_RE.search(url):
        os.remove(path); return  # mai registrare login/auth

    # Redazione PII PRIMA di dedupe/insert: url (query string può contenere
    # email/token), titolo e filename. Il dedupe confronta la forma redatta,
    # coerente con ciò che viene salvato come subject.
    redact_on = (get_setting("privacy_redact", "1") or "1") == "1"
    url = privacy.redact_pii(url, enabled=redact_on)
    final_url = privacy.redact_pii(rec.get("final_url") or "", enabled=redact_on)
    title = privacy.redact_pii(rec.get("title") or "", enabled=redact_on)
    filename = privacy.redact_pii(rec.get("filename") or "", enabled=redact_on)
    try:
        nbytes = int(rec.get("bytes") or 0)
    except Exception:
        nbytes = 0

    # Dedupe visite: stessa URL già registrata negli ultimi N minuti.
    if cat == "visit":
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=_DEDUPE_MIN)).isoformat()
        dup = conn.execute(
            "SELECT 1 FROM system_events WHERE category='visit' AND subject=? AND ts>=? LIMIT 1",
            (url[:2048], cutoff_iso)).fetchone()
        if dup:
            os.remove(path); return

    if cat == "download":
        base = os.path.basename(filename.replace("\\", "/")) or "file"
        size = f" ({nbytes / 1048576:.1f} MB)" if nbytes > 0 else ""
        verb = "completato" if action == "completed" else "avviato"
        subject, text = (filename or url), f"Download {verb}: {base}{size}"
        detail = {"url": url, "final_url": final_url,
                  "domain": domain, "filename": filename,
                  "mime": rec.get("mime") or "", "bytes": nbytes}
    elif cat == "tab":
        if action == "opened":
            subject, text = (url or domain), ("Tab aperta" + (f": {domain}" if domain else ""))
        else:
            subject, text = "", "Tab chiusa"
        detail = {"url": url, "domain": domain, "title": title,
                  "tab_id": rec.get("tab_id") or 0}
    else:  # visit
        subject = url
        text = f"Pagina visitata: {title or domain or url}"
        detail = {"url": url, "domain": domain, "title": title}

    log_system_event(conn, "browser", cat, action or cat,
                     subject=subject, app=domain, detail=detail, text=text)
    conn.commit()
    os.remove(path)
    print(f"[WebIngest] Evento browser salvato: {cat}/{action}")


def _process_file(conn, path, ev_flags=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            rec = json.load(f)
    except Exception:
        try: os.remove(path)
        except Exception: pass
        return

    # Discriminatore: gli eventi browser viaggiano sullo stesso spool delle
    # pagine ma con kind="event".
    if rec.get("kind") == "event":
        _process_event(conn, path, rec, ev_flags or {})
        return

    url = (rec.get("url") or "").strip()
    domain = (rec.get("domain") or "").strip().lower()
    if not url:
        os.remove(path); return

    # Dominio escluso → scarta in silenzio.
    if web_bridge._domain_excluded(domain):
        os.remove(path); return

    # Difesa privacy: URL di login/auth → mai ingerire.
    if _LOGIN_URL_RE.search(url):
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


_EV_CATS = ("download", "tab", "visit")
_last_cfg = None


def _events_cfg_path():
    return os.path.join(paths.data_dir(), "events_cfg.json")


def _write_events_cfg(eff):
    """Pubblica per l'host nativo QUALI eventi browser è autorizzato a scrivere
    nello spool. Senza questo gate l'host scriverebbe SEMPRE (cronologia in
    chiaro su disco) anche con i toggle OFF: così invece, con tutto OFF/pausa,
    l'host non scrive nulla. Scrittura atomica, solo se cambia."""
    global _last_cfg
    if eff == _last_cfg:
        return
    try:
        import tempfile
        d = paths.data_dir()
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(eff, f)
        os.replace(tmp, _events_cfg_path())
        _last_cfg = dict(eff)
    except Exception:
        pass


def run(stop_event):
    conn = get_conn()
    print("[WebIngest] Avviato.")
    while not stop_event.is_set():
        try:
            _purge_stale()
            bridge = web_bridge.enabled()
            paused = privacy.is_paused()
            raw = {c: (get_setting(f"webev_{c}_enabled", "0") or "0") == "1" for c in _EV_CATS}
            # Effettivo = toggle ON e bridge attivo e non in pausa. È ciò che
            # l'host può scrivere: in pausa o con feature OFF → niente su disco.
            eff = {c: (raw[c] and bridge and not paused) for c in _EV_CATS}
            _write_events_cfg(eff)
            if bridge and not paused:
                for path in sorted(glob.glob(os.path.join(_inbox_dir(), "*.json"))):
                    if stop_event.is_set():
                        break
                    _process_file(conn, path, raw)
        except Exception:
            _log.exception("Errore ciclo web_ingest")
        stop_event.wait(timeout=3)
    conn.close()
    print("[WebIngest] Fermato.")
