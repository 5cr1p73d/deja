# i18n.py
"""
Localizzazione UI dell'app Déjà (it/en/es), basata su dizionario.

La lingua è salvata in settings (`ui_language`). Se non impostata, si prova a
dedurla dal sistema. Cambiare lingua aggiorna le UI ricostruite dopo il cambio
(tray, dialog); per una traduzione completa basta riavviare.
"""
import locale as _loc

DEFAULT = "it"
LANGUAGES = {"it": "Italiano", "en": "English", "es": "Español"}
LANG_FLAGS = {"it": "🇮🇹", "en": "🇬🇧", "es": "🇪🇸"}

# Nome lingua per istruire l'AI a rispondere in quella lingua.
AI_LANG_NAME = {"it": "italiano", "en": "English", "es": "español"}

_TR = {
    "it": {
        # ── Tray ──
        "tray.open": "Apri Deja",
        "tray.audio_settings": "⚙️ Impostazioni audio",
        "tray.ai_settings": "🤖 Impostazioni AI",
        "tray.diary": "📖 Diario AI",
        "tray.ask_screen": "👁 Chiedi allo schermo  (Ctrl+Shift+A)",
        "tray.backup": "📦 Backup DB…",
        "tray.restore": "📥 Ripristina DB…",
        "tray.privacy": "🛡 Privacy",
        "tray.pause_5": "Pausa 5 min",
        "tray.pause_15": "Pausa 15 min",
        "tray.pause_30": "Pausa 30 min",
        "tray.pause_2h": "Pausa 2 ore",
        "tray.resume": "▶ Riprendi cattura",
        "tray.restart_audio": "🔄 Riavvia cattura audio",
        "tray.autostart": "🚀 Avvia con Windows",
        "tray.about": "ℹ️ Informazioni su Déjà",
        "tray.quit": "❌ Esci",
        "tray.tooltip_active": "Déjà — registrazione attiva",
        "tray.tooltip_paused": "Déjà — in pausa",
        "tray.paused_for": "🛡 Cattura in pausa: {label}",
        "tray.resumed": "▶ Cattura ripresa",
        "tray.autostart_on": "Avvio con Windows attivato",
        "tray.autostart_off": "Avvio con Windows disattivato",
        "tray.autostart_fail": "Impossibile cambiare l'avvio automatico.",
        "tray.restart_audio_msg": "🔄 Riavvio cattura audio…",
        # ── About ──
        "about.title": "Informazioni su Déjà",
        "about.ocr_active": "attivo",
        "about.ocr_missing": "non disponibile (installa Tesseract)",
        "about.body": "<b>Déjà</b> v{version}<br><br>La memoria locale del tuo PC: cattura schermo e audio, li indicizza in locale e li rende cercabili con l'AI.<br><br><b>OCR:</b> {ocr}<br><b>Lingua:</b> {lang}<br><b>Dati:</b> {data}<br><b>Log:</b> {log}<br><br>100% on-device · nessun cloud.<br>Costruito da Scr1p73d.",
        # ── Onboarding ──
        "onb.title": "Benvenuto in Déjà",
        "onb.subtitle": "v{version} · la memoria locale del tuo PC",
        "onb.lang": "Lingua",
        "onb.intro": "Déjà cattura periodicamente <b>schermo</b> e <b>audio</b>, li trascrive e li indicizza <b>sul tuo computer</b>, così puoi ricercare a parole tue qualsiasi cosa tu abbia visto o sentito.",
        "onb.privacy_title": "La tua privacy",
        "onb.p_local": "I dati restano <b>in locale</b>: niente cloud, nessun account.",
        "onb.p_redact": "Dati sensibili (carte, IBAN, email…) <b>oscurati</b> nell'OCR.",
        "onb.p_pause": "Metti in <b>pausa</b> quando vuoi e auto-pausa quando sei inattivo o il PC è bloccato.",
        "onb.deps_title": "Stato componenti",
        "onb.ocr_ok": "OCR (Tesseract) trovato: il testo a schermo sarà cercabile.",
        "onb.ocr_missing": "OCR (Tesseract) non trovato: l'app funziona ma senza testo dagli screenshot. Installa Tesseract da <a href='https://github.com/UB-Mannheim/tesseract/wiki' style='color:#a78bfa;'>qui</a> per abilitarlo.",
        "onb.models_note": "Al primo utilizzo verranno scaricati i modelli vocale e di ricerca (qualche minuto, una sola volta).",
        "onb.ai_note": "La chat AI è <b>opzionale</b>: aggiungi una API key in Impostazioni → AI quando vuoi.",
        "onb.consent": "Acconsento alla cattura di schermo e audio sul mio PC. Ho capito che i dati restano in locale.",
        "onb.start": "Inizia a usare Déjà",
        "onb.exit": "Esci",
        # ── Settings ──
        "set.ui_language": "Lingua interfaccia",
        "set.ocr_language": "Lingue OCR (schermo)",
        "set.restart_note": "Alcune modifiche si applicano al riavvio.",
    },
    "en": {
        "tray.open": "Open Deja",
        "tray.audio_settings": "⚙️ Audio settings",
        "tray.ai_settings": "🤖 AI settings",
        "tray.diary": "📖 AI diary",
        "tray.ask_screen": "👁 Ask the screen  (Ctrl+Shift+A)",
        "tray.backup": "📦 Backup DB…",
        "tray.restore": "📥 Restore DB…",
        "tray.privacy": "🛡 Privacy",
        "tray.pause_5": "Pause 5 min",
        "tray.pause_15": "Pause 15 min",
        "tray.pause_30": "Pause 30 min",
        "tray.pause_2h": "Pause 2 hours",
        "tray.resume": "▶ Resume capture",
        "tray.restart_audio": "🔄 Restart audio capture",
        "tray.autostart": "🚀 Start with Windows",
        "tray.about": "ℹ️ About Déjà",
        "tray.quit": "❌ Quit",
        "tray.tooltip_active": "Déjà — recording active",
        "tray.tooltip_paused": "Déjà — paused",
        "tray.paused_for": "🛡 Capture paused: {label}",
        "tray.resumed": "▶ Capture resumed",
        "tray.autostart_on": "Start with Windows enabled",
        "tray.autostart_off": "Start with Windows disabled",
        "tray.autostart_fail": "Couldn't change auto-start.",
        "tray.restart_audio_msg": "🔄 Restarting audio capture…",
        "about.title": "About Déjà",
        "about.ocr_active": "active",
        "about.ocr_missing": "unavailable (install Tesseract)",
        "about.body": "<b>Déjà</b> v{version}<br><br>Your PC's local memory: it captures your screen and audio, indexes them locally and makes them searchable with AI.<br><br><b>OCR:</b> {ocr}<br><b>Language:</b> {lang}<br><b>Data:</b> {data}<br><b>Logs:</b> {log}<br><br>100% on-device · no cloud.<br>Built by Scr1p73d.",
        "onb.title": "Welcome to Déjà",
        "onb.subtitle": "v{version} · your PC's local memory",
        "onb.lang": "Language",
        "onb.intro": "Déjà periodically captures your <b>screen</b> and <b>audio</b>, transcribes and indexes them <b>on your computer</b>, so you can search in your own words anything you've seen or heard.",
        "onb.privacy_title": "Your privacy",
        "onb.p_local": "Data stays <b>local</b>: no cloud, no account.",
        "onb.p_redact": "Sensitive data (cards, IBAN, email…) <b>redacted</b> in OCR.",
        "onb.p_pause": "<b>Pause</b> whenever you want, plus auto-pause when you're idle or the PC is locked.",
        "onb.deps_title": "Component status",
        "onb.ocr_ok": "OCR (Tesseract) found: on-screen text will be searchable.",
        "onb.ocr_missing": "OCR (Tesseract) not found: the app works but without text from screenshots. Install Tesseract from <a href='https://github.com/UB-Mannheim/tesseract/wiki' style='color:#a78bfa;'>here</a> to enable it.",
        "onb.models_note": "On first use the speech and search models will be downloaded (a few minutes, once).",
        "onb.ai_note": "AI chat is <b>optional</b>: add an API key in Settings → AI whenever you want.",
        "onb.consent": "I consent to capturing screen and audio on my PC. I understand the data stays local.",
        "onb.start": "Start using Déjà",
        "onb.exit": "Quit",
        "set.ui_language": "Interface language",
        "set.ocr_language": "OCR languages (screen)",
        "set.restart_note": "Some changes apply after a restart.",
    },
    "es": {
        "tray.open": "Abrir Deja",
        "tray.audio_settings": "⚙️ Ajustes de audio",
        "tray.ai_settings": "🤖 Ajustes de IA",
        "tray.diary": "📖 Diario IA",
        "tray.ask_screen": "👁 Pregunta a la pantalla  (Ctrl+Shift+A)",
        "tray.backup": "📦 Copia de la BD…",
        "tray.restore": "📥 Restaurar BD…",
        "tray.privacy": "🛡 Privacidad",
        "tray.pause_5": "Pausa 5 min",
        "tray.pause_15": "Pausa 15 min",
        "tray.pause_30": "Pausa 30 min",
        "tray.pause_2h": "Pausa 2 horas",
        "tray.resume": "▶ Reanudar captura",
        "tray.restart_audio": "🔄 Reiniciar captura de audio",
        "tray.autostart": "🚀 Iniciar con Windows",
        "tray.about": "ℹ️ Acerca de Déjà",
        "tray.quit": "❌ Salir",
        "tray.tooltip_active": "Déjà — grabación activa",
        "tray.tooltip_paused": "Déjà — en pausa",
        "tray.paused_for": "🛡 Captura en pausa: {label}",
        "tray.resumed": "▶ Captura reanudada",
        "tray.autostart_on": "Inicio con Windows activado",
        "tray.autostart_off": "Inicio con Windows desactivado",
        "tray.autostart_fail": "No se pudo cambiar el inicio automático.",
        "tray.restart_audio_msg": "🔄 Reiniciando captura de audio…",
        "about.title": "Acerca de Déjà",
        "about.ocr_active": "activo",
        "about.ocr_missing": "no disponible (instala Tesseract)",
        "about.body": "<b>Déjà</b> v{version}<br><br>La memoria local de tu PC: captura tu pantalla y audio, los indexa en local y los hace buscables con IA.<br><br><b>OCR:</b> {ocr}<br><b>Idioma:</b> {lang}<br><b>Datos:</b> {data}<br><b>Logs:</b> {log}<br><br>100% en dispositivo · sin nube.<br>Hecho por Scr1p73d.",
        "onb.title": "Bienvenido a Déjà",
        "onb.subtitle": "v{version} · la memoria local de tu PC",
        "onb.lang": "Idioma",
        "onb.intro": "Déjà captura periódicamente tu <b>pantalla</b> y <b>audio</b>, los transcribe e indexa <b>en tu ordenador</b>, para que busques con tus palabras cualquier cosa que hayas visto u oído.",
        "onb.privacy_title": "Tu privacidad",
        "onb.p_local": "Los datos se quedan <b>en local</b>: sin nube, sin cuenta.",
        "onb.p_redact": "Datos sensibles (tarjetas, IBAN, email…) <b>ocultados</b> en el OCR.",
        "onb.p_pause": "<b>Pausa</b> cuando quieras, más auto-pausa cuando estás inactivo o el PC está bloqueado.",
        "onb.deps_title": "Estado de componentes",
        "onb.ocr_ok": "OCR (Tesseract) encontrado: el texto en pantalla será buscable.",
        "onb.ocr_missing": "OCR (Tesseract) no encontrado: la app funciona pero sin texto de las capturas. Instala Tesseract desde <a href='https://github.com/UB-Mannheim/tesseract/wiki' style='color:#a78bfa;'>aquí</a> para activarlo.",
        "onb.models_note": "En el primer uso se descargarán los modelos de voz y búsqueda (unos minutos, una sola vez).",
        "onb.ai_note": "El chat IA es <b>opcional</b>: añade una API key en Ajustes → IA cuando quieras.",
        "onb.consent": "Consiento la captura de pantalla y audio en mi PC. Entiendo que los datos se quedan en local.",
        "onb.start": "Empezar a usar Déjà",
        "onb.exit": "Salir",
        "set.ui_language": "Idioma de la interfaz",
        "set.ocr_language": "Idiomas OCR (pantalla)",
        "set.restart_note": "Algunos cambios se aplican al reiniciar.",
    },
}

_current = None


def _system_lang() -> str:
    try:
        code = (_loc.getdefaultlocale()[0] or "")[:2].lower()
        if code in _TR:
            return code
    except Exception:
        pass
    return "en"


def get_language() -> str:
    global _current
    if _current is None:
        try:
            from db import get_setting
            saved = get_setting("ui_language", "")
        except Exception:
            saved = ""
        _current = saved if saved in _TR else _system_lang()
    return _current if _current in _TR else DEFAULT


def set_language(lang: str):
    global _current
    if lang in _TR:
        _current = lang
        try:
            from db import save_setting
            save_setting("ui_language", lang)
        except Exception:
            pass


def t(key: str, **kwargs) -> str:
    lang = get_language()
    s = _TR.get(lang, {}).get(key) or _TR[DEFAULT].get(key) or key
    if kwargs:
        try:
            return s.format(**kwargs)
        except Exception:
            return s
    return s


def ai_language_name() -> str:
    return AI_LANG_NAME.get(get_language(), "italiano")
