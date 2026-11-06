# LLM Council

![llmcouncil](header.jpg)

The idea of this repo is that instead of asking a question to your favorite LLM provider (e.g. OpenAI GPT-6.1 Sol, Google Gemini 4 Argon, Anthropic Claude Sonnet 5.5, xAI Grok 4.7), you can group them into your "LLM Council". This repo is a simple, local web app that essentially looks like ChatGPT except it uses OpenRouter to send your query to multiple LLMs, it then asks them to review and rank each other's work, and finally a Chairman LLM produces the final response.

In a bit more detail, here is what happens when you submit a query:

1. **Stage 1: First opinions**. The user query is given to all LLMs individually, and the responses are collected. The individual responses are shown in a "tab view", so that the user can inspect them all one by one.
2. **Stage 2: Review**. Each individual LLM is given the responses of the other LLMs. Under the hood, the LLM identities are anonymized so that the LLM can't play favorites when judging their outputs. The LLM is asked to rank them in accuracy and insight.
3. **Stage 3: Final response**. The designated Chairman of the LLM Council takes all of the model's responses and compiles them into a single final answer that is presented to the user.

## Vibe Code Alert

This project was 99% vibe coded as a fun Saturday hack because I wanted to explore and evaluate a number of LLMs side by side in the process of [reading books together with LLMs](https://x.com/karpathy/status/1990577951671509438). It's nice and useful to see multiple responses side by side, and also the cross-opinions of all LLMs on each other's outputs. I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Configure API Key

Copy the example configuration, then add your OpenRouter API key locally:

```bash
cp .env.example .env
```

Set `OPENROUTER_API_KEY` in `.env` using a key from [OpenRouter](https://openrouter.ai/settings/keys). The backend sends requests to `https://openrouter.ai/api/v1/chat/completions`; you do not need separate provider keys. Keep the key out of frontend code and Git. `.env` is ignored by Git, and existing shell environment variables take precedence over it. Restart the backend after changing settings.

OpenRouter requires credits for these paid models. A new conversation normally makes ten model calls: four answers, four reviews, one synthesis, and one title. Subsequent messages normally make nine. See the [current catalog and pricing](https://openrouter.ai/models) before running questions.

### 3. Choose Models

Use the model settings in the app to add or remove council members and choose a separate chairman before sending a question. The chairman cannot also be one of the selected judges; routing variants of the same model do not count as a different model. OpenAI, Anthropic, Google, and xAI are prioritized; other OpenRouter text models can join the council and peer review too. You can enter a model ID directly if the public catalog is unavailable. Changes apply to the next question and do not change earlier answers. More council members mean more paid calls.

The app supports up to 26 unique council members so anonymous review labels remain A–Z. Model selection never requires entering an API key in the browser.

#### Default Configuration (Optional)

The defaults were checked against the [OpenRouter model catalog](https://openrouter.ai/api/v1/models) on November 6, 2026:

- Council: `openai/gpt-6.1-sol`, `google/gemini-4-argon`, `anthropic/claude-sonnet-5.5`, `x-ai/grok-4.7`.
- Chairman: `anthropic/claude-opus-5.5`, separate from every judge.
- Titles: `google/gemini-3.5-flash-lite`, a lightweight model for short titles.

The default chairman, Claude Opus 5.5, is a premium model: OpenRouter listed $4 per million input tokens and $20 per million output tokens at verification, before any applicable caching or provider-specific adjustments. This is higher than the former Gemini chairman ($2/$10). You can choose another distinct text model to control cost.

These are explicit, non-preview IDs rather than moving `latest` aliases. Availability and prices can change. Override them in `.env` without editing Python:

```bash
COUNCIL_MODELS=openai/gpt-6.1-sol,google/gemini-4-argon,anthropic/claude-sonnet-5.5,x-ai/grok-4.7
CHAIRMAN_MODEL=anthropic/claude-opus-5.5
TITLE_MODEL=google/gemini-3.5-flash-lite
OPENROUTER_TIMEOUT_SECONDS=180
```

The timeout is HTTPX's per-operation timeout for each model, not a deadline for the whole council. Title generation keeps a 30-second timeout and falls back to “New Conversation.” Requests are not automatically retried, since a timed-out request may already have incurred charges.

### 4. Check Configuration

Verify model IDs against the public catalog without sending a key, prompt, or paid completion:

```bash
uv run python -m backend.check_models
```

This checks catalog availability and text compatibility. It does **not** validate your API key, account credits, or a live generated response.

Run the offline test suite:

```bash
uv run python -m unittest discover -s tests -v
```

The tests mock OpenRouter, including full streaming and non-streaming council flows, and do not spend credits.

### OpenRouter Troubleshooting

- Chairman overlap: choose a model absent from the council list. If an existing `.env` still sets the old Gemini chairman, update or remove that override before restarting. The backend rejects overlapping configured defaults and API requests.

- Missing key: the message API returns 503 before saving a message or contacting OpenRouter. Set `OPENROUTER_API_KEY` and restart the backend.
- HTTP 401 in backend logs: check the key and any shell variable overriding `.env`.
- HTTP 402: check your OpenRouter credit balance.
- HTTP 429: wait before trying again.
- Missing model: run the catalog check and choose an available text model.
- Timeout: increase `OPENROUTER_TIMEOUT_SECONDS` if needed. Reasoning models can take longer; retrying may incur another charge.

Individual model failures do not stop successful members. If every model fails, the app reports an error instead of requesting rankings and synthesis from an empty council. Provider errors and malformed responses are logged without including prompts, keys, or raw API response bodies.

## Running the Application

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API
- **Frontend:** React + Vite, react-markdown for rendering
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript
