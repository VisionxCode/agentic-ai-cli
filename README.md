# Image-to-Source-Code Agent Workflow

This project separates the agent workflow into deterministic orchestration, OpenAI Agents SDK agent definitions, reusable skills, system instructions, MCP configs, and per-job artifacts.

Run the CLI:

```powershell
uv sync
uv run playwright install chromium
Copy-Item .env.example .env
uv run python -m app.main provider select
uv run python -m app.main --image path\to\original.png --note "Optional guidance"
```

The command prints the job status, score, iteration count, final artifact paths, and per-job log path. Add `--json` for machine-readable output, or `--job-id your-id` to choose the workspace/log id.

Provider selection is saved in a user-local config file at `~/.ibm_hackathon_agent/config.json` by default. Use `--provider openrouter` or `--provider codex` on a single image run to override the saved choice without changing it.

## OpenRouter API key mode

OpenRouter remains the default provider. The Agents SDK uses `OpenAIChatCompletionsModel` and `AsyncOpenAI(base_url="https://openrouter.ai/api/v1")`, which matches OpenRouter's OpenAI-compatible Chat Completions API.

During `python -m app.main provider select`, choose `openrouter` and provide an API key if `OPENROUTER_API_KEY` is not already set. Model selection defaults to `app/config/models.yaml`; saved provider setup can override it. Environment overrides still work: set `OPENROUTER_MODEL` to use one model for both agents, or `OPENROUTER_CODER_MODEL` and `OPENROUTER_EVALUATOR_MODEL` for separate models.

Optional generation settings can be set in `.env`. `OPENROUTER_TEMPERATURE` accepts `0.0` through `2.0`; blank values use OpenRouter/model defaults. Reasoning can be controlled with `OPENROUTER_REASONING_ENABLED`, `OPENROUTER_REASONING_EFFORT` (`none`, `minimal`, `low`, `medium`, `high`, or `xhigh`), and `OPENROUTER_REASONING_EXCLUDE`. These are sent through OpenRouter's unified `reasoning` request object.

Optional OpenRouter provider routing can be set with `OPENROUTER_PROVIDER_*` variables in `.env`. Blank values are ignored, so the request falls back to OpenRouter's default provider routing. For example, set `OPENROUTER_PROVIDER_ORDER=deepinfra/turbo,together` and `OPENROUTER_PROVIDER_ALLOW_FALLBACKS=false` to prefer those providers and disable fallback routing.

## Codex OAuth mode

Codex mode uses user-owned Codex/ChatGPT OAuth credentials and stores this app's copied credentials in `~/.ibm_hackathon_agent/auth.json` by default. It can import existing Codex CLI credentials from `~/.codex/auth.json` without mutating the Codex CLI file.

```powershell
uv run python -m app.main auth codex import
# or:
uv run python -m app.main auth codex login
uv run python -m app.main provider select --provider codex
```

Codex requires an explicit model. The setup flow can save one shared model or separate coder/evaluator models. For automation, set `CODEX_MODEL`, or set `CODEX_CODER_MODEL` and `CODEX_EVALUATOR_MODEL`. If Codex is selected without stored credentials or models, the run fails clearly and does not fall back to OpenRouter.

If the coder uses file tools heavily during revisions, increase `OPENROUTER_AGENT_MAX_TURNS` in `.env`. The default is `30` per coder attempt. If the coder reaches that budget, the app makes one bounded finalization pass using `OPENROUTER_AGENT_FINISH_TURNS` (`5` by default) to save a renderable partial result before the outer workflow continues to the next iteration.
