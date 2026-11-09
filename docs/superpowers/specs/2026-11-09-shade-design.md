# Shade — real-time call assistant (design)

Date: 2026-11-09

## Intent and the why

During live calls in English (presentations, work meetings with colleagues,
interviews), the user wants to react instantly to questions and tasks,
including tricky ones. Shade runs in the Windows tray, listens to both sides
of the call (microphone = the user, system audio = the other side), keeps a
live transcript, detects questions/tasks, and shows a short, ready-to-say
answer from an AI model within seconds. The model is guided by a per-call
**profile** `.md` file that describes the user's skills and what the call is
about.

Speed and glanceability matter more than completeness: a hint that arrives
late or is too long to read mid-sentence is useless.

## Goals

1. Tray app on Windows 11; start/stop a session from the tray.
2. Capture two sources at once: microphone ("Me") and system audio loopback
   ("Them"). Speaker label comes from the source, not from diarization.
3. Live English transcription shown on screen as the call goes.
4. Two trigger modes, user-selectable (and switchable mid-session):
   - **Auto**: Shade detects a question or task in "Them" speech and answers.
   - **Hotkey**: a global hotkey sends the latest part of the conversation
     to the model.
   Both can be enabled at once.
   - **Screenshot**: a global hotkey starts a region selection (drag a
     rectangle over any screen); the captured image is sent to the model
     (vision input) as the task — e.g. code shown on the other side's shared
     screen. The image goes together with the recent transcript, so the
     user can use audio only, screenshot only, or both.
   In Hotkey mode the model answers the **last question asked** in the
   conversation.
5. AI provider, user-selectable: **Claude (Anthropic API)**, an
   **OpenAI-compatible cloud service** with presets for **OpenAI, Grok (xAI),
   Groq, DeepSeek, Gemini** (plus any other via a custom base URL), or a
   **local model** via an OpenAI-compatible endpoint (Ollama, LM Studio).
   Model name configurable per provider.
