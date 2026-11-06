"""OpenRouter chat-completion client with isolated, safely logged failures."""

import asyncio
import logging
from typing import List, Dict, Any, Optional

import httpx

from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


def _text_content(content: Any) -> Optional[str]:
    """Accept text or typed text parts, never reasoning or other modalities."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                return None
            if part.get("type") == "text":
                if not isinstance(part.get("text"), str):
                    return None
                parts.append(part["text"])
        text = "".join(parts)
    else:
        return None
    return text if text.strip() else None


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = OPENROUTER_TIMEOUT_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Query a model, returning text and reasoning_details, or None on failure.

    Timeout is in seconds (HTTPX's per-operation timeout). No completion is
    retried automatically: a failed request may already have incurred charges.
    Diagnostics deliberately exclude prompts, credentials and API response bodies.
    """
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.strip():
        logger.warning("OpenRouter request skipped: OPENROUTER_API_KEY is missing.")
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "messages": messages},
            )
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict) or "error" in data:
            logger.warning("OpenRouter returned an API error or invalid response.")
            return None
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            logger.warning("OpenRouter response contains no valid completion choice.")
            return None
        choice = choices[0]
        message = choice.get("message")
        if "error" in choice or choice.get("finish_reason") == "error" or not isinstance(message, dict):
            logger.warning("OpenRouter response contains no valid assistant message.")
            return None
        content = _text_content(message.get("content"))
        if content is None:
            logger.warning("OpenRouter response contains no usable answer text.")
            return None
        return {"content": content, "reasoning_details": message.get("reasoning_details")}
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        advice = {
            401: "check OPENROUTER_API_KEY",
            402: "check OpenRouter credits",
            429: "rate limited; try again later",
        }.get(status, "request failed")
        logger.warning("OpenRouter HTTP %s: %s.", status, advice)
    except httpx.TimeoutException:
        logger.warning("OpenRouter request timed out.")
    except httpx.RequestError:
        logger.warning("OpenRouter network request failed.")
    except (ValueError, TypeError):
        logger.warning("OpenRouter request or response was malformed.")
    except Exception:
        # Preserve graceful per-model degradation without logging potentially
        # sensitive exception strings, request headers or response bodies.
        logger.warning("OpenRouter request failed unexpectedly.")
    return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query concurrently, preserving input order and isolating failed models."""
    responses = await asyncio.gather(
        *(query_model(model, messages) for model in models),
        return_exceptions=True,
    )
    results = {}
    for model, response in zip(models, responses):
        if isinstance(response, BaseException):
            logger.warning("An OpenRouter model query failed independently.")
            results[model] = None
        else:
            results[model] = response
    return results
