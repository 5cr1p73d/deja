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


def _data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Deja")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


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
        if isinstance(msg, dict) and msg.get("type") == "state":
            tab = msg.get("tab") or {}
            _write_state({
                "domain": str(tab.get("domain", ""))[:255],
                "url": str(tab.get("url", ""))[:2048],
                "is_login": bool(tab.get("is_login")),
                "is_excluded": bool(tab.get("is_excluded")),
            })
        # Altri tipi (es. "page" per l'ingest contenuto) verranno gestiti in F2.


if __name__ == "__main__":
    main()
