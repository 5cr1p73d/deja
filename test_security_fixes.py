# test_security_fixes.py
r"""
Verifica i fix di sicurezza/bug del 2026-07-26 (vedi
obsidian/deja/SecurityAudit-2026-07-26-progress.md).

Nessuna rete, nessun DB reale: tutto in-memory o su directory temporanea.
    .\venv\Scripts\python.exe test_security_fixes.py
"""
import os
import re
import sys
import json
import sqlite3
import tempfile

FAIL = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


# ── 1. is_local_endpoint: hostname parsato, non sottostringa ───────
def test_local_endpoint():
    print("\n[1] is_local_endpoint / anti-SSRF")
    from modules.ai_assistant import is_local_endpoint, is_safe_endpoint

    locali = ["http://localhost:11434/v1", "http://127.0.0.1:1234/v1",
              "http://[::1]:8080/v1", "http://0.0.0.0:5000/v1",
              "http://ollama.local:11434/v1", "https://LOCALHOST/v1"]
    for u in locali:
        check(f"locale riconosciuto: {u}", is_local_endpoint(u) is True)

    # I bypass che passavano col match a sottostringa.
    ostili = ["https://localhost.evil.com/v1", "https://x.localdomain.com/v1",
              "https://127.0.0.1.evil.com/v1", "https://api.openai.com/v1",
              "https://not-localhost-really.example/v1", "https://evil.com/?h=localhost"]
    for u in ostili:
        check(f"NON locale: {u}", is_local_endpoint(u) is False)

    # Conseguenza: l'anti-SSRF non viene più scavalcato.
    ok, why = is_safe_endpoint("http://localhost.evil.com/v1")
    check("is_safe_endpoint blocca http su host non locale", ok is False, why)
    ok, why = is_safe_endpoint("http://169.254.169.254/latest/meta-data/")
    check("is_safe_endpoint blocca metadata cloud in http", ok is False, why)
    ok, _ = is_safe_endpoint("http://127.0.0.1:11434/v1")
    check("is_safe_endpoint ammette ancora il locale vero", ok is True)


# ── 2. list_models passa dal gate anti-SSRF ────────────────────────
def test_list_models_gate():
    print("\n[2] list_models: gate anti-SSRF prima di spedire l'API key")
    from modules import ai_assistant

    ok, msg = ai_assistant.list_models(base_url="http://169.254.169.254/latest/",
                                       api_key="sk-segretissima")
    check("list_models rifiuta il link-local", ok is False and "non sicuro" in str(msg).lower(), str(msg))
    ok, msg = ai_assistant.list_models(base_url="http://api.esempio.invalid/v1",
                                       api_key="sk-segretissima")
    check("list_models rifiuta http pubblico", ok is False and "non sicuro" in str(msg).lower(), str(msg))


# ── 3. host nativo: gate 'page' sullo spool ────────────────────────
def test_page_gate():
    print("\n[3] web_host: nessuna pagina su disco senza autorizzazione")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "extension", "host"))
    import web_host

    with tempfile.TemporaryDirectory() as d:
        web_host._data_dir = lambda: d
        web_host._cfg_cache = {"mtime": 0.0, "data": {}}
        inbox = os.path.join(d, "web_inbox")
        msg = {"type": "page", "page": {"url": "https://banca.example/conto",
                                        "domain": "banca.example", "title": "Conto",
                                        "text": "SALDO 12345 EUR"}}

        def spool_files():
            return [f for f in os.listdir(inbox)] if os.path.isdir(inbox) else []

        def deliver():
            if web_host._events_allowed("page"):
                web_host._write_page(msg["page"])

        # a) nessun cfg (feature mai attivata / app mai partita)
        deliver()
        check("cfg assente → niente su disco", spool_files() == [], str(spool_files()))

        # b) cfg con page:false (bridge OFF o in pausa)
        with open(os.path.join(d, "events_cfg.json"), "w", encoding="utf-8") as f:
            json.dump({"download": True, "tab": True, "visit": True, "page": False}, f)
        web_host._cfg_cache = {"mtime": 0.0, "data": {}}
        deliver()
        check("page:false → niente su disco", spool_files() == [], str(spool_files()))

        # c) cfg senza `ts` (app di versione precedente): compat, si accetta
        with open(os.path.join(d, "events_cfg.json"), "w", encoding="utf-8") as f:
            json.dump({"download": False, "tab": False, "visit": False, "page": True}, f)
        web_host._cfg_cache = {"mtime": 0.0, "data": {}}
        deliver()
        check("page:true senza ts → pagina spoolata (compat)", len(spool_files()) == 1,
              str(spool_files()))

        # d) heartbeat scaduto (app killata/crashata): autorizzazione revocata
        import time as _t
        with open(os.path.join(d, "events_cfg.json"), "w", encoding="utf-8") as f:
            json.dump({"download": True, "tab": True, "visit": True, "page": True,
                       "ts": _t.time() - 600}, f)
        web_host._cfg_cache = {"mtime": 0.0, "data": {}}
        deliver()
        check("ts stantio → niente su disco", len(spool_files()) == 1, str(spool_files()))
        check("ts stantio → anche gli eventi bloccati",
              web_host._events_allowed("download") is False)

        # e) heartbeat fresco → autorizzato
        with open(os.path.join(d, "events_cfg.json"), "w", encoding="utf-8") as f:
            json.dump({"download": False, "tab": False, "visit": False, "page": True,
                       "ts": _t.time()}, f)
        web_host._cfg_cache = {"mtime": 0.0, "data": {}}
        deliver()
        check("ts fresco → pagina spoolata", len(spool_files()) == 2, str(spool_files()))


