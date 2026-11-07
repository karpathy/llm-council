"""Offline research API contract tests; no paid or external requests."""

import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend import openrouter


class ResearchClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.object(openrouter, "OPENROUTER_API_KEY", "test-only"))
        self.messages = [{"role": "user", "content": "Question"}]
        self.requests = []
        self.real_client = httpx.AsyncClient

    async def query(self, *, annotations=None, usage=None, fields=None, status=200, **options):
        message = {"content": "Answer", "annotations": annotations}
        choice = {"message": message, **(fields or {})}
        payload = {"choices": [choice], "usage": usage}

        def handler(request):
            self.requests.append(json.loads(request.content))
            return httpx.Response(status, json=payload)

        with patch.object(openrouter.httpx, "AsyncClient", side_effect=lambda **kwargs: self.real_client(
            transport=httpx.MockTransport(handler), **kwargs
        )):
            return await openrouter.query_model("provider/model", self.messages, **options)

    def annotation(self, url="https://example.com/evidence", **values):
        return {"type": "url_citation", "url_citation": {"url": url, "title": "Evidence", **values}}

    async def test_research_off_preserves_original_request_and_response(self):
        result = await self.query(annotations=[self.annotation()])
        self.assertEqual(self.requests, [{"model": "provider/model", "messages": self.messages}])
        self.assertEqual(result, {"content": "Answer", "reasoning_details": None})

    async def test_research_uses_bounded_explicit_server_tools(self):
        result = await self.query(research=True, annotations=[self.annotation(content="Evidence text")], usage={
            "server_tool_use_details": {"web_search_requests": 2, "tool_calls_executed": 4},
        })
        payload = self.requests[0]
        self.assertEqual(payload["tools"], [
            {"type": "openrouter:web_search", "parameters": {
                "engine": "exa", "mode": "auto", "max_uses": 2,
                "max_results": 3, "max_total_results": 6, "max_characters": 2000,
            }},
            {"type": "openrouter:web_fetch", "parameters": {
                "engine": "openrouter", "max_uses": 2, "max_content_tokens": 2000,
            }},
        ])
        self.assertEqual(payload["max_tool_calls"], 4)
        self.assertEqual(payload["max_tokens"], openrouter.RESEARCH_MAX_OUTPUT_TOKENS)
        self.assertEqual(payload["provider"], {"require_parameters": True})
        self.assertNotIn("plugins", payload)
        self.assertEqual(result["research"]["status"], "sources_returned")
        self.assertEqual(result["research"]["search_requests"], 2)
        self.assertEqual(result["research"]["tool_calls_executed"], 4)
        self.assertEqual(result["citations"][0]["content"], "Evidence text")
        self.assertTrue(any("do not verify" in warning for warning in result["research"]["warnings"]))

    async def test_output_cap_without_research_never_adds_tools(self):
        result = await self.query(max_output_tokens=1000)
        self.assertEqual(self.requests[0], {"model": "provider/model", "messages": self.messages, "max_tokens": 1000})
        self.assertNotIn("research", result)

    async def test_research_cannot_exceed_configured_output_cap(self):
        for requested, expected in [(100, 100), (openrouter.RESEARCH_MAX_OUTPUT_TOKENS * 2, openrouter.RESEARCH_MAX_OUTPUT_TOKENS)]:
            with self.subTest(requested=requested):
                await self.query(research=True, max_output_tokens=requested)
                self.assertEqual(self.requests[-1]["max_tokens"], expected)

    async def test_bad_output_limits_never_send_request(self):
        for value in [0, -1, True, "100", float("nan")]:
            with self.subTest(value=value), self.assertLogs(openrouter.logger):
                self.assertIsNone(await self.query(max_output_tokens=value))
        self.assertEqual(self.requests, [])

    async def test_missing_evidence_is_explicit(self):
        for annotations in [None, {}, "not annotations", [], [None, {}, {"type": "url_citation", "url_citation": []}]]:
            with self.subTest(annotations=annotations):
                result = await self.query(research=True, annotations=annotations)
                self.assertEqual(result["citations"], [])
                self.assertEqual(result["research"]["status"], "no_sources")
                self.assertIsNone(result["research"]["search_requests"])
                self.assertIn("No usable source citations were returned; this answer is not verified web research.", result["research"]["warnings"])

    async def test_usage_validation_and_unfinished_tool_warning(self):
        for usage in [None, [], {"server_tool_use_details": []}, {"server_tool_use_details": {
            "web_search_requests": True, "tool_calls_executed": "2",
        }}, {"server_tool_use_details": {"web_search_requests": -1, "tool_calls_executed": -1}}]:
            with self.subTest(usage=usage):
                result = await self.query(research=True, usage=usage)
                self.assertIsNone(result["research"]["search_requests"])
                self.assertIsNone(result["research"]["tool_calls_executed"])
        result = await self.query(research=True, fields={"finish_reason": "tool_calls"}, usage={
            "server_tool_use_details": {"web_search_requests": 0, "tool_calls_executed": 0},
        })
        warnings = " ".join(result["research"]["warnings"])
        self.assertIn("no web searches", warnings)
        self.assertIn("no executed server tools", warnings)
        self.assertIn("unfinished tool calls", warnings)
        limited = await self.query(research=True, fields={"finish_reason": "length"})
        self.assertIn("output limit", " ".join(limited["research"]["warnings"]))

    async def test_unsafe_links_and_malformed_annotations_are_not_exposed(self):
        unsafe = ["javascript:alert(1)", "data:text/html,bad", "file:///etc/passwd", "https://user:pass@example.com",
                  "http://localhost:8001", "http://host.local/path", "http://127.0.0.1", "http://10.0.0.1",
                  "http://169.254.169.254", "http://[::1]", "http://[fd00::1]", "http://2130706433",
                  "http://127.1", "http://example.com\\@127.0.0.1", "http://exa\nmple.com", "http://example.com:99999",
                  "http://127%2e0%2e0%2e1", "http://intranet", None, {}, 3]
        annotations = [self.annotation(url) for url in unsafe] + [self.annotation()]
        result = await self.query(research=True, annotations=annotations)
        self.assertEqual(result["citations"], [{"url": "https://example.com/evidence", "title": "Evidence"}])

    async def test_citations_are_deduplicated_truncated_and_bounded(self):
        first = self.annotation(title="T" * 500, content="E" * 3000, secret="not copied")
        result = await self.query(research=True, annotations=[first, first] + [self.annotation(f"https://example.com/{i}") for i in range(20)])
        self.assertEqual(len(result["citations"]), 12)
        self.assertEqual(len(result["citations"][0]["title"]), 300)
        self.assertEqual(len(result["citations"][0]["content"]), 2000)
        self.assertNotIn("secret", str(result))

    async def test_valid_citation_offsets_are_preserved(self):
        result = await self.query(research=True, annotations=[self.annotation(start_index=0, end_index=6)])
        self.assertEqual(result["citations"][0]["start_index"], 0)
        self.assertEqual(result["citations"][0]["end_index"], 6)
        for start, end in [(-1, 3), (3, 2), (False, 2), (0, 100), ("0", "3")]:
            result = await self.query(research=True, annotations=[self.annotation(start_index=start, end_index=end)])
            self.assertNotIn("start_index", result["citations"][0])

    async def test_research_failure_does_not_retry_or_downgrade(self):
        with self.assertLogs(openrouter.logger):
            self.assertIsNone(await self.query(research=True, status=400))
        self.assertEqual(len(self.requests), 1)
        self.assertIn("tools", self.requests[0])

    async def test_parallel_forwards_research_options(self):
        with patch.object(openrouter, "query_model", new_callable=AsyncMock, return_value={"content": "Answer"}) as query:
            await openrouter.query_models_parallel(["one/model", "two/model"], self.messages, research=True, max_output_tokens=2000)
        self.assertEqual(query.await_count, 2)
        for call in query.await_args_list:
            self.assertEqual(call.kwargs, {"research": True, "max_output_tokens": 2000})
