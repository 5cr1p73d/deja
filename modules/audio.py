# modules/audio.py
import time, queue, threading, logging
import numpy as np
import pyaudiowpatch as pyaudio
from datetime import datetime, timezone
from scipy import signal as _spsig
from db import get_conn
import config  # leggere config.X dinamicamente: un import by-value catturerebbe
# i default ignorando i valori salvati (load_settings_into_config).
import io
import soundfile as sf

_model = None
_model_lock = threading.Lock()
# RMS threshold (0.005 = ~-46dBFS). Più alta = più strict su silenzio.
SILENCE_RMS_THRESHOLD = 0.005

# Prompt iniziale: aiuta Whisper col contesto (lingua, dominio).
INITIAL_PROMPT_IT = (
    "Conversazione in italiano. Possono comparire termini tecnici, "
    "nomi di applicazioni, codice e parole inglesi."
)

def get_setting(key):
    conn = get_conn()
    row = conn.cursor().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close(); return row[0] if row else None

def list_devices():
    pa = pyaudio.PyAudio(); devices = []
    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)
        if dev["maxInputChannels"] > 0 and not dev.get("isLoopbackDevice", False):
            devices.append({"index":dev["index"],"name":dev["name"],"loopback":False})
    try:
        for dev in pa.get_loopback_device_info_generator():
            devices.append({"index":dev["index"],"name":dev["name"],"loopback":True})
    except: pass
    pa.terminate(); return devices

_log = logging.getLogger("deja.audio")

def _load_model(retries=3):
    """Carica Whisper con retry+backoff. Ritorna True se ok."""
    global _model
    if _model is not None:
        return True
    for attempt in range(retries):
        try:
            # Import lazy: faster_whisper tira ctranslate2 (e DLL native adiacenti
            # a torch). Caricarlo SOLO qui evita un crash all'avvio se le DLL non
            # inizializzano sulla macchina dell'utente (WinError 1114).
            from faster_whisper import WhisperModel
            print("[Audio] Carico modello Whisper (può scaricare al primo avvio)...")
            _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
            print("[Audio] Modello caricato.")
            return True
        except Exception as e:
            _log.error("Load Whisper fallito (%d/%d): %s", attempt + 1, retries, e)
            print(f"[Audio] Errore caricamento Whisper: {e}")
            time.sleep(min(20, 2 ** attempt))
    return False

def _resample(audio, from_rate, to_rate=16000):
    """Resampling FFT-based (memory bounded). Per voce qualità ok."""
    if from_rate == to_rate:
        return audio.astype(np.float32, copy=False)
    n_in = int(len(audio))
    if n_in == 0:
        return np.zeros(0, dtype=np.float32)
    n_out = int(round(n_in * to_rate / from_rate))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    # FFT-resample: memoria ~5× audio (no polyphase explosion su 44.1k→16k)
    try:
        out = _spsig.resample(audio, n_out)
    except Exception:
        # fallback linear se scipy ha issues
        x_old = np.linspace(0.0, 1.0, n_in, endpoint=False)
        x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
        out = np.interp(x_new, x_old, audio)
    return np.asarray(out, dtype=np.float32)

def _preprocess(audio):
    """DC offset removal + peak normalize (-1 dBFS). Aiuta Whisper su audio basso."""
    if audio.size == 0:
        return audio
    # float64 accumulator per evitare overflow su array grandi
    mean = float(np.mean(audio.astype(np.float64, copy=False)))
    audio = (audio - mean)
    # Sanitize NaN/inf (Whisper crash su quelli)
    if not np.all(np.isfinite(audio)):
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(audio)))
    if peak > 1e-6 and np.isfinite(peak):
        audio = audio * (0.89 / peak)
    return audio.astype(np.float32, copy=False)

def _transcribe(audio):
    audio = _preprocess(audio)
    with _model_lock:
        segs, info = _model.transcribe(
            audio,
            language="it",
            task="transcribe",
            beam_size=5,
            best_of=5,
            temperature=[0.0, 0.2, 0.4],  # fallback sampling se compression_ratio alto
            initial_prompt=INITIAL_PROMPT_IT,
            condition_on_previous_text=True,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            vad_filter=True,
            vad_parameters={
                "threshold": 0.5,
                "min_speech_duration_ms": 250,
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 200,
            },
        )
        segs = list(segs)
    text = " ".join(s.text for s in segs).strip()
    speech_parts = []
    for seg in segs:
        start = max(0, min(int(seg.start*16000), len(audio)))
        end   = max(0, min(int(seg.end  *16000), len(audio)))
        if end > start: speech_parts.append(audio[start:end])
    return text, (np.concatenate(speech_parts) if speech_parts else None)

