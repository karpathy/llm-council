"""Public model discovery prioritizes the big four without excluding others."""

import unittest
from unittest.mock import patch

import httpx

from backend import model_catalog


class ModelCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_models_are_text_compatible_and_prioritized(self):
        seen = []
        def handler(request):
            seen.append(request)
            models = [{"id": name, "name": name, "architecture": {
                "input_modalities": ["text"], "output_modalities": ["text"],
            }} for name in ["other/model", "google/model", "x-ai/model", "anthropic/model", "openai/model"]]
            models.append({"id": "image/only", "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]}})
            return httpx.Response(200, json={"data": models})
        real = httpx.AsyncClient
        with patch.object(model_catalog.httpx, "AsyncClient", side_effect=lambda **kwargs: real(
            transport=httpx.MockTransport(handler), **kwargs
        )):
            result = await model_catalog.list_model_options()
        self.assertTrue(result["catalog_available"])
        self.assertEqual([m["id"] for m in result["models"]], [
            "openai/model", "anthropic/model", "google/model", "x-ai/model", "other/model",
        ])
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].method, "GET")
        self.assertNotIn("authorization", seen[0].headers)
        self.assertEqual(seen[0].content, b"")

    async def test_catalog_failure_keeps_manual_defaults_available(self):
        with patch.object(model_catalog.httpx, "AsyncClient", side_effect=ImportError), self.assertLogs("backend.model_catalog"):
            result = await model_catalog.list_model_options()
        self.assertFalse(result["catalog_available"])
        self.assertTrue(result["models"])
        self.assertIn("chairman_model", result["defaults"])
