Agents reason and create. Deterministic scripts execute filesystem, rendering, image inspection, validation, and orchestration work.

Keep outputs modular:
- prompts live in app/instructions
- reusable skills live in app/skills
- deterministic Python tools live in app/tools
- MCP server configs live in app/mcp
- generated job artifacts live in app/workspaces/{job_id}

