""""Test connection" for OpenAI-compatible services (Ollama, LM Studio, clouds)."""

from __future__ import annotations

import openai


def check_connection(base_url: str, api_key: str, model: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Ask the service for its model list; say whether `model` is among them."""
    client = openai.OpenAI(base_url=base_url, api_key=api_key or "none", timeout=timeout, max_retries=0)
    try:
        names = sorted(m.id for m in client.models.list())
    except openai.APIConnectionError:
        return False, f"Cannot connect to {base_url}. Is the server running and reachable?"
    except openai.AuthenticationError:
        return False, "Connected, but the API key was rejected."
    except openai.APIError as e:
        return False, f"Connected, but the service answered with an error: {e}"
    listed = ", ".join(names) if names else "none"
    if model and model not in names:
        return False, f"Connected. Model '{model}' not found. Available: {listed}"
    return True, f"Connected. Available models: {listed}"
