import base64
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.sdk_common import build_agent_runtime
from app.config_loader import load_models
from app.providers.codex import _normalize_codex_final_response, _tool_call_from_leaked_text
from app.providers.codex_auth import read_codex_tokens, save_codex_tokens
from app.providers.selection import resolve_provider
from app.providers.settings import save_active_provider, save_provider_models


class FakeModelSettings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeAsyncOpenAI:
    latest_kwargs = None

    def __init__(self, **kwargs):
        FakeAsyncOpenAI.latest_kwargs = kwargs


class FakeOpenAIResponsesModel:
    latest_kwargs = None

    def __init__(self, **kwargs):
        FakeOpenAIResponsesModel.latest_kwargs = kwargs


class FakeAgent:
    latest_kwargs = None

    def __init__(self, **kwargs):
        FakeAgent.latest_kwargs = kwargs


class ProviderSelectionTests(unittest.TestCase):
    def test_provider_defaults_to_openrouter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"IBM_HACKATHON_AGENT_HOME": temp_dir}, clear=True):
                self.assertEqual("openrouter", resolve_provider())

    def test_provider_uses_env_when_no_saved_config_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {"IBM_HACKATHON_AGENT_HOME": temp_dir, "AI_PROVIDER": "codex"}
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual("codex", resolve_provider())

    def test_saved_provider_wins_over_env_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {"IBM_HACKATHON_AGENT_HOME": temp_dir, "AI_PROVIDER": "codex"}
            with patch.dict(os.environ, env, clear=True):
                save_active_provider("openrouter")
                self.assertEqual("openrouter", resolve_provider())

    def test_cli_provider_override_wins_over_saved_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"IBM_HACKATHON_AGENT_HOME": temp_dir}, clear=True):
                save_active_provider("openrouter")
                self.assertEqual("codex", resolve_provider("codex"))

    def test_invalid_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "codex, openrouter"):
            resolve_provider("bogus")

    def test_codex_model_env_overrides_saved_models(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "IBM_HACKATHON_AGENT_HOME": temp_dir,
                "CODEX_MODEL": "gpt-codex-shared",
                "CODEX_EVALUATOR_MODEL": "gpt-codex-eval",
            }
            with patch.dict(os.environ, env, clear=True):
                save_provider_models(
                    "codex",
                    {"coder": "saved-coder", "evaluator": "saved-evaluator"},
                )
                self.assertEqual(
                    {"coder": "gpt-codex-shared", "evaluator": "gpt-codex-eval"},
                    load_models(Path("app"), provider="codex"),
                )

    def test_codex_model_missing_fails_clearly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"IBM_HACKATHON_AGENT_HOME": temp_dir}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "Codex is selected but no model"):
                    load_models(Path("app"), provider="codex")

    def test_codex_import_copies_cli_tokens_to_app_auth_store(self):
        from app.providers.codex_auth import import_codex_cli_tokens

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_home = root / "codex-cli"
            app_home = root / "app-home"
            codex_home.mkdir()
            cli_auth = codex_home / "auth.json"
            cli_auth.write_text(
                json.dumps(
                    {
                        "tokens": {
                            "access_token": "cli-access",
                            "refresh_token": "cli-refresh",
                        }
                    }
                ),
                encoding="utf-8",
            )

            env = {
                "IBM_HACKATHON_AGENT_HOME": str(app_home),
                "CODEX_HOME": str(codex_home),
            }
            with patch.dict(os.environ, env, clear=True):
                saved_path = import_codex_cli_tokens()
                stored = json.loads(saved_path.read_text(encoding="utf-8"))

            self.assertEqual(cli_auth.read_text(encoding="utf-8"), cli_auth.read_text(encoding="utf-8"))
            self.assertEqual("cli-access", stored["providers"]["codex"]["tokens"]["access_token"])
            self.assertNotEqual(cli_auth, saved_path)

    def test_codex_refresh_updates_stored_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"IBM_HACKATHON_AGENT_HOME": temp_dir}, clear=True):
                save_codex_tokens(
                    {
                        "access_token": _jwt_with_exp(1),
                        "refresh_token": "old-refresh",
                    },
                    source="test",
                )
                with patch(
                    "app.providers.codex_auth.refresh_codex_tokens",
                    return_value={"access_token": "new-access", "refresh_token": "new-refresh"},
                ):
                    data = read_codex_tokens()

                self.assertEqual("new-access", data["tokens"]["access_token"])
                stored = json.loads((Path(temp_dir) / "auth.json").read_text(encoding="utf-8"))
                self.assertEqual("new-refresh", stored["providers"]["codex"]["tokens"]["refresh_token"])

    def test_codex_runtime_builder_uses_responses_model_without_openrouter_body(self):
        fake_agents = types.SimpleNamespace(
            Agent=FakeAgent,
            AsyncOpenAI=FakeAsyncOpenAI,
            ModelSettings=FakeModelSettings,
            OpenAIResponsesModel=FakeOpenAIResponsesModel,
            Runner=object(),
            set_tracing_disabled=lambda disabled: None,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"IBM_HACKATHON_AGENT_HOME": temp_dir}, clear=True):
                save_codex_tokens(
                    {
                        "access_token": _jwt_with_exp(9999999999, account_id="acct_123"),
                        "refresh_token": "refresh",
                    },
                    source="test",
                )
                with patch.dict(sys.modules, {"agents": fake_agents}):
                    build_agent_runtime(
                        name="coder",
                        instructions="test",
                        model_name="gpt-codex-test",
                        provider="codex",
                    )

        self.assertEqual(
            {"store": False, "response_include": ["reasoning.encrypted_content"]},
            FakeAgent.latest_kwargs["model_settings"].kwargs,
        )
        self.assertEqual("gpt-codex-test", FakeOpenAIResponsesModel.latest_kwargs["model"])
        headers = FakeAsyncOpenAI.latest_kwargs["default_headers"]
        self.assertEqual("codex_cli_rs", headers["originator"])
        self.assertEqual("acct_123", headers["ChatGPT-Account-ID"])

    def test_codex_leaked_tool_call_text_is_converted_to_function_call(self):
        call = _tool_call_from_leaked_text(
            'assistant to=functions.write_html_file {"content":"<html></html>"}'
        )

        self.assertIsNotNone(call)
        self.assertEqual("function_call", getattr(call, "type", None))
        self.assertEqual("write_html_file", getattr(call, "name", None))
        self.assertEqual('{"content":"<html></html>"}', getattr(call, "arguments", None))

    def test_codex_empty_output_uses_output_text_fallback(self):
        response = types.SimpleNamespace(output=[], output_text="<html>ok</html>")

        normalized = _normalize_codex_final_response(response)

        self.assertEqual(1, len(normalized.output))
        self.assertEqual("message", getattr(normalized.output[0], "type", None))


def _jwt_with_exp(exp: int, *, account_id: str | None = None) -> str:
    payload = {"exp": exp}
    if account_id:
        payload["https://api.openai.com/auth"] = {"chatgpt_account_id": account_id}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"header.{encoded}.signature"


if __name__ == "__main__":
    unittest.main()
