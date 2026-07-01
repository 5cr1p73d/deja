# modules/ai_assistant.py
"""
AI assistant module for Déjà.
- chat_stream(): streaming chat with tool calling (search_memories, list_recent)
- rag_inline(): one-shot synthesis for inline search card
- Endpoint OpenAI-compatible (Gonka, OpenRouter, ecc.)
"""
import json
import re
import math
import time as _time
import concurrent.futures
from datetime import datetime, timezone, timedelta

from db import get_conn
from modules import search as search_module
from modules.secrets import reveal_secret
import i18n
from config import (
    AI_BASE_URL_DEFAULT, AI_MODEL_DEFAULT,
    AI_MAX_TOKENS, AI_CONTEXT_TOKENS, AI_RAG_TOP_K,
)

# ── Settings access ────────────────────────────────────────────────
def _get_setting(key, default=""):
    conn = get_conn()
    row = conn.cursor().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def get_ai_config():
    base = (_get_setting("ai_base_url", AI_BASE_URL_DEFAULT) or AI_BASE_URL_DEFAULT).strip()
    # Auto-upgrade vecchio http:// → https://
    if base.startswith("http://node4.gonka.ai") or base.startswith("http://api.gonkagate"):
        base = "https://" + base[len("http://"):]
    # Auto-migrate vecchio endpoint node4.gonka.ai → api.gonkagate.com (firma diversa)
    if "node4.gonka.ai" in base:
        base = "https://api.gonkagate.com/v1"
    return {
        "api_key":   reveal_secret(_get_setting("ai_api_key", "")).strip(),
        "base_url":  base,
        "model":     (_get_setting("ai_model", AI_MODEL_DEFAULT) or AI_MODEL_DEFAULT).strip(),
        "inline":    _get_setting("ai_inline_rag", "0") == "1",
    }

# ── Ricerca agentica (fan-out parallelo) ───────────────────────────
# Quando attiva: la domanda viene scomposta in più query, le ricerche locali
# girano, poi N chiamate LLM PARALLELE estraggono i fatti (ognuna col proprio
# budget di token → si supera il limite per-call), e una sintesi finale unisce.
AGENTIC_MAX_WORKERS      = 4    # chiamate LLM CONCORRENTI (parallelismo reale)
AGENTIC_MAX_BATCHES      = 8    # max worker totali per turno (tetto costo)
AGENTIC_MAX_SUBQUERIES   = 6    # angoli di ricerca dal planner (più = più coverage)
AGENTIC_RESULTS_PER_QUERY = 15  # risultati per ogni sub-query
AGENTIC_POOL_CAP         = 48   # tetto risultati totali considerati
AGENTIC_WEB_CHARS        = 6000 # testo pagina web dato a un worker (per risultato)
AGENTIC_OTHER_CHARS      = 1000 # screenshot/audio per risultato
AGENTIC_CALL_OVERHEAD_TOK = 2500  # margine per system+domanda+formattazione
AGENTIC_WORKER_OUT_TOK   = 2000   # output max di un worker (estrazione = concisa)

# Limiti REALI per modello (dal pannello endpoint). context/output in token.
# Match per sottostringa normalizzata (l'id può avere prefisso provider, es. "Qwen/").
_MODEL_CAPS = {
    "qwen3-235b-a22b-instruct-2507-fp8": {"context": 128000, "max_output": 8192},
    "kimi-k2.6":    {"context": 128000, "max_output": 3072},
    "minimax-m2.7": {"context": 128000, "max_output": 4096},
}
_DEFAULT_CAPS = {"context": 128000, "max_output": 4096}

# Risposta pulita quando davvero non si trova nulla (mai mostrare il sentinel grezzo).
_NOTHING_MSG = ("Non ho trovato nei tuoi ricordi qualcosa che corrisponde alla richiesta. "
                "Se è più vecchio o lo ricordi diversamente, dammi qualche dettaglio in più "
                "(quando è successo, con chi, l'argomento).")


def _model_caps(model: str) -> dict:
    norm = re.sub(r"[^a-z0-9]", "", (model or "").lower())
    for key, caps in _MODEL_CAPS.items():
        k = re.sub(r"[^a-z0-9]", "", key)
        if k and (k in norm or norm in k):
            return caps
    return _DEFAULT_CAPS


def agentic_enabled() -> bool:
    return _get_setting("ai_agentic_search", "0") == "1"


def is_local_endpoint(url: str) -> bool:
    """True se l'endpoint punta a un server locale (Ollama, LM Studio, llama.cpp…).
    Gli endpoint locali OpenAI-compatibili non richiedono API key."""
    u = (url or "").lower()
    return (any(h in u for h in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]", "://::1"))
            or ".local" in u)


def is_safe_endpoint(url: str):
    """Anti-SSRF. Ritorna (ok, motivo). Consente endpoint locali espliciti
    (Ollama/LM Studio/.local) e https pubblici; BLOCCA https verso IP privati,
    loopback, link-local (169.254/16, metadata cloud), riservati. Risolve il
    DNS e valida ogni IP (difesa best-effort anche da DNS-rebind banale)."""
    import ipaddress, socket
    from urllib.parse import urlparse
    u = (url or "").strip()
    if not u:
        return False, "URL vuoto"
    if is_local_endpoint(u):
        return True, ""  # locale esplicito: ammesso (anche http)
    try:
        p = urlparse(u)
    except Exception:
        return False, "URL non valido"
    if p.scheme != "https":
        return False, "Per endpoint non locali è richiesto https://"
    host = p.hostname
    if not host:
        return False, "Host mancante nell'URL"
    try:
        infos = socket.getaddrinfo(host, p.port or 443, proto=socket.IPPROTO_TCP)
    except Exception as e:
        return False, f"Risoluzione host fallita: {e}"
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, f"IP non consentito ({ip}) per un endpoint pubblico"
    return True, ""

def is_configured():
    cfg = get_ai_config()
    # Serve un modello scelto dall'utente (nessun default preimpostato), più una
    # key oppure un endpoint locale (la key non serve in locale).
    return bool(cfg["model"]) and (bool(cfg["api_key"]) or is_local_endpoint(cfg["base_url"]))

# ── Chat persistence ──────────────────────────────────────────────
def save_chat_message(role, content, conversation_id=1):
    if not content:
        return
    conn = get_conn()
    conn.cursor().execute(
        "INSERT INTO chat_messages (ts, role, content, conversation_id) VALUES (?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), role, content, conversation_id),
    )
    conn.commit(); conn.close()

def load_chat_history(conversation_id=1, limit=200):
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT role, content FROM chat_messages WHERE conversation_id=? ORDER BY id ASC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def clear_chat_history(conversation_id=1):
    conn = get_conn()
    conn.cursor().execute("DELETE FROM chat_messages WHERE conversation_id=?", (conversation_id,))
    conn.commit(); conn.close()

def generate_daily_summary(day_iso):
    """Genera un riepilogo giornaliero via AI. day_iso = YYYY-MM-DD.
    Ritorna (ok: bool, content_or_error: str)."""
    try:
        client, model = _client()
    except Exception as e:
        return False, str(e)
    # Recupera attività della giornata
    try:
        ctx = _tool_list_by_date_range({"start": day_iso, "end": day_iso, "limit": 300})
    except Exception as e:
        return False, f"Errore fetch attività: {e}"
    if "Nessuna attività" in ctx:
        return False, "Nessuna attività registrata in quella data."
    system = (
        "Sei Déjà. Genera un diario sintetico di una giornata, basandoti sui ricordi forniti. "
        "Formato markdown:\n"
        "## Cose principali\n- (3-5 bullet)\n\n## Persone / temi ricorrenti\n- ...\n\n"
        "## Citazioni notevoli (audio)\n> \"...\" [au:ID]\n\n## Momenti salienti (screen)\n[ss:ID]\n\n"
        "Cita SEMPRE le fonti con [ss:ID]/[au:ID]. Tono colloquiale italiano, 2a persona."
    )
    import time as _t
    last_err = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Data: {day_iso}\n\nRicordi:\n{ctx}"},
                ],
                max_tokens=AI_MAX_TOKENS,
                temperature=0.5,
            )
            content = (resp.choices[0].message.content or "").strip()
            if content: return True, content
            last_err = "Risposta vuota"
        except Exception as e:
            last_err = str(e)
            # Retry solo su 5xx/timeout/connection
            err_s = last_err.lower()
            retryable = any(x in err_s for x in ("502", "503", "504", "timeout", "connection", "bad gateway"))
            if not retryable: break
            _t.sleep(2 ** attempt)  # 1s, 2s, 4s
    # Errore finale leggibile
    short = (last_err or "?")[:200]
    if "502" in short or "bad gateway" in short.lower():
        return False, "Endpoint AI temporaneamente giù (502). Riprova tra 1-2 min."
    if "401" in short:
        return False, "API key non valida. Verifica in Impostazioni AI."
    if "429" in short:
        return False, "Rate limit AI. Riprova tra qualche minuto."
    return False, f"Errore AI: {short}"

