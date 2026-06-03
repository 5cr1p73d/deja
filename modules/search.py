# modules/search.py
import re
import numpy as np

from db import get_conn, vec_available, quantize_int8
import config  # AUDIO_MIN_SCORE / EMBEDDING_MODEL letti dinamicamente (vedi capturer.py)
from config import TOP_K_RESULTS, AUDIO_SEMANTIC_PENALTY, SCREENSHOT_MIN_SCORE
MIN_SCORE_SCREENSHOT = SCREENSHOT_MIN_SCORE

_model = None

# Cache embedding matrici in memoria. Invalidate quando count cambia.
_ss_cache = {"count": -1, "ids": [], "mat": None}
_au_cache = {"count": -1, "ids": [], "mat": None}


def _get_model():
    """Carica (lazy) il modello embedding. Import di torch differito qui dentro:
    se le DLL native non si caricano (WinError 1114) ritorna None e la ricerca
    prosegue in modalità testuale esatta, senza crashare."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model

def invalidate_cache():
    """Forza ricarica embedding alla prossima query (es. dopo clear DB)."""
    _ss_cache["count"] = -1
    _au_cache["count"] = -1

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

def _exact_search_screenshots(conn, text: str) -> list[int]:
    c = conn.cursor()
    tokens = _tokenize_query(text)
    if not tokens:
        c.execute("SELECT id FROM screenshots WHERE text LIKE ?", (f"%{text}%",))
        return [r[0] for r in c.fetchall()]
    where = " AND ".join("LOWER(text) LIKE ?" for _ in tokens)
    params = tuple(f"%{t}%" for t in tokens)
    c.execute(f"SELECT id FROM screenshots WHERE {where}", params)
    return [r[0] for r in c.fetchall()]

def _exact_search_audio(conn, text: str) -> list[int]:
    c = conn.cursor()
    tokens = _tokenize_query(text)
    if not tokens:
        c.execute("SELECT id FROM audio_segments WHERE transcript LIKE ?", (f"%{text}%",))
        return [r[0] for r in c.fetchall()]
    where = " AND ".join("LOWER(transcript) LIKE ?" for _ in tokens)
    params = tuple(f"%{t}%" for t in tokens)
    c.execute(f"SELECT id FROM audio_segments WHERE {where}", params)
    return [r[0] for r in c.fetchall()]

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

def query(text: str, top_k: int = None) -> list[dict]:
    k = top_k if top_k else TOP_K_RESULTS
    conn  = get_conn()

    # Embedding per la ricerca semantica. Se il modello (torch) non è disponibile
    # degradiamo alla sola ricerca testuale esatta invece di crashare.
    q_emb = None
    try:
        model = _get_model()
        q_emb = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]
    except Exception as e:
        print(f"[search] modello non disponibile, solo ricerca esatta: {e}")

    screenshots = {}
    audio       = {}
    c = conn.cursor()

    # ── 1. EXACT screenshot (priorità, no cap) ────────────────────
    for sid in _exact_search_screenshots(conn, text):
        key = f"ss_{sid}"
        row = c.execute("SELECT ts, text, app FROM screenshots WHERE id = ?", (sid,)).fetchone()
        if row:
            screenshots[key] = {
                "id": sid, "score": 1.0, "ts": row[0],
                "text": row[1], "app": row[2] or "Sconosciuta",
                "type": "screenshot", "exact": True
            }

    # ── 2. SEMANTIC screenshot (sqlite-vec se disponibile) ────────
    # Saltato del tutto se il modello non è disponibile (q_emb None).
    sem_cap = max(k * 3, 30)
    use_vec = vec_available() and q_emb is not None
    if use_vec:
        try:
            q_i8 = quantize_int8(q_emb).tobytes()
            vec_hits = _vec_search(conn, "vec_screenshots", q_i8, sem_cap)
        except Exception:
            vec_hits = None
    else:
        vec_hits = None

    if vec_hits is not None:
        for sid, score in vec_hits:
            if len(screenshots) >= sem_cap: break
            if score < MIN_SCORE_SCREENSHOT: continue
            key = f"ss_{sid}"
            if key in screenshots: continue
            row = c.execute("SELECT ts, text, app FROM screenshots WHERE id = ?", (sid,)).fetchone()
            if row:
                screenshots[key] = {
                    "id": sid, "score": score, "ts": row[0],
                    "text": row[1], "app": row[2] or "Sconosciuta",
                    "type": "screenshot", "exact": False
                }
    elif q_emb is not None:
        # Fallback numpy (solo se abbiamo l'embedding della query)
        ss_ids, ss_mat = _load_screenshot_embeddings(conn)
        if ss_mat is not None:
            sims       = ss_mat @ q_emb
            idx_sorted = np.argsort(-sims)
            for idx in idx_sorted:
                if len(screenshots) >= sem_cap: break
                score = float(sims[idx])
                if score < MIN_SCORE_SCREENSHOT: break
                sid = int(ss_ids[idx])
                key = f"ss_{sid}"
                if key in screenshots: continue
                row = c.execute("SELECT ts, text, app FROM screenshots WHERE id = ?", (sid,)).fetchone()
                if row:
                    screenshots[key] = {
                        "id": sid, "score": score, "ts": row[0],
                        "text": row[1], "app": row[2] or "Sconosciuta",
                        "type": "screenshot", "exact": False
                    }

    # ── 3. EXACT audio (priorità) ─────────────────────────────────
    for aid in _exact_search_audio(conn, text):
        key = f"au_{aid}"
        row = c.execute(
            "SELECT ts, source, transcript, audio_data, audio_format FROM audio_segments WHERE id = ?",
            (aid,)
        ).fetchone()
        if row:
            audio[key] = {
                "id": aid, "score": 1.0, "ts": row[0],
                "source": row[1], "transcript": row[2], "audio_data": row[3],
                "audio_format": row[4] or "f32",
                "type": "audio", "exact": True,
                "app": _MIC_EMOJI + ("Microfono" if row[1] == "mic" else "Sistema"),
                "text": row[2]
            }

    # ── 4. SEMANTIC audio ─────────────────────────────────────────
    sem_cap_au = max(k * 3, 30)
    if use_vec:
        try:
            q_i8 = quantize_int8(q_emb).tobytes()
            au_hits = _vec_search(conn, "vec_audio", q_i8, sem_cap_au)
        except Exception:
            au_hits = None
    else:
        au_hits = None

    if au_hits is not None:
        for aid, score in au_hits:
            if len(audio) >= sem_cap_au: break
            if score < config.AUDIO_MIN_SCORE: continue
            key = f"au_{aid}"
            if key in audio: continue
            row = c.execute(
                "SELECT ts, source, transcript, audio_data FROM audio_segments WHERE id = ?",
                (aid,)
            ).fetchone()
            if row:
                if text.lower() not in (row[2] or "").lower():
                    score *= AUDIO_SEMANTIC_PENALTY
                if score < config.AUDIO_MIN_SCORE: continue
                audio[key] = {
                    "id": aid, "score": score, "ts": row[0],
                    "source": row[1], "transcript": row[2], "audio_data": row[3],
                    "type": "audio", "exact": False,
                    "app": _MIC_EMOJI + ("Microfono" if row[1] == "mic" else "Sistema"),
                    "text": row[2]
                }
    elif q_emb is not None:
        au_ids, au_mat = _load_audio_embeddings(conn)
        if au_mat is not None:
            sims       = au_mat @ q_emb
            idx_sorted = np.argsort(-sims)
            for idx in idx_sorted:
                if len(audio) >= sem_cap_au: break
                score = float(sims[idx])
                if score < config.AUDIO_MIN_SCORE: break
                aid = int(au_ids[idx])
                key = f"au_{aid}"
                if key in audio: continue
                row = c.execute(
                    "SELECT ts, source, transcript, audio_data FROM audio_segments WHERE id = ?",
                    (aid,)
                ).fetchone()
                if row:
                    if text.lower() not in (row[2] or "").lower():
                        score *= AUDIO_SEMANTIC_PENALTY
                    if score < config.AUDIO_MIN_SCORE: continue
                    audio[key] = {
                        "id": aid, "score": score, "ts": row[0],
                        "source": row[1], "transcript": row[2], "audio_data": row[3],
                        "type": "audio", "exact": False,
                        "app": _MIC_EMOJI + ("Microfono" if row[1] == "mic" else "Sistema"),
                        "text": row[2]
                    }

    conn.close()

    # Sort: exact first, score desc, ts desc (recent first)
    def _sort_key(x):
        return (not x.get("exact", False), -x["score"], -_ts_int(x["ts"]))
    ss_sorted = sorted(screenshots.values(), key=_sort_key)[:k]
    au_sorted = sorted(audio.values(),       key=_sort_key)[:k]
    return ss_sorted + au_sorted


def get_all() -> list[dict]:
    """Ritorna tutti gli screenshot e audio ordinati per ts DESC."""
    conn = get_conn()
    c    = conn.cursor()
    results = []

    for row in c.execute("SELECT id, ts, text, app FROM screenshots ORDER BY ts DESC"):
        results.append({
            "id": row[0], "ts": row[1], "text": row[2],
            "app": row[3] or "Sconosciuta",
            "type": "screenshot", "score": 1.0, "exact": False
        })

    for row in c.execute(
    "SELECT id, ts, source, transcript, audio_data, audio_format FROM audio_segments ORDER BY ts DESC"
    ):
        results.append({
            "id": row[0], "ts": row[1], "source": row[2],
            "transcript": row[3], "audio_data": row[4],
            "audio_format": row[5] or "f32",
            "type": "audio", "score": 1.0, "exact": False,
            "app": "\U0001f399️ " + ("Microfono" if row[2] == "mic" else "Sistema"),
            "text": row[3]
        })


    conn.close()
    results.sort(key=lambda x: x["ts"], reverse=True)
    return results
