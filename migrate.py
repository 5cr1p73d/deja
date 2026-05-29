# migrate_audio.py
import io, numpy as np, soundfile as sf
from db import get_conn

def encode_opus(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format='OGG', subtype='OPUS')
    return buf.getvalue()

conn = get_conn()
c = conn.cursor()
rows = c.execute(
    "SELECT id, audio_data FROM audio_segments WHERE audio_format = 'f32' AND audio_data IS NOT NULL"
).fetchall()

print(f"[Migrazione] {len(rows)} record da convertire...")
for row_id, blob in rows:
    audio = np.frombuffer(blob, dtype=np.float32)
    opus = encode_opus(audio)
    c.execute(
        "UPDATE audio_segments SET audio_data = ?, audio_format = 'opus' WHERE id = ?",
        (opus, row_id)
    )
    print(f"  ✓ id={row_id} | {len(blob)/1024:.1f} KB → {len(opus)/1024:.1f} KB")

conn.commit()
conn.close()
print("[Migrazione] Completata.")
