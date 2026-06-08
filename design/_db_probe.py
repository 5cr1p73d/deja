"""Sonda READ-ONLY: quale deja.db si apre con la chiave dbkey.bin attuale?
Non scrive nulla (solo PRAGMA key + SELECT). Diagnostica recupero dati.
"""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlcipher3 import dbapi2 as sq
from modules.secrets import get_db_key_hex
import paths

key = get_db_key_hex()
print("key hex (prime 8):", (key[:8] + "…") if key else None, "| len", len(key) if key else 0)

proj = r"D:\Deja\deja.db"
local = os.path.join(paths.data_dir(), "deja.db")

def probe(path):
    print(f"\n--- {path}  ({os.path.getsize(path)/1e9:.2f} GB)" if os.path.exists(path) else f"\n--- {path} (assente)")
    if not os.path.exists(path):
        return
    try:
        c = sq.connect(path, check_same_thread=False, timeout=10)
        c.execute(f"PRAGMA key=\"x'{key}'\"")
        c.execute("PRAGMA cipher_memory_security = OFF")
        n = c.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
        print(f"  APRE OK con chiave attuale — {n} oggetti in sqlite_master")
        for tbl in ("screenshots", "audio_segments", "audio"):
            try:
                cnt = c.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
                print(f"    {tbl}: {cnt} righe")
            except Exception:
                pass
        c.close()
    except Exception as e:
        print(f"  NON apre con la chiave attuale: {type(e).__name__}: {e}")

probe(local)   # quello atteso buono
probe(proj)    # quello stantio (atteso: fallisce)
print("\nPROBE DONE")
