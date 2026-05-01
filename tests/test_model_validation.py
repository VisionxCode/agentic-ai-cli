import unittest
from pathlib import Path

from app.config_loader import load_env_file, load_models
from app.model_validation import validate_image_input_models


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ModelValidationTests(unittest.TestCase):
    def test_rejects_known_text_only_model_for_image_input_workflow(self):
        models = self._configured_models()
        with self.assertRaisesRegex(ValueError, "does not support image input"):
            validate_image_input_models(
                {
                    "coder": "xiaomi/mimo-v2.5-pro",
                    "evaluator": models["evaluator"],
                }
            )

    def test_accepts_configured_env_models(self):
        validate_image_input_models(self._configured_models())

    def _configured_models(self):
        load_env_file(PROJECT_ROOT)
        return load_models(PROJECT_ROOT / "app")


if __name__ == "__main__":
    unittest.main()
