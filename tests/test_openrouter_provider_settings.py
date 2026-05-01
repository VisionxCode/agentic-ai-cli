import os
import sys
import types
import unittest
from unittest.mock import patch

from app.agents.sdk_common import build_openrouter_agent, openrouter_provider_extra_body


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
            "OPENROUTER_PROVIDER_ONLY": "deepinfra",
        }

        with patch.dict(sys.modules, {"agents": fake_agents}), patch.dict(os.environ, env, clear=True):
            build_openrouter_agent(
                name="coder",
                instructions="test",
                model_name="custom/model",
            )

        model_settings = FakeAgent.latest_kwargs["model_settings"]
        self.assertEqual({"extra_body": {"provider": {"only": ["deepinfra"]}}}, model_settings.kwargs)


if __name__ == "__main__":
    unittest.main()
