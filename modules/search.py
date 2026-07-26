# modules/search.py
import re
from collections import Counter, OrderedDict

import numpy as np

from db import get_conn, vec_available, fts_ready, quantize_int8
import config  # AUDIO_MIN_SCORE / EMBEDDING_MODEL letti dinamicamente (vedi capturer.py)
from config import TOP_K_RESULTS, AUDIO_SEMANTIC_PENALTY, SCREENSHOT_MIN_SCORE
MIN_SCORE_SCREENSHOT = SCREENSHOT_MIN_SCORE

# Cache embedding matrici in memoria (fallback numpy quando sqlite-vec manca).
# Invalidate quando count cambia.
_ss_cache = {"count": -1, "ids": [], "mat": None}
_au_cache = {"count": -1, "ids": [], "mat": None}

# Cache LRU degli embedding delle QUERY: la stessa ricerca ripetuta (o le
# sub-query dell'agentica riusate tra turni) salta l'encode (~50-200ms CPU).
_q_emb_cache = OrderedDict()   # (model_name, text) -> np.ndarray
_Q_EMB_CAP = 128


def _get_model():
    """Modello embedding CONDIVISO (modules.embedder): una sola copia in RAM
    con l'indexer. Import di torch differito: se le DLL native non si caricano
    (WinError 1114) l'eccezione propaga e la ricerca degrada a solo testo."""
    from modules import embedder
    return embedder.get_model()


def _encode_queries(texts):
    """Encode di N query in UN SOLO batch (con cache LRU per singola query).
    Ritorna dict text -> vettore normalizzato. Solleva se il modello manca."""
    out, missing = {}, []
    mname = config.EMBEDDING_MODEL
    for t in texts:
        key = (mname, t)
        if key in _q_emb_cache:
            _q_emb_cache.move_to_end(key)
            out[t] = _q_emb_cache[key]
        elif t not in out and t not in missing:
            missing.append(t)   # niente doppioni: encode di 1 testo 2 volte
    if missing:
        from modules import embedder
        vecs = embedder.encode(missing)
        for t, v in zip(missing, vecs):
            out[t] = v
            _q_emb_cache[(mname, t)] = v
        while len(_q_emb_cache) > _Q_EMB_CAP:
            _q_emb_cache.popitem(last=False)
    return out


def invalidate_cache():
    """Forza ricarica embedding alla prossima query (es. dopo clear DB)."""
    _ss_cache["count"] = -1
    _au_cache["count"] = -1
    _q_emb_cache.clear()

def _load_screenshot_embeddings(conn):
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM screenshot_embeddings").fetchone()[0]
    if count == _ss_cache["count"] and _ss_cache["mat"] is not None:
        return _ss_cache["ids"], _ss_cache["mat"]
    c.execute("SELECT screenshot_id, vector FROM screenshot_embeddings")
    rows = c.fetchall()
    if not rows:
        _ss_cache.update(count=count, ids=[], mat=None)
        return [], None
    ids  = [r[0] for r in rows]
    mat  = np.vstack([np.frombuffer(r[1], dtype="float32") for r in rows])
    _ss_cache.update(count=count, ids=ids, mat=mat)
    return ids, mat

def _load_audio_embeddings(conn):
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM audio_embeddings").fetchone()[0]
    if count == _au_cache["count"] and _au_cache["mat"] is not None:
        return _au_cache["ids"], _au_cache["mat"]
    c.execute("SELECT audio_segment_id, vector FROM audio_embeddings")
    rows = c.fetchall()
    if not rows:
        _au_cache.update(count=count, ids=[], mat=None)
        return [], None
    ids  = [r[0] for r in rows]
    mat  = np.vstack([np.frombuffer(r[1], dtype="float32") for r in rows])
    _au_cache.update(count=count, ids=ids, mat=mat)
    return ids, mat

def _tokenize_query(text: str) -> list[str]:
    """Split su non-word chars, tieni token >= 2 char. Lowercase."""
    return [t for t in re.split(r"[^\w]+", text.lower()) if len(t) >= 2]

# Tabella sorgente → tabella FTS5 (external content, vedi db.py).
_FTS_TABLE = {
    "screenshots":    "screenshots_fts",
    "audio_segments": "audio_fts",
    "web_pages":      "web_fts",
}


