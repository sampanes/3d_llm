"""
Unified LLM Client Wrapper
===========================
Provides a common interface for OpenAI, Anthropic, and Google Generative AI APIs.
Handles API errors, rate limits, retries, and code extraction from responses.

Usage:
    from scripts.llm_clients import generate

    code = generate(
        prompt="Create a gear with 20 teeth",
        system_prompt="You are a 3D modeling assistant...",
        model="gpt-5.5",
        provider="openai",
    )
"""

from __future__ import annotations

import base64
import os
import re
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds

PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "ollama": None,  # local server, no key needed
}

# Current model defaults as of 2026-06. Override per call or in .env.
DEFAULT_MODELS = {
    "openai": "gpt-5.5",
    "anthropic": "claude-opus-4-8",
    "google": "gemini-3.5-flash",
    "ollama": "qwen2.5-coder:14b",
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Structured result returned by every provider call."""

    raw_text: str
    extracted_code: str
    model: str
    provider: str
    usage: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Code Extraction
# ---------------------------------------------------------------------------


def extract_code(text: str) -> str:
    """Strip markdown fences and return the inner code block.

    Handles ```openscad, ```python, ```scad, or bare ``` fences.
    If no fences are found the full text is returned as-is.
    """
    # Try to match fenced code blocks (greedy, multiline)
    pattern = r"```(?:openscad|scad|python|py|cadquery)?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        # Return the longest match (most likely the main code)
        return max(matches, key=len).strip()
    # Fallback: return the raw text stripped of any stray backticks
    return text.strip().strip("`").strip()


# ---------------------------------------------------------------------------
# Reference images (vision input)
# ---------------------------------------------------------------------------

IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def load_images(image_paths: Optional[Sequence]) -> list[tuple[str, bytes]]:
    """Read reference image files -> ``[(media_type, raw_bytes), ...]``.

    Fails loudly on missing files or unsupported extensions, before any
    tokens are spent.
    """
    loaded: list[tuple[str, bytes]] = []
    for ip in image_paths or []:
        p = Path(ip)
        media_type = IMAGE_MEDIA_TYPES.get(p.suffix.lower())
        if media_type is None:
            raise ValueError(
                f"Unsupported image type '{p.suffix}' for {p} "
                f"(use {', '.join(sorted(IMAGE_MEDIA_TYPES))})"
            )
        if not p.is_file():
            raise FileNotFoundError(f"Reference image not found: {p}")
        loaded.append((media_type, p.read_bytes()))
    return loaded


def _openai_user_content(prompt: str, images: list[tuple[str, bytes]]):
    """User message content for OpenAI-style chat APIs (also Ollama)."""
    if not images:
        return prompt
    parts: list[dict] = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mt};base64,{base64.b64encode(data).decode('ascii')}"
            },
        }
        for mt, data in images
    ]
    parts.append({"type": "text", "text": prompt})
    return parts


def _anthropic_user_content(prompt: str, images: list[tuple[str, bytes]]):
    """User message content blocks for the Anthropic Messages API."""
    if not images:
        return prompt
    parts: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mt,
                "data": base64.b64encode(data).decode("ascii"),
            },
        }
        for mt, data in images
    ]
    parts.append({"type": "text", "text": prompt})
    return parts


# ---------------------------------------------------------------------------
# Provider Implementations
# ---------------------------------------------------------------------------


def _call_openai(
    prompt: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    images: Optional[list] = None,
) -> LLMResponse:
    """Call the OpenAI ChatCompletion API."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not set. Add it to your .env file."
        )

    client = OpenAI(api_key=api_key)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": _openai_user_content(prompt, images or [])})

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_tokens,  # replaces deprecated max_tokens
    }
    # Reasoning models (gpt-5*, o-series) reject non-default temperature
    if not model.startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["temperature"] = temperature
    response = client.chat.completions.create(**kwargs)

    raw = response.choices[0].message.content or ""
    usage = {}
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    return LLMResponse(
        raw_text=raw,
        extracted_code=extract_code(raw),
        model=model,
        provider="openai",
        usage=usage,
    )


