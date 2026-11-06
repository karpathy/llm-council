"""Check configured models against OpenRouter's public catalog without inference."""

import sys

import httpx

from .config import COUNCIL_MODELS, CHAIRMAN_MODEL, TITLE_MODEL

CATALOG_URL = "https://openrouter.ai/api/v1/models"


def main() -> int:
    """Return nonzero if the catalog cannot confirm every configured model."""
    try:
        # Public endpoint: no API key, user prompt, or completion request is sent.
        response = httpx.get(CATALOG_URL, timeout=30.0)
        response.raise_for_status()
        models = {model["id"]: model for model in response.json()["data"]}
    except ImportError:
        print("Your proxy needs optional HTTPX dependencies (for SOCKS, install httpx[socks]).", file=sys.stderr)
        return 1
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        print("Could not read the OpenRouter model catalog. Check your connection.", file=sys.stderr)
        return 1

    valid = True
    for model_id in dict.fromkeys([*COUNCIL_MODELS, CHAIRMAN_MODEL, TITLE_MODEL]):
        model = models.get(model_id)
        if model is None:
            print(f"MISSING: {model_id}")
            valid = False
            continue
        architecture = model.get("architecture", {})
        if (
            "text" not in architecture.get("input_modalities", [])
            or "text" not in architecture.get("output_modalities", [])
        ):
            print(f"UNSUPPORTED: {model_id} does not advertise text input/output.")
            valid = False
            continue
        endpoints = model.get("endpoints")
        if endpoints is not None and "/api/v1/chat/completions" not in endpoints:
            print(f"UNSUPPORTED: {model_id} does not advertise chat completions.")
            valid = False
            continue
        print(f"FOUND: {model_id}")

    print("Catalog check only. API key, account credits, and inference have not been tested.")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
