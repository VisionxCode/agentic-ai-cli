import unittest

from app.model_validation import validate_image_input_models


class ModelValidationTests(unittest.TestCase):
    def test_rejects_known_text_only_model_for_image_input_workflow(self):
        with self.assertRaisesRegex(ValueError, "does not support image input"):
            validate_image_input_models(
                {
                    "coder": "xiaomi/mimo-v2.5-pro",
                    "evaluator": "openai/gpt-4o",
                }
            )

    def test_accepts_known_vision_model(self):
        validate_image_input_models(
            {
                "coder": "openai/gpt-4o",
                "evaluator": "openai/gpt-4o",
            }
        )


if __name__ == "__main__":
    unittest.main()
