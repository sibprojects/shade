# <img src="docs/images/shade-icon-s.png" width="48" alt=""> Shade

![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?logo=uv&logoColor=white)
![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![faster-whisper](https://img.shields.io/badge/STT-faster--whisper-FF6F00)
![CUDA](https://img.shields.io/badge/GPU-CUDA%2012-76B900?logo=nvidia&logoColor=white)
![Status](https://img.shields.io/badge/status-alpha-yellow)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Shade** is a real-time call assistant for Windows. It sits in the system
tray, listens to your microphone and your computer's audio during a call,
keeps a live English transcript, and streams a short answer you can say out
loud within seconds of being asked a question — including tasks shown on the
other side's screen.

> **Status:** alpha. Everything below is implemented and covered by tests;
> real-call behavior with each provider is still being measured.

## Screenshots

**Hint window** — the current hint on top (say the first lines out loud);
below it, tabs with the live **Transcript** and the **History** of earlier
hints. The status line at the bottom shows the trigger, the model and the
session cost.
It has the program icon and the usual minimize, maximize and close buttons,
but no taskbar button: minimize and close send it to the tray, and a click on
the tray icon (or **Show**) brings it back. **Day** or **Night** theme in
Settings → Display.

<table>
  <tr>
    <td align="center"><img src="docs/images/hint-window-day-2.png" alt="Hint window, day theme" width="400"></td>
    <td align="center"><img src="docs/images/hint-window-night-2.png" alt="Hint window, night theme" width="400"></td>
  </tr>
  <tr>
    <td align="center"><b>Window — Day theme</b></td>
    <td align="center"><b>Window — Night theme</b></td>
  </tr>
</table>

**Overlay** — the same hint on a semi-transparent layer over the call, with
the last three transcript lines. Hidden from screen sharing. Drag its edges
or corners to resize it, drag the status line at the bottom to move it;
`Ctrl+Alt+O` shows or hides it. Background
color, text color and background opacity are set in Settings → Display;
the text itself stays fully opaque.

<table>
  <tr>
    <td align="center"><img src="docs/images/overlay-dark-2.png" alt="Overlay, dark background" width="400"></td>
    <td align="center"><img src="docs/images/overlay-light-2.png" alt="Overlay, light background with dark text" width="400"></td>
  </tr>
  <tr>
    <td align="center"><b>Overlay — dark background, light text</b></td>
    <td align="center"><b>Overlay — light background, dark text</b></td>
  </tr>
</table>

**Tray menu and settings** — Shade lives in the system tray (the black-and-gray
gem with an **S**). Right-click it for the menu; **Settings…** has four tabs,
and **Apply** changes things without closing the window.

<table>
  <tr>
    <td align="center"><img src="docs/images/tray-menu-2.png" alt="Tray menu" height="290"></td>
    <td align="center"><img src="docs/images/settings-model-3.png" alt="Settings: Model tab with Claude" width="400"></td>
  </tr>
  <tr>
    <td align="center"><b>Tray menu</b></td>
    <td align="center"><b>Model — Claude</b></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/images/settings-model-grok-3.png" alt="Settings: Model tab with the Grok preset" width="400"></td>
    <td align="center"><img src="docs/images/settings-display-4.png" alt="Settings: Display tab" width="400"></td>
  </tr>
  <tr>
    <td align="center"><b>Model — Grok (OpenAI-compatible)</b></td>
    <td align="center"><b>Display — theme, font sizes, overlay colors and opacity</b></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/images/settings-audio-3.png" alt="Settings: Audio tab" width="400"></td>
    <td align="center"><img src="docs/images/settings-hotkeys-3.png" alt="Settings: Hotkeys tab" width="400"></td>
  </tr>
  <tr>
    <td align="center"><b>Audio — devices, mic gain and level, speech model, pause, context</b></td>
    <td align="center"><b>Hotkeys</b></td>
  </tr>
</table>

## At a glance

- **Use cases:** interviews, presentations, work calls with tricky
  questions. Anything in English where a fast, well-informed answer matters.
- **Two audio sources:** your microphone is labeled *Me*, system audio
  (Zoom, Teams, Meet, any app) is *Them*. No speaker diarization: the label
  comes from the source.
- **Speech-to-text:** runs locally on the GPU with faster-whisper
  (`large-v3-turbo`, float16; `large-v3` or `distil-large-v3` in Settings).
  Silero VAD cuts speech into utterances on a ~600 ms pause and keeps 0.2 s
  after the last word. The model also gets the call topic from the profile
  and the last two lines of the conversation, which helps with names and
  terms. Nothing is sent to the cloud for transcription.
- **Three triggers:**
  - **Auto:** a small, fast model checks each *Them* utterance for a question
    or a task, including indirect ones like "walk us through…".
  - **Hotkey:** answer the last question asked.
  - **Screenshot:** drag a rectangle over any screen, and the image is solved
    together with the recent conversation.
- **Call profiles:** before each call you pick a Markdown file from
  `profiles/` with your skills and what the call is about. It becomes the
  model's system prompt.
- **Models:** Claude, OpenAI, Grok (xAI), Groq, DeepSeek, Gemini, any other
  OpenAI-compatible service, or a local model through Ollama or LM Studio.
  You choose in Settings.
- **Hint format:** 1–3 lines you can say right away, then up to 4 short
  bullets, then code in one block if the task needs it. Hints stream token by
  token.
- **Display:** a normal window for a second monitor, or a semi-transparent
  always-on-top overlay with adjustable opacity and click-through.
- **Hidden from screen sharing:** every Shade window uses
  `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`, so it is not in your
  shared screen or in recordings.
- **Session notes:** `sessions/<date>_<profile>/` gets `transcript.md`,
  `hints.md` (question, answer, model, tokens, cost) and screenshots. Files
  are appended and flushed on every line, so a crash loses nothing.
- **Cost:** a running per-session cost counter is shown in the UI and
  written next to every hint. There is no hard cap.

## How it works

```mermaid
flowchart LR
    mic[Microphone] -->|Me| rs1[Resample<br/>16 kHz mono]
    sys[System audio<br/>WASAPI loopback] -->|Them| rs2[Resample<br/>16 kHz mono]
    rs1 --> vad1[Silero VAD<br/>segmenter]
    rs2 --> vad2[Silero VAD<br/>segmenter]
    vad1 --> stt[faster-whisper<br/>GPU]
    vad2 --> stt
    stt --> tr[Transcript]
    tr --> det{Question<br/>detector}
    det -->|ASK| eng[Engine]
    hk[Hotkey] --> eng
    shot[Screenshot<br/>region] --> eng
    prof[Profile .md] --> eng
    eng -->|stream| llm[(LLM provider)]
    llm -->|tokens| ui[Window / Overlay]
    tr --> ui
    eng --> files[sessions/<br/>transcript.md · hints.md]
```

**Latency budget** (target: first words within 2–3 s after *Them* stops
talking):

| Stage | Budget |
|---|---|
| End-of-utterance pause (VAD) | ~0.6 s |
| Speech-to-text on the GPU | ≤ 0.5 s |
| Question detection (fast model) | ~0.3–0.5 s |
| Model time to first token | ~0.5–1.5 s |

**When questions collide:** a new hotkey or screenshot request cancels any
hint that is still streaming. A new auto-detected question replaces an
older auto hint, but never interrupts one you asked for. Cancelled hints are
still saved, marked *(cancelled)*.

**When something fails:** a missing API key, a provider outage or a stopped
local server shows a short message in the hint area. Transcription keeps
running. If the microphone or system audio device disappears, the other
source keeps working.

## Providers

| Provider | Key variable | Images | Notes |
|---|---|---|---|
| Claude | `ANTHROPIC_API_KEY` | yes | default; answers on Opus 5.5 (low effort), detection on Haiku 5.5 |
| Claude Code (subscription) | — (your Claude sign-in) | yes | the installed `claude` CLI in headless mode; Opus 5.5 by default (Sonnet 5.5 and Haiku 5.5 in the list) |
| OpenAI | `OPENAI_API_KEY` | yes | |
| Grok (xAI) | `XAI_API_KEY` | yes | OpenAI-compatible |
| Groq | `GROQ_API_KEY` | model-dependent | very low latency |
| DeepSeek | `DEEPSEEK_API_KEY` | no | |
| Gemini | `GEMINI_API_KEY` | yes | OpenAI-compatible endpoint |
| Local model (this PC) | — | model-dependent | Ollama / LM Studio on this PC |
| Local model (network PC) | — | model-dependent | Ollama on another computer in your network |

Keys are read from environment variables or the git-ignored `.env` file. They are never written to
settings, logs or session files. Model names, base URLs and image support are
editable per provider, and you can add your own OpenAI-compatible preset.

**Local model on the same GPU:** with **Local model (this PC)**, speech-to-text
switches to a lighter setup (`small.en`, int8) to leave VRAM for the model,
and Shade warns when GPU memory is above 90%. Small quantized models
(~3–8B, Q4) are recommended; for screenshots, use one with vision.

**Local model on another PC:** run Ollama there with `OLLAMA_HOST=0.0.0.0`,
allow TCP port 11434 in its firewall, choose **Local model (network PC)** and set its base URL to
`http://<that-pc-ip>:11434/v1`. Speech-to-text then keeps the full model,
because this GPU is not shared. **Test connection** in Settings → Model
checks the address and lists the models the server has.

**Claude Code (subscription):** answers come from the installed, unmodified
Claude Code (`claude -p`, stream-json) signed in with your own Claude account,
so they use your subscription instead of API credit. Tools, MCP servers and
project settings are off, and the system prompt is Shade's own. Each question
runs in its own process, and the next one is started in advance: measured
first token 0.64–0.72 s (1.2 s for the very first question). Answers count
toward your plan's usage limits. With this provider, questions are found by
rules on this PC (no model call), so only the answers use the plan; auto hints
can be turned off in Settings → Model. Use it for yourself only; see
[Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance).

**Question detection by rules** (`src/shade/rules.py`): a question mark, a
question word followed by a question (`how would…`, not `when I was…`), an
inverted auxiliary (`do you…`, `could you…`), a task (`tell me…`, `walk me
through…`, `write…`, `imagine…`) or an indirect question (`I'm curious…`);
small talk and line checks (`can you hear me?`, `how are you?`) are skipped.
Measured on a one-hour real call plus 45 interview-style lines (436 lines,
67 of them questions or tasks):

| Detector | Found | False alarms | Median time |
|---|---|---|---|
| Rules | 63 / 67 | 18 | 0 ms |
| Haiku 5.5 | 65 / 67 | 20 | 840 ms |
| qwen2.5:7b (Ollama, GPU) | 58 / 67 | 35 | 410 ms |
| qwen2.5:3b | 63 / 67 | 243 | 265 ms |
| gemma3:4b | 65 / 67 | 348 | 670 ms |

The rules were tuned on the same lines, so expect somewhat lower numbers on
new calls. Most remaining false alarms are questions inside a video the other
side was playing.

## Hotkeys

| Action | Keys |
|---|---|
| Answer the last question | `Ctrl+Alt+A` |
| Screenshot a region | `Ctrl+Alt+S` |
| Switch window / overlay | `Ctrl+Alt+V` |
| Show / hide overlay | `Ctrl+Alt+O` |
| Show / hide window | `Ctrl+Alt+W` |
| Toggle overlay click-through | `Ctrl+Alt+C` |
| Clear the answers and start a new topic | `Ctrl+Alt+D` |
| Toggle auto hints | `Ctrl+Alt+Q` |
| Last answer: shorter | `Ctrl+Alt+1` |
| Last answer: more detail | `Ctrl+Alt+2` |
| Last answer: code example | `Ctrl+Alt+3` |
| Questions to ask them | `Ctrl+Alt+4` |

All hotkeys are global (they work while another app has focus) and can be
changed in Settings. In the screenshot selector, Esc or a right click cancels.

## Project layout

```
src/shade/
  audio/        capture (mic, loopback), resampling, VAD segmenter
  llm/          Claude and OpenAI-compatible providers
  ui/           tray app, window, overlay, hotkeys, screenshot, settings
  stt.py        faster-whisper worker
  transcript.py rolling transcript
  detect.py     question detector
  engine.py     orchestration, cancel/replace
  session.py    crash-safe session files
profiles/       call profiles (Markdown)
sessions/       saved calls (git-ignored)
```

## Requirements

- Windows 10 2004+ / Windows 11
- Python 3.11 and [uv](https://docs.astral.sh/uv/)
- NVIDIA GPU with CUDA 12 support (tested target: RTX 3070 Ti, 8 GB)
- Headphones are recommended, so the microphone doesn't pick up the other side

## Setup

```powershell
git clone https://github.com/sibprojects/shade.git
cd shade
uv sync
copy .env.example .env   # then put your key(s) into .env
uv run python -m shade
```

API keys go into `.env` in the project folder (it is in `.gitignore`), e.g.
`ANTHROPIC_API_KEY=sk-ant-...`. Variables already set in the environment
take precedence over the file.

The first start downloads the speech model (`large-v3-turbo`, ~1.6 GB) to
the Hugging Face cache. A tray icon appears; when its tooltip says
**ready**, right-click it → **Start session** → pick a profile.

- **Profiles:** put your own `.md` files in `profiles/` (see
  `profiles/example.md`) or use **Browse…**.
- **Settings:** tray → **Settings…** (provider, models, display, audio
  devices, hotkeys). Saved to `settings.toml` next to the app, without keys.
- **Code in hints:** shown on black with syntax colors for PHP, Python and Go
  (the language comes from the code fence), wrapped to the width of the
  window, so there is no sideways scrolling; its font size is set separately
  (Settings → Display, 2 pt smaller than the text by default).
- **Follow-up questions:** answers stack up, newest at the bottom, and the
  last three go along with the next question, so a follow-up ("and for
  writes?") builds on them. A new question scrolls to its start once; while
  it streams, the view stays where you scroll. `Ctrl+Alt+D` clears the answers
  and starts a new topic.
- **Quick actions** (hotkeys or tray → **Quick actions**): make the last
  answer shorter (1–2 sentences to say right away), add more detail, show a
  code example, or suggest three questions to ask the other side. The result
  becomes the last answer, so actions can follow each other.
- **Sessions:** tray → **Open sessions folder**.
- **Local model:** run Ollama (`ollama pull qwen2.5vl:7b`) or LM Studio,
  choose **Local model** in Settings and check the base URL
  (`http://localhost:11434/v1` for Ollama, `http://localhost:1234/v1` for
  LM Studio).
- **Check audio only:** `uv run python scripts/smoke_audio.py` prints a live
  *Me*/*Them* transcript with recognition time per phrase.

## Measured

On an RTX 3070 Ti (8 GB), Windows 11:

| What | Result |
|---|---|
| Speech-to-text, `large-v3-turbo` float16, 7.8 s phrase | 0.20–0.27 s |
| Speech-to-text, `large-v3` float16, same phrase | 0.39–0.46 s |
| Speech-to-text, `small.en` int8 (local-model mode), same phrase | 0.15 s |
| End of speech → first hint word, excluding model time | ~0.8–0.9 s |

Time to first token for each provider will be added after real calls.

## Development

- **Environment:** uv, Python 3.11.
- **Tests:** `uv run pytest`. The core (transcript, segmenter, detector,
  engine, providers, session files) is tested with fakes; UI widgets with
  pytest-qt. Audio, GPU, hotkeys and screen capture get scripted manual checks.
- **Docs:** [design](docs/superpowers/specs/2026-11-09-shade-design.md) ·
  [implementation plan](docs/superpowers/plans/2026-11-09-shade.md)

## A note on consent

Shade transcribes other people's speech. Depending on where you and they are,
recording or transcribing a conversation may require their consent. Making
sure you have it is your responsibility.

## License

[MIT](LICENSE)
