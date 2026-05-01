# Image-to-HTML Agent Workflow

This project separates the agent workflow into deterministic orchestration, OpenAI Agents SDK agent definitions, reusable skills, system instructions, MCP configs, and per-job artifacts.

Run the API:

```powershell
uv sync
uv run playwright install chromium
$env:OPENROUTER_API_KEY="..."
uv run uvicorn app.main:app --reload
```

The Agents SDK is configured with `OpenAIChatCompletionsModel` and `AsyncOpenAI(base_url="https://openrouter.ai/api/v1")`, which matches OpenRouter's OpenAI-compatible Chat Completions API.

