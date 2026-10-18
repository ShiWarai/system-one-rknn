"""Kev-0.8B on CPU torch: Qwen3.5-0.8B-Base with the Kev LoRA merged at load.

The pointer head is the same NumPy math as on NPU; only the hidden states
come from the fp32 model instead of RKLLM. Base and adapter cache under
HF_HOME, which the image points at the models volume.
"""
import json
import os
import time

import torch
from tokenizers import Tokenizer

from app.kev_encode import encode_question
from app.kev_pointer import PointerHead

BASE = "Qwen/Qwen3.5-0.8B-Base"
BASE_REV = "dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68"
LORA = "jaredpalmer/kev-0.8b"
LORA_REV = "9a45d25eb2ab761841196625383fa1dff0e56c1e"


class KevCpuEngine:
    name = "kev-0.8b"
    description = "Kev-0.8B merged into Qwen3.5-0.8B-Base, torch CPU FP32, context 320"
    release_date = "2026-09-30"

    def __init__(self, lm, tok, head, temperature):
        self._lm = lm.eval()
        self._tok = tok
        self._head = head
        self._temperature_value = temperature

    @classmethod
    def load(cls, root):
        from peft import PeftModel
        from transformers import AutoModelForCausalLM

        kev_root = os.path.join(root, "kev")
        base = AutoModelForCausalLM.from_pretrained(
            BASE, revision=BASE_REV, dtype=torch.float32, attn_implementation="eager"
        )
        base.model = PeftModel.from_pretrained(base.model, LORA, revision=LORA_REV).merge_and_unload()
        with open(os.path.join(kev_root, "pointer.json"), encoding="utf-8") as handle:
            temperature = float(json.load(handle)["temperature"])
        return cls(
            base,
            Tokenizer.from_file(os.path.join(kev_root, "tokenizer.json")),
            PointerHead(kev_root),
            temperature,
        )

    def temperature(self, kind):
        del kind
        return self._temperature_value

    def forward(self, state, item):
        ids, decide, opt_idx = encode_question(self._tok, state, item)
        started = time.perf_counter()
        with torch.no_grad():
            out = self._lm(input_ids=torch.tensor([ids]), output_hidden_states=True)
            hidden = out.hidden_states[-1][0].float().numpy()
        elapsed = (time.perf_counter() - started) * 1000
        logits = self._head.logits(hidden, decide, opt_idx)
        return logits.tolist(), len(ids), elapsed