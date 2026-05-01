import tempfile
import unittest
from pathlib import Path

from app.config_loader import load_agent_profile


class RegistryTests(unittest.TestCase):
    def test_agent_profile_combines_system_instructions_shared_rules_and_skills(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "instructions").mkdir()
            (root / "skills" / "image_to_html").mkdir(parents=True)
            (root / "config").mkdir()

            (root / "instructions" / "coder_system.md").write_text(
                "Coder instruction.", encoding="utf-8"
            )
            (root / "instructions" / "shared_rules.md").write_text(
                "Shared rule.", encoding="utf-8"
            )
            (root / "skills" / "image_to_html" / "SKILL.md").write_text(
                "Image skill.", encoding="utf-8"
            )
            (root / "config" / "agent_registry.yaml").write_text(
                """
agents:
  coder:
    instructions:
      - instructions/coder_system.md
      - instructions/shared_rules.md
    skills:
      - skills/image_to_html/SKILL.md
    tools:
      - file_ops
      - render_screenshot
""",
                encoding="utf-8",
            )

            profile = load_agent_profile(root, "coder")

        self.assertEqual(profile.tool_names, ["file_ops", "render_screenshot"])
        self.assertIn("Coder instruction.", profile.instructions)
        self.assertIn("Shared rule.", profile.instructions)
        self.assertIn("Image skill.", profile.instructions)


if __name__ == "__main__":
    unittest.main()
