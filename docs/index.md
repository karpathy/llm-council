# LLM Council

## Elevator pitch

Don't trust a single LLM. **LLM Council** asks several models the same question, has them anonymously peer-review and rank each other's answers, and then a Chairman model synthesizes one final answer. The result is more balanced and less biased, and every raw response and ranking is open to inspection. For high-stakes answers, you can also ask a teammate to review the council's response.

## How it works

1. **Stage 1 – Individual responses:** every council model answers the question in parallel.
2. **Stage 2 – Anonymous peer review:** responses are relabeled "Response A, B, C…" and each model ranks them. Rankings are aggregated into an average position per model.
3. **Stage 3 – Synthesis:** the Chairman model produces the final answer from all responses and rankings.

## Requesting a team review

Under the Stage 3 answer, click **Request team review**, enter the reviewer's name or email and an optional note, then send. The request is saved on that assistant message (`review_requests`) with status `pending` and is shown beneath the answer.

### API

`POST /api/conversations/{conversation_id}/messages/{message_index}/review-requests`

```json
{ "reviewer": "alice@example.com", "note": "Please check the cost estimate." }
```

Returns the created request:

```json
{
  "id": "…",
  "reviewer": "alice@example.com",
  "note": "Please check the cost estimate.",
  "status": "pending",
  "requested_at": "2026-01-01T12:00:00"
}
```

`message_index` is the position of the assistant message in the conversation. Errors: `404` (conversation or message not found), `400` (message is not an assistant response), `422` (missing reviewer).

> Requests are only stored; no notification is sent yet. Email/Slack/Teams delivery is a natural next step.

## Running locally

See the project [README](../README.md): backend on port 8001 (`python -m backend.main`), frontend on port 5173 (`npm run dev` in `frontend/`).