def _encode_opus(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format='OGG', subtype='OPUS')
    return buf.getvalue()

def decode_audio(blob: bytes, fmt: str = 'opus') -> np.ndarray:
    # Tutti i blob devono essere Opus — il default è ora 'opus'
    if blob[:4] == b'OggS' or fmt == 'opus':
        buf = io.BytesIO(blob)
        audio, _ = sf.read(buf, dtype='float32')
        return audio
    # Fallback f32 solo per eventuale debug — logga un warning
    print(f"[Audio] WARN: blob non-Opus ricevuto (fmt={fmt!r}, size={len(blob)}), tento f32")
    return np.frombuffer(blob, dtype=np.float32)



def _save(text, source, audio):
    encoded = _encode_opus(audio)
    conn = get_conn()
    conn.cursor().execute(
        "INSERT INTO audio_segments (ts, source, transcript, audio_data, audio_format) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), source, text, encoded, 'opus')
    )
    conn.commit(); conn.close()

def _rms(audio):
    if audio.size == 0:
        return 0.0
    a64 = audio.astype(np.float64, copy=False)
    m = float(np.mean(a64 * a64))
    if not np.isfinite(m) or m < 0:
        return 0.0
    return float(np.sqrt(m))

def _process_loop(data_queue, source_label, stop_event):
    while not stop_event.is_set():
        try:
            audio = data_queue.get(timeout=1)
            if audio is None: continue
            rms = _rms(audio)
            if rms < SILENCE_RMS_THRESHOLD: continue
            text, speech_audio = _transcribe(audio)
            if text and speech_audio is not None:
                _save(text, source_label, speech_audio)
                print(f"[Audio/{source_label}] trascritto {len(text)} char ({len(speech_audio)/16000:.1f}s rms={rms:.4f})")
        except queue.Empty: continue
        except Exception as e: print(f"[Audio/{source_label}] Errore: {e}")

def record_and_transcribe(stop_event, max_seconds=60, device_index=None):
    """Registra dal mic via callback (stesso pattern di capture continua, robusto).
    Trascrive con Whisper. Ritorna (text, status_log)."""
    log = []
    try:
        _load_model()
        log.append("model_ready")
    except Exception as e:
        log.append(f"model_fail={e}")
        return "", "; ".join(log)

    pa = pyaudio.PyAudio()
    dev = None
    try:
        if device_index is not None:
            dev = pa.get_device_info_by_index(device_index)
        else:
            from db import get_conn
            conn = get_conn()
            row = conn.cursor().execute(
                "SELECT value FROM settings WHERE key='audio_mic_index'"
            ).fetchone()
            conn.close()
            if row and row[0]:
                try: dev = pa.get_device_info_by_index(int(row[0]))
                except Exception: dev = None
            if dev is None:
                dev = pa.get_default_input_device_info()
        log.append(f"dev=[{dev['index']}]{dev['name']!r}")
    except Exception as e:
        pa.terminate()
        log.append(f"dev_fail={e}")
        return "", "; ".join(log)

    try:
        rate = int(dev["defaultSampleRate"])
    except Exception:
        rate = 16000
    if rate < 8000 or rate > 192000:
        rate = 16000
    log.append(f"rate={rate}")

    # CALLBACK pattern (come capturer continuo): più affidabile su Windows
    buf = []
    def _cb(in_data, fc, ti, st, _buf=buf):
        try:
            frames = np.frombuffer(in_data, dtype=np.float32).copy()
            _buf.extend(frames)
        except Exception:
            pass
        return (None, pyaudio.paContinue)

    try:
        stream = pa.open(format=pyaudio.paFloat32, channels=1, rate=rate,
                         input=True, input_device_index=dev["index"],
                         frames_per_buffer=1024, stream_callback=_cb)
        stream.start_stream()
        log.append("stream_started")
    except Exception as e:
        pa.terminate()
        log.append(f"open_fail={e}")
        return "", "; ".join(log)

    start = time.time()
    try:
        while not stop_event.is_set() and (time.time() - start) < max_seconds:
            time.sleep(0.05)
    finally:
        try: stream.stop_stream(); stream.close()
        except Exception: pass
        pa.terminate()

    if not buf:
        log.append("no_audio")
        return "", "; ".join(log)

    audio = np.array(buf, dtype=np.float32)
    log.append(f"samples={len(audio)} dur={len(audio)/rate:.1f}s")

    # Hard cap: max 5 min raw audio (prevenire OOM su buf gigante)
    max_samples = rate * 300
    if len(audio) > max_samples:
        log.append(f"audio_truncated_from={len(audio)}")
        audio = audio[-max_samples:]

    # Resample 16k usando stessa funzione del capturer
    if rate != 16000:
        try:
            audio = _resample(audio, rate, 16000)
            log.append(f"resampled samples={len(audio)}")
        except Exception as e:
            log.append(f"resample_fail={e}")
            return "", "; ".join(log)

    rms = _rms(audio)
    log.append(f"rms={rms:.4f}")
    if rms < SILENCE_RMS_THRESHOLD * 0.5:
        log.append("silent")
        return "", "; ".join(log)

    t0 = time.time()
    try:
        text = _transcribe_voice(audio)
    except Exception as e:
        log.append(f"transcribe_fail={e}")
        return "", "; ".join(log)
    log.append(f"transcribe_took={time.time()-t0:.1f}s")

    text = (text or "").strip()
    log.append(f"text_len={len(text)}")
    return text, "; ".join(log)


