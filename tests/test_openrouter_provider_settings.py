import os
import sys
import types
import unittest
from unittest.mock import patch

from app.agents.sdk_common import (
    build_openrouter_agent,
    openrouter_extra_body,
    openrouter_provider_extra_body,
    openrouter_reasoning_extra_body,
    openrouter_temperature,
)


class FakeModelSettings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeAsyncOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeOpenAIChatCompletionsModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeAgent:
    latest_kwargs = None

    def __init__(self, **kwargs):
        FakeAgent.latest_kwargs = kwargs


class OpenRouterProviderSettingsTests(unittest.TestCase):
    def test_empty_provider_settings_use_default_request_body(self):
        with patch.dict(os.environ, {"OPENROUTER_PROVIDER_ORDER": ""}, clear=True):
            self.assertIsNone(openrouter_provider_extra_body())

    def test_provider_settings_are_read_from_environment(self):
        env = {
            "OPENROUTER_PROVIDER_ORDER": "deepinfra/turbo, together",
            "OPENROUTER_PROVIDER_ALLOW_FALLBACKS": "false",
            "OPENROUTER_PROVIDER_REQUIRE_PARAMETERS": "true",
            "OPENROUTER_PROVIDER_DATA_COLLECTION": "deny",
            "OPENROUTER_PROVIDER_ONLY": "",
        }

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                {
                    "provider": {
                        "order": ["deepinfra/turbo", "together"],
                        "allow_fallbacks": False,
                        "require_parameters": True,
                        "data_collection": "deny",
                    }
                },
                openrouter_provider_extra_body(),
            )

    def test_temperature_is_read_from_environment(self):
        with patch.dict(os.environ, {"OPENROUTER_TEMPERATURE": "0.35"}, clear=True):
            self.assertEqual(0.35, openrouter_temperature())

    def test_temperature_rejects_invalid_values(self):
        with patch.dict(os.environ, {"OPENROUTER_TEMPERATURE": "2.5"}, clear=True):
            with self.assertRaises(ValueError):
                openrouter_temperature()

    def test_reasoning_settings_are_read_from_environment(self):
        env = {
            "OPENROUTER_REASONING_ENABLED": "true",
            "OPENROUTER_REASONING_EFFORT": "HIGH",
            "OPENROUTER_REASONING_EXCLUDE": "false",
        }

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                {
                    "reasoning": {
                        "enabled": True,
                        "effort": "high",
                        "exclude": False,
                    }
                },
                openrouter_reasoning_extra_body(),
            )

    def test_reasoning_effort_rejects_unknown_level(self):
        with patch.dict(os.environ, {"OPENROUTER_REASONING_EFFORT": "maximum"}, clear=True):
            with self.assertRaises(ValueError):
                openrouter_reasoning_extra_body()

    def test_extra_body_merges_provider_and_reasoning_settings(self):
        env = {
            "OPENROUTER_PROVIDER_ORDER": "openai",
            "OPENROUTER_REASONING_ENABLED": "true",
            "OPENROUTER_REASONING_EFFORT": "medium",
        }

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                {
                    "provider": {"order": ["openai"]},
                    "reasoning": {"enabled": True, "effort": "medium"},
                },
                openrouter_extra_body(),
            )

    def test_build_openrouter_agent_passes_provider_settings_to_model_settings(self):
        fake_agents = types.SimpleNamespace(
            Agent=FakeAgent,
            AsyncOpenAI=FakeAsyncOpenAI,
            ModelSettings=FakeModelSettings,
            OpenAIChatCompletionsModel=FakeOpenAIChatCompletionsModel,
            Runner=object(),
            set_tracing_disabled=lambda disabled: None,
        )
        env = {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_TEMPERATURE": "0.2",
            "OPENROUTER_PROVIDER_ONLY": "deepinfra",
            "OPENROUTER_REASONING_ENABLED": "true",
            "OPENROUTER_REASONING_EFFORT": "low",
            "OPENROUTER_REASONING_EXCLUDE": "true",
        }

        with patch.dict(sys.modules, {"agents": fake_agents}), patch.dict(os.environ, env, clear=True):
            build_openrouter_agent(
                name="coder",
                instructions="test",
                model_name="custom/model",
            )

        model_settings = FakeAgent.latest_kwargs["model_settings"]
        self.assertEqual(
            {
                "temperature": 0.2,
                "extra_body": {
                    "provider": {"only": ["deepinfra"]},
                    "reasoning": {"enabled": True, "effort": "low", "exclude": True},
                },
            },
            model_settings.kwargs,
        )


if __name__ == "__main__":
    unittest.main()
