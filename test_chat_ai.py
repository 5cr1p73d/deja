r"""
Test della chat AI: fix orari, loop tool, sentinel, smalltalk, capability endpoint.
Vedi obsidian/deja/ChatAI-Overhaul-progress.md.

Nessuna rete: il client OpenAI è finto.
    .\venv\Scripts\python.exe test_chat_ai.py
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

FAIL = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


# ── 1. Orari: UTC nel DB → ora LOCALE per il modello ───────────────
def test_timezone():
    print("\n[1] orari mostrati al modello = ora locale")
    from modules.ai_assistant import _ts_local, _norm_bound

    # Istante noto in UTC → deve uscire nell'offset locale della macchina.
    utc = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)
    local = utc.astimezone()
    got = _ts_local(utc.isoformat())
    check("UTC → locale", got == local.strftime("%Y-%m-%d %H:%M:%S"), got)
    off_h = local.utcoffset().total_seconds() / 3600
    print(f"       (offset locale {off_h:+.0f}h, {utc:%H:%M} UTC → {got[11:16]} locale)")
    if off_h != 0:
        check("l'ora NON è più quella UTC grezza", got[11:16] != "12:00", got)
    check("ts naive trattato come UTC", _ts_local("2026-07-26T12:00:00") == got)
    check("ts vuoto", _ts_local(None) == "?")
    check("ts spazzatura non esplode", isinstance(_ts_local("boh"), str))

    # Un giorno indicato dal modello = giorno LOCALE, convertito in UTC.
    lo = _norm_bound("2026-07-26", is_end=False)
    hi = _norm_bound("2026-07-26", is_end=True)
    lo_dt, hi_dt = datetime.fromisoformat(lo), datetime.fromisoformat(hi)
    check("start è mezzanotte LOCALE", lo_dt.astimezone().strftime("%H:%M:%S") == "00:00:00",
          lo_dt.astimezone().isoformat())
    check("end è fine giornata LOCALE", hi_dt.astimezone().strftime("%H:%M") == "23:59",
          hi_dt.astimezone().isoformat())
    check("la finestra dura 24h", 86390 < (hi_dt - lo_dt).total_seconds() <= 86400,
          str((hi_dt - lo_dt).total_seconds()))
    check("i confini sono in UTC per il confronto sul DB",
          lo.endswith("+00:00") and hi.endswith("+00:00"), f"{lo} {hi}")
    # Confronto lessicografico con un ts del DB (è così che filtra il codice).
    mid = datetime(2026, 7, 26, 10, 30, tzinfo=None).astimezone().astimezone(timezone.utc).isoformat()
    check("un ts a metà giornata cade nella finestra", lo <= mid <= hi, f"{lo} <= {mid} <= {hi}")
    # Il vecchio bug: la prima ora locale del giorno finiva FUORI finestra.
    early = datetime(2026, 7, 26, 0, 30, tzinfo=None).astimezone().astimezone(timezone.utc).isoformat()
    check("le 00:30 locali sono dentro 'oggi'", lo <= early <= hi, f"{lo} <= {early}")
    check("ISO con ora esplicita passa", "T" in _norm_bound("2026-07-26T20:10:00", is_end=False))


# ── 2. Sentinel "niente": niente falsi positivi ────────────────────
def test_is_nothing():
    print("\n[2] _is_nothing")
    from modules.ai_assistant import _is_nothing

    for t in ("NIENTE", "niente.", "", "   ", "Non ho trovato nulla di rilevante",
              "Nessun ricordo pertinente."):
        check(f"riconosce non-risposta: {t[:34]!r}", _is_nothing(t) is True)
    # Questi PRIMA venivano scambiati per non-risposte e buttati via.
    for t in ("Nessun errore Python, ma alle 15:04 hai aperto Chrome",
              "Non ho trovato la fattura, però il preventivo era 1.250 € [web:88]",
              "Nulla di rilevante negli screenshot; l'audio delle 14:02 sì [au:9]"):
        check(f"NON scarta la risposta valida: {t[:38]!r}", _is_nothing(t) is False)
    check("testo lungo mai considerato niente", _is_nothing("Non ho trovato " + "x" * 200) is False)


# ── 3. Chiacchiera: niente ricerca forzata ─────────────────────────
def test_smalltalk():
    print("\n[3] _looks_like_smalltalk")
    from modules.ai_assistant import _looks_like_smalltalk

    for m in ("ciao", "Ciao!", "grazie mille", "ok", "perfetto, grazie", "buongiorno",
              "scusa", "come stai?", "ahahah"):
        check(f"chiacchiera: {m!r}", _looks_like_smalltalk(m) is True)
    for m in ("cosa ho fatto ieri?", "quanto ho speso per la sedia",
              "ciao, a che ora ho aperto Chrome?", "riassumi la telefonata",
              "ok e quanto costava?", "no, intendevo la pagina di ieri"):
        check(f"vera domanda: {m[:34]!r}", _looks_like_smalltalk(m) is False)


# ── 4. Trim del contesto consapevole dei tool ──────────────────────
def test_trim():
    print("\n[4] _trim_for_tools")
    from modules.ai_assistant import _trim_for_tools, _approx_tokens, _clip_tool_result

    msgs = [{"role": "system", "content": "S"}]
    for i in range(6):
        msgs.append({"role": "user", "content": f"domanda {i}"})
        msgs.append({"role": "assistant", "content": None,
                     "tool_calls": [{"id": f"c{i}", "type": "function",
                                     "function": {"name": "search_memories", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 8000})

    out = _trim_for_tools(msgs, 2000)
    # O rientra nel budget, o è già ridotto al minimo indispensabile (system +
    # ultimo blocco): l'ultimo blocco non si scarta mai, o il modello perde la
    # domanda a cui deve rispondere.
    minimal = len(out) <= 4
    check("rientra nel budget (o è già al minimo)", _approx_tokens(out) <= 2000 or minimal,
          f"{_approx_tokens(out)} tok, {len(out)} msg")
    check("ha buttato via la roba vecchia", len(out) < len(msgs), f"{len(out)}/{len(msgs)}")
    check("il system resta", out and out[0].get("role") == "system")
    # Il vincolo vero: nessun 'tool' senza la sua assistant con tool_calls prima.
    ok = True
    for i, m in enumerate(out):
        if m.get("role") == "tool":
            prev = out[i - 1] if i else None
            if not (prev and (prev.get("tool_calls") or prev.get("role") == "tool")):
                ok = False
    check("nessun messaggio tool orfano (l'API rifiuterebbe)", ok)
    check("sotto budget non tocca nulla", _trim_for_tools(msgs, 10 ** 6) is msgs)

    big = "y" * 40000
    check("risultato tool troncato", len(_clip_tool_result(big)) < 15000)
    check("nota di troncamento presente", "troncato" in _clip_tool_result(big))
    check("risultato piccolo intatto", _clip_tool_result("ciao") == "ciao")


# ── 5. Capability endpoint memorizzate ─────────────────────────────
def test_ep_caps():
    print("\n[5] capability endpoint")
    from modules import ai_assistant as a

    a._EP_CAPS["key"] = None
    check("di default si prova tool_choice", a._ep_supports("tool_choice") is True)
    a._ep_mark_unsupported(["tool_choice"], "400 unsupported")
    check("dopo il rifiuto non si riprova", a._ep_supports("tool_choice") is False)
    check("gli altri parametri restano", a._ep_supports("frequency_penalty") is True)
    a._EP_CAPS["key"] = ("altro-endpoint", "altro-modello")
    check("cambio endpoint → si riparte da zero", a._ep_supports("tool_choice") is True)


# ── 6. Loop a tool: chiusura garantita, niente turno vuoto ─────────
class _FakeStream:
    """Stream OpenAI finto: emette testo e/o una tool call."""

    def __init__(self, text=None, tool=None):
        self._text, self._tool = text, tool

    def __iter__(self):
        class D:  # delta
            content = None
            tool_calls = None

        class C:
            finish_reason = None
            delta = None

        class Ch:
            choices = None

        if self._tool:
            class TC:
                index = 0
                id = "call_1"

                class function:
                    name = None
                    arguments = None
            tc = TC()
            tc.function.name = self._tool[0]
            tc.function.arguments = self._tool[1]
            d = D(); d.tool_calls = [tc]
            c = C(); c.delta = d; c.finish_reason = "tool_calls"
            ch = Ch(); ch.choices = [c]
            yield ch
        if self._text:
            d = D(); d.content = self._text
            c = C(); c.delta = d; c.finish_reason = "stop"
            ch = Ch(); ch.choices = [c]
            yield ch


class _FakeClient:
    """Client che chiama SEMPRE un tool: forza l'esaurimento delle iterazioni."""

    def __init__(self):
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.calls.append(kw)
        if kw.get("tools"):
            return _FakeStream(tool=("list_recent", '{"hours": 2}'))
        return _FakeStream(text="Ecco cosa ho trovato: nulla di che alle 15.")


