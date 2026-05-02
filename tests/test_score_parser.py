import unittest

from app.tools.score_parser import EvaluationParseError, parse_evaluation


class ScoreParserTests(unittest.TestCase):
    def test_parses_json_with_required_evaluator_fields(self):
        raw = """
        {
          "score": 0.91,
          "identical": false,
          "critique": "close",
          "missing_details": ["logo shadow"],
          "revision_instructions": ["tighten spacing"]
        }
        """

        parsed = parse_evaluation(raw)

        self.assertEqual(parsed["score"], 0.91)
        self.assertFalse(parsed["identical"])
        self.assertEqual(parsed["missing_details"], ["logo shadow"])

    def test_rejects_invalid_score_range(self):
        raw = """
        {
          "score": 1.4,
          "identical": false,
          "critique": "too high",
          "missing_details": [],
          "revision_instructions": []
        }
        """

        with self.assertRaises(EvaluationParseError):
            parse_evaluation(raw)

    def test_parses_first_json_object_when_codex_appends_extra_text(self):
        raw = """
        {
          "score": 0.55,
          "identical": false,
          "critique": "layout exists but spacing differs",
          "missing_details": ["button spacing"],
          "revision_instructions": ["tighten spacing"]
        }

        Extra commentary that Codex should not have emitted:
        {"ignored": true}
        """

        parsed = parse_evaluation(raw)

        self.assertEqual(0.55, parsed["score"])
        self.assertEqual(["tighten spacing"], parsed["revision_instructions"])


if __name__ == "__main__":
    unittest.main()
