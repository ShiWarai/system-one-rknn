import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

try:
    import torch
    import torch.nn as nn

    TORCH = True
except ModuleNotFoundError:
    torch = None
    nn = None
    TORCH = False

from app.kev_encode import SPECIAL
from app.kev_pointer import PointerHead
from app.laya_encode import QTYPES, build_sequence, pad

if TORCH:
    from app.kev_cpu import KevCpuEngine
    from app.laya_cpu import LayaCpuEngine

H = 8
D = 4
VOCAB = 256
TEMPS = [1.5, 2.5, 3.5]

POINTERS = {token: index + 1 for index, token in enumerate(SPECIAL)}


def laya_choice(count=2):
    labels = ["o%d" % i for i in range(count)]
    return {"kind": "choice", "instructions": "pick", "labels": labels, "options": labels}


def kev_choice(count=3):
    labels = ["a", "b", "c"][:count]
    return {"kind": "choice", "instructions": "pick", "labels": labels, "options": labels}


class LayaTok:
    mask_token = "<mask>"
    mask_token_id = 4
    cls_token_id = 2
    sep_token_id = 1

    def __call__(self, text, add_special_tokens=False, truncation=False, max_length=None):
        del add_special_tokens
        ids = [i % 64 for i in range(len(text))]
        if truncation and max_length is not None:
            ids = ids[:max_length]
        return {"input_ids": ids}


class KevTok:
    _ids = POINTERS

    def token_to_id(self, token):
        return self._ids[token]

    def encode(self, text, add_special_tokens=False):
        del add_special_tokens
        return SimpleNamespace(ids=[i % 64 for i in range(len(text))])


def write_pointer_head(root):
    np.save(root / "q_weight.npy", np.ones((D, H), np.float32))
    np.save(root / "q_bias.npy", np.zeros(D, np.float32))
    np.save(root / "k_weight.npy", np.ones((D, H), np.float32))
    np.save(root / "k_bias.npy", np.zeros(D, np.float32))
    (root / "pointer.json").write_text('{"temperature": 2.0}', encoding="utf-8")


if TORCH:

    class _PassLayer(nn.Module):
        def forward(self, hidden, src_key_padding_mask=None):
            del src_key_padding_mask
            return hidden

    class _Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(VOCAB, H)

        def forward(self, input_ids, attention_mask):
            del attention_mask
            return SimpleNamespace(last_hidden_state=self.emb(input_ids))

    class _Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.layers = nn.ModuleList([_PassLayer()])

    class _FakeLayaModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = _Encoder()
            self.type_emb = nn.Embedding(3, H)
            self.head = _Head()
            self.scorer = nn.Linear(H, 1)
            self.temperature = nn.Parameter(torch.tensor(TEMPS))

    class _FakeKevLM(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(VOCAB, H)

        def forward(self, input_ids, output_hidden_states=False):
            del output_hidden_states
            hidden = self.emb(input_ids)
            return SimpleNamespace(hidden_states=(hidden,))


@unittest.skipUnless(TORCH, "torch not installed")
class LayaCpuEngineTest(unittest.TestCase):
    def _engine(self):
        torch.manual_seed(0)
        return LayaCpuEngine(_FakeLayaModel(), LayaTok())

    def test_forward_returns_one_finite_logit_per_option(self):
        engine = self._engine()
        logits, n_tokens, elapsed = engine.forward("a state", laya_choice(3))
        self.assertEqual(len(logits), 3)
        self.assertEqual(n_tokens, len(build_sequence(engine._tok, "a state", laya_choice(3))[0]))
        self.assertGreater(elapsed, 0.0)
        for value in logits:
            self.assertIsInstance(value, float)
            self.assertTrue(np.isfinite(value))

    def test_marker_positions_scored_and_tail_masked(self):
        engine = self._engine()
        item = laya_choice(2)
        ids, markers = build_sequence(engine._tok, "a state", item)
        arrays = pad(ids, markers, QTYPES["choice"])
        row, _ = engine._run(arrays)
        self.assertEqual(row.shape, (64,))
        self.assertGreater(row[0], -9000.0)
        self.assertGreater(row[1], -9000.0)
        self.assertEqual(row[2], -10000.0)

    def test_temperature_follows_question_kind(self):
        engine = self._engine()
        self.assertAlmostEqual(engine.temperature("choice"), TEMPS[0])
        self.assertAlmostEqual(engine.temperature("score"), TEMPS[1])
        self.assertAlmostEqual(engine.temperature("noul"), TEMPS[2])


@unittest.skipUnless(TORCH, "torch not installed")
class KevCpuEngineTest(unittest.TestCase):
    def _engine(self):
        root = Path(tempfile.mkdtemp())
        write_pointer_head(root)
        torch.manual_seed(0)
        return KevCpuEngine(_FakeKevLM(), KevTok(), PointerHead(str(root)), 2.0)

    def test_forward_returns_pointer_logit_per_option(self):
        engine = self._engine()
        logits, n_tokens, elapsed = engine.forward("hello world", kev_choice(3))
        self.assertEqual(len(logits), 3)
        self.assertGreater(n_tokens, 1)
        self.assertGreaterEqual(elapsed, 0.0)
        for value in logits:
            self.assertIsInstance(value, float)

    def test_temperature_is_scalar(self):
        self.assertAlmostEqual(self._engine().temperature("choice"), 2.0)

    def test_pointer_head_exact_math(self):
        root = Path(tempfile.mkdtemp())
        write_pointer_head(root)
        head = PointerHead(str(root))
        hidden = np.full((6, H), 0.5, np.float32)
        got = head.logits(hidden, 5, [1, 2, 3])
        np.testing.assert_allclose(got, np.full(3, 32.0, np.float32), rtol=1e-4)


class DownloadCatalogTest(unittest.TestCase):
    def test_cpu_skips_rknn_graphs_and_keeps_numpy_heads(self):
        from app.download import model_files

        cpu = model_files("laya-repo", "kev-repo", ["laya", "kev"], engine="cpu")
        names = {name for _r, _f, name in cpu}
        folders = {folder for _r, folder, _n in cpu}
        self.assertNotIn("laya", folders)
        self.assertNotIn("kev-0.8b-w8a8-opt0-ctx320.rkllm", names)
        self.assertIn("q_weight.npy", names)
        self.assertIn("tokenizer.json", names)

    def test_npu_catalog_unchanged(self):
        from app.download import model_files

        npu = model_files("laya-repo", "kev-repo", ["laya", "kev"])
        names = {name for _r, _f, name in npu}
        self.assertIn("laya-multilingual-fp16-seq512.rknn", names)
        self.assertIn("kev-0.8b-w8a8-opt0-ctx320.rkllm", names)


if __name__ == "__main__":
    unittest.main()
