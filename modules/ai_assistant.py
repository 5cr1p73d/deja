# modules/ai_assistant.py
"""
AI assistant module for Déjà.
- chat_stream(): streaming chat with tool calling (search_memories, list_recent)
- rag_inline(): one-shot synthesis for inline search card
- Endpoint OpenAI-compatible (Gonka, OpenRouter, ecc.)
"""
import json
from datetime import datetime, timezone, timedelta

from db import get_conn
from modules import search as search_module
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
        "api_key":   _get_setting("ai_api_key", "").strip(),
        "base_url":  base,
        "model":     (_get_setting("ai_model", AI_MODEL_DEFAULT) or AI_MODEL_DEFAULT).strip(),
        "inline":    _get_setting("ai_inline_rag", "0") == "1",
    }

def is_configured():
    return bool(_get_setting("ai_api_key", "").strip())

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
    if not cfg["api_key"]:
        raise RuntimeError("API key mancante. Configura in Impostazioni → AI.")
    key = cfg["api_key"]
    try:
        print(f"[AI] client url={cfg['base_url']} model={cfg['model']} key={key[:6]}...{key[-4:]} (len={len(key)})")
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
                "Cerca semanticamente nell'INTERO archivio storico dell'utente — screenshot OCR + "
                "trascrizioni audio — senza nessun limite temporale. Copre TUTTO il database "
                "(mesi, anni indietro). Usa SEMPRE questo tool quando l'utente chiede di qualcosa "
                "che ha visto/letto/sentito/fatto, anche se molto vecchio. Usa keyword corte e "
                "specifiche. Combina ricerca semantica + match esatto. Restituisce risultati "
                "ordinati per rilevanza con timestamp, app/sorgente, contenuto."
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
                "Lista attività in un range di date specifico — copre QUALSIASI periodo, "
                "anche mesi/anni fa. Usa per domande tipo 'il mese scorso', 'a marzo', "
                "'tra il 5 e il 10 aprile'. Date in formato ISO (YYYY-MM-DD)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Data inizio inclusa, formato YYYY-MM-DD"},
                    "end":   {"type": "string", "description": "Data fine inclusa, formato YYYY-MM-DD"},
                    "kind":  {"type": "string", "enum": ["all", "screenshot", "audio"], "default": "all"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["start", "end"],
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

def _fmt_results(results, max_chars=500):
    if not results:
        return "Nessun ricordo trovato."
    out = []
    for r in results:
        ts = r["ts"][:19].replace("T", " ")
        if r.get("type") == "screenshot":
            body = (r.get("text") or "").strip()[:max_chars]
            ref = f"[ss:{r['id']}]"
            out.append(f"{ref} Screenshot @ {ts} | App: {r.get('app','?')}\n{body}")
        else:
            body = (r.get("transcript") or "").strip()[:max_chars]
            src = "microfono" if r.get("source") == "mic" else "sistema"
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
    return _fmt_results(results[:limit])

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
            src = "mic" if row[2] == "mic" else "pc"
            lines.append(f"[au:{row[0]}] {row[1][:19]} | {src}: {txt}")
    conn.close()
    return "\n".join(lines) if lines else f"Nessuna attività nelle ultime {hours}h."

def _tool_list_by_date_range(args):
    start = str(args.get("start") or "").strip()
    end   = str(args.get("end")   or "").strip()
    kind  = str(args.get("kind", "all") or "all")
    if kind not in ("all", "screenshot", "audio"): kind = "all"
    limit = min(max(1, _safe_int(args.get("limit"), 100)), 500)
    if not start or not end:
        return "Parametri 'start' e 'end' richiesti (formato YYYY-MM-DD)."
    # Normalizza a ISO datetime con TZ UTC
    start_iso = start + "T00:00:00+00:00"
    end_iso   = end   + "T23:59:59+00:00"
    conn = get_conn(); c = conn.cursor()
    lines = []
    if kind in ("all", "screenshot"):
        for row in c.execute(
            "SELECT id, ts, app, text FROM screenshots WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT ?",
            (start_iso, end_iso, limit),
        ):
            txt = (row[3] or "").strip().replace("\n", " ")[:200]
            lines.append(f"[ss:{row[0]}] {row[1][:19]} | {row[2] or '?'}: {txt}")
    if kind in ("all", "audio"):
        for row in c.execute(
            "SELECT id, ts, source, transcript FROM audio_segments WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT ?",
            (start_iso, end_iso, limit),
        ):
            txt = (row[3] or "").strip().replace("\n", " ")[:200]
            src = "mic" if row[2] == "mic" else "pc"
            lines.append(f"[au:{row[0]}] {row[1][:19]} | {src}: {txt}")
    conn.close()
    return "\n".join(lines) if lines else f"Nessuna attività tra {start} e {end}."

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
        if name == "search_memories":     return _tool_search_memories(args)
        if name == "list_recent":         return _tool_list_recent(args)
        if name == "list_by_date_range":  return _tool_list_by_date_range(args)
        if name == "memory_stats":        return _tool_memory_stats(args)
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
    "Sei Déjà, assistente AI personale dell'utente. "
    "Hai accesso COMPLETO e SENZA LIMITI TEMPORALI alla sua memoria digitale:\n"
    "- screenshot con OCR (testo estratto da ogni schermata)\n"
    "- trascrizioni audio (microfono + audio sistema)\n"
    "L'archivio copre TUTTO lo storico — può estendersi a mesi o anni. "
    "NON ASSUMERE MAI un limite temporale arbitrario (es. '7 giorni'). "
    "Se non sai quanto in là va l'archivio, chiama 'memory_stats'.\n\n"
    "TOOL DISPONIBILI:\n"
    "- 'search_memories(query, limit=30)' → ricerca semantica + esatta sull'INTERO database, "
    "nessun filtro temporale. Usa sempre questo per domande tematiche, anche su cose vecchie.\n"
    "- 'list_recent(hours, kind)' → SOLO ultime ore (max sensato 168=7gg). Per finestre più "
    "ampie usa list_by_date_range.\n"
    "- 'list_by_date_range(start, end, kind)' → range date custom (qualsiasi periodo).\n"
    "- 'memory_stats()' → estensione totale archivio (date primo/ultimo screen+audio).\n\n"
    "REGOLE:\n"
    "1. Se utente chiede di cose vecchie (settimane/mesi/anni fa) → usa search_memories o "
    "list_by_date_range. MAI rispondere 'ho solo gli ultimi N giorni'.\n"
    "2. Prima di dire 'non ho dati per periodo X' → chiama memory_stats per VERIFICARE.\n"
    "3. Combina più chiamate se serve (es. memory_stats poi search_memories).\n"
    "4. Cita timestamp e app/sorgente nelle risposte.\n"
    "5. **CITAZIONI FONTI**: ogni volta che riferisci un fatto preso da un ricordo, "
    "inserisci subito DOPO la frase il tag `[ss:ID]` per screenshot o `[au:ID]` per audio "
    "(usa l'ID esatto restituito dal tool). L'UI li trasforma in card cliccabili. "
    "Esempio: 'Hai parlato di Python verso le 14:30 [au:512]. Poco dopo hai aperto "
    "VS Code [ss:3421].' Cita SEMPRE quando possibile — è il valore aggiunto.\n"
    "6. Rispondi sempre in italiano, conciso. Se non trovi nulla DAVVERO, dillo dopo "
    "aver provato con keyword diverse."
)

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

    system_loc = SYSTEM_PROMPT + f"\n\nIMPORTANTE: rispondi sempre in {i18n.ai_language_name()}."
    messages = [{"role": "system", "content": system_loc}] + list(history) + [
        {"role": "user", "content": message}
    ]
    # leave room for output + tool results
    budget = AI_CONTEXT_TOKENS - AI_MAX_TOKENS - 4000
    messages = _trim_history(messages, budget)

    for _ in range(5):  # max 5 tool-call iterations
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                stream=True,
                max_tokens=AI_MAX_TOKENS,
                temperature=0.6,
            )
        except Exception as e:
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
    ctx = _fmt_results(results[:AI_RAG_TOP_K], max_chars=400)
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
