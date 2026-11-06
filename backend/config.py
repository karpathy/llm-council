"""Configuration for the LLM Council."""

import math
import os
from pathlib import Path
from dotenv import load_dotenv

# Load the project's .env regardless of the current working directory.
# Existing process environment variables take precedence.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Explicit OpenRouter IDs verified against the public catalog on 2026-11-06.
DEFAULT_COUNCIL_MODELS = [
    "openai/gpt-6.1-sol",
    "google/gemini-4-argon",
    "anthropic/claude-sonnet-5.5",
    "x-ai/grok-4.7",
    "moonshotai/kimi-k3.1-pro",
    "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3.8-max-0902",
]
COUNCIL_MODELS = [
    model.strip()
    for model in os.getenv("COUNCIL_MODELS", ",".join(DEFAULT_COUNCIL_MODELS)).split(",")
    if model.strip()
]
if not COUNCIL_MODELS or len(COUNCIL_MODELS) != len(set(COUNCIL_MODELS)):
    raise ValueError("COUNCIL_MODELS must contain unique, nonempty OpenRouter model IDs.")

# Chairman model - synthesizes final response without also serving as a judge.
CHAIRMAN_MODEL = os.getenv("CHAIRMAN_MODEL", "anthropic/claude-opus-5.5").strip()
TITLE_MODEL = os.getenv("TITLE_MODEL", "google/gemini-3.5-flash-lite").strip()
if not CHAIRMAN_MODEL or not TITLE_MODEL:
    raise ValueError("CHAIRMAN_MODEL and TITLE_MODEL must be nonempty OpenRouter model IDs.")


def validate_distinct_chairman(council_models, chairman_model):
    """Routing variants of the same model must not fill both roles."""
    chairman_id = chairman_model.strip().split(":", 1)[0]
    if any(model.strip().split(":", 1)[0] == chairman_id for model in council_models):
        raise ValueError("The chairman must be a different model from every council judge.")


validate_distinct_chairman(COUNCIL_MODELS, CHAIRMAN_MODEL)

# Give reasoning models time to finish. This is a per-model HTTP timeout.
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "180"))
if not math.isfinite(OPENROUTER_TIMEOUT_SECONDS) or OPENROUTER_TIMEOUT_SECONDS <= 0:
    raise ValueError("OPENROUTER_TIMEOUT_SECONDS must be a positive, finite number.")

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
