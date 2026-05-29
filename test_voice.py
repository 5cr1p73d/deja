# test_voice.py — diagnostica voice input isolata
import sys, io, threading, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from db import init_db, get_conn

init_db()

# Mostra device disponibili
import pyaudiowpatch as pyaudio
pa = pyaudio.PyAudio()
print("== Devices input ==")
for i in range(pa.get_device_count()):
    d = pa.get_device_info_by_index(i)
    if d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice", False):
        print(f"  [{d['index']:2}] {d['name']!r}  rate={int(d['defaultSampleRate'])}")
print()

try:
    default = pa.get_default_input_device_info()
    print(f"DEFAULT: [{default['index']}] {default['name']!r}")
except Exception as e:
    print(f"NO DEFAULT: {e}")
pa.terminate()

# Setting registrato
conn = get_conn()
row = conn.cursor().execute("SELECT value FROM settings WHERE key='audio_mic_index'").fetchone()
conn.close()
print(f"\nSetting audio_mic_index = {row[0] if row else '(null)'}")

# Test record + transcribe 5s
print("\n== Test record 5s ==")
print("PARLA ORA...")
stop_event = threading.Event()
def auto_stop():
    time.sleep(5)
    stop_event.set()
threading.Thread(target=auto_stop, daemon=True).start()

from modules.audio import record_and_transcribe
text, log = record_and_transcribe(stop_event, max_seconds=6)
print(f"\nLOG: {log}")
print(f"TEXT: {text!r}")
