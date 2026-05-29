# db.py
import sqlite3
from config import DB_PATH

# Embedding dim (paraphrase-multilingual-mpnet-base-v2)
EMBED_DIM = 768

_vec_available = None

def _try_load_vec(conn):
    """Carica estensione sqlite-vec. Ritorna True se OK."""
    global _vec_available
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        _vec_available = True
        return True
    except Exception as e:
        _vec_available = False
        return False

def vec_available():
    return _vec_available is True

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
    except Exception as e:
        print(f"[DB] PRAGMA setup fail: {e}")
    _try_load_vec(conn)
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            ts    TEXT NOT NULL,
            app   TEXT,
            hash  TEXT NOT NULL,
            image BLOB NOT NULL,
            text  TEXT
        );
        CREATE TABLE IF NOT EXISTS screenshot_embeddings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            screenshot_id INTEGER NOT NULL,
            dim           INTEGER NOT NULL,
            vector        BLOB NOT NULL,
            FOREIGN KEY (screenshot_id) REFERENCES screenshots(id)
        );
        CREATE TABLE IF NOT EXISTS audio_segments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            source     TEXT NOT NULL,
            transcript TEXT NOT NULL,
            audio_data BLOB
        );
        CREATE TABLE IF NOT EXISTS audio_embeddings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            audio_segment_id INTEGER NOT NULL,
            dim              INTEGER NOT NULL,
            vector           BLOB NOT NULL,
            FOREIGN KEY (audio_segment_id) REFERENCES audio_segments(id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT NOT NULL,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            conversation_id INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_chat_conv         ON chat_messages(conversation_id, id);
        CREATE INDEX IF NOT EXISTS idx_screenshots_ts    ON screenshots(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audio_ts          ON audio_segments(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_ss_emb_sid        ON screenshot_embeddings(screenshot_id);
        CREATE INDEX IF NOT EXISTS idx_au_emb_aid        ON audio_embeddings(audio_segment_id);
        CREATE TABLE IF NOT EXISTS daily_summaries (
            day_iso       TEXT PRIMARY KEY,
            content       TEXT NOT NULL,
            ts_generated  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS search_history (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            ts    TEXT NOT NULL,
            query TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_search_history_ts ON search_history(ts DESC);
        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS item_tags (
            tag_id    INTEGER NOT NULL,
            kind      TEXT NOT NULL,   -- 'ss' | 'au'
            item_id   INTEGER NOT NULL,
            PRIMARY KEY (tag_id, kind, item_id),
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_item_tags_item ON item_tags(kind, item_id);
    """)
    # Pinned column su screenshots e audio_segments
    existing_ss = {row[1] for row in c.execute("PRAGMA table_info(screenshots)")}
    if "pinned" not in existing_ss:
        c.execute("ALTER TABLE screenshots ADD COLUMN pinned INTEGER DEFAULT 0")
        print("[DB] Migrazione: screenshots.pinned")
    existing_au2 = {row[1] for row in c.execute("PRAGMA table_info(audio_segments)")}
    if "pinned" not in existing_au2:
        c.execute("ALTER TABLE audio_segments ADD COLUMN pinned INTEGER DEFAULT 0")
        print("[DB] Migrazione: audio_segments.pinned")
    existing_audio = {row[1] for row in c.execute("PRAGMA table_info(audio_segments)")}
    if "audio_data" not in existing_audio:
        c.execute("ALTER TABLE audio_segments ADD COLUMN audio_data BLOB")
        print("[DB] Migrazione: aggiunta colonna audio_data")
    if "audio_format" not in existing_audio:
        c.execute("ALTER TABLE audio_segments ADD COLUMN audio_format TEXT DEFAULT 'f32'")
        print("[DB] Migrazione: aggiunta colonna audio_format")

    # ── sqlite-vec virtual tables (int8 cosine) ──
    if vec_available():
        try:
            c.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_screenshots "
                f"USING vec0(emb int8[{EMBED_DIM}] distance_metric=cosine)"
            )
            c.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_audio "
                f"USING vec0(emb int8[{EMBED_DIM}] distance_metric=cosine)"
            )
            print("[DB] sqlite-vec virtual tables OK (int8 cosine).")
        except Exception as e:
            print(f"[DB] vec virtual tables fail: {e}")
    else:
        print("[DB] sqlite-vec non disponibile; uso fallback numpy.")

    conn.commit()
    conn.close()

    # Migrazione one-shot embedding esistenti → vec tables
    if _vec_available:
        try:
            migrate_embeddings_to_vec()
        except Exception as e:
            print(f"[DB] migrazione vec fallita: {e}")

    print("[DB] Inizializzato.")


def quantize_int8(vec_f32):
    """Quantize normalized float32 vector to int8 (range [-127, 127])."""
    import numpy as _np
    return _np.round(_np.clip(_np.asarray(vec_f32, dtype=_np.float32) * 127.0, -127, 127)).astype(_np.int8)


def migrate_embeddings_to_vec():
    """Popola vec_screenshots / vec_audio da tabelle embedding legacy se vuote."""
    if not vec_available():
        return
    import numpy as _np
    conn = get_conn(); c = conn.cursor()

    n_vec_ss = c.execute("SELECT COUNT(*) FROM vec_screenshots").fetchone()[0]
    n_emb_ss = c.execute("SELECT COUNT(*) FROM screenshot_embeddings").fetchone()[0]
    if n_vec_ss < n_emb_ss:
        # Trova quelli mancanti
        rows = c.execute("""
            SELECT e.screenshot_id, e.vector FROM screenshot_embeddings e
            LEFT JOIN vec_screenshots v ON v.rowid = e.screenshot_id
            WHERE v.rowid IS NULL
        """).fetchall()
        migrated = 0
        for sid, blob in rows:
            try:
                f32 = _np.frombuffer(blob, dtype="float32")
                if f32.size != EMBED_DIM: continue
                i8 = quantize_int8(f32)
                c.execute("INSERT INTO vec_screenshots(rowid, emb) VALUES (?, vec_int8(?))",
                          (sid, i8.tobytes()))
                migrated += 1
            except Exception as e:
                pass
        if migrated:
            conn.commit()
            print(f"[DB] Vec migrazione screenshot: {migrated} embedding int8 quantizzati.")

    n_vec_au = c.execute("SELECT COUNT(*) FROM vec_audio").fetchone()[0]
    n_emb_au = c.execute("SELECT COUNT(*) FROM audio_embeddings").fetchone()[0]
    if n_vec_au < n_emb_au:
        rows = c.execute("""
            SELECT e.audio_segment_id, e.vector FROM audio_embeddings e
            LEFT JOIN vec_audio v ON v.rowid = e.audio_segment_id
            WHERE v.rowid IS NULL
        """).fetchall()
        migrated = 0
        for aid, blob in rows:
            try:
                f32 = _np.frombuffer(blob, dtype="float32")
                if f32.size != EMBED_DIM: continue
                i8 = quantize_int8(f32)
                c.execute("INSERT INTO vec_audio(rowid, emb) VALUES (?, vec_int8(?))",
                          (aid, i8.tobytes()))
                migrated += 1
            except Exception:
                pass
        if migrated:
            conn.commit()
            print(f"[DB] Vec migrazione audio: {migrated} embedding int8 quantizzati.")

    conn.close()


# ── Settings ↔ Config bridge ───────────────────────────────────────
# Mapping: config attribute name → (DB key, type converter)
_CONFIG_SETTINGS = {
    "EMBEDDING_MODEL":     ("embedding_model",     str),
    "WHISPER_MODEL":       ("whisper_model",       str),
    "CAPTURE_INTERVAL":    ("capture_interval",    int),
    "AUDIO_CHUNK_SECONDS": ("audio_chunk_seconds", int),
    "AUDIO_MIN_SCORE":     ("audio_min_score",     float),
}

def load_settings_into_config():
    """Read settings from DB and override config module attributes."""
    import config
    conn = get_conn(); c = conn.cursor()
    for attr, (key, conv) in _CONFIG_SETTINGS.items():
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row and row[0]:
            try:
                setattr(config, attr, conv(row[0]))
            except (ValueError, TypeError):
                pass
    conn.close()

def backup_db(dest_zip_path):
    """Backup deja.db (+ WAL files se attivi) in zip. Ritorna (ok, msg)."""
    import os, zipfile
    if not os.path.exists(DB_PATH):
        return False, "DB non esiste"
    try:
        # Checkpoint WAL prima di backup per consistency
        conn = get_conn()
        try: conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception: pass
        conn.close()

        with zipfile.ZipFile(dest_zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(DB_PATH, arcname=os.path.basename(DB_PATH))
            # WAL/SHM files se presenti
            for ext in ("-wal", "-shm"):
                p = DB_PATH + ext
                if os.path.exists(p):
                    z.write(p, arcname=os.path.basename(p))
        size_mb = os.path.getsize(dest_zip_path) / 1024 / 1024
        return True, f"Backup {size_mb:.1f}MB → {dest_zip_path}"
    except Exception as e:
        return False, f"Errore backup: {e}"


def restore_db(src_zip_path):
    """Restore DB da zip. SOSTITUISCE deja.db corrente (DESTRUCTIVE)."""
    import os, zipfile, shutil
    if not os.path.exists(src_zip_path):
        return False, "Zip non trovato"
    backup_old = DB_PATH + ".prev_backup"
    try:
        # Backup vecchio prima
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_old)
        # Estrai zip in cwd (sovrascrive deja.db, -wal, -shm)
        target_dir = os.path.dirname(os.path.abspath(DB_PATH)) or "."
        with zipfile.ZipFile(src_zip_path, "r") as z:
            for member in z.namelist():
                if member.endswith(".db") or member.endswith("-wal") or member.endswith("-shm"):
                    z.extract(member, target_dir)
        return True, f"Restore OK. Backup precedente: {backup_old}. Riavvia app."
    except Exception as e:
        return False, f"Errore restore: {e}"


def vacuum_db():
    """Compatta DB. Pesante: chiama solo a shutdown o on-demand."""
    import os
    try:
        size_before = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        conn = get_conn()
        conn.execute("VACUUM")
        conn.close()
        size_after = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        saved = (size_before - size_after) / (1024 * 1024)
        print(f"[DB] VACUUM: {size_before/1024/1024:.1f}MB -> {size_after/1024/1024:.1f}MB (-{saved:.1f}MB)")
    except Exception as e:
        print(f"[DB] VACUUM errore: {e}")

def get_distinct_apps(limit=50):
    """Top N app per count screenshot."""
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT COALESCE(app, '?') AS a, COUNT(*) AS c FROM screenshots "
        "GROUP BY a ORDER BY c DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [{"app": r[0], "count": r[1]} for r in rows]

def set_pinned(kind, item_id, pinned):
    table = "screenshots" if kind == "ss" else "audio_segments"
    conn = get_conn()
    conn.cursor().execute(f"UPDATE {table} SET pinned=? WHERE id=?",
                          (1 if pinned else 0, item_id))
    conn.commit(); conn.close()

def get_pinned():
    conn = get_conn(); c = conn.cursor()
    out = []
    for row in c.execute("SELECT id, ts, app, text FROM screenshots WHERE pinned=1 ORDER BY ts DESC"):
        out.append({"id": row[0], "ts": row[1], "app": row[2] or "?", "text": row[3],
                    "type": "screenshot", "score": 1.0, "exact": False})
    for row in c.execute("SELECT id, ts, source, transcript FROM audio_segments WHERE pinned=1 ORDER BY ts DESC"):
        out.append({"id": row[0], "ts": row[1], "source": row[2], "transcript": row[3],
                    "type": "audio", "score": 1.0, "exact": False,
                    "app": "🎙️ " + ("Microfono" if row[2] == "mic" else "Sistema"),
                    "text": row[3]})
    conn.close()
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out

def add_tag(kind, item_id, name):
    name = (name or "").strip().lower()
    if not name: return
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
    tid = c.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()[0]
    c.execute("INSERT OR IGNORE INTO item_tags(tag_id, kind, item_id) VALUES (?, ?, ?)",
              (tid, kind, item_id))
    conn.commit(); conn.close()

def remove_tag(kind, item_id, name):
    name = (name or "").strip().lower()
    if not name: return
    conn = get_conn(); c = conn.cursor()
    row = c.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
    if row:
        c.execute("DELETE FROM item_tags WHERE tag_id=? AND kind=? AND item_id=?",
                  (row[0], kind, item_id))
        conn.commit()
    conn.close()

def get_tags(kind, item_id):
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id=t.id "
        "WHERE it.kind=? AND it.item_id=? ORDER BY t.name", (kind, item_id)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]

def save_search_query(q):
    if not q or not q.strip(): return
    from datetime import datetime, timezone
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM search_history WHERE query=?", (q,))
    c.execute("INSERT INTO search_history(ts, query) VALUES (?, ?)",
              (datetime.now(timezone.utc).isoformat(), q))
    # Trim last 50
    c.execute("""DELETE FROM search_history WHERE id NOT IN
                 (SELECT id FROM search_history ORDER BY id DESC LIMIT 50)""")
    conn.commit(); conn.close()

def load_search_history(limit=10):
    conn = get_conn()
    rows = conn.cursor().execute(
        "SELECT query FROM search_history ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]

def save_setting(key, value):
    conn = get_conn()
    conn.cursor().execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value)))
    conn.commit(); conn.close()

def get_setting(key, default=None):
    conn = get_conn()
    row = conn.cursor().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default
