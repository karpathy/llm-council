"""Public OpenRouter model choices for the local settings UI."""

import logging

import httpx

from .config import COUNCIL_MODELS, CHAIRMAN_MODEL

logger = logging.getLogger(__name__)
CATALOG_URL = "https://openrouter.ai/api/v1/models"
PREFERRED_PROVIDERS = ("openai", "anthropic", "google", "x-ai")


async def list_model_options():
    """Fetch without authentication, falling back to editable configured IDs."""
    defaults = {"council_models": COUNCIL_MODELS, "chairman_model": CHAIRMAN_MODEL}
    fallback = [{"id": model, "name": model} for model in dict.fromkeys([*COUNCIL_MODELS, CHAIRMAN_MODEL])]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(CATALOG_URL)
            response.raise_for_status()
            data = response.json()["data"]
        options = {}
        for model in data:
            if not isinstance(model, dict) or not isinstance(model.get("id"), str):
                continue
            architecture = model.get("architecture") or {}
            if "text" not in architecture.get("input_modalities", []) or "text" not in architecture.get("output_modalities", []):
                continue
            if model.get("endpoints") is not None and "/api/v1/chat/completions" not in model["endpoints"]:
                continue
            options[model["id"]] = {"id": model["id"], "name": model.get("name") or model["id"]}
        if not options:
            raise ValueError("Empty text model catalog")

        def sort_key(model):
            provider = model["id"].split("/", 1)[0]
            priority = PREFERRED_PROVIDERS.index(provider) if provider in PREFERRED_PROVIDERS else len(PREFERRED_PROVIDERS)
            return priority, model["name"].casefold(), model["id"]

        return {"models": sorted(options.values(), key=sort_key), "defaults": defaults, "catalog_available": True}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, ImportError):
        logger.warning("OpenRouter model catalog unavailable; manual model selection remains available.")
        return {"models": fallback, "defaults": defaults, "catalog_available": False}