6. Before a session the user picks a profile `.md` file (their skills, the
   meeting's context, instructions). It is the system prompt for the model.
7. Display mode, user-selectable:
   - **Window**: a normal resizable window (meant for a second monitor).
   - **Overlay**: semi-transparent, always-on-top layer over other windows,
     adjustable opacity, toggleable click-through.
8. Both the window and the overlay are **excluded from screen capture**, so
   people don't see them when the user shares their screen.
9. After each session, saved to disk: the full transcript (timestamps,
   Me/Them labels) and every hint (timestamp, the question it answered,
   provider/model, the answer).
10. Everything in English: UI, transcript, hints, saved files.

## Latency and hint format (anti-goal guards)

- **Target:** first words of a hint visible within 2–3 s after the other side
  stops speaking. Rough budget: end-of-utterance detection ~0.5–0.7 s, STT
  ~0.3–0.5 s, model time-to-first-token ~0.5–1.5 s.
- Hints **stream** onto the screen token by token.
- **Format:** first a 1–3 line answer the user can say aloud right away;
  below it, optional short supporting points; code or task solutions in a
  separate code block. The profile can refine style, but the short answer
  always comes first.

## Anti-goals (failure even if it "works")

- Hints arrive too late to use.
- Hints are too long to read during the call.
- The window or overlay is visible to others during screen sharing.
- The transcript or hints are lost if the app crashes mid-call.
- The app makes the call laggy (CPU/GPU hogging that hurts the meeting app).

## Non-goals

- Languages other than English.
- macOS / Linux.
- Telling apart multiple remote speakers (all system audio is "Them").
- Speaking answers aloud (TTS) or typing them into other apps.
- Recording raw audio files (transcript only). *(Builder may add an opt-in
  debug toggle; off by default.)*

## Constraints

- Windows 11 Pro; NVIDIA RTX 3070 Ti (8 GB VRAM).
- Python 3.11 in a `uv`-managed environment (3.10/3.11/3.14 and `uv` are
  installed; 3.11 picked for compatibility with CUDA/STT libraries).
- Project folder `W:\work\python\shade` (currently empty, not yet a git repo).
- API keys for Anthropic and OpenAI provided by the user (env vars or
  settings file — never hard-coded, never written to logs or session files).
- The user will typically wear headphones; with speakers the mic picks up the
  other side too (see "Left to the builder").
- Recording other people may require their consent depending on
  jurisdiction — the user's responsibility; the app doesn't enforce it.

## Decided by the user

- Tray app; listens to mic + system audio; English calls.
- Instant reaction to questions and tasks, including tricky ones; use cases:
  interviews, presentations, work calls.
- Per-call profile `.md` chosen before the session (skills + what we're doing).
- Both display modes (window / overlay), user's choice.
- Both trigger modes (auto / hotkey), user's choice.
- Providers: Claude, OpenAI, local model — user's choice; plus cheap cloud
  presets Grok (xAI), Groq, DeepSeek, Gemini.
- Saved after session: full transcript and all AI hints.
- Tasks shown on screen: hotkey → select screen region → send image to the
  model; works alone or together with the audio context.
- The local model runs on **this same PC** (shared RTX 3070 Ti with STT and
  the meeting app).
- Trigger modes: Auto (hints switched on, Shade answers on its own) and
  Manual (hotkey answers the last question asked). No API budget cap given.
- All of the failure cases listed above matter.
- Everything in English.

## Claude's calls (user may override)

- **Language/stack:** Python 3.11, `uv`.
- **UI toolkit:** PySide6 (Qt) — tray icon, main window, overlay, settings
  dialog in one toolkit; good support for frameless/translucent/always-on-top.
- **Audio capture:** WASAPI. Mic via `sounddevice`; system audio via WASAPI
  loopback (`PyAudioWPatch` or `soundcard`). Default devices, selectable in
  settings. Resample to 16 kHz mono for STT.
- **Segmentation:** Silero VAD per source; end of utterance on ~600 ms pause
  (configurable).
- **STT:** local `faster-whisper` on CUDA (float16), English-only model;
  default a model that keeps STT under ~0.5 s per utterance on the 3070 Ti
  (e.g. `distil-large-v3` or `small.en`), configurable. One model instance
  shared by both sources through a queue.
- **Live partials:** transcript shows text as utterances complete; showing
  in-progress partials is nice-to-have.
- **Screen-capture exclusion:** `SetWindowDisplayAffinity(hwnd,
  WDA_EXCLUDEFROMCAPTURE)` on every Shade window.
- **Providers:** official `anthropic` and `openai` SDKs with streaming; local
  model = OpenAI SDK with custom `base_url`. Default models: a fast tier per
  provider (e.g. Claude Haiku / a small OpenAI model) — speed first;
  switchable in settings.
- **Prompt to the model:** system = built-in short answering rules (format
  above) + the profile `.md`; user message = recent transcript window (last
  few minutes, Me/Them labeled) + the detected question/task. Use prompt
  caching for the system part where the provider supports it.
- **Profiles:** a `profiles/` folder; choose from the tray menu or a
  file-picker at session start. Ship one example profile.
- **Session output:** `sessions/YYYY-MM-DD_HH-MM_<profile>/transcript.md`
  and `hints.md`, appended incrementally as the call goes (crash-safe).
- **Settings:** a single settings file (TOML) in the project/app folder, plus
  a settings dialog for the common options (provider, model, display mode,
  trigger mode, hotkeys, opacity, audio devices).
- **Hotkeys (defaults, configurable):** ask now; screenshot region; toggle
  overlay/window; toggle click-through; dismiss current hint; toggle Auto
  on/off.
- **Auto-mode cost:** since no budget was set, Auto favors recall (catching
  indirect tasks) over saving tokens. A running per-session cost/token
  counter is shown in the UI and written to `hints.md`; no hard cap.
- **Screenshots:** sent as images to vision-capable models (Claude and
  OpenAI models support this). Images are saved into the session folder next
  to the hint that used them. If the selected local model has no vision
  support, Shade shows a clear message instead of failing silently.
- **Local model on the shared GPU:** when the local provider is active, STT
  switches to a lighter config (smaller model and/or int8) to leave VRAM for
  the LLM; recommended local models are small, quantized (~3–8B, Q4) and,
  for screenshots, a small vision model. Shade shows a warning if VRAM is
  nearly full. Target latency still applies; if the local setup can't meet
  it, that is reported, not hidden.

## Left to the builder

- **Auto-detection method.** Must catch questions *and* tasks/requests
  ("walk us through…", "how would you handle…"), including indirect ones,
  without spamming hints on small talk. Options include heuristics (Whisper
  punctuation, interrogatives, imperatives), a cheap model call that may
  answer "nothing to answer", or a mix. Must fit the latency budget and have
  a sensitivity setting. Detection runs on "Them" speech; hotkey works on
  everything.
- What "latest part of the conversation" means for the hotkey (e.g. last
  "Them" utterance(s) since the previous hint, or last N seconds).
- Behavior when a new question arrives while a hint is still streaming
  (cancel and replace vs. queue).
- Echo handling when not using headphones (e.g. suppress "Me" text that
  duplicates recent "Them" text) — nice-to-have.
- How hints history is shown (latest only vs. scrollable list) in each mode.
- Error UX: provider down, bad key, local server unreachable — show it
  briefly in the hint area, keep transcribing.
- Packaging (run from `uv run` is fine for v1; a one-file exe is optional).