def _fts_coverage(conn, table, tokens, limit=300):
    """Copertura token via indice FTS5: una MATCH per token ('"tok"*', match a
    inizio parola, ms anche su tabelle enormi), frac = quota dei token il cui
    match-set contiene l'id. Ritorna [(id, frac)] ordinato per copertura desc,
    [] se zero hit, None se FTS non pronto/errore (→ fallback LIKE)."""
    fts = _FTS_TABLE.get(table)
    if not fts or not fts_ready() or not tokens:
        return None
    counts = Counter()
    try:
        for t in tokens:
            # ORDER BY rowid DESC: senza, FTS5 restituisce i match in rowid
            # ASCENDENTE e il LIMIT tagliava tenendo i ricordi PIÙ VECCHI —
            # su un token comune (>20k occorrenze) tutto il recente spariva
            # dalla ricerca. Gli id crescono nel tempo → DESC = più recenti.
            rows = conn.execute(
                f"SELECT rowid FROM {fts} WHERE {fts} MATCH ? ORDER BY rowid DESC LIMIT 20000",
                (f'"{t}"*',),
            ).fetchall()
            for (rid,) in rows:
                counts[rid] += 1
    except Exception as e:
        print(f"[search] fts {fts} fail: {e}")
        return None
    n = len(tokens)
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [(rid, c / n) for rid, c in ranked]


def _coverage_like(conn, table, cols, text, limit=300):
    """Fallback LIKE '%tok%' (scan completo): usato quando FTS non è pronto,
    oppure quando FTS dà 0 hit (il LIKE trova anche substring a metà parola)."""
    tokens = _tokenize_query(text)
    if not tokens:
        like = f"%{text}%"
        where = " OR ".join(f"{c} LIKE ?" for c in cols)
        rows = conn.execute(
            f"SELECT id FROM {table} WHERE {where} LIMIT ?",
            tuple(like for _ in cols) + (limit,),
        ).fetchall()
        return [(r[0], 1.0) for r in rows]
    col_or = "(" + " OR ".join(f"LOWER({c}) LIKE ?" for c in cols) + ")"
    cov_expr = " + ".join(f"(CASE WHEN {col_or} THEN 1 ELSE 0 END)" for _ in tokens)
    where = " OR ".join(col_or for _ in tokens)
    p = []
    for tk in tokens:
        for _ in cols:
            p.append(f"%{tk}%")
    params = p + list(p) + [limit]
    sql = f"SELECT id, ({cov_expr}) AS cov FROM {table} WHERE {where} ORDER BY cov DESC LIMIT ?"
    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception as e:
        print(f"[search] coverage {table} fail: {e}")
        return []
    n = len(tokens)
    return [(r[0], (r[1] or 0) / n) for r in rows if (r[1] or 0) > 0]


def _coverage_search(conn, table, cols, text, limit=300):
    """Ricerca testuale con **copertura token**: ritorna [(id, frac)] dove
    frac = quota dei token presenti (0<frac<=1), ordinato per copertura desc.
    Prima prova l'indice FTS5 (veloce); LIKE solo come fallback."""
    hits = _fts_coverage(conn, table, _tokenize_query(text), limit)
    if hits:
        return hits
    # None = FTS non disponibile/errore; [] = 0 hit a inizio parola → il LIKE
    # può ancora trovare substring interne (es. 'kagate' in 'gonkagate').
    return _coverage_like(conn, table, cols, text, limit)

def _vec_search(conn, table, q_int8_bytes, k):
    """Usa sqlite-vec per top-k cosine. Ritorna list[(id, similarity)]."""
    try:
        rows = conn.execute(
            f"SELECT rowid, distance FROM {table} "
            f"WHERE emb MATCH vec_int8(?) ORDER BY distance LIMIT ?",
            (q_int8_bytes, k),
        ).fetchall()
        # sqlite-vec cosine: 0=identici, 1=ortogonali, 2=opposti → similarity = 1 - dist
        return [(int(rid), max(-1.0, 1.0 - float(dist))) for rid, dist in rows]
    except Exception as e:
        print(f"[search] vec_search {table} fail: {e}")
        return None

def _ts_int(ts):
    try:
        s = ts.replace("-", "").replace(":", "").replace("T", "").replace("+", "").split(".")[0]
        return int(s[:14])
    except Exception:
        return 0

_MIC_EMOJI = "\U0001f399️ "

def _fetch_by_ids(conn, sql_prefix, ids):
    """Fetch in BATCH (`WHERE id IN`, chunk da 400) invece di un SELECT per id.
    `sql_prefix` = "SELECT id, ... FROM tabella". Ritorna dict id -> tuple(resto)."""
    out = {}
    ids = [i for i in ids if i is not None]
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        ph = ",".join("?" * len(chunk))
        for row in conn.execute(f"{sql_prefix} WHERE id IN ({ph})", chunk):
            out[row[0]] = row[1:]
    return out


