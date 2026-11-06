"""Exercise the local API end to end with an offline OpenRouter transport."""

import asyncio
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from backend import config, main, openrouter, storage


class ApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.enterContext(patch.object(storage, "DATA_DIR", temporary.name))
        self.enterContext(patch.object(main, "OPENROUTER_API_KEY", "test-only"))
        self.enterContext(patch.object(openrouter, "OPENROUTER_API_KEY", "test-only"))
        self.client = self.enterContext(TestClient(main.app))
        self.id = self.client.post("/api/conversations", json={}).json()["id"]

    def mock_router(self, handler):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        return patch.object(
            openrouter.httpx, "AsyncClient",
            side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
        )

    def response_handler(self, requests):
        def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            prompt = payload["messages"][0]["content"]
            if payload["model"] == config.TITLE_MODEL:
                content = "Offline Council Test"
            elif "Now provide your evaluation and ranking:" in prompt:
                content = "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n4. Response D"
            elif "You are the Chairman" in prompt:
                content = "Combined answer"
            else:
                content = "Individual answer"
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        return handler

    def test_full_nonstreaming_council(self):
        requests = []
        with self.mock_router(self.response_handler(requests)):
            response = self.client.post(f"/api/conversations/{self.id}/message", json={"content": "Question"})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual([r["model"] for r in result["stage1"]], config.COUNCIL_MODELS)
        self.assertEqual(len(result["stage2"]), 4)
        self.assertEqual(result["stage3"], {"model": config.CHAIRMAN_MODEL, "response": "Combined answer"})
        self.assertEqual(len(result["metadata"]["aggregate_rankings"]), 4)
        self.assertEqual(len(requests), 10)
        stored = storage.get_conversation(self.id)
        self.assertEqual(stored["title"], "Offline Council Test")
        self.assertEqual(len(stored["messages"]), 2)

    def test_full_streaming_council(self):
        requests = []
        with self.mock_router(self.response_handler(requests)):
            response = self.client.post(f"/api/conversations/{self.id}/message/stream", json={"content": "Question"})
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1]["type"], "complete")
        self.assertNotIn("error", [event["type"] for event in events])
        final = next(event["data"] for event in events if event["type"] == "stage3_complete")
        self.assertEqual(final["response"], "Combined answer")
        self.assertEqual(len(requests), 10)

    def test_missing_key_rejected_before_storage_or_requests(self):
        for suffix in ["message", "message/stream"]:
            with self.subTest(suffix=suffix), patch.object(main, "OPENROUTER_API_KEY", ""), patch.object(
                openrouter.httpx, "AsyncClient"
            ) as client:
                response = self.client.post(f"/api/conversations/{self.id}/{suffix}", json={"content": "Question"})
            self.assertEqual(response.status_code, 503)
            self.assertIn("OPENROUTER_API_KEY", response.json()["detail"])
            client.assert_not_called()
            self.assertEqual(storage.get_conversation(self.id)["messages"], [])

    def test_custom_council_and_chairman_in_both_flows(self):
        for suffix in ["message", "message/stream"]:
            requests = []
            with self.subTest(suffix=suffix), self.mock_router(self.response_handler(requests)):
                response = self.client.post(f"/api/conversations/{self.id}/{suffix}", json={
                    "content": "Question", "council_models": ["openai/custom", "other-provider/custom"],
                    "chairman_model": "independent/chairman",
                })
            self.assertEqual(response.status_code, 200)
            called = [request["model"] for request in requests]
            self.assertEqual(called.count("openai/custom"), 2)
            self.assertEqual(called.count("other-provider/custom"), 2)
            self.assertEqual(called.count("independent/chairman"), 1)
            self.assertNotIn(config.CHAIRMAN_MODEL, called)

    def test_invalid_model_choices_are_rejected(self):
        for options in [
            {"council_models": []}, {"council_models": ["provider/a", "provider/a"]},
            {"council_models": ["no-provider"]}, {"chairman_model": " "},
            {"council_models": [f"provider/{i}" for i in range(27)]},
        ]:
            with self.subTest(options=options):
                response = self.client.post(f"/api/conversations/{self.id}/message", json={"content": "Question", **options})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(storage.get_conversation(self.id)["messages"], [])

    def test_stream_failure_stops_before_rankings_and_cancels_title(self):
        async def slow_title(_):
            await asyncio.sleep(60)
            return "Too Late"
        with patch.object(main, "stage1_collect_responses", new_callable=AsyncMock, return_value=[]), patch.object(
            main, "stage2_collect_rankings", new_callable=AsyncMock
        ) as rank, patch.object(main, "stage3_synthesize_final", new_callable=AsyncMock) as synthesize, patch.object(
            main, "generate_conversation_title", side_effect=slow_title
        ):
            response = self.client.post(f"/api/conversations/{self.id}/message/stream", json={"content": "Question"})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("OpenRouter", events[-1]["message"])
        rank.assert_not_called()
        synthesize.assert_not_called()
        self.assertEqual(len(storage.get_conversation(self.id)["messages"]), 1)
