"""Offline client tests. Never send paid requests or use real API credentials."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend import openrouter


class OpenRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.messages = [{"role": "user", "content": "PRIVATE_PROMPT"}]
        self.key_patch = patch.object(openrouter, "OPENROUTER_API_KEY", "PRIVATE_KEY")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.client_type = httpx.AsyncClient
        self.requests = []

    async def query(self, response=None, error=None, timeout=17):
        def handler(request):
            self.requests.append(request)
            if error:
                raise error
            return response

        def client_factory(**kwargs):
            self.assertEqual(kwargs["timeout"], timeout)
            return self.client_type(transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(openrouter.httpx, "AsyncClient", side_effect=client_factory):
            return await openrouter.query_model("test/model", self.messages, timeout=timeout)

    def completion(self, content="Answer", **message_fields):
        return httpx.Response(200, json={"choices": [{"message": {"content": content, **message_fields}}]})

    async def test_text_request_contract_and_reasoning_metadata(self):
        details = [{"type": "reasoning.summary", "summary": "metadata"}]
        result = await self.query(self.completion(" Answer\n", reasoning_details=details))
        self.assertEqual(result, {"content": " Answer\n", "reasoning_details": details})
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(str(request.url), "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer PRIVATE_KEY")
        self.assertEqual(json.loads(request.content), {"model": "test/model", "messages": self.messages})

    async def test_text_parts_only(self):
        result = await self.query(self.completion([
            {"type": "text", "text": "Hello "},
            {"type": "image_url", "image_url": {"url": "ignored"}},
            {"type": "reasoning", "text": "must not leak"},
            {"type": "text", "text": "world"},
        ]))
        self.assertEqual(result, {"content": "Hello world", "reasoning_details": None})

    async def test_missing_key_does_not_construct_client(self):
        for key in (None, "", " \n\t"):
            with self.subTest(key=key), patch.object(openrouter, "OPENROUTER_API_KEY", key):
                with patch.object(openrouter.httpx, "AsyncClient") as client:
                    with self.assertLogs(openrouter.logger, level="WARNING"):
                        self.assertIsNone(await openrouter.query_model("test/model", self.messages))
                    client.assert_not_called()

    async def test_http_failures_are_safe_and_not_retried(self):
        for status, hint in ((401, "API_KEY"), (402, "credits"), (429, "rate limited"), (500, "request failed"), (503, "request failed")):
            with self.subTest(status=status), self.assertLogs(openrouter.logger, level="WARNING") as logs:
                before = len(self.requests)
                self.assertIsNone(await self.query(httpx.Response(status, text="PRIVATE_BODY PRIVATE_PROMPT PRIVATE_KEY")))
                self.assertEqual(len(self.requests), before + 1)
                output = " ".join(logs.output)
                self.assertIn(str(status), output)
                self.assertIn(hint, output)
                for secret in ("PRIVATE_BODY", "PRIVATE_PROMPT", "PRIVATE_KEY", "Authorization"):
                    self.assertNotIn(secret, output)

    async def test_network_timeout_and_unexpected_errors_are_safe(self):
        for error in (httpx.ReadTimeout("PRIVATE_KEY"), httpx.ConnectTimeout("PRIVATE_KEY"), httpx.ConnectError("PRIVATE_KEY"), RuntimeError("PRIVATE_KEY")):
            with self.subTest(error=type(error)), self.assertLogs(openrouter.logger, level="WARNING") as logs:
                self.assertIsNone(await self.query(error=error))
                self.assertNotIn("PRIVATE_KEY", " ".join(logs.output))

    async def test_invalid_json(self):
        with self.assertLogs(openrouter.logger, level="WARNING") as logs:
            self.assertIsNone(await self.query(httpx.Response(200, text="PRIVATE_BODY")))
            self.assertNotIn("PRIVATE_BODY", " ".join(logs.output))

    async def test_invalid_payload_shapes_and_embedded_errors(self):
        payloads = [None, [], "oops", {}, {"error": {"message": "PRIVATE_BODY"}},
                    {"choices": None}, {"choices": {}}, {"choices": []}, {"choices": [None]},
                    {"choices": [{}]}, {"choices": [{"message": None}]},
                    {"choices": [{"message": []}]},
                    {"choices": [{"error": {"message": "PRIVATE_BODY"}, "message": {"content": "partial"}}]},
                    {"choices": [{"finish_reason": "error", "message": {"content": "partial"}}]},
                    {"error": {"message": "PRIVATE_BODY"}, "choices": [{"message": {"content": "partial"}}]}]
        for payload in payloads:
            with self.subTest(payload=payload), self.assertLogs(openrouter.logger, level="WARNING") as logs:
                self.assertIsNone(await self.query(httpx.Response(200, json=payload)))
                self.assertNotIn("PRIVATE_BODY", " ".join(logs.output))

    async def test_no_text_and_reasoning_only_are_not_answers(self):
        contents = [None, "", " \n", 42, {}, [], ["wrong"], [{"type": "text", "text": None}],
                    [{"type": "text", "text": " "}], [{"type": "image_url", "image_url": {}}],
                    [{"type": "reasoning", "text": "PRIVATE_REASONING"}]]
        for content in contents:
            with self.subTest(content=content), self.assertLogs(openrouter.logger, level="WARNING") as logs:
                self.assertIsNone(await self.query(self.completion(content, reasoning="PRIVATE_REASONING", reasoning_details=[{"text": "PRIVATE_REASONING"}])))
                self.assertNotIn("PRIVATE_REASONING", " ".join(logs.output))

    async def test_configured_default_timeout(self):
        def factory(**kwargs):
            self.assertEqual(kwargs["timeout"], openrouter.OPENROUTER_TIMEOUT_SECONDS)
            return self.client_type(transport=httpx.MockTransport(lambda request: self.completion()), **kwargs)
        with patch.object(openrouter.httpx, "AsyncClient", side_effect=factory):
            self.assertIsNotNone(await openrouter.query_model("test/model", self.messages))

    async def test_parallel_real_client_failure_order_and_concurrency(self):
        all_started = asyncio.Event()
        started = []
        completed = []

        async def handler(request):
            model = json.loads(request.content)["model"]
            started.append(model)
            if len(started) == 3:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=1)
            if model == "slow":
                await asyncio.sleep(0.01)
            completed.append(model)
            return httpx.Response(429) if model == "failed" else self.completion(model)

        def factory(**kwargs):
            return self.client_type(transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(openrouter.httpx, "AsyncClient", side_effect=factory):
            with self.assertLogs(openrouter.logger, level="WARNING"):
                result = await openrouter.query_models_parallel(["slow", "failed", "fast"], self.messages)
        self.assertEqual(list(result), ["slow", "failed", "fast"])
        self.assertIsNone(result["failed"])
        self.assertEqual(result["slow"]["content"], "slow")
        self.assertEqual(result["fast"]["content"], "fast")
        self.assertEqual(completed[-1], "slow")
        self.assertEqual(len(started), 3)

    async def test_parallel_unexpected_exception_isolated(self):
        with patch.object(openrouter, "query_model", new=AsyncMock(side_effect=[RuntimeError("PRIVATE_KEY"), {"content": "ok"}])):
            with self.assertLogs(openrouter.logger, level="WARNING") as logs:
                result = await openrouter.query_models_parallel(["bad", "good"], self.messages)
        self.assertEqual(result, {"bad": None, "good": {"content": "ok"}})
        self.assertNotIn("PRIVATE_KEY", " ".join(logs.output))

    async def test_empty_parallel_list(self):
        with patch.object(openrouter, "query_model", new=AsyncMock()) as query:
            self.assertEqual(await openrouter.query_models_parallel([], self.messages), {})
            query.assert_not_called()

    async def test_parent_cancellation_propagates(self):
        started = asyncio.Event()

        async def slow_query(*args):
            started.set()
            await asyncio.Event().wait()

        with patch.object(openrouter, "query_model", side_effect=slow_query):
            task = asyncio.create_task(openrouter.query_models_parallel(["slow"], self.messages))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    unittest.main()