def _numpy_hits(loader, conn, q_emb, cap, min_score):
    """Fallback semantico numpy (sqlite-vec assente): top-`cap` sopra soglia."""
    ids, mat = loader(conn)
    if mat is None:
        return []
    sims = mat @ q_emb
    order = np.argsort(-sims)
    out = []
    for idx in order:
        score = float(sims[idx])
        if score < min_score or len(out) >= cap:
            break
        out.append((int(ids[idx]), score))
    return out


def _semantic_hits(conn, vec_table, loader, q_emb, q_i8, cap, min_score):
    """Hit semantici [(id, score)]: sqlite-vec se c'è, altrimenti numpy."""
    if q_emb is None:
        return []
    if q_i8 is not None:
        hits = _vec_search(conn, vec_table, q_i8, cap)
        if hits is not None:
            return [(i, s) for i, s in hits if s >= min_score]
    if loader is None:
        return []
    return _numpy_hits(loader, conn, q_emb, cap, min_score)


def _query_with_emb(conn, text: str, q_emb, k: int) -> list[dict]:
    """Core della ricerca per una singola query (embedding già calcolato o
    None → solo testo). NON chiude la connessione (riusabile per più query)."""
    sem_cap = max(k * 3, 30)
    q_i8 = None
    if q_emb is not None and vec_available():
        try:
            q_i8 = quantize_int8(q_emb).tobytes()
        except Exception:
            q_i8 = None
    low_text = text.lower()

    # ── SCREENSHOT: testo (FTS/LIKE) + semantica, righe in batch ──
    ss_entries = {}   # id -> (score, exact)
    for sid, frac in _coverage_search(conn, "screenshots", ["text"], text):
        ss_entries.setdefault(sid, (1.0 if frac >= 1.0 else frac, frac >= 1.0))
    for sid, score in _semantic_hits(conn, "vec_screenshots", _load_screenshot_embeddings,
                                     q_emb, q_i8, sem_cap, MIN_SCORE_SCREENSHOT):
        if len(ss_entries) >= sem_cap:
            break
        ss_entries.setdefault(sid, (score, False))
    ss_rows = _fetch_by_ids(conn, "SELECT id, ts, text, app FROM screenshots", ss_entries.keys())
    screenshots = []
    for sid, (score, exact) in ss_entries.items():
        row = ss_rows.get(sid)
        if row:
            screenshots.append({
                "id": sid, "score": score, "ts": row[0],
                "text": row[1], "app": row[2] or "Sconosciuta",
                "type": "screenshot", "exact": exact,
            })

    # ── AUDIO: come sopra; i BLOB audio NON vengono più caricati qui
    # (erano MB inutili per ricerca: la UI li recupera on-demand con
    # get_audio_blob alla selezione, come già fa Esplora). ──
    au_entries = {}
    for aid, frac in _coverage_search(conn, "audio_segments", ["transcript"], text):
        au_entries.setdefault(aid, (1.0 if frac >= 1.0 else frac, frac >= 1.0))
    au_sem = []
    for aid, score in _semantic_hits(conn, "vec_audio", _load_audio_embeddings,
                                     q_emb, q_i8, sem_cap, config.AUDIO_MIN_SCORE):
        if aid not in au_entries:
            au_sem.append((aid, score))
    au_rows = _fetch_by_ids(conn, "SELECT id, ts, source, transcript FROM audio_segments",
                            list(au_entries.keys()) + [a for a, _ in au_sem])
    audio = []
    for aid, (score, exact) in au_entries.items():
        row = au_rows.get(aid)
        if row:
            audio.append({
                "id": aid, "score": score, "ts": row[0],
                "source": row[1], "transcript": row[2],
                "type": "audio", "exact": exact,
                "app": _MIC_EMOJI + ("Microfono" if row[1] == "mic" else "Sistema"),
                "text": row[2],
            })
    for aid, score in au_sem:
        if len(audio) >= sem_cap:
            break
        row = au_rows.get(aid)
        if not row:
            continue
        # Penalità semantica: match solo per significato (la query non appare
        # nel transcript) → score ridotto, e rifiltrato sulla soglia.
        if low_text not in (row[2] or "").lower():
            score *= AUDIO_SEMANTIC_PENALTY
            if score < config.AUDIO_MIN_SCORE:
                continue
        audio.append({
            "id": aid, "score": score, "ts": row[0],
            "source": row[1], "transcript": row[2],
            "type": "audio", "exact": False,
            "app": _MIC_EMOJI + ("Microfono" if row[1] == "mic" else "Sistema"),
            "text": row[2],
        })

    # ── PAGINE WEB (estensione browser): testo + semantica (solo vec) ──
    web_entries = {}
    for wid, frac in _coverage_search(conn, "web_pages", ["text", "title", "url"], text):
        web_entries.setdefault(wid, (1.0 if frac >= 1.0 else frac, frac >= 1.0))
    for wid, score in _semantic_hits(conn, "vec_web", None,
                                     q_emb, q_i8, sem_cap, MIN_SCORE_SCREENSHOT):
        if len(web_entries) >= sem_cap:
            break
        web_entries.setdefault(wid, (score, False))
    web_rows = _fetch_by_ids(conn, "SELECT id, ts, url, domain, title, text FROM web_pages",
                             web_entries.keys())
    web = []
    for wid, (score, exact) in web_entries.items():
        row = web_rows.get(wid)
        if row:
            web.append({
                "id": wid, "score": score, "ts": row[0], "url": row[1],
                "domain": row[2] or "", "title": row[3] or "", "text": row[4] or "",
                "type": "web", "exact": exact, "app": "🌐 " + (row[2] or "web"),
            })

    # Sort: exact first, score desc, ts desc (recent first)
    def _sort_key(x):
        return (not x.get("exact", False), -x["score"], -_ts_int(x["ts"]))
    return (sorted(screenshots, key=_sort_key)[:k]
            + sorted(audio, key=_sort_key)[:k]
            + sorted(web, key=_sort_key)[:k])


