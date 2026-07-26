# Déjà 1.2.2

Your private, on-device memory for Windows — now it also remembers **what you do**, and the AI assistant got a lot smarter about finding it.

Everything stays local and encrypted (SQLCipher + DPAPI). All new capture is **OFF by default** and opt-in per category.

## ✨ New: System & Browser Activity (opt-in)

Déjà can now record the **actions** on your PC, not just screenshots and audio. Enable any category in **Settings → Events** (all off until you turn them on):

**System events** (no admin rights required)
- Apps opened / closed (name, path, user, run time)
- Foreground app focus changes
- File created / deleted / moved in your folders (configurable list)
- Programs installed / updated / uninstalled (name, version, publisher)
- USB drives and disks connected / removed
- Network interfaces up / down
- Sleep / resume (with duration), session lock / unlock, system clock changes

**Browser events** (via the Déjà browser extension)
- Downloads (file name, source, size)
- Tabs opened / closed
- Pages visited (URL + title)

How it shows up:
- A new **"Events"** filter in the Timeline (lightning-bolt items).
- A **"Show hidden"** toggle: background/system/Déjà processes are hidden by default so the timeline isn't flooded — flip it to see *everything*.
- Fully searchable by the AI assistant.

**Privacy by design**
- Off by default, per-category toggles, read live (no restart).
- Pause/incognito stops event capture too — and never back-fills activity that happened while paused.
- PII redaction applies to event details (window titles, paths, URLs).
- App blocklist is honored for focus/process events.
- "Off means nothing on disk": the browser host only writes an event to disk if that category is actually enabled.

## 🧠 Smarter AI Assistant

Fixes the cases where the assistant used to make things up or fail to find data:

- **No more hallucinations.** It must search before answering and only reports what the tools actually return — and clearly says when it found nothing instead of inventing a summary.
- **Knows where to look.** Routes "when did I open/close an app", "what did I download", "which programs did I install" to the events log; "what was on that page / what did I read" to web pages; "what was being said" to audio.
- **Web page transcriptions are finally used** (and were previously shown empty by a bug). Citations now include clickable **web cards** that open the page.
- **"What was said while I was playing X"** now works: it finds the time window from screenshots/events, then pulls the audio from exactly that window.
- **Mic vs. system audio** is understood: microphone = you talking; system audio = your speakers (another person *or* a video/music — not always a conversation).
- **Better dates & retrieval:** today's date is anchored (correct "today/yesterday"), single-day queries are exact, and results warn when truncated so it narrows instead of giving up.
- More robust under the hood: anti-repetition, higher tool budget, and tolerant tool-name matching.

## 🔧 Notes
- Updating the browser extension? It now requests the `downloads` permission for download events — your browser will ask you to re-enable it.
- Existing databases migrate automatically on first launch.

---
*Déjà is local-first: your screenshots, audio, pages and events never leave your machine. The optional AI assistant only sends the text it needs to answer your question to the model endpoint you configured.*
