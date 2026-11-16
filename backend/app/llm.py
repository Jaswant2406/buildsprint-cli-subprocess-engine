"""
LLM provider wrapper.
Supports heuristic (no-key) mode as a first-class citizen.
"""
from __future__ import annotations

from app.config import get_settings


class LLMError(Exception):
    pass


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1000,
    temperature: float = 0.3,
) -> str:
    """
    Call the configured LLM provider, or raise LLMError in heuristic mode.
    Returns the assistant's text response.
    """
    settings = get_settings()
    if settings.llm_mode != "llm":
        raise LLMError("No LLM configured; using heuristic mode")

    provider = settings.llm_provider.lower()
    api_key = settings.llm_api_key
    model = settings.llm_model

    if provider in ("openai", "azure_openai"):
        return _call_openai(api_key, model, system_prompt, user_prompt, max_tokens, temperature)
    elif provider in ("anthropic", "claude"):
        return _call_anthropic(api_key, model, system_prompt, user_prompt, max_tokens, temperature)
    elif provider in ("google", "gemini"):
        return _call_google(api_key, model, system_prompt, user_prompt, max_tokens, temperature)
    else:
        raise LLMError(f"Unknown LLM provider: {provider!r}")


def _call_openai(
    api_key: str, model: str, system: str, user: str,
    max_tokens: int, temperature: float,
) -> str:
    import httpx
    model = model or "gpt-4o-mini"
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenAI network error: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"OpenAI response parse error: {exc}") from exc


def _call_anthropic(
    api_key: str, model: str, system: str, user: str,
    max_tokens: int, temperature: float,
) -> str:
    import httpx
    model = model or "claude-3-haiku-20240307"
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "temperature": temperature,
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"Anthropic network error: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(f"Anthropic error {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
        return data["content"][0]["text"]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"Anthropic response parse error: {exc}") from exc


def _call_google(
    api_key: str, model: str, system: str, user: str,
    max_tokens: int, temperature: float,
) -> str:
    import httpx
    model = model or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    try:
        resp = httpx.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
            },
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"Google/Gemini network error: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(f"Google/Gemini error {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"Google/Gemini response parse error: {exc}") from exc
