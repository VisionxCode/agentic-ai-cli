import logging
import unittest
from unittest.mock import patch

from app.runtime import _build_orchestrator


class MainLoggingTests(unittest.TestCase):
    def test_build_orchestrator_logs_agent_skills_and_tools(self):
        logger = logging.getLogger("test.agent-setup")
        logger.handlers.clear()
        logger.propagate = True

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with self.assertLogs("test.agent-setup", level="INFO") as logs:
                _build_orchestrator(logger)

        output = "\n".join(logs.output)
        self.assertIn("AGENT coder", output)
        self.assertIn("skills=", output)
        self.assertIn("runtime_tools=", output)
        self.assertIn("replace_html_lines", output)
        self.assertIn("AGENT evaluator", output)


if __name__ == "__main__":
    unittest.main()