def _transcribe_voice(audio):
    """Trascrizione minimale per voice input. Usa modello SHARED con capture.
    Lock acquire con timeout (no hang infinito)."""
    _load_model()
    audio = _preprocess(audio)
    # Acquire lock con timeout — se capture occupato troppo, rinuncia
    acquired = _model_lock.acquire(timeout=20)
    if not acquired:
        raise RuntimeError("model_lock_timeout (capture occupato >20s)")
    try:
        segs, _ = _model.transcribe(
            audio,
            language="it",
            task="transcribe",
            beam_size=3,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            no_speech_threshold=0.6,
        )
        text_parts = [s.text for s in segs]
    finally:
        _model_lock.release()
    return " ".join(text_parts).strip()


# Heartbeat: ultimo timestamp callback per ogni source. Watchdog ricrea stream se dead.
_audio_heartbeat = {"mic": 0.0, "pc": 0.0}
WATCHDOG_DEAD_AFTER = 300  # 5 min senza callback → restart

# Hot-swap event: settings UI lo set per forzare reload device senza restart app
_restart_event = threading.Event()

def request_restart():
    """Trigger restart immediato degli streams (reload settings device)."""
    _restart_event.set()

def _setup_streams(pa, stop_event, chunk_secs):
    """Crea streams pc + mic. Ritorna (streams, proc_threads)."""
    mic_idx_str = get_setting("audio_mic_index")
    out_idx_str = get_setting("audio_out_index")
    streams = []; proc_threads = []

    if out_idx_str is not None:
        idx = int(out_idx_str)
        try:
            lb_dev = next((d for d in pa.get_loopback_device_info_generator() if d["index"]==idx), None)
            if lb_dev:
                rate=int(lb_dev["defaultSampleRate"]); ch=min(lb_dev["maxInputChannels"],2)
                buf=[]; q_pc=queue.Queue(); tf=int(rate*chunk_secs)
                def cb_pc(in_data,fc,ti,st,_buf=buf,_q=q_pc,_ch=ch,_rate=rate,_tf=tf):
                    _audio_heartbeat["pc"] = time.time()
                    frames=np.frombuffer(in_data,dtype=np.float32).copy(); _buf.extend(frames)
                    if len(_buf)>=_tf*_ch:
                        audio=np.array(_buf[:_tf*_ch],dtype=np.float32); del _buf[:_tf*_ch]
                        if _ch>1: audio=audio.reshape(-1,_ch).mean(axis=1)
                        _q.put(_resample(audio,_rate))
                    return (None,pyaudio.paContinue)
                stream=pa.open(format=pyaudio.paFloat32,channels=ch,rate=rate,input=True,
                               input_device_index=idx,frames_per_buffer=1024,stream_callback=cb_pc)
                streams.append(("pc", stream))
                _audio_heartbeat["pc"] = time.time()
                print(f"[Audio] Loopback: {lb_dev['name']}")
                proc_threads.append(threading.Thread(target=_process_loop,args=(q_pc,"pc",stop_event),daemon=True))
        except Exception as e: print(f"[Audio] Errore loopback: {e}")

    if mic_idx_str is not None:
        idx = int(mic_idx_str)
        try:
            dev=pa.get_device_info_by_index(idx); rate=int(dev["defaultSampleRate"])
            buf=[]; q_mic=queue.Queue(); tf=int(rate*chunk_secs)
            def cb_mic(in_data,fc,ti,st,_buf=buf,_q=q_mic,_rate=rate,_tf=tf):
                _audio_heartbeat["mic"] = time.time()
                frames=np.frombuffer(in_data,dtype=np.float32).copy(); _buf.extend(frames)
                if len(_buf)>=_tf:
                    audio=np.array(_buf[:_tf],dtype=np.float32); del _buf[:_tf]
                    _q.put(_resample(audio,_rate))
                return (None,pyaudio.paContinue)
            stream=pa.open(format=pyaudio.paFloat32,channels=1,rate=rate,input=True,
                           input_device_index=idx,frames_per_buffer=1024,stream_callback=cb_mic)
            streams.append(("mic", stream))
            _audio_heartbeat["mic"] = time.time()
            print(f"[Audio] Microfono: {dev['name']}")
            proc_threads.append(threading.Thread(target=_process_loop,args=(q_mic,"mic",stop_event),daemon=True))
        except Exception as e: print(f"[Audio] Errore microfono: {e}")

    return streams, proc_threads


