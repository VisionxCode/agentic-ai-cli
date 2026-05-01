import tempfile
import unittest
from pathlib import Path

from app.workspace import JobWorkspace


class JobWorkspaceTests(unittest.TestCase):
    def test_creates_expected_artifact_layout_for_a_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = JobWorkspace.create(Path(temp_dir), "job-123")
            source_root = workspace.root / "working" / "src"
            source_root.mkdir(parents=True)
            (source_root / "index.html").write_text("<html></html>", encoding="utf-8")
            (source_root / "styles.css").write_text("body { color: red; }", encoding="utf-8")
            original = workspace.save_original_image(b"image-bytes", ".png")
            iteration = workspace.save_iteration(
                number=1,
                source_html="<html></html>",
                source_root=source_root,
                generated_image=b"generated",
                evaluation={"score": 0.75},
            )
            (source_root / "index.html").write_text("<html>final</html>", encoding="utf-8")
            final = workspace.save_final(
                source_html="<html>final</html>",
                source_root=source_root,
                generated_image=b"final-image",
                report={"score": 0.95},
            )

            self.assertEqual(original.name, "original_image.png")
            self.assertTrue((workspace.root / "iterations" / "001").is_dir())
            self.assertEqual(iteration.source.read_text(encoding="utf-8"), "<html></html>")
            self.assertEqual(
                (iteration.source_root / "styles.css").read_text(encoding="utf-8"),
                "body { color: red; }",
            )
            self.assertEqual(iteration.generated_image.read_bytes(), b"generated")
            self.assertIn('"score": 0.75', iteration.evaluation.read_text(encoding="utf-8"))
            self.assertEqual(final.source.read_text(encoding="utf-8"), "<html>final</html>")
            self.assertEqual(
                (final.source_root / "index.html").read_text(encoding="utf-8"),
                "<html>final</html>",
            )


if __name__ == "__main__":
    unittest.main()
