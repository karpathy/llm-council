"""OpenRouter chat-completion client with isolated, safely logged failures."""

import asyncio
import ipaddress
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urlsplit

import httpx

from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_TIMEOUT_SECONDS,
    RESEARCH_MAX_OUTPUT_TOKENS,
)

logger = logging.getLogger(__name__)


def _safe_source_url(value: Any) -> Optional[str]:
    """Validate link syntax without fetching, resolving, or trusting page content."""
    if not isinstance(value, str) or len(value) > 4096:
        return None
    url = value.strip()
    if not url or "\\" in url or any(char.isspace() or ord(char) < 32 for char in url):
        return None
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in ("http", "https") or not host or parsed.username is not None or parsed.password is not None:
            return None
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return None
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".invalid")) or "%" in host:
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Reject single-label and legacy numeric address forms, not just IPv4.
            if "." not in host or all(char.isdigit() or char == "." for char in host):
                return None
        else:
            if not address.is_global:
                return None
    except ValueError:
        return None
    return url


def _research_evidence(data: Dict[str, Any], choice: Dict[str, Any], message: Dict[str, Any]) -> Dict[str, Any]:
    citations = []
    seen = set()
    annotations = message.get("annotations")
    if isinstance(annotations, list):
        for annotation in annotations:
            if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                continue
            citation = annotation.get("url_citation")
            if not isinstance(citation, dict):
                continue
            url = _safe_source_url(citation.get("url"))
            if url is None or url in seen:
                continue
            title = citation.get("title")
            item = {"url": url, "title": title[:300] if isinstance(title, str) and title.strip() else url}
            excerpt = citation.get("content")
            if isinstance(excerpt, str) and excerpt.strip():
                item["content"] = excerpt[:2000]
            start, end = citation.get("start_index"), citation.get("end_index")
            answer = _text_content(message.get("content"))
            if type(start) is int and type(end) is int and answer is not None and 0 <= start < end <= len(answer):
                item.update({"start_index": start, "end_index": end})
            citations.append(item)
            seen.add(url)
            if len(citations) >= 12:
                break
    usage = data.get("usage")
    details = usage.get("server_tool_use_details") if isinstance(usage, dict) else None
    details = details if isinstance(details, dict) else {}

    def counter(name):
        value = details.get(name)
        return value if type(value) is int and value >= 0 else None

    searches = counter("web_search_requests")
    executed = counter("tool_calls_executed")
    warnings = []
    if not citations:
        warnings.append("No usable source citations were returned; this answer is not verified web research.")
    if searches == 0:
        warnings.append("OpenRouter reported no web searches for this answer.")
    if executed == 0:
        warnings.append("OpenRouter reported no executed server tools for this answer.")
    if searches is None or executed is None:
        warnings.append("OpenRouter did not return complete tool-usage details.")
    if message.get("tool_calls") or choice.get("finish_reason") == "tool_calls":
        warnings.append("The answer contains unfinished tool calls; research may be incomplete.")
    if choice.get("finish_reason") == "length":
        warnings.append("The output limit was reached; the answer may be incomplete.")
    # Citation and aggregate usage counters are not page-fetch receipts.
    warnings.append("Returned citations do not verify that individual pages were fetched successfully.")
    return {"citations": citations, "research": {
        "requested": True,
        "status": "sources_returned" if citations else "no_sources",
        "search_requests": searches,
        "tool_calls_executed": executed,
        "warnings": warnings,
    }}


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
    *,
    research: bool = False,
    max_output_tokens: Optional[int] = None,
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
        payload = {"model": model, "messages": messages}
        if max_output_tokens is not None:
            if type(max_output_tokens) is not int or max_output_tokens <= 0:
                raise ValueError("Output limit must be a positive integer")
            payload["max_tokens"] = max_output_tokens
        if research:
            payload.update({
                "tools": [
                    {"type": "openrouter:web_search", "parameters": {
                        "engine": "exa", "mode": "auto", "max_uses": 2,
                        "max_results": 3, "max_total_results": 6, "max_characters": 2000,
                    }},
                    {"type": "openrouter:web_fetch", "parameters": {
                        "engine": "openrouter", "max_uses": 2, "max_content_tokens": 2000,
                    }},
                ],
                "max_tool_calls": 4,
                "max_tokens": min(max_output_tokens or RESEARCH_MAX_OUTPUT_TOKENS, RESEARCH_MAX_OUTPUT_TOKENS),
                "provider": {"require_parameters": True},
            })
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                    "Content-Type": "application/json",
                },
                json=payload,
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
        result = {"content": content, "reasoning_details": message.get("reasoning_details")}
        if max_output_tokens is not None and choice.get("finish_reason") == "length":
            result["completion_warning"] = "The output limit was reached; this response may be incomplete."
        if research:
            result.update(_research_evidence(data, choice, message))
        return result
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
    *,
    research: bool = False,
    max_output_tokens: Optional[int] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query concurrently, preserving input order and isolating failed models."""
    options = {}
    if research:
        options["research"] = True
    if max_output_tokens is not None:
        options["max_output_tokens"] = max_output_tokens
    responses = await asyncio.gather(
        *(query_model(model, messages, **options) for model in models),
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