# ── 4. web_host._data_dir allineata a paths.data_dir() ─────────────
def test_data_dir_match():
    print("\n[4] web_host._data_dir == paths.data_dir()")
    import importlib
    import paths
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "extension", "host"))
    import web_host
    importlib.reload(web_host)   # ripristina la _data_dir vera dopo il test 3

    check("stessa cartella dati dell'app", web_host._data_dir() == paths.data_dir(),
          f"{web_host._data_dir()} != {paths.data_dir()}")

    # L'app deve pubblicare heartbeat + chiave page, e revocarli a chiusura.
    ing = open(os.path.join("modules", "web_ingest.py"), encoding="utf-8").read()
    check("web_ingest pubblica la chiave page", 'eff["page"]' in ing)
    check("web_ingest scrive il ts di heartbeat", 'ts=now' in ing)
    check("web_ingest revoca tutto a chiusura",
          '{c: False for c in (*_EV_CATS, "page")}' in ing)

    # Ramo Linux: XDG, non ~/Deja (non eseguibile su win, si verifica il sorgente).
    src = open(os.path.join("extension", "host", "web_host.py"), encoding="utf-8").read()
    check("ramo non-Windows usa XDG_DATA_HOME", "XDG_DATA_HOME" in src)
    check("ramo non-Windows usa ~/.local/share", '".local", "share"' in src)


# ── 5. validazione ID estensione ───────────────────────────────────
def test_ext_id():
    print("\n[5] install_native_host: ID estensione")
    from modules import web_bridge

    ok, msg = web_bridge.install_native_host("à" * 32)      # 32 lettere unicode
    check("rifiuta ID non-ASCII", ok is False, str(msg))
    ok, msg = web_bridge.install_native_host("z" * 32)      # fuori dal range a-p
    check("rifiuta lettere fuori a-p", ok is False, str(msg))
    ok, msg = web_bridge.install_native_host("abc")
    check("rifiuta ID corto", ok is False, str(msg))
    check("regex accetta un ID valido", bool(re.fullmatch(r"[a-p]{32}", "a" * 32)))


# ── 6. FTS: il LIMIT tiene i ricordi RECENTI ───────────────────────
def test_fts_recent():
    print("\n[6] _fts_coverage: ORDER BY rowid DESC")
    from modules import search

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE screenshots_fts USING fts5(text)")
    except sqlite3.OperationalError as e:
        print(f"  SKIP  FTS5 non disponibile in questo sqlite3 stdlib ({e})")
        return
    # 500 righe con lo stesso token: le prime (id bassi) sono le più VECCHIE.
    conn.executemany("INSERT INTO screenshots_fts(rowid, text) VALUES (?, ?)",
                     [(i, "riunione progetto") for i in range(1, 501)])
    conn.commit()

    orig = search.fts_ready
    search.fts_ready = lambda: True
    try:
        hits = search._fts_coverage(conn, "screenshots", ["riunione"], limit=10)
    finally:
        search.fts_ready = orig
    ids = [i for i, _ in hits]
    check("torna risultati", len(ids) > 0)
    # Con LIMIT 20000 il taglio non morde su 500 righe: si verifica l'ORDINE
    # della query, che è ciò che cambia quale fetta sopravvive al LIMIT.
    rows = conn.execute("SELECT rowid FROM screenshots_fts WHERE screenshots_fts "
                        "MATCH ? ORDER BY rowid DESC LIMIT 10", ('"riunione"*',)).fetchall()
    check("la query ordina dal più recente", [r[0] for r in rows] == list(range(500, 490, -1)))
    src = open(os.path.join("modules", "search.py"), encoding="utf-8").read()
    check("_fts_coverage usa ORDER BY rowid DESC", "ORDER BY rowid DESC LIMIT 20000" in src)
    conn.close()


# ── 7. encode senza doppioni ───────────────────────────────────────
def test_encode_dedupe():
    print("\n[7] _encode_queries: nessun encode doppio")
    from modules import search, embedder
    import numpy as np

    calls = []

    def fake_encode(texts):
        texts = list(texts)
        calls.append(texts)
        return np.ones((len(texts), 4), dtype="float32")

    orig = embedder.encode
    embedder.encode = fake_encode
    search._q_emb_cache.clear()
    try:
        out = search._encode_queries(["tecnico", "tecnico", "appuntamento"])
    finally:
        embedder.encode = orig
        search._q_emb_cache.clear()
    check("un solo batch", len(calls) == 1, str(calls))
    check("nessun testo ripetuto nel batch", calls and len(calls[0]) == len(set(calls[0])), str(calls))
    check("tutte le query hanno un vettore", set(out) == {"tecnico", "appuntamento"})


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    test_local_endpoint()
    test_list_models_gate()
    test_page_gate()
    test_data_dir_match()
    test_ext_id()
    test_fts_recent()
    test_encode_dedupe()
    print("\n" + ("TUTTI OK" if not FAIL else f"FALLITI {len(FAIL)}: " + ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)
