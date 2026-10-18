import unittest

from app.api import ApiError, assemble, choice_confidence, parse_request, score_confidence, softmax


MODELS = {"laya-multilingual", "kev-0.8b"}


def question(kind, **extra):
    body = {"type": kind, "instructions": "decide"}
    body.update(extra)
    return body


class ApiTest(unittest.TestCase):
    def test_choice_confidence_formula(self):
        self.assertEqual(choice_confidence([1.0]), 1.0)
        probs = [0.1, 0.2, 0.7]
        self.assertAlmostEqual(choice_confidence(probs), (0.7 - 1 / 3) / (1 - 1 / 3))

    def test_score_confidence_formula(self):
        probs = [0.1, 0.2, 0.7]
        self.assertAlmostEqual(score_confidence(probs), 0.4)

    def test_noul_answer_has_no_confidence(self):
        probs = softmax([0.0, 2.0], 1.0)
        answer = assemble(
            {"kind": "noul", "labels": ["false", "true"], "criteria": {}},
            probs,
        )
        self.assertEqual(set(answer), {"type", "noul"})
        self.assertGreater(answer["noul"], 0.5)

    def test_score_sits_between_levels(self):
        answer = assemble(
            {"kind": "score", "labels": ["0", "1", "2"], "criteria": ["Low", "Medium", "High"]},
            [0.25, 0.5, 0.25],
        )
        self.assertEqual(answer["score"], 1.0)
        self.assertEqual(answer["legend"]["1"], "Medium")
        self.assertIn("confidence", answer)

    def test_empty_questions(self):
        with self.assertRaises(ApiError) as caught:
            parse_request({"state": "x", "model": "kev-0.8b", "questions": {}}, MODELS)
        self.assertEqual(caught.exception.status, 422)

    def test_missing_state(self):
        with self.assertRaises(ApiError) as caught:
            parse_request({"model": "laya-multilingual", "questions": {"a": question("noul")}}, MODELS)
        self.assertEqual(caught.exception.detail[0]["type"], "missing")

    def test_unknown_model(self):
        with self.assertRaises(ApiError):
            parse_request(
                {"state": "x", "model": "other", "questions": {"a": question("noul")}},
                MODELS,
            )

    def test_alias_resolves_to_canonical(self):
        name, _state, items = parse_request(
            {
                "state": {"note": "x"},
                "model": "kev-latest",
                "questions": {"urgent": question("noul")},
            },
            MODELS,
        )
        self.assertEqual(name, "kev-0.8b")
        self.assertEqual(items[0]["labels"], ["false", "true"])


if __name__ == "__main__":
    unittest.main()
