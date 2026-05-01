import tempfile
import unittest
from pathlib import Path

from app.agents.skill_file_tools import list_skill_files_for_root, read_skill_file_for_root


class SkillFileToolTests(unittest.TestCase):
    def test_lists_and_reads_files_inside_skill_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            skill_root = skills_root / "huashu_design"
            (skill_root / "assets" / "source").mkdir(parents=True)
            (skill_root / "assets" / "source" / "SKILL.md").write_text(
                "Huashu body.", encoding="utf-8"
            )

            self.assertEqual(
                ["assets/source/SKILL.md"],
                list_skill_files_for_root(skills_root, "huashu_design", "assets"),
            )
            self.assertEqual(
                "Huashu body.",
                read_skill_file_for_root(skills_root, "huashu_design", "assets/source/SKILL.md"),
            )

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            skill_root = skills_root / "huashu_design"
            skill_root.mkdir(parents=True)
            outside = Path(temp_dir) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")

            with self.assertRaises(ValueError):
                read_skill_file_for_root(skills_root, "huashu_design", "../secret.txt")


if __name__ == "__main__":
    unittest.main()
