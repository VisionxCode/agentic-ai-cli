# Image-to-HTML Agent Workflow

This project separates the agent workflow into deterministic orchestration, OpenAI Agents SDK agent definitions, reusable skills, system instructions, MCP configs, and per-job artifacts.

Run the API:

```powershell
uv sync
uv run playwright install chromium
Copy-Item .env.example .env
# Edit .env and set OPENROUTER_API_KEY and OPENROUTER_MODEL.
uv run uvicorn app.main:app --reload
```

The Agents SDK is configured with `OpenAIChatCompletionsModel` and `AsyncOpenAI(base_url="https://openrouter.ai/api/v1")`, which matches OpenRouter's OpenAI-compatible Chat Completions API.

Model selection defaults to `app/config/models.yaml`. Set `OPENROUTER_MODEL` in `.env` to use one model for both the coder and evaluator agents, or set `OPENROUTER_CODER_MODEL` and `OPENROUTER_EVALUATOR_MODEL` for separate models.

If the coder uses file tools heavily during revisions, increase `OPENROUTER_AGENT_MAX_TURNS` in `.env`. The default is `30`.
