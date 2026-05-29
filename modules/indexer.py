# modules/indexer.py
import time
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from db import get_conn
from config import EMBEDDING_MODEL, INDEXER_BATCH, INDEXER_INTERVAL

log = logging.getLogger("deja.indexer")
model = None

def _load_model(retries=3):
    """Carica il modello embedding con retry+backoff. Ritorna True se ok."""
    global model
    if model is not None:
        return True
    for attempt in range(retries):
        try:
            print("[Indexer] Carico modello embedding (può scaricare al primo avvio)...")
            model = SentenceTransformer(EMBEDDING_MODEL)
            print("[Indexer] Modello caricato.")
            return True
        except Exception as e:
            log.error("Load modello embedding fallito (%d/%d): %s", attempt + 1, retries, e)
            print(f"[Indexer] Errore caricamento modello: {e}")
            time.sleep(min(20, 2 ** attempt))
    return False

def _fetch_unindexed_screenshots(conn, limit):
    c = conn.cursor()
    c.execute("""
        SELECT s.id, s.text FROM screenshots s
        LEFT JOIN screenshot_embeddings e ON e.screenshot_id = s.id
        WHERE (s.text IS NOT NULL AND s.text != '') AND e.id IS NULL
        ORDER BY s.id ASC LIMIT ?
    """, (limit,))
    return c.fetchall()

def _save_screenshot_embedding(conn, sid, vec):
    c = conn.cursor()
    c.execute(
        "INSERT INTO screenshot_embeddings (screenshot_id, dim, vector) VALUES (?, ?, ?)",
        (sid, vec.shape[0], vec.astype("float32").tobytes()))
    # Anche in vec_screenshots (int8 quantized)
    try:
        from db import vec_available, quantize_int8
        if vec_available():
            i8 = quantize_int8(vec)
            c.execute("INSERT INTO vec_screenshots(rowid, emb) VALUES (?, vec_int8(?))",
                      (sid, i8.tobytes()))
    except Exception as e:
        print(f"[Indexer] vec_ss insert fail #{sid}: {e}")
    conn.commit()

def _fetch_unindexed_audio(conn, limit):
    c = conn.cursor()
    c.execute("""
        SELECT a.id, a.transcript FROM audio_segments a
        LEFT JOIN audio_embeddings e ON e.audio_segment_id = a.id
        WHERE (a.transcript IS NOT NULL AND a.transcript != '') AND e.id IS NULL
        ORDER BY a.id ASC LIMIT ?
    """, (limit,))
    return c.fetchall()

def _save_audio_embedding(conn, aid, vec):
    c = conn.cursor()
    c.execute(
        "INSERT INTO audio_embeddings (audio_segment_id, dim, vector) VALUES (?, ?, ?)",
        (aid, vec.shape[0], vec.astype("float32").tobytes()))
    try:
        from db import vec_available, quantize_int8
        if vec_available():
            i8 = quantize_int8(vec)
            c.execute("INSERT INTO vec_audio(rowid, emb) VALUES (?, vec_int8(?))",
                      (aid, i8.tobytes()))
    except Exception as e:
        print(f"[Indexer] vec_au insert fail #{aid}: {e}")
    conn.commit()

def run(stop_event):
    if not _load_model():
        print("[Indexer] Modello non disponibile: indicizzazione disattivata (la ricerca userà il fallback).")
        log.warning("Indexer disattivato: modello embedding non caricato.")
        return
    conn = get_conn()
    print("[Indexer] Avviato.")
    while not stop_event.is_set():
        try:
            rows = _fetch_unindexed_screenshots(conn, INDEXER_BATCH)
            if rows:
                vecs = model.encode([r[1] for r in rows], convert_to_numpy=True, normalize_embeddings=True)
                for (sid, _), vec in zip(rows, vecs): _save_screenshot_embedding(conn, sid, vec)
                print(f"[Indexer] Screenshot: indicizzati {len(rows)} embedding.")
            audio_rows = _fetch_unindexed_audio(conn, INDEXER_BATCH)
            if audio_rows:
                vecs = model.encode([r[1] for r in audio_rows], convert_to_numpy=True, normalize_embeddings=True)
                for (aid, _), vec in zip(audio_rows, vecs): _save_audio_embedding(conn, aid, vec)
                print(f"[Indexer] Audio: indicizzati {len(audio_rows)} embedding.")
        except Exception as e:
            # Un errore in un ciclo non deve uccidere il thread per sempre.
            log.exception("Errore nel ciclo indexer")
            print(f"[Indexer] Errore ciclo (continuo): {e}")
        stop_event.wait(timeout=INDEXER_INTERVAL)
    conn.close(); print("[Indexer] Fermato.")
