# Déjà 1.3.0

Your private, on-device memory for Windows. This release makes audio capture **reliable across reboots**, gives the AI assistant a powerful new **agentic search**, and adds a full **audio browser** so you can reach any recording — old ones included.

Everything stays local and encrypted (SQLCipher + DPAPI).

## 🎧 Audio capture that survives reboots

- **Primary + backup devices.** Pick a main and a fallback source for both the microphone and system audio (e.g. *headphones → speakers*). Déjà uses the main one; if it isn't connected it falls back automatically.
- **Live switching, no restart.** Plug or unplug your headphones while Déjà is running and it switches on the fly (mic and system audio both).
- **Reboot-proof.** Devices are now stored by **name** instead of by index, so a restart no longer scrambles your capture settings.
- **Clearer settings.** Capture settings are grouped into **🎙 Microphone** and **🔊 System audio**, each with a *Primary* and *Backup* choice, plus a **Detect devices** button to pick up gear you connected after launch.

## 🧠 Agentic search (opt-in)

A new mode for the assistant, toggled in **Settings → AI Assistant**. When on, a question is split into several angles and answered by **multiple agents working in parallel**:

- **Faster and bigger.** Agents run concurrently, and each has its own token budget — together they process **far more context than a single request** and won't get cut off by per-answer limits. Sizing adapts to your model's real context/output limits.
- **You can see them work.** Live progress shows how many agents are running and what each one is looking at.
- **Knows when to use them.** A router decides whether a question actually needs a search (small talk gets a normal reply, no agents wasted) and how many angles to open.
- **Searches the way you'd actually say it.** It expands your question into synonyms and real phrasings, and picks up **indirect clues** — e.g. "what time is the technician coming?" is answered by "see you around 3" even if nobody said the word *technician*.
- **Recent conversations.** Ask about "the call from earlier" and it pulls the recent audio and summarizes it — even when the other person's name never appears in the transcript, and even when a phone call was captured entirely on your mic (it works out who's who from the dialogue).

## 🔎 Better retrieval (both modes)

- **Finds details buried in a page.** Results now show the **relevant snippet** (around your terms and any prices) instead of the top of the page — so "how much did I spend on X" actually finds the price.
- **Web pages are no longer crowded out** of results by screenshots.

## 🗂️ Audio browser + context

- **Gallery → Audio.** A new section lists **all** your recordings with a **date and time filter** (pick a day and an hour range). This reaches old audio that the timeline (recent-only) couldn't.
- **Nearby audio.** While viewing a recording, jump to the ones **before/after within ± N minutes** — handy for following a conversation across segments.
- **Date & time shown.** The player now displays exactly **when** a recording was made.

## 🔧 Fixes

- Audio playback is **no longer interrupted** when the timeline refreshes in the background.
- Long transcripts are **no longer clipped** on the right edge of the detail panel.
- The Gallery/Timeline top bar no longer slips **under the window buttons**.

---
*Déjà is local-first: your screenshots, audio, pages and events never leave your machine. The optional AI assistant only sends the text it needs to answer your question to the model endpoint you configured.*
