"""Laya multilingual scorer on CPU torch; same padded contract as the RKNN graph.

The forward math mirrors scripts/export_onnx.py ScorerLogits from the rknn
repo, so logits match the published graph up to float rounding. Weights load
through the laya package and cache under HF_HOME, which the image points at
the models volume.
"""
import time

import torch
from tokenizers import Tokenizer

from app.laya_encode import QTYPES, HubTok, build_sequence, pad

LAYA_REPO = "convaiinnovations/laya"
LAYA_SUBFOLDER = "multilingual"


class LayaCpuEngine:
    name = "laya-multilingual"
    description = "Laya multilingual FP32 torch CPU, sequence 512, up to 64 markers"
    release_date = "2026-09-30"

    def __init__(self, model, tok):
        self._model = model.eval().float()
        self._tok = tok
        self._temps = self._model.temperature.detach().float().cpu().numpy().reshape(-1).tolist()

    @classmethod
    def load(cls, root):
        del root
        from huggingface_hub import hf_hub_download

        from laya import load as laya_load

        agent = laya_load(LAYA_REPO, subfolder=LAYA_SUBFOLDER, device="cpu")
        model = agent.model
        encoder = model.encoder
        if hasattr(encoder, "set_attn_implementation"):
            encoder.set_attn_implementation("eager")
        else:
            encoder.config._attn_implementation = "eager"
        tokenizer_path = hf_hub_download(LAYA_REPO, LAYA_SUBFOLDER + "/tokenizer/tokenizer.json")
        return cls(model, HubTok(Tokenizer.from_file(tokenizer_path)))

    def temperature(self, kind):
        return float(self._temps[QTYPES[kind]])

    def forward(self, state, item):
        ids, markers = build_sequence(self._tok, state, item)
        arrays = pad(ids, markers, QTYPES[item["kind"]])
        logits, elapsed = self._run(arrays)
        return logits[: len(item["labels"])].tolist(), len(ids), elapsed

    def _run(self, arrays):
        tensors = [torch.as_tensor(array, dtype=torch.int64) for array in arrays]
        started = time.perf_counter()
        with torch.no_grad():
            logits = self._score(*tensors)
        elapsed = (time.perf_counter() - started) * 1000
        return logits[0].float().numpy(), elapsed

    def _score(self, input_ids, attention_mask, marker_pos, marker_mask, qtype):
        model = self._model
        hidden = model.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        hidden = hidden + model.type_emb(qtype)[:, None, :]
        padding = attention_mask == 0
        for layer in model.head.layers:
            hidden = layer(hidden, src_key_padding_mask=padding)
        index = marker_pos.clamp(min=0)[:, :, None].expand(-1, -1, hidden.size(-1))
        gathered = torch.gather(hidden, 1, index)
        logits = model.scorer(gathered).squeeze(-1)
        return logits.masked_fill(marker_mask == 0, -1.0e4)