def _call_anthropic(
    prompt: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    images: Optional[list] = None,
) -> LLMResponse:
    """Call the Anthropic Messages API."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file."
        )

    client = anthropic.Anthropic(api_key=api_key)

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": _anthropic_user_content(prompt, images or [])}],
    }
    # Sampling params are removed on Opus 4.7+ / Fable models (400 if sent)
    if not any(marker in model for marker in ("fable", "opus-4-7", "opus-4-8")):
        kwargs["temperature"] = temperature
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)

    # Take the first *text* block. Newer models can lead with a thinking or
    # tool_use block, so don't blindly index content[0].
    raw = next(
        (b.text for b in (response.content or []) if getattr(b, "type", None) == "text"),
        "",
    )
    usage = {}
    if response.usage:
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

    return LLMResponse(
        raw_text=raw,
        extracted_code=extract_code(raw),
        model=model,
        provider="anthropic",
        usage=usage,
    )


def _call_google(
    prompt: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    images: Optional[list] = None,
) -> LLMResponse:
    """Call the Gemini API via the google-genai SDK.

    (The old google-generativeai package is deprecated; this uses its
    replacement, ``pip install google-genai``.)
    """
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY not set. Add it to your .env file."
        )

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
        system_instruction=system_prompt or None,
    )
    contents: object = prompt
    if images:
        contents = [
            types.Part.from_bytes(data=data, mime_type=mt) for mt, data in images
        ] + [prompt]
    response = client.models.generate_content(
        model=model, contents=contents, config=config
    )

    raw = response.text or ""
    usage = {}
    um = getattr(response, "usage_metadata", None)
    if um is not None:
        usage = {
            "prompt_tokens": getattr(um, "prompt_token_count", None),
            "completion_tokens": getattr(um, "candidates_token_count", None),
        }

    return LLMResponse(
        raw_text=raw,
        extracted_code=extract_code(raw),
        model=model,
        provider="google",
        usage=usage,
    )


def _call_ollama(
    prompt: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    images: Optional[list] = None,
) -> LLMResponse:
    """Call a local Ollama server through its OpenAI-compatible endpoint.

    Images only work with multimodal models (llama3.2-vision, qwen2.5vl,
    llava, ...). Text-only models like qwen2.5-coder ignore them or error.
    """
    from openai import OpenAI

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    client = OpenAI(base_url=base_url, api_key="ollama")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": _openai_user_content(prompt, images or [])})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Ollama call failed - is Ollama running and is '{model}' pulled? "
            f"(check with `ollama list`) Original error: {exc}"
        ) from exc

    raw = response.choices[0].message.content or ""
    return LLMResponse(
        raw_text=raw,
        extracted_code=extract_code(raw),
        model=model,
        provider="ollama",
        usage={},
    )


# ---------------------------------------------------------------------------
# Dispatch Map
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "google": _call_google,
    "ollama": _call_ollama,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate(
    prompt: str,
    system_prompt: str = "",
    model: Optional[str] = None,
    provider: str = "openai",
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    images: Optional[Sequence] = None,
) -> LLMResponse:
    """Generate text from the specified LLM provider.

    Parameters
    ----------
    prompt : str
        The user prompt describing the desired 3D model.
    system_prompt : str
        System-level instructions loaded from prompts/ directory.
    model : str | None
        Model identifier. If *None*, uses the provider's default.
    provider : str
        One of ``"openai"``, ``"anthropic"``, ``"google"``.
    temperature : float
        Sampling temperature (0.0 - 2.0).
    max_tokens : int
        Maximum tokens in the response.
    images : sequence of str | Path | None
        Optional reference image files (png/jpg/webp/gif) sent alongside
        the prompt. All hosted defaults are vision models; on Ollama you
        must pick a multimodal model yourself.

    Returns
    -------
    LLMResponse
        Structured response containing raw text, extracted code, and metadata.

    Raises
    ------
    ValueError
        If the provider is not supported.
    EnvironmentError
        If the required API key is missing.
    """
    provider = provider.lower().strip()
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unsupported provider '{provider}'. "
            f"Choose from: {', '.join(_PROVIDERS)}"
        )

    if model is None:
        model = DEFAULT_MODELS[provider]

    loaded_images = load_images(images)

    call_fn = _PROVIDERS[provider]
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Attempt %d/%d - calling %s / %s%s",
                attempt,
                MAX_RETRIES,
                provider,
                model,
                f" (+{len(loaded_images)} image(s))" if loaded_images else "",
            )
            return call_fn(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                images=loaded_images,
            )
        except Exception as exc:
            last_error = exc
            # Check for rate-limit / transient errors worth retrying
            err_str = str(exc).lower()
            retryable = any(
                kw in err_str
                for kw in ("rate", "limit", "timeout", "overloaded", "529", "503", "429")
            )
            if retryable and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.warning(
                    "Retryable error: %s - waiting %.1fs before retry",
                    exc,
                    wait,
                )
                time.sleep(wait)
            else:
                break

    raise RuntimeError(
        f"LLM call failed after {MAX_RETRIES} attempts: {last_error}"
    ) from last_error
