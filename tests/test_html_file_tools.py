import tempfile
import unittest
import logging
from pathlib import Path

from app.agents.html_file_tools import (
    insert_after_line,
    read_html_line_range,
    replace_html_line_range,
)
from app.job_logging import job_logging_context


class HtmlFileToolTests(unittest.TestCase):
    def test_read_html_line_range_returns_numbered_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.html"
            path.write_text("one\ntwo\nthree\n", encoding="utf-8")

            self.assertEqual("2: two\n3: three", read_html_line_range(str(path), 2, 3))

    def test_replace_html_line_range_updates_only_target_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.html"
            path.write_text("one\ntwo\nthree\n", encoding="utf-8")

            result = replace_html_line_range(str(path), 2, 2, "TWO")

            self.assertIn("Replaced lines 2-2", result)
            self.assertEqual("one\nTWO\nthree\n", path.read_text(encoding="utf-8"))

    def test_insert_after_line_inserts_without_rewriting_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.html"
            path.write_text("one\ntwo\n", encoding="utf-8")

            result = insert_after_line(str(path), 1, "middle")

            self.assertIn("Inserted after line 1", result)
            self.assertEqual("one\nmiddle\ntwo\n", path.read_text(encoding="utf-8"))

    def test_tool_usage_is_logged_when_context_is_active(self):
        logger = logging.getLogger("test.tool-usage")
        logger.handlers.clear()
        logger.propagate = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source.html"
            path.write_text("one\ntwo\n", encoding="utf-8")

            with self.assertLogs("test.tool-usage", level="INFO") as logs:
                with job_logging_context(logger):
                    replace_html_line_range(str(path), 2, 2, "TWO")

        output = "\n".join(logs.output)
        self.assertIn("TOOL replace_html_lines", output)
        self.assertIn("changed=True", output)


if __name__ == "__main__":
    unittest.main()