def query(text: str, top_k: int = None) -> list[dict]:
    k = top_k if top_k else TOP_K_RESULTS
    # Embedding per la ricerca semantica. Se il modello (torch) non è disponibile
    # degradiamo alla sola ricerca testuale invece di crashare.
    q_emb = None
    try:
        q_emb = _encode_queries([text])[text]
    except Exception as e:
        print(f"[search] modello non disponibile, solo ricerca testuale: {e}")
    conn = get_conn()
    try:
        return _query_with_emb(conn, text, q_emb, k)
    finally:
        conn.close()


def query_many(texts: list[str], top_k: int = None) -> list[list[dict]]:
    """Ricerca di N query in una passata: encode in UN batch (il collo di
    bottiglia locale) e una sola connessione DB. Usata dalla ricerca agentica.
    Ritorna una lista di liste, allineata a `texts`."""
    k = top_k if top_k else TOP_K_RESULTS
    embs = {}
    try:
        embs = _encode_queries(list(dict.fromkeys(texts)))
    except Exception as e:
        print(f"[search] modello non disponibile, solo ricerca testuale: {e}")
    conn = get_conn()
    try:
        return [_query_with_emb(conn, t, embs.get(t), k) for t in texts]
    finally:
        conn.close()


def get_all(limit: int = 3000, offset: int = 0) -> list[dict]:
    """Ritorna una "pagina" di screenshot + audio ordinati per ts DESC.

    Paginabile con `offset` per lo scroll-infinito di "Esplora" (così si può
    sfogliare TUTTO l'archivio, non solo i più recenti). NON carica i blob audio
    (`audio_data`): erano il collo di bottiglia. Il blob si recupera on-demand
    con `get_audio_blob(id)` alla selezione.

    Ogni tabella ha indice su `ts DESC`: prendere i primi `limit+offset` da
    ciascuna (top-N indicizzato) e fondere è veloce e dà l'ordine globale
    corretto anche con offset.
    """
    n = max(0, limit + offset)
    conn = get_conn()
    c    = conn.cursor()
    results = []

    for row in c.execute(
        "SELECT id, ts, text, app FROM screenshots ORDER BY ts DESC LIMIT ?", (n,)
    ):
        results.append({
            "id": row[0], "ts": row[1], "text": row[2],
            "app": row[3] or "Sconosciuta",
            "type": "screenshot", "score": 1.0, "exact": False
        })

    for row in c.execute(
        "SELECT id, ts, source, transcript, audio_format FROM audio_segments "
        "ORDER BY ts DESC LIMIT ?", (n,)
    ):
        results.append({
            "id": row[0], "ts": row[1], "source": row[2],
            "transcript": row[3], "audio_format": row[4] or "f32",
            "type": "audio", "score": 1.0, "exact": False,
            "app": "\U0001f399️ " + ("Microfono" if row[2] == "mic" else "Sistema"),
            "text": row[3]
        })

    for row in c.execute(
        "SELECT id, ts, url, domain, title, text FROM web_pages "
        "ORDER BY ts DESC LIMIT ?", (n,)
    ):
        results.append({
            "id": row[0], "ts": row[1], "url": row[2], "domain": row[3] or "",
            "title": row[4] or "", "text": row[5] or "",
            "type": "web", "score": 1.0, "exact": False,
            "app": "🌐 " + (row[3] or "web"),
        })

    # Eventi di sistema/browser (tabella vuota finché l'utente non attiva le
    # categorie in Impostazioni → Eventi: nessun costo nel caso comune).
    for row in c.execute(
        "SELECT id, ts, source, category, action, subject, app, detail, text, hidden "
        "FROM system_events ORDER BY ts DESC LIMIT ?", (n,)
    ):
        results.append({
            "id": row[0], "ts": row[1], "source": row[2] or "system",
            "category": row[3] or "", "action": row[4] or "",
            "subject": row[5] or "", "event_app": row[6] or "",
            "detail": row[7] or "", "text": row[8] or "",
            "hidden": row[9] or 0,
            "type": "system", "score": 1.0, "exact": False,
            "app": "⚙ " + (row[3] or "evento"),
        })

    conn.close()
    results.sort(key=lambda x: x["ts"], reverse=True)
    return results[offset:offset + limit]


