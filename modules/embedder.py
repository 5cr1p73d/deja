# modules/embedder.py
"""Istanza CONDIVISA del modello embedding (sentence-transformers).

Prima search.py e indexer.py caricavano ciascuno la PROPRIA copia dello stesso
modello (~1 GB l'una di RAM, e la prima ricerca pagava l'intero load). Qui c'è
una sola istanza lazy, protetta da lock solo per il caricamento: encode() di
torch è thread-safe in inference, quindi indexer e ricerca possono chiamarlo
in concorrenza senza serializzarsi.

Se l'utente cambia EMBEDDING_MODEL nelle impostazioni il modello viene
ricaricato alla chiamata successiva (config è letto dinamicamente, come in
capturer.py).
"""
import threading

import config

_model = None
_model_name = None
_load_lock = threading.Lock()


def get_model():
    """Ritorna il modello condiviso, caricandolo se serve. Import di torch
    differito: se le DLL native non si caricano (WinError 1114) l'eccezione
    propaga e il chiamante degrada (ricerca testuale, indexer disattivato)."""
    global _model, _model_name
    name = config.EMBEDDING_MODEL
    if _model is not None and _model_name == name:
        return _model
    with _load_lock:
        if _model is None or _model_name != name:
            from sentence_transformers import SentenceTransformer
            print(f"[Embedder] Carico modello embedding '{name}'…")
            _model = SentenceTransformer(name)
            _model_name = name
            print("[Embedder] Modello caricato.")
    return _model


def encode(texts):
    """Encode di una lista di testi → matrice numpy normalizzata (per cosine)."""
    return get_model().encode(list(texts), convert_to_numpy=True,
                              normalize_embeddings=True)


def is_loaded() -> bool:
    return _model is not None