def test_tool_loop_closes():
    print("\n[6] loop a tool: risposta garantita anche a iterazioni esaurite")
    from modules import ai_assistant as a

    fake = _FakeClient()
    orig_client, orig_agentic = a._client, a.agentic_enabled
    a._client = lambda: (fake, "fake-model")
    a.agentic_enabled = lambda: False
    try:
        evs = list(a.chat_stream([], "cosa ho fatto nelle ultime due ore?"))
    finally:
        a._client, a.agentic_enabled = orig_client, orig_agentic

    kinds = [e[0] for e in evs]
    text = "".join(e[1] for e in evs if e[0] == "text")
    check("il turno finisce", kinds[-1] == "done", str(kinds[-3:]))
    check("l'utente riceve una risposta", bool(text.strip()), repr(text[:60]))
    check("nessun errore secco 'limite iterazioni'",
          not any(e[0] == "error" and "Limite iterazioni" in str(e[1]) for e in evs))
    n_tool_calls = sum(1 for kw in fake.calls if kw.get("tools"))
    check(f"si ferma a {a.MAX_TOOL_ITERATIONS} giri con tool", n_tool_calls == a.MAX_TOOL_ITERATIONS,
          str(n_tool_calls))
    check("chiusura finale SENZA tool", any(not kw.get("tools") for kw in fake.calls))


