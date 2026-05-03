import tempfile
import unittest
from pathlib import Path

from app.agents.html_file_tools import read_html_line_range, scoped_source_path


class HtmlFileToolTests(unittest.TestCase):
    def test_scoped_source_path_rejects_absolute_paths_outside_session_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "workspace" / "src"
            source_root.mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "outside the session source root"):
                scoped_source_path(source_root, Path(temp_dir) / "src" / "index.html")

    def test_scoped_source_path_resolves_relative_paths_inside_session_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "workspace" / "src"
            source_root.mkdir(parents=True)

            self.assertEqual(
                (source_root / "styles.css").resolve(),
                scoped_source_path(source_root, "styles.css").resolve(),
            )

    def test_read_html_line_range_uses_session_scoped_relative_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "workspace" / "src"
            source_root.mkdir(parents=True)
            (source_root / "index.html").write_text("<h1>A</h1>\n<p>B</p>\n", encoding="utf-8")

            self.assertEqual(
                "1: <h1>A</h1>\n2: <p>B</p>",
                read_html_line_range("index.html", 1, 2, source_root=source_root),
            )


if __name__ == "__main__":
    unittest.main()