def _close_streams(streams, pa):
    for _src, s in streams:
        try: s.stop_stream(); s.close()
        except Exception: pass
    try: pa.terminate()
    except Exception: pass


def _audio_enabled() -> bool:
    """Toggle utente: cattura audio disattivabile da Impostazioni → Cattura."""
    return (get_setting("capture_audio_enabled") or "1") == "1"

def _has_audio_devices() -> bool:
    return bool(get_setting("audio_mic_index") or get_setting("audio_out_index"))

def run(stop_event):
    """Loop audio resiliente a: device assenti, toggle on/off da impostazioni,
    hot-swap device, e stream morti (watchdog). Gli stream restano aperti SOLO
    quando la cattura audio è abilitata e c'è almeno un device configurato.
    Il modello Whisper viene caricato pigramente alla prima attivazione."""
    chunk_secs = config.AUDIO_CHUNK_SECONDS
    pa = None
    streams, proc_threads = [], []
    model_loaded = False
    last_watchdog_check = time.time()
    print("[Audio] Avviato.")

    def _open():
        nonlocal pa, streams, proc_threads, model_loaded
        if not _audio_enabled():
            print("[Audio] Cattura audio disattivata da impostazioni."); return False
        if not _has_audio_devices():
            print("[Audio] Nessun dispositivo configurato."); return False
        if not model_loaded:
            if not _load_model():
                print("[Audio] Modello vocale non disponibile: trascrizione disattivata.")
                _log.warning("Audio disattivato: Whisper non caricato.")
                return False
            model_loaded = True
        try:
            pa = pyaudio.PyAudio()
        except Exception as e:
            print(f"[Audio] PyAudio init fail: {e}"); pa = None; return False
        streams, proc_threads = _setup_streams(pa, stop_event, chunk_secs)
        if not streams:
            print("[Audio] Nessuno stream aperto."); _close(); return False
        for _src, s in streams: s.start_stream()
        for t in proc_threads: t.start()
        print("[Audio] Registrazione avviata.")
        return True

    def _close():
        nonlocal pa, streams, proc_threads
        if pa is not None:
            _close_streams(streams, pa)
        streams, proc_threads = [], []
        pa = None

    # Apertura iniziale (no-op se disabilitata o senza device: si riproverà nel loop).
    _open()

    while not stop_event.is_set():
        try:
            stop_event.wait(timeout=2.0)
            if stop_event.is_set(): break

            enabled = _audio_enabled()
            active = bool(streams)

            # Toggle OFF → chiudi gli stream e resta in idle finché riattivato.
            if active and not enabled:
                print("[Audio] Cattura audio disattivata: chiudo gli stream.")
                _close()
                _restart_event.clear()
                continue
            # Toggle OFF e già chiuso → nulla da fare.
            if not enabled:
                continue

            # Hot-swap request (settings UI: device o toggle cambiati).
            force_restart = _restart_event.is_set()
            if force_restart:
                _restart_event.clear()
                print("[Audio] Hot-swap request: ricarico device da settings…")

            # Abilitato ma nessuno stream aperto (riattivato, o device aggiunto).
            if not active:
                _open()
                last_watchdog_check = time.time()
                continue

            now = time.time()
            dead_sources = []
            if not force_restart:
                if now - last_watchdog_check < 30: continue
                last_watchdog_check = now
                dead_sources = [src for src, s in streams
                                if (now - _audio_heartbeat.get(src, 0)) > WATCHDOG_DEAD_AFTER]

            if dead_sources or force_restart:
                reason = ("hot-swap" if force_restart else f"morti {dead_sources}")
                print(f"[Audio] Restart ({reason})…")
                _close()
                time.sleep(0.5)
                _open()
                last_watchdog_check = time.time()
        except Exception as e:
            _log.exception("Errore nel ciclo audio")
            print(f"[Audio] Errore ciclo (continuo): {e}")
            stop_event.wait(timeout=2.0)

    _close()
    print("[Audio] Fermato.")