def save_daily_summary(day_iso, content):
    conn = get_conn()
    conn.cursor().execute(
        "INSERT OR REPLACE INTO daily_summaries (day_iso, content, ts_generated) VALUES (?, ?, ?)",
        (day_iso, content, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit(); conn.close()

def load_daily_summary(day_iso):
    conn = get_conn()
    row = conn.cursor().execute(
        "SELECT content, ts_generated FROM daily_summaries WHERE day_iso=?", (day_iso,)
    ).fetchone()
    conn.close()
    return {"content": row[0], "ts_generated": row[1]} if row else None

def list_daily_summaries():
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT day_iso, ts_generated, substr(content,1,120) FROM daily_summaries ORDER BY day_iso DESC"
    ).fetchall()
    conn.close()
    return [{"day_iso": r[0], "ts_generated": r[1], "preview": r[2]} for r in rows]

def list_models(base_url=None, api_key=None):
    """Interroga l'endpoint OpenAI-compatibile per i modelli disponibili.

    Usa GET /models (client.models.list()). Funziona con qualsiasi provider
    OpenAI-compatibile (Gonkagate, OpenRouter, OpenAI, Gemini openai-compat, ecc.).
    Se base_url/api_key non passati, usa quelli salvati in config AI.

    Ritorna (ok: bool, list[str] di model id  |  str messaggio errore).
    """
    try:
        from openai import OpenAI
    except ImportError:
        return False, "openai SDK non installato"
    cfg = get_ai_config()
    base = (base_url if base_url is not None else cfg["base_url"]).strip() or AI_BASE_URL_DEFAULT
    key  = (api_key  if api_key  is not None else cfg["api_key"]).strip()
    if not key:
        if is_local_endpoint(base):
            key = "local"  # endpoint locale: chiave non richiesta
        else:
            return False, "API key mancante"
    try:
        client = OpenAI(base_url=base, api_key=key)
        resp = client.models.list()
        ids = []
        for m in getattr(resp, "data", []) or []:
            mid = getattr(m, "id", None) or (m.get("id") if isinstance(m, dict) else None)
            if not mid:
                continue
            # Gemini openai-compat ritorna "models/gemini-..." → normalizza
            if mid.startswith("models/"):
                mid = mid[len("models/"):]
            ids.append(mid)
        ids = sorted(set(ids))
        return (True, ids) if ids else (False, "Nessun modello restituito dall'endpoint")
    except Exception as e:
        return False, str(e)[:200]

def test_connection():
    """Quick API ping. Returns (ok: bool, message: str)."""
    try:
        client, model = _client()
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

def _client():
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai SDK non installato. Esegui: pip install openai") from e
    cfg = get_ai_config()
    ok, why = is_safe_endpoint(cfg["base_url"])
    if not ok:
        raise RuntimeError(f"Endpoint AI non sicuro: {why}")
    key = cfg["api_key"]
    if not key:
        if is_local_endpoint(cfg["base_url"]):
            key = "local"  # endpoint locale: chiave fittizia (l'SDK la esige non vuota)
        else:
            raise RuntimeError("API key mancante. Configura in Impostazioni → AI.")
    try:
        print(f"[AI] client url={cfg['base_url']} model={cfg['model']} key={'set' if key else 'none'}")
    except Exception:
        pass
    return OpenAI(base_url=cfg["base_url"], api_key=key), cfg["model"]

# ── Tools ───────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_memories",
            "description": (
                "Cerca semanticamente nell'INTERO archivio storico dell'utente, su TRE fonti "
                "insieme: 1) screenshot OCR (cosa ha visto), 2) trascrizioni audio (cosa ha "
                "sentito/detto), 3) TRASCRIZIONI DI PAGINE WEB catturate dall'estensione browser "
                "(testo completo delle pagine visitate). Nessun limite temporale, copre tutto il "
                "database. Usa SEMPRE questo tool quando l'utente chiede di qualcosa che ha visto/"
                "letto/sentito/fatto online o no — incluso il CONTENUTO di una pagina/articolo/"
                "documento web (le pagine web hanno il testo PIENO, molto più ricco dell'OCR). "
                "Keyword corte e specifiche. Risultati ordinati per rilevanza, etichettati come "
                "'Screenshot' [ss:ID], 'Audio' [au:ID] o 'Pagina web' [web:ID]."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword o frase breve (es. 'casa nuova', 'gonka', 'errore python')"},
                    "limit": {"type": "integer", "description": "Max risultati (default 30, max 100)", "default": 30},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent",
            "description": (
                "Lista attività in finestra temporale RECENTE (ultime ore/giorni). "
                "Usa per 'cosa ho fatto oggi', 'ieri', 'stamattina'. "
                "Per cose più vecchie usa list_by_date_range o search_memories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "Finestra in ore. Max sensato: 168 (7 giorni). Per più indietro usa list_by_date_range.", "default": 24},
                    "kind":  {"type": "string", "enum": ["all", "screenshot", "audio"], "default": "all"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_by_date_range",
            "description": (
                "Lista screenshot/audio in un intervallo specifico — QUALSIASI periodo, anche "
                "mesi/anni fa. Usa per 'il mese scorso', 'a marzo', 'tra il 5 e il 10 aprile'. "
                "ACCETTA ANCHE L'ORA: passa un datetime ISO completo (YYYY-MM-DDTHH:MM:SS) per "
                "una FINESTRA PRECISA — fondamentale per 'cosa si sentiva MENTRE facevo X': "
                "trova prima l'orario di X, poi chiama qui con kind='audio' e quell'intervallo. "
                "Gli orari sono nello stesso formato dei timestamp restituiti dai tool (UTC), "
                "quindi riusa i ts che hai già visto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Inizio incluso: YYYY-MM-DD (giorno intero) oppure YYYY-MM-DDTHH:MM:SS (istante preciso)"},
                    "end":   {"type": "string", "description": "Fine inclusa: YYYY-MM-DD oppure YYYY-MM-DDTHH:MM:SS"},
                    "kind":  {"type": "string", "enum": ["all", "screenshot", "audio"], "default": "all", "description": "Usa 'audio' per le trascrizioni in una finestra."},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_system_events",
            "description": (
                "Eventi di AZIONI sul PC registrati da Déjà (NON screenshot/audio): app "
                "aperte/chiuse, app in primo piano, file creati/eliminati/spostati, programmi "
                "installati/disinstallati, unità USB, rete, sospensione/ripresa, blocco "
                "sessione, cambio orario, download, tab e pagine visitate.\n"
                "USA QUESTO (non gli screenshot) per QUALSIASI domanda su quando/quante volte "
                "l'utente ha aperto/chiuso/usato un'app o un file, cosa ha scaricato/installato, "
                "ecc. Esempi: 'a che ora ho aperto e chiuso Chrome?' → category='process', "
                "subject='chrome' (vedrai le righe action=start e action=stop con l'orario); "
                "'quante volte ho aperto Spotify oggi?' → category='process', action='start', "
                "subject='spotify'; 'qual è la PRIMA volta che ho aperto X?' → subject='X', "
                "order='asc', limit piccolo.\n"
                "FILTRA con subject invece di scorrere lunghe liste. NOTA: la cattura eventi è "
                "opzionale e OFF di default — se non trovi nulla, l'utente potrebbe non averla "
                "attivata in Impostazioni → Eventi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "Finestra recente in ore (alternativa a start/end). Default 24.", "default": 24},
                    "start": {"type": "string", "description": "Data inizio inclusa YYYY-MM-DD (prevale su hours). Usa la data ODIERNA fornita per calcolare 'oggi'/'ieri'."},
                    "end":   {"type": "string", "description": "Data fine inclusa YYYY-MM-DD (opzionale; se assente = stessa di start)"},
                    "category": {"type": "string",
                                 "description": "Filtro categoria. Per app aperte/chiuse usa 'process'.",
                                 "enum": ["all", "process", "focus", "file", "install", "clock",
                                          "power", "session", "device", "network",
                                          "download", "tab", "visit"],
                                 "default": "all"},
                    "subject": {"type": "string", "description": "Filtro testo su nome app/file/URL (match parziale). ES: 'chrome', 'fattura.pdf'. È il modo MIGLIORE per trovare l'evento giusto."},
                    "action": {"type": "string", "description": "Filtro azione esatta: per i processi 'start' (apertura) o 'stop' (chiusura); per i file 'created'/'deleted'/'moved'; per i download 'started'/'completed'."},
                    "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc", "description": "'asc' = dal più vecchio (per 'prima volta che…'), 'desc' = più recente prima (default)."},
                    "include_hidden": {"type": "boolean", "default": False, "description": "Includere processi background/sistema/Déjà (di solito NO)."},
                    "limit": {"type": "integer", "default": 100, "description": "Max risultati (max 500). Con un buon subject ne bastano pochi."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_stats",
            "description": (
                "Mostra estensione totale dell'archivio: data del primo e ultimo "
                "screenshot/audio, conteggio totale. Usa per capire SE l'utente "
                "ha dati per un certo periodo, prima di dire 'non ho dati'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

# Prezzi/valute: usate per centrare lo snippet quando la domanda è "quanto costa".
_PRICE_RE = re.compile(
    r"(?:€|£|\$|usd|eur|gbp)\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:€|£|\$|euro?|eur|usd|gbp|dollar[io]?)\b",
    re.I,
)
# Parole che segnalano intento "prezzo" nella domanda → includi sempre i prezzi.
_PRICE_INTENT = ("prezzo", "prezzi", "costa", "costo", "costato", "speso", "spesa",
                 "pagato", "pagare", "totale", "quanto", "euro", "price", "cost", "paid")


def _best_snippets(text, query, max_chars=700):
    """Estrae le finestre di testo PIÙ RILEVANTI (attorno ai termini della query
    e ai prezzi) invece di troncare dall'inizio. Così un dettaglio a metà pagina
    — es. il prezzo di un prodotto — raggiunge davvero il modello, e si inviano
    meno token inutili (header/menu)."""
    text = (text or "").strip()
    if not text or not query:
        return text[:max_chars]
    if len(text) <= max_chars:
        return text
    low = text.lower()
    terms = [t for t in re.split(r"[^\w]+", query.lower()) if len(t) >= 3]

    hits = []
    for t in set(terms):
        start = 0
        while len(hits) < 60:
            i = low.find(t, start)
            if i < 0:
                break
            hits.append(i)
            start = i + len(t)
    # I prezzi sono quasi sempre il dato cercato: includili (specie se intento prezzo).
    for m in _PRICE_RE.finditer(text):
        hits.append(m.start())
        if len(hits) > 120:
            break
    if not hits:
        return text[:max_chars]

    win = 280
    hits.sort()
    windows = []
    for h in hits:
        s = max(0, h - win // 3); e = min(len(text), h + win)
        if windows and s <= windows[-1][1] + 50:
            windows[-1][1] = max(windows[-1][1], e)
        else:
            windows.append([s, e])

    # Se la domanda è sui prezzi, emetti per prime le finestre che contengono un
    # prezzo: così, anche con budget stretto, l'importo non viene mai tagliato.
    if any(w in query.lower() for w in _PRICE_INTENT):
        windows.sort(key=lambda se: 0 if _PRICE_RE.search(text[se[0]:se[1]]) else 1)

    parts, used = [], 0
    for s, e in windows:
        if used >= max_chars:
            break
        seg = text[s:e].strip()
        if used + len(seg) > max_chars:
            seg = seg[: max(0, max_chars - used)]
        if seg:
            parts.append(("…" if s > 0 else "") + seg + ("…" if e < len(text) else ""))
            used += len(seg)
    return " ".join(parts) if parts else text[:max_chars]


def _fmt_results(results, query=None, max_chars=700, web_max_chars=1700):
    if not results:
        return "Nessun ricordo trovato."
    out = []
    for r in results:
        ts = r["ts"][:19].replace("T", " ")
        t = r.get("type")
        if t == "screenshot":
            body = _best_snippets(r.get("text"), query, max_chars)
            ref = f"[ss:{r['id']}]"
            out.append(f"{ref} Screenshot @ {ts} | App: {r.get('app','?')}\n{body}")
        elif t == "web":
            # Pagina web catturata dall'estensione: testo PIENO. Budget più alto
            # + snippet centrati così il dettaglio (prezzo, dato) non viene tagliato.
            body = _best_snippets(r.get("text"), query, web_max_chars)
            title = (r.get("title") or "").strip()
            url = (r.get("url") or "").strip()
            ref = f"[web:{r['id']}]"
            head = f"{ref} Pagina web @ {ts} | {title or r.get('domain','')}"
            if url:
                head += f" | {url}"
            out.append(f"{head}\n{body}")
        else:
            body = _best_snippets(r.get("transcript"), query, max_chars)
            src = ("microfono (voce utente)" if r.get("source") == "mic"
                   else "audio di sistema (altoparlanti: altri o media)")
            ref = f"[au:{r['id']}]"
            out.append(f"{ref} Audio @ {ts} | Sorgente: {src}\n{body}")
    return "\n\n---\n\n".join(out)

def _tool_search_memories(args):
    q = str(args.get("query", "") or "").strip()
    limit = min(max(1, _safe_int(args.get("limit"), 30)), 100)
    if not q:
        return "Query vuota."
    try:
        results = search_module.query(q, top_k=limit)
    except Exception as e:
        return f"Errore ricerca: {e}"
    if not results:
        return f"Nessun ricordo trovato per '{q}' in INTERO archivio."

    # query() ritorna screenshot + audio + web (web IN CODA). Un naive
    # results[:limit] poteva buttar fuori le pagine web (testo PIENO, la fonte
    # migliore per il contenuto letto online). Ordina GLOBALMENTE per
    # rilevanza, poi garantisci la presenza di qualche pagina web se esiste.
    def _rank(r):
        return (not r.get("exact", False), -float(r.get("score", 0) or 0),
                -search_module._ts_int(r.get("ts", "")))
    results.sort(key=_rank)
    top = results[:limit]
    web_all = [r for r in results if r.get("type") == "web"]
    if web_all and not any(r.get("type") == "web" for r in top):
        # Riserva gli ultimi slot alle migliori pagine web rimaste fuori.
        reserve = min(3, limit, len(web_all))
        top = top[: max(1, limit - reserve)] + web_all[:reserve]
    return _fmt_results(top, query=q)

def _tool_list_recent(args):
    hours = max(1, _safe_int(args.get("hours"), 24))
    kind  = str(args.get("kind", "all") or "all")
    if kind not in ("all", "screenshot", "audio"): kind = "all"
    limit = min(max(1, _safe_int(args.get("limit"), 50)), 200)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = get_conn(); c = conn.cursor()
    lines = []
    if kind in ("all", "screenshot"):
        for row in c.execute(
            "SELECT id, ts, app, text FROM screenshots WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (cutoff, limit),
        ):
            txt = (row[3] or "").strip().replace("\n", " ")[:200]
            lines.append(f"[ss:{row[0]}] {row[1][:19]} | {row[2] or '?'}: {txt}")
    if kind in ("all", "audio"):
        for row in c.execute(
            "SELECT id, ts, source, transcript FROM audio_segments WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (cutoff, limit),
        ):
            txt = (row[3] or "").strip().replace("\n", " ")[:200]
            lines.append(f"[au:{row[0]}] {row[1][:19]} | {_audio_src_label(row[2])}: {txt}")
    conn.close()
    return "\n".join(lines) if lines else f"Nessuna attività nelle ultime {hours}h."

def _norm_bound(v, is_end):
    """Normalizza un estremo del range: 'YYYY-MM-DD' → giorno intero; un ISO con
    'T' → istante preciso (finestra fine). Aggiunge TZ UTC se assente."""
    v = (v or "").strip()
    if "T" in v:
        if "+" not in v and "Z" not in v[10:]:
            v += "+00:00"
        return v
    return v + ("T23:59:59+00:00" if is_end else "T00:00:00+00:00")


def _audio_src_label(source):
    # mic = voce dell'utente; system = altoparlanti (altra persona OPPURE media)
    return "microfono(utente)" if source == "mic" else "sistema(altoparlanti)"


def _tool_list_by_date_range(args):
    start = str(args.get("start") or "").strip()
    end   = str(args.get("end")   or "").strip()
    kind  = str(args.get("kind", "all") or "all")
    if kind not in ("all", "screenshot", "audio"): kind = "all"
    limit = min(max(1, _safe_int(args.get("limit"), 100)), 500)
    if not start or not end:
        return "Parametri 'start' e 'end' richiesti (YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS)."
    start_iso = _norm_bound(start, is_end=False)
    end_iso   = _norm_bound(end, is_end=True)
    conn = get_conn(); c = conn.cursor()
    lines = []
    ss_n = au_n = 0
    if kind in ("all", "screenshot"):
        for row in c.execute(
            "SELECT id, ts, app, text FROM screenshots WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT ?",
            (start_iso, end_iso, limit),
        ):
            ss_n += 1
            txt = (row[3] or "").strip().replace("\n", " ")[:200]
            lines.append(f"[ss:{row[0]}] {row[1][:19]} | {row[2] or '?'}: {txt}")
    if kind in ("all", "audio"):
        for row in c.execute(
            "SELECT id, ts, source, transcript FROM audio_segments WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT ?",
            (start_iso, end_iso, limit),
        ):
            au_n += 1
            txt = (row[3] or "").strip().replace("\n", " ")[:200]
            lines.append(f"[au:{row[0]}] {row[1][:19]} | {_audio_src_label(row[2])}: {txt}")
    conn.close()
    if not lines:
        return f"Nessuna attività tra {start} e {end}."
    out = "\n".join(lines)
    # Avviso troncamento: i risultati sono i PIÙ RECENTI del periodo; se hit del
    # limite, ci sono altri dati più vecchi non mostrati → il modello deve
    # restringere (es. a un solo giorno) invece di concludere "non c'è nulla".
    if ss_n >= limit or au_n >= limit:
        out += (f"\n\n[NB: risultati TRONCATI a {limit} (solo i più recenti del periodo). "
                "Ci sono altri dati più vecchi non mostrati: restringi a un giorno/finestra più "
                "piccola o alza 'limit' per vederli.]")
    return out

def _tool_list_system_events(args):
    cats = ("process", "focus", "file", "install", "clock", "power", "session",
            "device", "network", "download", "tab", "visit")
    cat = str(args.get("category", "all") or "all").strip().lower()
    if cat not in cats: cat = "all"
    limit = min(max(1, _safe_int(args.get("limit"), 100)), 500)
    subject = str(args.get("subject") or "").strip()
    action = str(args.get("action") or "").strip().lower()
    order = "ASC" if str(args.get("order") or "desc").strip().lower() == "asc" else "DESC"
    include_hidden = bool(args.get("include_hidden"))
    start = str(args.get("start") or "").strip()
    end   = str(args.get("end") or "").strip()
    if start:
        start_iso = start + "T00:00:00+00:00"
        end_iso = (end or start) + "T23:59:59+00:00"
    else:
        hours = max(1, _safe_int(args.get("hours"), 24))
        start_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        end_iso = "9999"
    conn = get_conn(); c = conn.cursor()
    # Di default esclude i processi background/sistema/Déjà (hidden=1): l'utente
    # chiede cosa HA FATTO, non il rumore di servizi e helper interni.
    sql = "SELECT id, ts, source, category, action, subject, text FROM system_events WHERE ts >= ? AND ts <= ?"
    params = [start_iso, end_iso]
    if not include_hidden:
        sql += " AND hidden = 0"
    if cat != "all":
        sql += " AND category = ?"; params.append(cat)
    if action:
        sql += " AND LOWER(action) = ?"; params.append(action)
    if subject:
        # match su subject (exe/path/url) E sul testo leggibile → trova l'app
        # giusta senza dover scorrere centinaia di righe.
        like = f"%{subject}%"
        sql += " AND (subject LIKE ? OR text LIKE ?)"; params.extend([like, like])
    # ASC = dal più vecchio (per 'prima volta che…'); DESC = più recente prima.
    sql += f" ORDER BY ts {order} LIMIT ?"; params.append(limit)
    lines = []
    for row in c.execute(sql, params):
        subj = (row[5] or "").strip().replace("\n", " ")[:120]
        txt = (row[6] or "").strip().replace("\n", " ")[:200]
        lines.append(f"{row[1][:19]} | {row[3]}/{row[4]}: {txt}" + (f" ({subj})" if subj and subj not in txt else ""))
    conn.close()
    if lines:
        hdr = f"{len(lines)} eventi (ordine {'crescente' if order == 'ASC' else 'decrescente'} per data):\n"
        return hdr + "\n".join(lines)
    msg = "Nessun evento corrisponde ai filtri"
    if subject:
        msg += f" (subject~'{subject}')"
    msg += (". Se la categoria eventi non è mai stata attivata in Impostazioni → "
            "Eventi, NON ci sono dati: avvisa l'utente invece di insistere. "
            "Altrimenti prova ad allargare il periodo o togliere il filtro subject.")
    return msg

def _tool_memory_stats(_args):
    conn = get_conn(); c = conn.cursor()
    ss_total = c.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
    au_total = c.execute("SELECT COUNT(*) FROM audio_segments").fetchone()[0]
    ss_first = c.execute("SELECT MIN(ts), MAX(ts) FROM screenshots").fetchone()
    au_first = c.execute("SELECT MIN(ts), MAX(ts) FROM audio_segments").fetchone()
    conn.close()
    out = [
        f"Screenshot: {ss_total} totali",
        f"  primo: {(ss_first[0] or 'n/a')[:19]}",
        f"  ultimo: {(ss_first[1] or 'n/a')[:19]}",
        f"Audio: {au_total} segmenti",
        f"  primo: {(au_first[0] or 'n/a')[:19]}",
        f"  ultimo: {(au_first[1] or 'n/a')[:19]}",
    ]
    return "\n".join(out)

def _safe_int(v, default):
    try:
        if isinstance(v, bool): return default
        return int(v)
    except (ValueError, TypeError):
        return default

def _execute_tool(name, args):
    try:
        if not isinstance(args, dict):
            args = {}
        # Match tollerante: alcuni modelli (es. MiniMax) storpiano il nome con
        # maiuscole/underscore diversi ('list_By_Date_Range', 'list_ystem_events').
        # Normalizza a minuscolo senza separatori e mappa al tool reale.
        norm = "".join(ch for ch in (name or "").lower() if ch.isalnum())
        dispatch = {
            "searchmemories":   _tool_search_memories,
            "listrecent":       _tool_list_recent,
            "listbydaterange":  _tool_list_by_date_range,
            "listsystemevents": _tool_list_system_events,
            "memorystats":      _tool_memory_stats,
        }
        fn = dispatch.get(norm)
        if fn is not None:
            return fn(args)
        # fuzzy: nome storpiato/typo (es. 'listystemevents') → match più vicino
        import difflib
        m = difflib.get_close_matches(norm, list(dispatch.keys()), n=1, cutoff=0.72)
        if m:
            return dispatch[m[0]](args)
        return f"Tool sconosciuto: {name}"
    except Exception as e:
        return f"Errore esecuzione tool {name}: {e}"

# ── Context window management ──────────────────────────────────────
def _approx_tokens(messages):
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += len(content) // 4
        for tc in m.get("tool_calls") or []:
            total += len(json.dumps(tc)) // 4
    return total

def _trim_history(messages, max_tokens):
    if _approx_tokens(messages) <= max_tokens:
        return messages
    head = [messages[0]] if messages and messages[0].get("role") == "system" else []
    tail = messages[len(head):]
    while tail and _approx_tokens(head + tail) > max_tokens:
        tail.pop(0)
    return head + tail

# ── Streaming chat with tool calls ─────────────────────────────────
SYSTEM_PROMPT = (
    "Sei Déjà, assistente AI personale dell'utente.\n\n"
    "════ REGOLA #0 — NON INVENTARE MAI (la più importante) ════\n"
    "Tu NON hai memoria delle attività dell'utente: la conosci SOLO attraverso i risultati "
    "dei tool. Quindi:\n"
    "• È ASSOLUTAMENTE VIETATO produrre riassunti, elenchi, frasi citate, nomi, prezzi, "
    "quantità, orari, titoli o QUALSIASI dettaglio concreto che non sia LETTERALMENTE presente "
    "in un risultato di tool appena ricevuto. Niente esempi plausibili, niente 'tipicamente', "
    "niente riempire i vuoti.\n"
    "• Per OGNI domanda su ricordi/conversazioni/attività/contenuti DEVI prima chiamare un "
    "tool e aspettarne il risultato. Se non hai (ancora) chiamato un tool, NON rispondere nel "
    "merito: chiama il tool. Mai rispondere 'a memoria' o per intuizione.\n"
    "• Se i tool non restituiscono nulla, o restituiscono poco, DILLO chiaramente "
    "('Non ho trovato registrazioni per ieri') invece di inventare. Una risposta vuota onesta "
    "è SEMPRE meglio di una inventata. Mai abbellire o estrapolare oltre il testo grezzo.\n"
    "• Riporta i contenuti il più possibile VERBATIM dai risultati (con i tag [ss:ID]/[au:ID]). "
    "Se un dato non c'è nel testo del tool, NON esiste per te.\n"
    "═══════════════════════════════════════════════════════════\n\n"
    "Hai accesso COMPLETO e SENZA LIMITI TEMPORALI alla sua memoria digitale:\n"
    "- screenshot con OCR (testo estratto da ogni schermata) → cosa ha VISTO/letto\n"
    "- trascrizioni audio (microfono + audio sistema) → cosa ha SENTITO/detto\n"
    "- eventi di sistema/browser → le AZIONI sul PC (app aperte/chiuse, file, programmi "
    "installati, USB, rete, standby, blocco sessione, download, tab, pagine visitate)\n"
    "L'archivio copre TUTTO lo storico — può estendersi a mesi o anni. "
    "NON ASSUMERE MAI un limite temporale arbitrario (es. '7 giorni'). "
    "Se non sai quanto in là va l'archivio, chiama 'memory_stats'.\n\n"
    "TOOL DISPONIBILI:\n"
    "- 'search_memories(query, limit)' → ricerca semantica+esatta su screenshot+audio, "
    "INTERO database, nessun filtro temporale. Per domande sul CONTENUTO (cosa ho letto/"
    "visto/detto su un tema), anche vecchio.\n"
    "- 'list_recent(hours, kind)' → screenshot/audio nelle ultime ore (max 168=7gg).\n"
    "- 'list_by_date_range(start, end, kind)' → screenshot/audio in un range di date.\n"
    "- 'list_system_events(category, subject, action, order, start/end|hours)' → AZIONI sul "
    "PC. Usa SEMPRE questo (NON gli screenshot) per: quando/quante volte ho aperto o chiuso "
    "un'app, cosa ho scaricato, quando ho installato/disinstallato qualcosa, file creati/"
    "cancellati, USB collegata, quando ho bloccato il PC, ecc. Filtra con subject (nome app/"
    "file) e action (start=apertura, stop=chiusura).\n"
    "- 'memory_stats()' → estensione totale archivio (date primo/ultimo screen+audio).\n\n"
    "INSTRADAMENTO (scegli il tool giusto PRIMA di rispondere):\n"
    "• 'a che ora ho aperto/chiuso X', 'quante volte ho usato X', 'che app ho aperto', "
    "'cosa ho scaricato/installato', 'quando ho collegato la chiavetta' → list_system_events "
    "(category='process' per app; subject=nome). NON cercare negli screenshot per queste cose: "
    "lì NON c'è l'orario di apertura/chiusura.\n"
    "• 'cosa diceva quella pagina/quel articolo che leggevo', 'dov'è che ho letto X', "
    "'riassumi la pagina su Y', 'di cosa parlavo' → search_memories. Le PAGINE WEB visitate "
    "sono salvate col TESTO COMPLETO (estensione browser): per il contenuto di ciò che l'utente "
    "leggeva online sono la fonte migliore, molto più dell'OCR. Non ignorarle: se tra i risultati "
    "ci sono righe 'Pagina web [web:ID]', USALE e citale.\n"
    "• 'quanto ho speso/pagato per X', 'che prezzo aveva X', 'quanto costa la cosa che ho visto' → "
    "search_memories col NOME del prodotto (es. 'sedia ergonomica'). Prezzi, totali e dettagli "
    "d'acquisto stanno nelle PAGINE WEB catturate (a volte negli screenshot del checkout): lo "
    "snippet del tool è centrato sul prezzo — leggilo e riporta l'importo ESATTO col tag "
    "[web:ID]/[ss:ID]. Se in una pagina ci sono più prezzi, scegli quello del prodotto giusto e "
    "dillo; non sommare/indovinare.\n\n"
    "AUDIO — due sorgenti, significato diverso:\n"
    "• 'microfono (voce utente)' = sta parlando L'UTENTE (o chi gli sta accanto fisicamente).\n"
    "• 'audio di sistema (altoparlanti)' = ciò che usciva dalle casse: può essere un'ALTRA "
    "persona (es. in chiamata/gioco online) MA ANCHE un video YouTube, musica, audio di gioco. "
    "NON dare per scontato che sia una conversazione: capiscilo dal contenuto della trascrizione "
    "e dagli screenshot vicini (es. se la finestra era YouTube → è un video, non un dialogo). "
    "Quando riferisci, distingui: 'tu dicevi…' (microfono) vs 'dalle casse/nel video si sentiva…' "
    "(sistema), e dì se sembra dialogo o media.\n\n"
    "DOMANDE 'cosa si diceva / di che si parlava MENTRE facevo X' (es. 'mentre giocavo ad Apex'):\n"
    "L'audio quasi MAI contiene il nome del gioco/app, quindi cercare 'apex' tra le trascrizioni "
    "fallisce — NON concludere 'non c'è audio'. Procedi a due passi:\n"
    "  1) Trova QUANDO l'utente faceva X: list_system_events(category='process', subject='X') per "
    "gli orari apri/chiudi, oppure search_memories('X') per gli screenshot (leggine i timestamp).\n"
    "  2) Prendi l'AUDIO di quella finestra: list_by_date_range(start, end, kind='audio') passando "
    "l'intervallo trovato CON l'ora (es. start='2026-06-10T20:10:00', end='2026-06-10T21:00:00').\n"
    "  3) Riassumi le trascrizioni in quella finestra, distinguendo microfono vs sistema.\n\n"
    "REGOLE:\n"
    "1. DATE: usa la DATA ODIERNA indicata sotto come riferimento per 'oggi/ieri/questa "
    "settimana'. 'oggi' = la data odierna; 'ieri' = il giorno PRIMA; calcola i range da lì. "
    "Per UN SOLO giorno (ieri, oggi, una data precisa) metti lo STESSO valore in start E end "
    "(es. ieri → start='2026-06-10', end='2026-06-10'): NON mettere il giorno dopo in end, o "
    "includi giorni sbagliati. Se un tool risponde 'troncato', i risultati sono solo i più "
    "recenti del periodo: RESTRINGI a un giorno/intervallo più piccolo (NON concludere 'non ci "
    "sono dati' solo perché vedi un altro giorno). In dubbio sull'estensione dati → memory_stats.\n"
    "2. Se utente chiede di cose vecchie → usa il tool con un range date adatto. MAI dire "
    "'ho solo gli ultimi N giorni'. Prima di dire 'non ho dati per il periodo X' → VERIFICA "
    "con memory_stats (o list_system_events allargando il periodo).\n"
    "3. NON sfidarti dei primi 100 risultati a caso: se cerchi una cosa specifica RESTRINGI "
    "(subject, action, category, range di date) invece di scorrere liste lunghe. Per 'la PRIMA "
    "volta' usa order='asc'; per 'l'ultima/più recente' order='desc'. Se un tool tronca i "
    "risultati e non trovi ciò che serve, rifai la chiamata con filtri più stretti o un "
    "periodo diverso, NON arrenderti al primo tentativo.\n"
    "4. Combina più chiamate se serve (es. per 'aperto e poi chiuso Chrome' una con "
    "action='start' e una con action='stop', o una sola e leggi entrambe le righe). MA non "
    "ripetere la STESSA chiamata con argomenti quasi identici: se un tool torna VUOTO, CAMBIA "
    "approccio (altra fonte, altro filtro, altro periodo), non riprovarlo uguale. Hai poche "
    "chiamate a disposizione: usale bene. Per 'di cosa parlavo mentre facevo X', se gli eventi "
    "non danno l'orario (cattura magari OFF in quel periodo), passa SUBITO a search_memories('X') "
    "sugli screenshot per trovare la finestra, poi list_by_date_range(kind='audio').\n"
    "5. Cita timestamp e app/sorgente nelle risposte.\n"
    "6. **CITAZIONI FONTI**: per fatti presi da uno SCREENSHOT, AUDIO o PAGINA WEB inserisci "
    "subito dopo la frase il tag `[ss:ID]`, `[au:ID]` o `[web:ID]` (ID esatto dal tool); l'UI li "
    "rende card cliccabili (la card web apre l'URL). Per gli eventi di sistema NON usare tag: "
    "cita solo l'orario in chiaro.\n"
    "7. Rispondi sempre in italiano, conciso. Se davvero non trovi nulla dopo aver provato "
    "filtri/keyword diversi, dillo — e se è una domanda da eventi e non trovi nulla, ricorda "
    "che la cattura eventi è OFF di default e va attivata in Impostazioni → Eventi.\n"
    "8. STILE OUTPUT: scrivi SOLO la risposta finale, pulita e diretta. NON mostrare il tuo "
    "ragionamento passo-passo, NON scrivere meta-frasi tipo 'vedo che…', 'devo controllare…', "
    "'sembra che…'. MAI ripetere la stessa frase. Usa pochi bullet brevi quando aiuta. Quando "
    "riassumi tante trascrizioni, raggruppa per tema/momento in 3-6 punti, non elencare ogni "
    "frammento."
)


def _now_context() -> str:
    """Ancora temporale iniettata nel system prompt: senza una 'data odierna'
    esplicita il modello sbaglia i range (oggi/ieri/settimana scorsa)."""
    try:
        now = datetime.now().astimezone()
        giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
        return (f"\n\nDATA ODIERNA: {giorni[now.weekday()]} {now.strftime('%Y-%m-%d')}, "
                f"ora locale {now.strftime('%H:%M')}. Usala per ogni calcolo di date.")
    except Exception:
        return ""

def _complete(client, model, messages, max_tokens, temperature=0.3):
    """Chiamata non-streaming con retry su errori transitori. Ritorna testo."""
    last = None
    for attempt in range(3):
        try:
            r = client.chat.completions.create(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temperature,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            last = str(e); s = last.lower()
            retryable = any(x in s for x in ("429", "500", "502", "503", "504",
                                             "timeout", "connection", "overloaded", "bad gateway"))
            if not retryable:
                break
            _time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last or "call failed")


# "Niente trovato" robusto: i worker a volte rispondono in modo verboso invece
# del sentinel esatto 'NIENTE' → senza questo finivano tra i "findings" e
# avvelenavano la sintesi (che poi rispondeva 'NIENTE').
_NOTHING_RE = re.compile(
    r"\b(niente|nessun\w*|non ho trovato|non risult\w*|nulla di (?:pertinente|rilevante|utile)|"
    r"non c'?è nulla|no relevant|nothing (?:relevant|found))\b", re.I)


def _is_nothing(txt: str) -> bool:
    t = (txt or "").strip()
    if not t or t.upper() == "NIENTE":
        return True
    # Risposta breve che dice in sostanza "non ho trovato".
    return len(t) <= 100 and bool(_NOTHING_RE.search(t))


def _recent_history_text(history, n=6, max_chars=1400):
    msgs = [m for m in (history or [])
            if m.get("role") in ("user", "assistant") and m.get("content")][-n:]
    lines = []
    for m in msgs:
        who = "Utente" if m["role"] == "user" else "Assistente"
        lines.append(f"{who}: {str(m['content']).strip().replace(chr(10), ' ')[:300]}")
    return "\n".join(lines)[-max_chars:]


# Rilevatore deterministico di domande temporali/conversazione: NON ci si può
# fidare solo del router LLM (a volte non mette recent_hours → la telefonata non
# viene mai recuperata). Questi pattern forzano una finestra temporale.
_CONV_RE = re.compile(
    r"\b(telefonat\w*|chiamat\w*|conversazion\w*|call|riunion\w*|meeting|"
    r"videochiamat\w*|parlat\w*|detto|sentit\w*|discuss\w*|intervist\w*)\b", re.I)
_RECENT_RE = re.compile(
    r"\b(di prima|poco fa|prima|poc'?anzi|appena|adesso|or ora|stamattina|stamani|"
    r"oggi|earlier|just now|recenttemente|di recente)\b", re.I)
_YESTERDAY_RE = re.compile(r"\bieri\b|\byesterday\b", re.I)


def _infer_recent_hours(message: str) -> int:
    m = (message or "").lower()
    if _YESTERDAY_RE.search(m):
        return 48
    if _RECENT_RE.search(m) or _CONV_RE.search(m):
        return 24
    return 0


def _route_and_plan(client, model, history, message):
    """ROUTER: decide se serve cercare nei ricordi e, se sì, in quanti angoli.
    Ritorna {"search": bool, "queries": [...]}. Risolve i follow-up col contesto.
    Così gli agenti partono SOLO quando ha senso (no chiacchiera/saluti/scuse)."""
    hist = _recent_history_text(history)
    sys = (
        "Sei il ROUTER di un assistente con memoria personale dell'utente "
        "(screenshot OCR, audio, pagine web visitate). Decidi se per rispondere "
        "all'ultimo messaggio SERVE cercare nei ricordi.\n"
        "• search=false → chiacchiera, saluti, ringraziamenti, scuse ('ok scusa'), "
        "meta-commenti, o domande di pura conoscenza generale/ragionamento che NON "
        "riguardano ciò che l'utente ha visto/fatto/letto/sentito.\n"
        "• search=true → riguarda attività, contenuti, prezzi, pagine, acquisti, cose "
        "viste o sentite dall'utente (ANCHE i follow-up: usa il contesto per il tema).\n"
        "Se search=true genera 2-6 query BREVI, DIVERSE tra loro, e RISOLVI i "
        "riferimenti col contesto (es. 'altre alternative' → l'argomento dei messaggi "
        "precedenti, tipo il prodotto o l'auto).\n"
        "ESPANDI bene la ricerca, non limitarti alle parole della domanda:\n"
        "  – includi SINONIMI e termini correlati;\n"
        "  – soprattutto le FRASI/parole che la persona avrebbe REALMENTE detto o "
        "scritto, non l'etichetta astratta. Es. per 'a che ora arriva il tecnico?' → "
        "['tecnico', 'appuntamento', 'intervento', 'verso le', 'ti aspetto alle', "
        "'passo alle', 'fascia oraria', 'tra le e le']. Pensa a COME comparirebbe nel "
        "parlato o nel testo reale (orari, conferme, modi di dire), così trovi la "
        "risposta anche quando il ricordo non nomina esplicitamente l'argomento.\n"
        "Se search=false → queries vuoto.\n"
        "• recent_hours → se la domanda riguarda qualcosa di RECENTE/temporale "
        "('di prima', 'poco fa', 'appena', 'prima', 'stamattina', 'oggi' → 24; "
        "'ieri' → 48; 'questa settimana' → 168), metti le ore da guardare indietro. "
        "IMPORTANTE per cose come telefonate/conversazioni/video di cui il contenuto "
        "NON contiene la keyword (es. 'la chiamata con Wind3' non dice 'wind3' nel "
        "parlato): in quei casi imposta recent_hours per recuperare l'audio recente. "
        "0 se non temporale.\n"
        'Rispondi SOLO con JSON: {"search": true/false, "queries": ["..."], "recent_hours": 0}'
    )
    user = (f"Storico recente:\n{hist}\n\n" if hist else "") + f"Ultimo messaggio: {message}"
    try:
        raw = _complete(client, model,
                        [{"role": "system", "content": sys},
                         {"role": "user", "content": user}],
                        max_tokens=240, temperature=0.2)
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0) if m else raw)
        search = bool(data.get("search", True))
        qs = [str(q).strip() for q in (data.get("queries") or []) if str(q).strip()]
        recent_hours = _safe_int(data.get("recent_hours"), 0)
    except Exception:
        search, qs, recent_hours = True, [message], 0  # in dubbio, cerca
    if search and not qs:
        qs = [message]
    # Rete deterministica: se il router non ha colto la temporalità ma il
    # messaggio parla di una telefonata/conversazione/'di prima', forziamo una
    # finestra così l'audio recente entra nel pool.
    if search:
        recent_hours = max(recent_hours, _infer_recent_hours(message))
    recent_hours = max(0, min(recent_hours, 24 * 14))  # tetto 2 settimane
    out, seen = [], set()
    for q in qs:
        k = q.lower()
        if k not in seen:
            seen.add(k); out.append(q)
    return {"search": search, "queries": out[:AGENTIC_MAX_SUBQUERIES], "recent_hours": recent_hours}


def _converse_stream(client, model, history, message):
    """Risposta conversazionale (niente agenti/ricerca) quando il router decide
    che non serve cercare nei ricordi. Stesso protocollo di chat_stream."""
    lang = i18n.ai_language_name()
    sys = (
        "Sei Déjà, assistente personale dell'utente. Rispondi in modo naturale, "
        "amichevole e conciso. Questo messaggio NON richiede di cercare nei ricordi. "
        "Non inventare fatti sull'utente; se servisse un dato dai ricordi che non hai, "
        f"dillo e invita a riformulare. Rispondi in {lang}." + _now_context()
    )
    messages = ([{"role": "system", "content": sys}] + list(history)
                + [{"role": "user", "content": message}])
    messages = _trim_history(messages, AI_CONTEXT_TOKENS - AI_MAX_TOKENS - 2000)
    try:
        stream = client.chat.completions.create(
            model=model, messages=messages, stream=True,
            max_tokens=AI_MAX_TOKENS, temperature=0.5,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            d = chunk.choices[0].delta
            if d and getattr(d, "content", None):
                yield ("text", d.content)
    except Exception as e:
        yield ("error", f"Errore: {e}")
    yield ("done", None)


def _is_deja_ui(r) -> bool:
    """True se il ricordo è la UI di Déjà stessa (es. la finestra chat dove
    l'utente ha DIGITATO la domanda). Va escluso dal pool: altrimenti la keyword
    'wind3' matcha lo screenshot della chat e il modello risponde 'hai chiesto di
    riassumere…' invece di trovare la telefonata vera."""
    if r.get("type") != "screenshot":
        return False
    app = str(r.get("app") or "").lower()
    return "déj" in app or "deja" in app


def _recent_pool(hours, limit=30):
    """Audio + screenshot delle ultime `hours` ore (newest first). Serve per le
    domande temporali su contenuti SENZA keyword nel testo (es. 'la telefonata
    con Wind3 di prima': il parlato non contiene 'wind3' → la keyword search
    fallisce, ma l'audio recente sì)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, hours))).isoformat()
    out = []
    try:
        conn = get_conn(); c = conn.cursor()
        for row in c.execute(
            "SELECT id, ts, source, transcript FROM audio_segments "
            "WHERE ts>=? AND transcript IS NOT NULL AND transcript != '' "
            "ORDER BY ts DESC LIMIT ?", (cutoff, limit)):
            out.append({"type": "audio", "id": row[0], "ts": row[1], "source": row[2],
                        "transcript": row[3], "text": row[3], "score": 0.55, "exact": False,
                        "app": "🎙️ " + ("Microfono" if row[2] == "mic" else "Sistema")})
        for row in c.execute(
            "SELECT id, ts, app, text FROM screenshots WHERE ts>=? "
            "ORDER BY ts DESC LIMIT ?", (cutoff, max(8, limit // 3))):
            app = (row[2] or "")
            if "déj" in app.lower() or "deja" in app.lower():
                continue  # niente UI di Déjà
            out.append({"type": "screenshot", "id": row[0], "ts": row[1],
                        "app": app or "?", "text": row[3], "score": 0.4, "exact": False})
        conn.close()
    except Exception as e:
        print(f"[AI/agentic] recent pool fail: {e}")
    return out


def _agentic_retrieve(queries, recent_hours=0):
    """Esegue le ricerche locali (sequenziali, veloci), fonde e ordina, e
    garantisce la presenza di pagine web. Se `recent_hours`, aggiunge l'audio/
    schermate recenti (per le domande temporali). Ritorna lista risultati (cap)."""
    seen, pooled = set(), []

    def _add(items):
        for r in items:
            key = (r.get("type"), r.get("id"))
            if key in seen:
                continue
            seen.add(key); pooled.append(r)

    for q in queries:
        try:
            _add(search_module.query(q, top_k=AGENTIC_RESULTS_PER_QUERY))
        except Exception as e:
            print(f"[AI/agentic] search '{q}' fail: {e}")
    if recent_hours:
        _add(_recent_pool(recent_hours))

    # Escludi la UI di Déjà (la chat dove l'utente ha scritto la domanda): è la
    # fonte di falsi positivi tipo "hai chiesto di riassumere la telefonata".
    pooled = [r for r in pooled if not _is_deja_ui(r)]

    def _rank(r):
        return (not r.get("exact", False), -float(r.get("score", 0) or 0),
                -search_module._ts_int(r.get("ts", "")))
    pooled.sort(key=_rank)
    # Domanda temporale (telefonata/conversazione): l'audio è ciò che conta →
    # mettilo davanti così non viene soffocato da pagine web/schermate rumorose.
    if recent_hours:
        pooled.sort(key=lambda r: (r.get("type") != "audio", _rank(r)))
    top = pooled[:AGENTIC_POOL_CAP]

    def _guarantee(kind, n):
        nonlocal top
        avail = [r for r in pooled if r.get("type") == kind]
        if avail and not any(r.get("type") == kind for r in top):
            res = min(n, len(avail))
            top = top[: max(1, AGENTIC_POOL_CAP - res)] + avail[:res]

    _guarantee("web", 3)
    if recent_hours:
        _guarantee("audio", 4)  # le domande temporali vivono nell'audio
    return top


def _batch_token_estimate(batch, query):
    """Token approssimati che un lotto occuperà come INPUT del worker."""
    body = _fmt_results(batch, query=query,
                        max_chars=AGENTIC_OTHER_CHARS, web_max_chars=AGENTIC_WEB_CHARS)
    return max(1, len(body) // 4)


def _pack_batches(results, query, budget_tokens, want_batches):
    """Impacchetta i risultati in lotti che NON superano `budget_tokens` (il
    limite di contesto per chiamata), puntando a ~`want_batches` lotti per
    sfruttare il parallelismo. Più lotti = più agenti = più contesto totale
    del singolo limite per-call. Nessun risultato viene scartato."""
    sized = []
    for r in results:
        b = _fmt_results([r], query=query,
                         max_chars=AGENTIC_OTHER_CHARS, web_max_chars=AGENTIC_WEB_CHARS)
        sized.append((r, max(1, len(b) // 4)))
    total = sum(t for _, t in sized) or 1
    # Numero lotti: abbastanza da stare sotto il budget, e almeno want_batches.
    need = math.ceil(total / budget_tokens)
    nb = max(1, min(AGENTIC_MAX_BATCHES, max(need, want_batches)))
    soft = min(budget_tokens, max(1, math.ceil(total / nb)))
    batches, cur, cur_tok = [], [], 0
    for r, tk in sized:
        if cur and cur_tok + tk > soft and len(batches) < nb - 1:
            batches.append(cur); cur, cur_tok = [], 0
        cur.append(r); cur_tok += tk
    if cur:
        batches.append(cur)
    return batches


def _batch_desc(batch):
    """Riassunto leggibile di cosa sta analizzando un agente."""
    cnt = {"web": 0, "screenshot": 0, "audio": 0}
    for r in batch:
        cnt[r.get("type", "screenshot")] = cnt.get(r.get("type", "screenshot"), 0) + 1
    bits = []
    if cnt.get("web"):        bits.append(f"{cnt['web']} pagine web")
    if cnt.get("screenshot"): bits.append(f"{cnt['screenshot']} schermate")
    if cnt.get("audio"):      bits.append(f"{cnt['audio']} audio")
    samples = []
    for r in batch[:3]:
        if r.get("type") == "web":
            samples.append((r.get("domain") or r.get("title") or "web")[:30])
        elif r.get("type") == "screenshot":
            samples.append(str(r.get("app") or "schermata")[:24])
        else:
            samples.append("audio")
    head = f"{len(batch)} ricord{'o' if len(batch) == 1 else 'i'} (" + ", ".join(bits) + ")"
    uniq = list(dict.fromkeys(s for s in samples if s))
    return head + (f" · es. {', '.join(uniq)}" if uniq else "")


def _agentic_worker(client, model, message, batch, max_out, temporal=False):
    """Estrae i fatti rilevanti da un lotto di ricordi (1 chiamata LLM)."""
    # Per le domande su conversazioni leggi l'audio in ordine CRONOLOGICO: aiuta
    # a seguire il botta-e-risposta e a capire chi parla.
    if temporal:
        batch = sorted(batch, key=lambda r: r.get("ts", ""))
    ctx = _fmt_results(batch, query=message,
                       max_chars=AGENTIC_OTHER_CHARS, web_max_chars=AGENTIC_WEB_CHARS)
    sys = (
        "Estrai i fatti rilevanti alla domanda dai ricordi forniti. "
        "Riporta numeri, prezzi, nomi, orari VERBATIM dal testo. Mantieni per "
        "ogni fatto il suo tag [ss:ID]/[au:ID]/[web:ID]. "
        "Considera anche gli indizi INDIRETTI: un orario, una conferma, un numero, "
        "una frase che RISPONDE alla domanda anche se NON nomina esplicitamente "
        "l'argomento (es. 'ti aspetto verso le 15' risponde a 'a che ora arriva il "
        "tecnico'). Meglio riportare un indizio utile con la sua citazione che "
        "scartarlo. "
    )
    if temporal:
        sys += (
            "La domanda riguarda una CONVERSAZIONE/telefonata/video RECENTE: gli "
            "AUDIO recenti SONO quel contenuto. RIASSUMI ciò che viene detto. "
            "ATTENZIONE ai ruoli: l'utente e l'interlocutore possono stare sullo "
            "STESSO canale audio (es. telefonata fatta col telefono e captata dal "
            "microfono del PC → entrambe le voci sono 'mic'). NON dare per scontato "
            "che 'mic'=solo utente: DEDUCI dal CONTENUTO e dal botta-e-risposta chi "
            "è l'utente e chi l'interlocutore (chi chiama, chi risponde, domande vs "
            "risposte, ruoli tipo operatore/cliente). Riassumi attribuendo i turni "
            "in base al senso, ANCHE se nomi o argomento esatto non compaiono. NON "
            "scartare l'audio solo perché manca la keyword. "
        )
    sys += (
        "Se DAVVERO nessun ricordo è pertinente, rispondi esattamente 'NIENTE'. "
        "Non inventare nulla che non sia nei ricordi."
    )
    try:
        return _complete(client, model,
                         [{"role": "system", "content": sys},
                          {"role": "user", "content": f"Domanda: {message}\n\nRicordi:\n{ctx}"}],
                         max_tokens=max_out, temperature=0.2)
    except Exception as e:
        print(f"[AI/agentic] worker fail: {e}")
        return ""


def _agentic_chat_stream(client, model, history, message, queries, recent_hours=0):
    """Pipeline agentica: ricerche → worker PARALLELI → sintesi stream.
    `queries` arriva dal router. Dimensiona i lotti sui limiti REALI del modello
    (context/output): ogni worker resta sotto il contesto per-call, ma N worker
    insieme processano molto più di 128K e producono più del limite di output
    singolo. Numero di agenti ∝ ampiezza della domanda (numero di angoli)."""
    caps = _model_caps(model)
    ctx_tok, out_tok = caps["context"], caps["max_output"]
    worker_out = min(out_tok, AGENTIC_WORKER_OUT_TOK)
    # Budget INPUT per worker = contesto modello − output worker − overhead prompt.
    per_worker_in = max(8000, ctx_tok - worker_out - AGENTIC_CALL_OVERHEAD_TOK)

    head = "🧠 Ricerca agentica · " + " · ".join(queries)
    if recent_hours:
        head += f" · + audio ultime {recent_hours}h"
    yield ("tool", head)

    pooled = _agentic_retrieve(queries, recent_hours)
    # Agenti proporzionati all'ampiezza: domanda precisa (1 angolo) → pochi agenti.
    want = max(1, min(AGENTIC_MAX_WORKERS, len(queries)))
    batches = _pack_batches(pooled, message, per_worker_in, want) if pooled else []

    findings = []
    if batches:
        # Quanti agenti e cosa fa ciascuno (visibile all'utente).
        n = len(batches)
        lbl = ("1 agente" if n == 1 else f"{n} agenti in parallelo")
        ric = f"{len(pooled)} ricord{'o' if len(pooled) == 1 else 'i'}"
        yield ("tool", f"👥 {lbl} · {ric} "
                       f"(ctx {ctx_tok // 1000}K, output {out_tok} tok per agente)")
        for i, b in enumerate(batches):
            yield ("tool", f"  Agente {i + 1}/{len(batches)} → {_batch_desc(b)}")

        temporal = bool(recent_hours)
        with concurrent.futures.ThreadPoolExecutor(max_workers=AGENTIC_MAX_WORKERS) as ex:
            futs = {ex.submit(_agentic_worker, client, model, message, b, worker_out, temporal): i
                    for i, b in enumerate(batches)}
            done = 0
            for fut in concurrent.futures.as_completed(futs):
                i = futs[fut]; done += 1
                txt = (fut.result() or "").strip()
                ok = not _is_nothing(txt)
                yield ("tool", f"  ✓ Agente {i + 1} ({done}/{len(batches)}) — "
                               + ("ha trovato qualcosa" if ok else "niente di rilevante"))
                if ok:
                    findings.append(txt)
    elif pooled:
        yield ("tool", "1 agente · analizzo i ricordi")

    # ── Sintesi finale (streaming) — usa il MAX OUTPUT del modello così le
    # risposte lunghe non vengono troncate. ──
    yield ("tool", "✍️ Sintesi finale…")
    lang = i18n.ai_language_name()
    synth_sys = (
        "Sei Déjà, assistente personale. Hai già raccolto qui sotto degli ESTRATTI "
        "dai ricordi dell'utente (ognuno con citazioni [ss:ID]/[au:ID]/[web:ID]).\n"
        "REGOLA #0 — NON INVENTARE: usa SOLO i fatti presenti negli estratti. Non "
        "aggiungere prezzi, nomi, numeri o dettagli che non siano scritti lì. "
        "Mantieni i tag di citazione esatti dopo ogni fatto.\n"
        "Se gli estratti NON contengono la risposta, scrivi una frase naturale che lo "
        "spiega (es. 'Non ho trovato nulla nei tuoi ricordi su …') — NON rispondere mai "
        "con la sola parola 'NIENTE' o con un sentinel.\n"
        "Rispondi conciso, diretto, senza mostrare il ragionamento. "
        f"Rispondi sempre in {lang}." + _now_context()
    )
    if recent_hours:
        synth_sys += (
            "\nLa domanda riguarda una CONVERSAZIONE/telefonata RECENTE: se gli estratti "
            "contengono il dialogo audio, RIASSUMILO. L'utente e l'interlocutore possono "
            "stare sullo STESSO canale (telefonata fatta col telefono e captata dal "
            "microfono): NON dedurre i ruoli dal solo canale mic/sistema, deducili dal "
            "CONTENUTO (botta-e-risposta, chi chiede e chi risponde). NON dire che 'manca "
            "il contenuto' o che 'risulta solo la richiesta': il dialogo audio recente È "
            "la telefonata richiesta."
        )
    findings_blob = ("\n\n".join(f"— Estratto {i+1} —\n{f}" for i, f in enumerate(findings))
                     if findings else "NESSUN estratto rilevante trovato.")
    messages = ([{"role": "system", "content": synth_sys}]
                + list(history)
                + [{"role": "user",
                    "content": f"Domanda: {message}\n\nEstratti dai ricordi:\n{findings_blob}"}])
    # Lascia spazio all'output pieno del modello.
    messages = _trim_history(messages, max(8000, ctx_tok - out_tok - 4000))

    # Guard anti-sentinel: bufferizza la testa della risposta; se è un "niente"
    # secco (es. il modello sputa 'NIENTE'), NON mostrarlo → frase naturale.
    try:
        stream = client.chat.completions.create(
            model=model, messages=messages, stream=True,
            max_tokens=out_tok, temperature=0.4,
        )
        parts, emitted = [], False
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not (delta and getattr(delta, "content", None)):
                continue
            parts.append(delta.content)
            if emitted:
                yield ("text", delta.content)
                continue
            joined = "".join(parts)
            if len(joined) < 28:
                continue            # ancora poco: aspetta per decidere
            if _is_nothing(joined):
                continue            # sembra un "niente": continua a bufferare
            yield ("text", joined); emitted = True
        full = "".join(parts).strip()
        if not emitted:
            # Mai emesso: o è corto, o è un "niente" → output pulito.
            if full and not _is_nothing(full):
                yield ("text", full)
            else:
                yield ("text", _NOTHING_MSG)
    except Exception as e:
        yield ("error", f"Sintesi fallita: {e}")
    yield ("done", None)


def chat_stream(history, message):
    """
    Generator yields tuples:
      ("text", str)   - chunk testuale da AI
      ("tool", str)   - notifica esecuzione tool (label descrittivo)
      ("error", str)  - errore
      ("done", None)  - fine

    history: list di dict {"role": "user"|"assistant", "content": str}
    message: messaggio utente corrente
    """
    try:
        client, model = _client()
    except Exception as e:
        yield ("error", str(e))
        yield ("done", None)
        return

    # Ricerca agentica (opt-in): prima un ROUTER decide se vale la pena cercare
    # (no chiacchiera/saluti) e in quanti angoli (→ quanti agenti). Se non serve
    # cercare, risponde conversazionalmente senza agenti. Se la pipeline fallisce
    # a metà senza testo, degrada al loop a tool sequenziale.
    if agentic_enabled():
        plan = _route_and_plan(client, model, history, message)
        if not plan["search"]:
            yield from _converse_stream(client, model, history, message)
            return
        produced = False
        try:
            for ev in _agentic_chat_stream(client, model, history, message,
                                           plan["queries"], plan.get("recent_hours", 0)):
                if ev[0] in ("text", "error"):
                    produced = True
                if ev[0] == "done":
                    if produced:
                        yield ("done", None)
                        return
                    break  # niente prodotto → prova il percorso normale
                yield ev
        except Exception as e:
            print(f"[AI] agentic fallita, fallback sequenziale: {e}")
        if produced:
            yield ("done", None)
            return
        yield ("tool", "passo alla ricerca standard…")

    system_loc = (SYSTEM_PROMPT + _now_context()
                  + f"\n\nIMPORTANTE: rispondi sempre in {i18n.ai_language_name()}.")
    messages = [{"role": "system", "content": system_loc}] + list(history) + [
        {"role": "user", "content": message}
    ]
    # leave room for output + tool results
    budget = AI_CONTEXT_TOKENS - AI_MAX_TOKENS - 4000
    messages = _trim_history(messages, budget)

    for _it in range(8):  # max 8 tool-call iterations (multi-step: 2-passi audio, fallback)
        # Primo turno: FORZA una chiamata tool (tool_choice="required") così il
        # modello non può rispondere "a memoria" inventando. Fallback se
        # l'endpoint non supporta il parametro. Iterazioni successive: "auto"
        # (deve poter chiudere con la risposta finale).
        # temperature 0.45 + frequency_penalty: evitano i loop di ripetizione
        # (con temp troppo bassa + contesto ripetitivo il modello si incarta).
        kwargs = dict(model=model, messages=messages, tools=TOOLS, stream=True,
                      max_tokens=AI_MAX_TOKENS, temperature=0.45, frequency_penalty=0.3)
        if _it == 0:
            kwargs["tool_choice"] = "required"
        try:
            stream = client.chat.completions.create(**kwargs)
        except Exception as e:
            # Alcuni endpoint non accettano tool_choice="required" e/o
            # frequency_penalty: riprova una volta SENZA i parametri opzionali.
            had_opt = ("tool_choice" in kwargs) or ("frequency_penalty" in kwargs)
            kwargs.pop("tool_choice", None)
            kwargs.pop("frequency_penalty", None)
            if had_opt:
                try:
                    stream = client.chat.completions.create(**kwargs)
                except Exception as e2:
                    yield ("error", f"API error: {e2}")
                    yield ("done", None)
                    return
            else:
                yield ("error", f"API error: {e}")
                yield ("done", None)
                return

        text_buf = []
        tool_acc = {}  # index -> {id, name, args}
        finish = None

        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if delta and getattr(delta, "content", None):
                    text_buf.append(delta.content)
                    yield ("text", delta.content)

                if delta and getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = tc.index if tc.index is not None else 0
                        slot = tool_acc.setdefault(idx, {"id": None, "name": "", "args": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                slot["name"] += tc.function.name
                            if tc.function.arguments:
                                slot["args"] += tc.function.arguments

                if choice.finish_reason:
                    finish = choice.finish_reason
        except Exception as e:
            yield ("error", f"Stream error: {e}")
            yield ("done", None)
            return

        # Decide next action
        has_tools = bool(tool_acc)
        if has_tools and (finish == "tool_calls" or finish is None or finish == "stop"):
            # Append assistant turn with tool_calls
            assistant_msg = {
                "role": "assistant",
                "content": "".join(text_buf) or None,
                "tool_calls": [
                    {
                        "id": v["id"] or f"call_{i}",
                        "type": "function",
                        "function": {"name": v["name"], "arguments": v["args"] or "{}"},
                    }
                    for i, v in sorted(tool_acc.items())
                ],
            }
            messages.append(assistant_msg)

            # Execute tools
            for i, v in sorted(tool_acc.items()):
                name = v["name"]
                raw_args = v["args"] or "{}"
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
                label = f"{name}({', '.join(f'{k}={json.dumps(va, ensure_ascii=False)}' for k, va in args.items())})"
                yield ("tool", label)
                result = _execute_tool(name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": v["id"] or f"call_{i}",
                    "content": result,
                })
            continue  # next iteration

        # No tool calls -> done
        yield ("done", None)
        return

    yield ("error", "Limite iterazioni tool raggiunto.")
    yield ("done", None)

# ── Inline RAG (non-streaming) ─────────────────────────────────────
def rag_inline(query, results):
    """One-shot AI synthesis over already-fetched search results."""
    try:
        client, model = _client()
    except Exception as e:
        return f"⚠ {e}"
    if not results:
        return "Nessun ricordo per questa query."
    ctx = _fmt_results(results[:AI_RAG_TOP_K], query=query, max_chars=600, web_max_chars=1400)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "Sintetizza in italiano in 2-3 frasi una risposta alla domanda dell'utente "
                    "basandoti SOLO sui ricordi forniti. Cita timestamp/app se utile. "
                    "Se i ricordi non contengono la risposta, dillo."
                )},
                {"role": "user", "content": f"Domanda: {query}\n\nRicordi rilevanti:\n{ctx}"},
            ],
            max_tokens=400,
            temperature=0.4,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠ Errore AI: {e}"
