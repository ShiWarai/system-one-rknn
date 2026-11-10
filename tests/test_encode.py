import os
import unittest
from types import SimpleNamespace
from unittest import mock

from app.api import LimitError
from app.kev_encode import (
    ENV_MAX_CONTEXT,
    MAX_CONTEXT,
    encode_question,
    resolve_max_context,
    serving_limit,
)
from app.laya_encode import build_sequence


class LayaTok:
    mask_token = "<mask>"
    mask_token_id = 4
    cls_token_id = 2
    sep_token_id = 1

    def __call__(self, text, add_special_tokens=False, truncation=False, max_length=None):
        del add_special_tokens
        ids = list(range(len(text)))
        if truncation and max_length is not None:
            ids = ids[:max_length]
        return {"input_ids": ids}


class KevTok:
    _ids = {
        "<|fim_prefix|>": 1,
        "<|fim_middle|>": 2,
        "<|box_start|>": 3,
        "<|box_end|>": 4,
        "<|fim_suffix|>": 5,
    }

    def token_to_id(self, token):
        return self._ids[token]

    def encode(self, text, add_special_tokens=False):
        del add_special_tokens
        return SimpleNamespace(ids=list(range(len(text))))


def choice(count=2):
    labels = ["o%d" % i for i in range(count)]
    return {
        "kind": "choice",
        "instructions": "pick",
        "labels": labels,
        "options": labels,
        "criteria": {label: None for label in labels},
    }


class EncodeTest(unittest.TestCase):
    def test_laya_rejects_a_state_that_does_not_fit(self):
        with self.assertRaises(LimitError):
            build_sequence(LayaTok(), "x" * 600, choice())

    def test_laya_rejects_more_than_64_options(self):
        with self.assertRaises(LimitError):
            build_sequence(LayaTok(), "ok", choice(65))

    def test_laya_short_state_fits(self):
        ids, markers = build_sequence(LayaTok(), "ok", choice())
        self.assertLessEqual(len(ids), 512)
        self.assertEqual(len(markers), 2)

    def test_kev_rejects_a_row_over_16384(self):
        with self.assertRaises(LimitError):
            encode_question(KevTok(), "x" * 17000, choice())

    def test_kev_short_row_keeps_one_decide_token(self):
        ids, decide, opts = encode_question(KevTok(), "paw", choice())
        self.assertLessEqual(len(ids), 16384)
        self.assertEqual(decide, len(ids) - 1)
        self.assertEqual(len(opts), 2)

    def test_kev_honours_a_serving_limit_below_the_file(self):
        # KevTok makes one id per char; the row is ~12 + len(state) tokens.
        with self.assertRaises(LimitError) as ctx:
            encode_question(KevTok(), "x" * 12, choice(), max_context=8)
        message = str(ctx.exception)
        self.assertIn("serving limit is 8", message)
        self.assertIn(ENV_MAX_CONTEXT, message)
        self.assertIn("file holds %d" % MAX_CONTEXT, message)

    def test_kev_serving_limit_at_the_file_capacity_keeps_the_file_message(self):
        with self.assertRaises(LimitError) as ctx:
            encode_question(KevTok(), "x" * 17000, choice(), max_context=MAX_CONTEXT)
        self.assertIn("this file holds %d" % MAX_CONTEXT, str(ctx.exception))


class ServingLimitEnvTest(unittest.TestCase):
    def test_unset_default_to_file_capacity(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve_max_context())
            self.assertEqual(serving_limit(), MAX_CONTEXT)

    def test_blank_default_to_file_capacity(self):
        with mock.patch.dict(os.environ, {ENV_MAX_CONTEXT: "  "}):
            self.assertEqual(serving_limit(), MAX_CONTEXT)

    def test_reads_the_environment(self):
        with mock.patch.dict(os.environ, {ENV_MAX_CONTEXT: "512"}):
            self.assertEqual(serving_limit(), 512)

    def test_rejects_above_the_file_capacity(self):
        with mock.patch.dict(os.environ, {ENV_MAX_CONTEXT: str(MAX_CONTEXT + 1)}):
            with self.assertRaises(LimitError):
                serving_limit()

    def test_rejects_non_positive(self):
        with mock.patch.dict(os.environ, {ENV_MAX_CONTEXT: "0"}):
            with self.assertRaises(LimitError):
                serving_limit()

    def test_rejects_non_integer(self):
        with mock.patch.dict(os.environ, {ENV_MAX_CONTEXT: "16k"}):
            with self.assertRaises(LimitError):
                serving_limit()


if __name__ == "__main__":
    unittest.main()
