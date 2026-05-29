"""Diagnostica pipeline screenshot → OCR → embedding → search."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from datetime import datetime, timezone, timedelta
from db import get_conn

conn = get_conn(); c = conn.cursor()

# Ultimi 15 screenshot con stato indicizzazione
print("== Ultimi 15 screenshot ==")
rows = c.execute("""
    SELECT s.id, s.ts, s.app, length(coalesce(s.text,'')) as tlen,
           CASE WHEN e.id IS NULL THEN 'NO' ELSE 'OK' END as embed,
           substr(coalesce(s.text,''), 1, 80)
    FROM screenshots s
    LEFT JOIN screenshot_embeddings e ON e.screenshot_id = s.id
    ORDER BY s.id DESC LIMIT 15
""").fetchall()
for r in rows:
    print(f"  #{r[0]:5}  {r[1][:19]}  emb={r[4]}  text_len={r[3]:4}  app={r[2][:30]:30}  | {r[5]!r}")

# Conteggio totali
total_ss = c.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
total_emb = c.execute("SELECT COUNT(*) FROM screenshot_embeddings").fetchone()[0]
empty_text = c.execute("SELECT COUNT(*) FROM screenshots WHERE text IS NULL OR text=''").fetchone()[0]
print(f"\n== Totali ==")
print(f"  screenshot:  {total_ss}")
print(f"  embedding:   {total_emb}")
print(f"  text vuoto:  {empty_text}")
print(f"  pendenti:    {total_ss - total_emb - empty_text}")

# Ultimi audio
print(f"\n== Ultimi 5 audio ==")
arows = c.execute("""
    SELECT a.id, a.ts, a.source, length(coalesce(a.transcript,'')) as tlen,
           CASE WHEN e.id IS NULL THEN 'NO' ELSE 'OK' END as embed,
           substr(coalesce(a.transcript,''), 1, 80)
    FROM audio_segments a
    LEFT JOIN audio_embeddings e ON e.audio_segment_id = a.id
    ORDER BY a.id DESC LIMIT 5
""").fetchall()
for r in arows:
    print(f"  #{r[0]:5}  {r[1][:19]}  emb={r[4]}  len={r[3]:4}  src={r[2]:6}  | {r[5]!r}")

# Soglie correnti
from config import AUDIO_MIN_SCORE, SCREENSHOT_MIN_SCORE
print(f"\n== Soglie ==")
print(f"  SCREENSHOT_MIN_SCORE = {SCREENSHOT_MIN_SCORE}")
print(f"  AUDIO_MIN_SCORE      = {AUDIO_MIN_SCORE}")

conn.close()

# Test ricerca interattiva
if len(sys.argv) > 1:
    q = " ".join(sys.argv[1:])
    print(f"\n== Test ricerca: {q!r} ==")
    from modules import search as sm
    results = sm.query(q)
    if not results:
        print("  NESSUN RISULTATO")
    for r in results[:10]:
        score = r["score"]; t = r["type"]; tid = r["id"]
        body = (r.get("text") or "")[:80].replace("\n", " ")
        ex = "EXACT" if r.get("exact") else "sem"
        print(f"  [{t:10}] #{tid:5} score={score:.3f} {ex}  | {body!r}")