def test_smalltalk_no_forced_tool():
    print("\n[7] chiacchiera: nessuna ricerca forzata")
    from modules import ai_assistant as a

    class Chatty(_FakeClient):
        def create(self, **kw):
            self.calls.append(kw)
            return _FakeStream(text="Ciao! Dimmi pure.")

    fake = Chatty()
    orig_client, orig_agentic = a._client, a.agentic_enabled
    a._client = lambda: (fake, "fake-model")
    a.agentic_enabled = lambda: False
    a._EP_CAPS["key"] = None
    try:
        evs = list(a.chat_stream([], "ciao"))
    finally:
        a._client, a.agentic_enabled = orig_client, orig_agentic

    first = fake.calls[0]
    check("niente tool_choice='required' su 'ciao'", first.get("tool_choice") is None,
          str(first.get("tool_choice")))
    check("risponde subito", any(e[0] == "text" for e in evs))

    fake2 = Chatty()
    a._client = lambda: (fake2, "fake-model")
    a.agentic_enabled = lambda: False
    try:
        list(a.chat_stream([], "quanto ho speso per la sedia?"))
    finally:
        a._client, a.agentic_enabled = orig_client, orig_agentic
    check("su una vera domanda il tool resta forzato",
          fake2.calls[0].get("tool_choice") == "required", str(fake2.calls[0].get("tool_choice")))


def test_ui_widgets():
    print("\n[8] widget chat: attività di turno, input, stop")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent
    from ui.window import TurnActivity, ChatInput

    app = QApplication.instance() or QApplication([])

    act = TurnActivity()
    for s in ("🧠 Ricerca agentica · tecnico", "👥 3 agenti · 42 ricordi",
              "  ✓ Agente 1 — ha trovato qualcosa", "✍️ Sintesi finale…"):
        act.add_step(s)
    check("i passi stanno in UN solo widget", len(act._steps) == 4)
    check("la testa mostra il passo corrente", "Sintesi" in act._label.text(), act._label.text())
    check("il contatore segue", act._count.text() == "4", act._count.text())
    check("dettaglio chiuso di default", act._detail.isVisible() is False)
    act._toggle()
    check("si espande al clic", act._open is True)
    act.finish()
    check("collassa in riepilogo", "passagg" in act._label.text(), act._label.text())
    check("il contatore sparisce a fine turno", act._count.text() == "")
    act2 = TurnActivity(); act2.add_step("x"); act2.fail("fermato")
    check("stato interrotto", act2._label.text() == "fermato")
    check("passo vuoto ignorato", (lambda a: (a.add_step("  "), len(a._steps))[1])(TurnActivity()) == 0)

    inp = ChatInput()
    inp.show()
    sent = []
    inp.submitted.connect(lambda: sent.append(1))
    inp.setText("una riga")
    h1 = inp.height()
    inp.setText("riga\nriga\nriga\nriga")
    app.processEvents()
    check("l'input cresce col testo", inp.height() > h1, f"{h1} → {inp.height()}")
    check("ma non oltre il tetto", inp.height() <= ChatInput.MAX_H, str(inp.height()))
    inp.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, int(Qt.Key.Key_Return),
                                Qt.KeyboardModifier.NoModifier))
    check("Invio invia", len(sent) == 1, str(len(sent)))
    before = inp.toPlainText()
    inp.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, int(Qt.Key.Key_Return),
                                Qt.KeyboardModifier.ShiftModifier))
    check("Maiusc+Invio va a capo, non invia",
          len(sent) == 1 and inp.toPlainText() != before, str(len(sent)))
    check("compatibile con l'uso da QLineEdit", inp.text() == inp.toPlainText())


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.getcwd())
    test_timezone()
    test_is_nothing()
    test_smalltalk()
    test_trim()
    test_ep_caps()
    test_tool_loop_closes()
    test_smalltalk_no_forced_tool()
    test_ui_widgets()
    print("\n" + ("TUTTI OK" if not FAIL else f"FALLITI {len(FAIL)}: " + ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)
