"""Deterministic logits so HTTP tests run without an NPU."""


class FakeEngine:
    def __init__(self, name, description, release_date, temperature=1.0):
        self.name = name
        self.description = description
        self.release_date = release_date
        self._temperature = temperature

    def temperature(self, kind):
        del kind
        return self._temperature

    def forward(self, state, item):
        del state
        logits = [0.0] * len(item["labels"])
        if logits:
            logits[-1] = 2.0
        return logits, 4, 1.0
