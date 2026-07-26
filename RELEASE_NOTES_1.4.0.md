# Déjà 1.4.0

Your private, on-device memory for Windows. This release is about **speed, honesty and control**: search is now backed by a real full-text index, the assistant stopped getting the clock wrong, the sidebar tells you the truth about what's happening, and there's a **Linux build** for the first time.

Everything still stays on your machine, encrypted (SQLCipher + DPAPI).

## ⚡ Search, rebuilt

- **Full-text index (FTS5).** Text search used to scan three whole tables on every query. It now runs against a proper index — milliseconds instead of seconds, even on an archive of hundreds of thousands of memories. The index is built once in the background, in small batches, and resumes exactly where it left off if you close the app mid-way.
- **Half the memory.** The embedding model was being loaded **twice** (once by the indexer, once by search). Now there's a single shared instance — about 1 GB of RAM back, and your first search is already warm.
- **Results arrive in one trip.** Rows are fetched in batches instead of one query per result, and audio blobs are no longer dragged into search results (they're loaded only when you actually open a recording).
- **Repeated searches are instant** thanks to a query-embedding cache.

## 🧠 Assistant: got the clock right

The biggest fix in this release. Timestamps are stored in UTC, but the assistant was being told "today is *this* date" in **your local time** — so every hour it quoted back to you was **off by one or two hours**. Worse, when it asked for "today", it actually got 02:00 → 01:59 local: the first hours of your day were missing and yesterday evening was included.

Times are now converted once, at the point where they're handed to the model, and day ranges are interpreted as **your local days**. "What time did I open Chrome?" finally answers with the time you actually saw.

## 🧠 Assistant: better answers

- **Rewritten system prompt.** Shorter and denser, with things that simply weren't said before: what to do when memories **contradict each other** (report both, with source and time — don't silently pick one), when OCR looks garbled (flag it, don't "fix" it), and when to **stop searching** and answer.
- **Agentic search is now a superset.** When the parallel agents come up empty, the assistant falls back to the adaptive tool loop instead of replying "I found nothing" — so it can widen the time window, try different wording, or read a memory in full.
- **Multi-angle search in one call.** The assistant can now search several phrasings at once and fuse the results, which finds answers phrased the way you'd actually say them ("see you around 3" answers "what time is the technician coming?").
- **Read the whole thing.** A new tool lets the assistant open the **complete text** of a single memory when the snippet is cut off exactly where the price or the time was.
- **No more reasoning leaking into answers.** Models that emit `<think>` blocks were flooding replies with their own scratchpad and getting stuck repeating themselves. Filtered out everywhere, including mid-stream.

## 📊 Live status panel (new)

The block at the bottom of the sidebar used to be decoration: "Capture active" was hard-coded text that stayed green even while paused, the archive count only reflected the page currently loaded, and "local · encrypted" was a fixed string that would claim encryption even if there wasn't any.

It's now real, and you can click it:

- **True capture state** — active, paused (with time left), incognito, screen-only, audio-only, or off — with a dot that pulses only when something is actually being recorded.
- **Real totals**: screenshots, audio, web pages, events; disk used; time since the last memory.
- **Pause/resume inline**, without opening a menu.
- **Full panel** on click: growth in MB/day, free space, **estimated days of headroom**, indexing progress, search index state, encryption and key backend, app lock status. Plus *Open data folder*.

Collecting all that is kept off the UI thread and split into a fast tick and a slower full refresh, so it never gets in the way of capture.

## 💬 Chat, redesigned

- **One activity box per turn.** Every step the assistant took used to become a permanent chip; an agentic answer left 10–15 lines of progress buried in your history forever. Now a single live box shows the current step, expands if you want to follow along, and collapses to `✓ 9 steps · 2.3s` when it's done.
- **Stop button.** You can interrupt a long answer instead of waiting it out.
- **Multi-line input** that grows as you type — Enter sends, Shift+Enter adds a line — and stays editable while the assistant replies.
- **Suggestions on the empty chat**, one per source, so it's clear what you can actually ask.

## 🐧 Linux (experimental)

First Linux build (X11): XDG data directories with 0700 permissions, secrets in the system keyring (SecretService/KWallet), idle detection via XScreenSaver, screen-lock detection over D-Bus, active window through xdotool, PulseAudio/PipeWire monitor sources for system audio, global hotkeys via pynput, and XDG autostart. Build with `build_linux.sh`. Windows behaviour is unchanged.

## 🔒 Security

- **Fixed an anti-SSRF bypass.** The check for "is this a local endpoint" matched anywhere in the URL, so a host like `localhost.example.com` was treated as local and skipped the whole safety check (plain HTTP allowed, private and cloud-metadata IPs unblocked). It now parses the hostname properly.
- **The model list button no longer leaks your API key.** "Detect models" sent your key to whatever URL was in the box, with no endpoint check — the same guard the rest of the app already used is now applied there too.
- **Browser page text no longer written in the clear when the bridge is off.** With the browser integration disabled or paused, the native host still wrote the **full text of every page you visited** (unredacted) to a plaintext spool file, where it sat for up to six hours — or forever, if Déjà wasn't running to clean it up. Page capture now requires explicit, **expiring** authorization from the app: if Déjà is closed, paused, or killed, nothing gets written.
- Extension ID validation tightened, and the native host now uses the same data directory as the app on every platform.

## 🔧 Other fixes

- **Search stopped hiding recent memories.** The per-term result cap kept the *oldest* matches, so for any common word everything recent silently vanished from text search.
- **Closing the app is fast again.** Shutdown ran a full `VACUUM` on every exit — a complete rewrite of the database file, minutes on a large archive, to reclaim essentially nothing. Replaced with a WAL checkpoint.
- **Long conversations no longer break.** The assistant's context was trimmed once and then grew unchecked as tool results piled up, eventually overflowing the model's limit mid-conversation.
- **Small talk doesn't trigger a search.** Saying "thanks" used to run a full memory search before it could reply.
- **You always get an answer.** Running out of tool steps used to end the turn with an error and nothing else, throwing away everything already found.
- **Valid short answers are no longer swallowed.** A reply like "No Python errors, but you opened Chrome at 15:04" was being mistaken for a "nothing found" and discarded.
- Endpoints that reject optional parameters are now remembered, instead of wasting a failed request on every single step.

---

**Install**: `Deja-Setup-1.4.0.exe` (installer) or `Deja-1.4.0-win64.zip` (portable).
**Browser integration** (optional): `deja-extension-1.4.0.zip` — load unpacked in Chrome/Edge, then register the native host from Settings → Browser.
