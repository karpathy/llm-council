"""The catalog check never sends credentials or calls inference."""

import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import httpx

from backend import check_models


class CatalogTests(unittest.TestCase):
    def run_check(self, payload, status=200):
        response = httpx.Response(status, json=payload, request=httpx.Request("GET", check_models.CATALOG_URL))
        output = io.StringIO()
        with patch.object(check_models, "COUNCIL_MODELS", ["provider/model"]), patch.object(
            check_models, "CHAIRMAN_MODEL", "provider/model"
        ), patch.object(check_models, "TITLE_MODEL", "provider/model"), patch.object(
            check_models.httpx, "get", return_value=response
        ) as get, redirect_stdout(output), redirect_stderr(output):
            code = check_models.main()
        get.assert_called_once_with(check_models.CATALOG_URL, timeout=30.0)
        return code, output.getvalue()

    def model(self, **overrides):
        return {"id": "provider/model", "architecture": {
            "input_modalities": ["text"], "output_modalities": ["text"],
        }, **overrides}

    def test_available_text_chat_model(self):
        code, output = self.run_check({"data": [self.model(endpoints=["/api/v1/chat/completions"])]})
        self.assertEqual(code, 0)
        self.assertEqual(output.count("FOUND:"), 1)
        self.assertIn("inference have not been tested", output)

    def test_older_catalog_without_endpoints(self):
        self.assertEqual(self.run_check({"data": [self.model()]})[0], 0)

    def test_missing_model(self):
        self.assertEqual(self.run_check({"data": []})[0], 1)

    def test_unsupported_model(self):
        for model in [self.model(endpoints=["/api/v1/images/generations"]), self.model(architecture={})]:
            with self.subTest(model=model):
                self.assertEqual(self.run_check({"data": [model]})[0], 1)

    def test_failed_catalog(self):
        for payload, status in [({"error": "failed"}, 500), ({}, 200), ({"data": None}, 200)]:
            with self.subTest(status=status):
                self.assertEqual(self.run_check(payload, status)[0], 1)

    def test_missing_optional_proxy_dependency_is_actionable(self):
        output = io.StringIO()
        with patch.object(check_models.httpx, "get", side_effect=ImportError), redirect_stderr(output):
            self.assertEqual(check_models.main(), 1)
        self.assertIn("httpx[socks]", output.getvalue())
