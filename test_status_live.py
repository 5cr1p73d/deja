r"""
Test dello stato live in sidebar (card + pannello) — vedi
obsidian/deja/UI/App-Redesign-progress.md § "Stato live in sidebar".

Le funzioni dati sono pure (niente Qt): si testano headless. La parte widget è
verificata con avvio GUI reale.
    .\venv\Scripts\python.exe test_status_live.py
"""
import os
import sys
import time

FAIL = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


def test_formatters():
    print("\n[1] formattatori")
    from ui.app_shell import _fmt_bytes, _fmt_num, _fmt_ago, _fmt_left
    from datetime import datetime, timezone, timedelta

    check("byte → GB", _fmt_bytes(31_640_698_880) == "29,5 GB", _fmt_bytes(31_640_698_880))
    check("byte → MB", _fmt_bytes(16_191_440) == "15,4 MB", _fmt_bytes(16_191_440))
    check("byte piccoli", _fmt_bytes(512) == "512 B", _fmt_bytes(512))
    check("byte None", _fmt_bytes(None) == "—")
    check("numero con punti", _fmt_num(611603) == "611.603", _fmt_num(611603))
    check("numero None", _fmt_num(None) == "—")

    now = datetime.now(timezone.utc)
    check("adesso", _fmt_ago(now.isoformat()) == "ora")
    check("secondi", _fmt_ago((now - timedelta(seconds=30)).isoformat()) == "30s fa")
    check("minuti", _fmt_ago((now - timedelta(minutes=5)).isoformat()) == "5 min fa")
    check("ore", _fmt_ago((now - timedelta(hours=3)).isoformat()) == "3 h fa")
    check("giorni", _fmt_ago((now - timedelta(days=2)).isoformat()) == "2 g fa")
    check("ts assente", _fmt_ago(None) == "—")
    check("ts spazzatura", _fmt_ago("non-una-data") == "—")
    # ts naive (senza tz): trattato come UTC, non deve esplodere
    check("ts naive", _fmt_ago(now.replace(tzinfo=None).isoformat()) == "ora")
    check("pausa infinita = incognito", _fmt_left(10 * 365 * 24 * 3600) == "incognito")
    check("pausa in minuti", _fmt_left(900) == "15 min")


def test_headline():
    print("\n[2] status_headline: lo stato mostrato è quello VERO")
    from ui.app_shell import status_headline
    from ui import theme

    t, c = status_headline({"cap_screens": True, "cap_audio": True, "paused": False})
    check("tutto attivo → verde", t == "Cattura attiva" and c == theme.EMERALD, f"{t} {c}")
    t, c = status_headline({"cap_screens": True, "cap_audio": True, "paused": True,
                            "pause_left": 900})
    check("in pausa → ambra + residuo", t == "In pausa · 15 min" and c == theme.AMBER, t)
    t, _ = status_headline({"cap_screens": True, "cap_audio": True, "paused": True,
                            "pause_left": 10 * 365 * 24 * 3600})
    check("incognito", t == "Incognito", t)
    t, c = status_headline({"cap_screens": False, "cap_audio": False, "paused": False})
    check("cattura spenta NON è verde", t == "Cattura disattivata" and c != theme.EMERALD, t)
    t, _ = status_headline({"cap_screens": True, "cap_audio": False, "paused": False})
    check("solo schermate", t == "Solo schermate", t)
    t, _ = status_headline({"cap_screens": False, "cap_audio": True, "paused": False})
    check("solo audio", t == "Solo audio", t)
    check("stato vuoto non esplode", status_headline({})[0] == "Stato sconosciuto")
    check("None non esplode", status_headline(None)[0] == "Stato sconosciuto")


def test_collect():
    print("\n[3] collect_status sul DB reale")
    from ui.app_shell import collect_status

    t0 = time.time()
    cheap = collect_status(full=False)
    t_cheap = time.time() - t0
    t0 = time.time()
    full = collect_status(full=True)
    t_full = time.time() - t0
    print(f"       economico {t_cheap * 1000:.0f} ms · completo {t_full * 1000:.0f} ms")

    check("nessun errore DB", "db_error" not in full, full.get("db_error", ""))
    for k in ("db_bytes", "disk_free", "cap_screens", "paused", "last_ss", "encrypted"):
        check(f"giro economico ha '{k}'", k in cheap)
    check("giro economico NON fa i COUNT", "n_ss" not in cheap)
    for k in ("n_ss", "n_au", "n_web", "n_ev", "n_ss_emb", "first_ts"):
        check(f"giro completo ha '{k}'", k in full)
    check("il giro economico è molto più rapido", t_cheap < max(0.25, t_full / 2),
          f"{t_cheap:.3f}s vs {t_full:.3f}s")
    check("crescita calcolata", isinstance(full.get("bytes_day"), float))
    check("autonomia calcolata", isinstance(full.get("days_left"), float))

    # Deve reggere anche senza DB leggibile: nessuna eccezione fuori.
    import paths
    orig = paths.db_path
    paths.db_path = lambda: os.path.join(paths.data_dir(), "non_esiste_.db")
    try:
        st = collect_status(full=False)
    finally:
        paths.db_path = orig
    check("DB assente → nessuna eccezione", isinstance(st, dict))
    check("DB assente → dimensione 0", st.get("db_bytes") == 0, str(st.get("db_bytes")))


def test_poller():
    print("\n[4] StatusPoller: cadenza a due velocità, niente worker accodati")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from ui.app_shell import StatusPoller

    app = QApplication.instance() or QApplication([])
    seen = []
    p = StatusPoller(lambda st: seen.append(dict(st)), full_every=3600.0)

    p.tick(force_full=True)          # 1° giro: completo
    p.tick()                         # ignorato: worker ancora in volo
    while p.busy():
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    check("primo giro completo ha i totali", seen and "n_ss" in seen[0], str(list(seen[0])[:5]) if seen else "")
    n_after_full = len(seen)

    p.tick()                         # full_every alto → giro economico
    while p.busy():
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    check("secondo giro è economico", len(seen) == n_after_full + 1)
    check("i totali restano (fotografie fuse)", "n_ss" in seen[-1] and "n_ss" in p.state)
    check("lo stato si aggiorna comunque", seen[-1].get("ts") != seen[0].get("ts"))


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.getcwd())
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # nessuna finestra: solo logica
    test_formatters()
    test_headline()
    test_collect()
    test_poller()
    print("\n" + ("TUTTI OK" if not FAIL else f"FALLITI {len(FAIL)}: " + ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)
