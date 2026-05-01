import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.mcp_loader import load_mcp_stdio_servers


class McpLoaderTests(unittest.TestCase):
    def test_minimax_key_placeholder_resolves_from_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "minimax_server.json"
            config_path.write_text(
                """
{
  "mcpServers": {
    "MiniMax": {
      "command": "uvx",
      "args": ["minimax-coding-plan-mcp", "-y"],
      "env": {
        "MINIMAX_API_KEY": "MINIMAX_API_KEY",
        "MINIMAX_API_HOST": "https://api.minimax.io"
      }
    }
  }
}
""",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"MINIMAX_API_KEY": "real-key"}, clear=True):
                servers = load_mcp_stdio_servers([config_path])

        self.assertEqual(1, len(servers))
        self.assertEqual("MiniMax", servers[0].name)
        self.assertEqual("real-key", servers[0].params.env["MINIMAX_API_KEY"])
        self.assertEqual(
            "https://api.minimax.io",
            servers[0].params.env["MINIMAX_API_HOST"],
        )

    def test_minimax_server_is_skipped_without_api_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "minimax_server.json"
            config_path.write_text(
                """
{
  "mcpServers": {
    "MiniMax": {
      "command": "uvx",
      "args": ["minimax-coding-plan-mcp", "-y"],
      "env": {
        "MINIMAX_API_KEY": "MINIMAX_API_KEY"
      }
    }
  }
}
""",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual([], load_mcp_stdio_servers([config_path]))


if __name__ == "__main__":
    unittest.main()
