import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config_loader import load_agent_profile, load_env_file, load_models


class RegistryTests(unittest.TestCase):
    def test_agent_profile_combines_system_instructions_shared_rules_and_skills(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "instructions").mkdir()
            (root / "skills" / "image_to_sourcecode").mkdir(parents=True)
            (root / "config").mkdir()

            (root / "instructions" / "coder_system.md").write_text(
                "Coder instruction.", encoding="utf-8"
            )
            (root / "instructions" / "shared_rules.md").write_text(
                "Shared rule.", encoding="utf-8"
            )
            (root / "skills" / "image_to_sourcecode" / "SKILL.md").write_text(
                "Image source-code skill.", encoding="utf-8"
            )
            (root / "config" / "agent_registry.yaml").write_text(
                """
agents:
  coder:
    instructions:
      - instructions/coder_system.md
      - instructions/shared_rules.md
    skills:
      - skills/image_to_sourcecode/SKILL.md
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
        self.assertIn("Image source-code skill.", profile.instructions)

    def test_project_coder_profile_includes_huashu_design_skill(self):
        profile = load_agent_profile(Path("app"), "coder")

        self.assertIn(Path("app/skills/image_to_sourcecode/SKILL.md"), profile.skill_paths)
        self.assertIn(Path("app/skills/iconography/SKILL.md"), profile.skill_paths)
        self.assertIn(Path("app/skills/tailwind_css/SKILL.md"), profile.skill_paths)
        self.assertNotIn(Path("app/skills/image_to_html/SKILL.md"), profile.skill_paths)
        self.assertNotIn(Path("app/skills/svg_generation/SKILL.md"), profile.skill_paths)
        self.assertIn(Path("app/skills/huashu_design/SKILL.md"), profile.skill_paths)
        self.assertIn("Huashu Design", profile.instructions)
        self.assertIn("Image To Source Code", profile.instructions)
        self.assertIn("Iconography", profile.instructions)
        self.assertIn("Tailwind CSS", profile.instructions)
        self.assertIn("Corporate Logos", profile.instructions)
        self.assertIn("MiniMax MCP", profile.instructions)
        self.assertIn("assets/logos/", profile.instructions)

    def test_env_file_populates_openrouter_settings_without_overriding_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                """
OPENROUTER_API_KEY=from-env-file
OPENROUTER_MODEL=env-file-model
OPENROUTER_HTTP_REFERER="http://localhost:8000"
""",
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {"OPENROUTER_API_KEY": "already-set"},
                clear=True,
            ):
                load_env_file(root)

                self.assertEqual("already-set", __import__("os").environ["OPENROUTER_API_KEY"])
                self.assertEqual("env-file-model", __import__("os").environ["OPENROUTER_MODEL"])
                self.assertEqual(
                    "http://localhost:8000",
                    __import__("os").environ["OPENROUTER_HTTP_REFERER"],
                )

    def test_openrouter_model_env_overrides_both_agent_models(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            (root / "config" / "models.yaml").write_text(
                """
models:
  coder: fallback-coder
  evaluator: fallback-evaluator
""",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"OPENROUTER_MODEL": "openrouter/custom-model"}):
                self.assertEqual(
                    {
                        "coder": "openrouter/custom-model",
                        "evaluator": "openrouter/custom-model",
                    },
                    load_models(root),
                )


if __name__ == "__main__":
    unittest.main()
