"""Offline model configuration and title wiring tests."""

import importlib
import os
import unittest
from unittest.mock import AsyncMock, patch

from backend import config, council


class ConfigTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)

    def load_config(self, **variables):
        with patch.dict(os.environ, variables, clear=True), patch("dotenv.load_dotenv"):
            return importlib.reload(config)

    def test_current_defaults(self):
        result = self.load_config()
        self.assertEqual(result.COUNCIL_MODELS, [
            "openai/gpt-6.1-sol", "google/gemini-4-argon",
            "anthropic/claude-sonnet-5.5", "x-ai/grok-4.7",
            "moonshotai/kimi-k3.1-pro", "deepseek/deepseek-v4.1-flash", "qwen/qwen3.8-max-0902",
        ])
        self.assertEqual(result.CHAIRMAN_MODEL, "anthropic/claude-opus-5.5")
        self.assertEqual(result.TITLE_MODEL, "google/gemini-3.5-flash-lite")
        self.assertEqual(result.OPENROUTER_TIMEOUT_SECONDS, 180.0)
        self.assertEqual(result.OPENROUTER_API_KEY, "")

    def test_environment_overrides(self):
        result = self.load_config(
            COUNCIL_MODELS=" provider/first , provider/second ",
            CHAIRMAN_MODEL=" provider/chair ", TITLE_MODEL=" provider/title ",
            OPENROUTER_TIMEOUT_SECONDS="240", OPENROUTER_API_KEY=" test-key ",
        )
        self.assertEqual(result.COUNCIL_MODELS, ["provider/first", "provider/second"])
        self.assertEqual(result.CHAIRMAN_MODEL, "provider/chair")
        self.assertEqual(result.TITLE_MODEL, "provider/title")
        self.assertEqual(result.OPENROUTER_TIMEOUT_SECONDS, 240.0)
        self.assertEqual(result.OPENROUTER_API_KEY, "test-key")

    def test_invalid_configuration(self):
        for variables in [
            {"COUNCIL_MODELS": " , "},
            {"COUNCIL_MODELS": "provider/a,provider/a"},
            {"CHAIRMAN_MODEL": " "}, {"TITLE_MODEL": ""},
            {"CHAIRMAN_MODEL": "google/gemini-4-argon"},
            {"CHAIRMAN_MODEL": "google/gemini-4-argon:online"},
            *({"OPENROUTER_TIMEOUT_SECONDS": value} for value in ["0", "-1", "nan", "inf", "oops"]),
        ]:
            with self.subTest(variables=variables), self.assertRaises(ValueError):
                self.load_config(**variables)

    def test_dotenv_is_project_relative(self):
        with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv") as load:
            importlib.reload(config)
        self.assertEqual(load.call_args.args[0], config.Path(config.__file__).resolve().parents[1] / ".env")


class TitleTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_configured_title_model(self):
        with patch.object(council, "TITLE_MODEL", "provider/title"), patch.object(
            council, "query_model", new_callable=AsyncMock, return_value={"content": '"A Short Title"'}
        ) as query:
            self.assertEqual(await council.generate_conversation_title("Question"), "A Short Title")
        self.assertEqual(query.call_args.args[0], "provider/title")
        self.assertEqual(query.call_args.kwargs["timeout"], 30.0)

    async def test_title_failure_has_fallback(self):
        with patch.object(council, "query_model", new_callable=AsyncMock, return_value=None):
            self.assertEqual(await council.generate_conversation_title("Question"), "New Conversation")
