# Shade

Real-time call assistant for Windows. Shade sits in the system tray, listens to
your microphone and your computer's audio during a call, keeps a live English
transcript, and streams instant AI hints when someone asks you a question or
gives you a task — including tasks shown on screen.

> **Status:** early development. Nothing is runnable yet.

## Features

- **Live transcription** of both sides of the call: microphone = *Me*,
  system audio = *Them*. Runs locally on the GPU with faster-whisper.
- **Instant hints** that start appearing within 2–3 seconds: a short answer
  you can say out loud first, then optional details, then code if needed.
- **Three ways to trigger a hint:**
  - **Auto**: Shade notices questions and tasks in the other side's speech.
  - **Hotkey**: answer the last question asked.
  - **Screenshot**: select a region of the screen (e.g. code on a shared
    screen) and get it solved.
- **Call profiles**: before each call, pick a Markdown file that describes
  your skills and what the call is about (interview, presentation, team
  meeting). The AI answers with that context.
- **Any model you like**: Claude, OpenAI, Grok (xAI), Groq, DeepSeek, Gemini,
  any other OpenAI-compatible service, or a local model through Ollama or
  LM Studio.
- **Two display modes**: a normal window for a second monitor, or a
  semi-transparent always-on-top overlay with optional click-through.
- **Hidden from screen sharing**: Shade's windows are excluded from screen
  capture, so others don't see them when you share your screen.
- **Session notes**: the full transcript and every hint (with screenshots and
  cost) are saved to `sessions/` as the call goes, so nothing is lost if the
  app crashes.

## Requirements

- Windows 10 2004+ / Windows 11
- Python 3.11 and [uv](https://docs.astral.sh/uv/)
- NVIDIA GPU with CUDA 12 support for local speech recognition
  (tested target: RTX 3070 Ti, 8 GB)
- Headphones are recommended, so the microphone doesn't pick up the other side

## Setup (planned)

```powershell
uv sync
uv run python -m shade
```

API keys are read from environment variables only and are never stored in
settings or session files:

| Provider   | Variable            |
|------------|---------------------|
| Claude     | `ANTHROPIC_API_KEY` |
| OpenAI     | `OPENAI_API_KEY`    |
| Grok (xAI) | `XAI_API_KEY`       |
| Groq       | `GROQ_API_KEY`      |
| DeepSeek   | `DEEPSEEK_API_KEY`  |
| Gemini     | `GEMINI_API_KEY`    |

A local model needs no key; point Shade at your Ollama or LM Studio endpoint
in Settings.

## A note on consent

Shade transcribes other people's speech. Depending on where you and they are,
recording or transcribing a conversation may require their consent. Making
sure you have it is your responsibility.