def list_audio(day_iso=None, hour_from=0, hour_to=23, limit=5000, offset=0):
    """Segmenti audio dal più recente. Se `day_iso` ('YYYY-MM-DD') è dato, filtra
    al giorno + fascia oraria LOCALE [hour_from, hour_to] (i ts sono UTC → la
    finestra locale viene convertita in UTC). Ritorna list[dict] type='audio'."""
    from datetime import datetime as _dt, timezone as _tz
    conn = get_conn(); c = conn.cursor()
    try:
        if day_iso:
            try:
                y, mo, d = (int(x) for x in str(day_iso).split("-"))
                hf = max(0, min(23, int(hour_from)))
                ht = max(hf, min(23, int(hour_to)))
                loc = _dt.now().astimezone().tzinfo
                start = _dt(y, mo, d, hf, 0, 0, tzinfo=loc).astimezone(_tz.utc).isoformat()
                end = _dt(y, mo, d, ht, 59, 59, tzinfo=loc).astimezone(_tz.utc).isoformat()
            except Exception:
                return []
            rows = c.execute(
                "SELECT id, ts, source, transcript FROM audio_segments "
                "WHERE ts>=? AND ts<=? ORDER BY ts DESC LIMIT ? OFFSET ?",
                (start, end, limit, offset)).fetchall()
        else:
            rows = c.execute(
                "SELECT id, ts, source, transcript FROM audio_segments "
                "ORDER BY ts DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "ts": r[1], "source": r[2], "transcript": r[3],
            "text": r[3], "type": "audio", "score": 1.0, "exact": False,
            "app": "\U0001f399️ " + ("Microfono" if r[2] == "mic" else "Sistema"),
        })
    return out


def list_audio_around(ts_iso, minutes=15, limit=20, exclude_id=None):
    """Audio entro ±`minutes` dal ts dato (stesso formato ISO UTC dei ts salvati),
    escluso `exclude_id`. Ordinati per ts ASC (dal più vecchio al più recente).
    Serve alla navigazione 'audio vicini' nel detail. Ritorna list[dict]."""
    from datetime import datetime as _dt, timedelta as _td
    try:
        base = _dt.fromisoformat(ts_iso)
    except Exception:
        return []
    lo = (base - _td(minutes=minutes)).isoformat()
    hi = (base + _td(minutes=minutes)).isoformat()
    conn = get_conn(); c = conn.cursor()
    try:
        q = ("SELECT id, ts, source, transcript FROM audio_segments "
             "WHERE ts>=? AND ts<=?")
        params = [lo, hi]
        if exclude_id is not None:
            q += " AND id<>?"; params.append(exclude_id)
        q += " ORDER BY ts ASC LIMIT ?"; params.append(limit)
        rows = c.execute(q, params).fetchall()
    finally:
        conn.close()
    return [{
        "id": r[0], "ts": r[1], "source": r[2], "transcript": r[3],
        "text": r[3], "type": "audio", "score": 1.0, "exact": False,
        "app": "\U0001f399️ " + ("Microfono" if r[2] == "mic" else "Sistema"),
    } for r in rows]


def get_audio_blob(audio_id):
    """Recupera (audio_data, audio_format) di un singolo segmento audio.
    Usato per il caricamento on-demand alla selezione (Esplora/ricerca)."""
    conn = get_conn()
    try:
        row = conn.cursor().execute(
            "SELECT audio_data, audio_format FROM audio_segments WHERE id=?", (audio_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None, "f32"
    return row[0], (row[1] or "f32")
