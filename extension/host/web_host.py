#!/usr/bin/env python3
# extension/host/web_host.py
"""
Host di native messaging per il bridge browser ↔ Déjà.

Lanciato dal browser (non dall'utente). Legge messaggi dall'estensione via
stdin (framing native messaging: 4 byte length LE + JSON UTF-8) e scrive lo
stato della tab attiva in `%LOCALAPPDATA%\\Deja\\web_state.json` (scrittura
atomica). NON tocca il database: l'unico writer del DB resta l'app Déjà.

Volutamente autonomo (nessun import dell'app) per essere robusto nel contesto
di esecuzione del browser.
"""
import sys
import os
import json
import time
import struct
import tempfile
import uuid


def _data_dir() -> str:
    """DEVE restare allineata a `paths.data_dir()` dell'app (qui è duplicata di
    proposito: l'host non importa nulla dell'app). Prima usava LOCALAPPDATA con
    fallback `~/Deja` anche su Linux, dove l'app legge invece
    `$XDG_DATA_HOME/Deja` (~/.local/share/Deja): il bridge era muto E lasciava
    cronologia in chiaro in `~/Deja` che nessun purge toccava."""
    if sys.platform == "win32":
        base = (os.environ.get("LOCALAPPDATA")
                or os.environ.get("APPDATA")
                or os.path.expanduser("~"))
        d = os.path.join(base, "Deja")
        mode = None
    else:
        base = (os.environ.get("XDG_DATA_HOME")
                or os.path.join(os.path.expanduser("~"), ".local", "share"))
        d = os.path.join(base, "Deja")
        mode = 0o700
    try:
        os.makedirs(d, exist_ok=True) if mode is None else os.makedirs(d, mode=mode, exist_ok=True)
    except Exception:
        pass
    return d


def _inbox_dir() -> str:
    d = os.path.join(_data_dir(), "web_inbox")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _write_page(page: dict) -> None:
    """Scrive una pagina visitata nello spool (l'app la inserisce nel DB)."""
    d = _inbox_dir()
    rec = {
        "v": 1, "ts": time.time(),
        "url": str(page.get("url", ""))[:2048],
        "domain": str(page.get("domain", ""))[:255],
        "title": str(page.get("title", ""))[:512],
        "text": str(page.get("text", ""))[:20000],
        "links": page.get("links") if isinstance(page.get("links"), list) else [],
    }
    rec["links"] = [str(x)[:2048] for x in rec["links"][:100]]
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(d, uuid.uuid4().hex + ".json"))
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


_cfg_cache = {"mtime": 0.0, "data": {}}


def _events_allowed(category: str) -> bool:
    """L'app pubblica in events_cfg.json cosa l'host è autorizzato a spoolare
    (toggle ON, bridge attivo, non in pausa, app viva). File assente/illeggibile
    → OFF: così con la feature spenta NON finisce cronologia in chiaro sul disco.
    Vale per le categorie evento (download/tab/visit) e per la chiave 'page'
    (testo integrale delle pagine)."""
    if not category:
        return False
    path = os.path.join(_data_dir(), "events_cfg.json")
    try:
        m = os.path.getmtime(path)
        if m != _cfg_cache["mtime"]:
            with open(path, "r", encoding="utf-8") as f:
                _cfg_cache["data"] = json.load(f)
            _cfg_cache["mtime"] = m
        cfg = _cfg_cache["data"]
        if not cfg.get(category):
            return False
        # L'autorizzazione SCADE: l'app la riscrive ogni 30s come heartbeat.
        # L'host vive quanto il browser, non quanto Déjà: se l'app viene killata
        # o crasha (niente revoca a chiusura) un cfg "ON" stantio lo teneva a
        # scrivere cronologia in chiaro all'infinito. Un cfg SENZA `ts` viene da
        # una versione precedente dell'app: si accetta (compat), la scadenza
        # entra in vigore dal primo heartbeat.
        ts = cfg.get("ts")
        if isinstance(ts, (int, float)) and (time.time() - ts) > 90:
            return False
        return True
    except Exception:
        return False


def _write_event(ev: dict) -> None:
    """Scrive un evento browser (download/tab/visita) nello spool. Stesso
    canale delle pagine; il discriminatore è `kind: "event"`. L'app filtra in
    base ai toggle webev_* e inserisce in system_events (unico writer DB)."""
    d = _inbox_dir()
    rec = {
        "v": 1, "kind": "event", "ts": time.time(),
        "category": str(ev.get("category", ""))[:32],
        "action": str(ev.get("action", ""))[:32],
        "url": str(ev.get("url", ""))[:2048],
        "final_url": str(ev.get("final_url", ""))[:2048],
        "domain": str(ev.get("domain", ""))[:255],
        "title": str(ev.get("title", ""))[:512],
        "filename": str(ev.get("filename", ""))[:1024],
        "mime": str(ev.get("mime", ""))[:255],
    }
    try:
        rec["bytes"] = int(ev.get("bytes") or 0)
    except Exception:
        rec["bytes"] = 0
    try:
        rec["tab_id"] = int(ev.get("tab_id") or 0)
    except Exception:
        rec["tab_id"] = 0
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(d, uuid.uuid4().hex + ".json"))
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _write_state(tab: dict) -> None:
    state = {"v": 1, "ts": time.time(), "enabled": True, "tab": tab}
    d = _data_dir()
    path = os.path.join(d, "web_state.json")
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    n = struct.unpack("<I", raw)[0]
    if n <= 0 or n > 1024 * 1024:
        return None
    data = sys.stdin.buffer.read(n)
    if len(data) < n:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def main():
    while True:
        try:
            msg = _read_message()
        except Exception:
            break
        if msg is None:
            break
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "state":
            tab = msg.get("tab") or {}
            _write_state({
                "domain": str(tab.get("domain", ""))[:255],
                "url": str(tab.get("url", ""))[:2048],
                "is_login": bool(tab.get("is_login")),
                "is_excluded": bool(tab.get("is_excluded")),
            })
        elif msg.get("type") == "page":
            # Stesso gate degli eventi. Senza, l'host scriveva il TESTO
            # INTEGRALE delle pagine (20k char, NON redatto) in chiaro nello
            # spool anche con il bridge OFF o in pausa: restava su disco fino
            # al purge (6h) o per sempre se l'app non girava.
            if _events_allowed("page"):
                _write_page(msg.get("page") or {})
        elif msg.get("type") == "event":
            ev = msg.get("event") or {}
            # Gate: scrivi solo se l'app ha autorizzato quella categoria.
            if _events_allowed(str(ev.get("category", ""))):
                _write_event(ev)


if __name__ == "__main__":
    main()
