"""One Laya question, padded like the seq-512 RKNN graph.

Special-token ids and the 256-token head budget are the ones checked on the
published graph. Option text for noul follows laya: false, then true.
"""
import json

from app.api import LimitError

MAX_LEN = 512
HEAD_MAX_LEN = 256
KMAX = 64
QTYPES = {"choice": 0, "score": 1, "noul": 2}
CLS, SEP, PAD, MASK = 2, 1, 0, 4
_NOUL_FALSE = "no, the statement does not hold"
_NOUL_TRUE = "yes, the statement holds"


def serialize_state(state):
    if isinstance(state, str):
        return state
    return json.dumps(state, ensure_ascii=False)


def render_criterion(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "), default=str)


def render_options(item):
    kind = item["kind"]
    if kind == "choice":
        return list(item["options"])
    if kind == "score":
        return ["level %d: %s" % (i, render_criterion(text)) for i, text in enumerate(item["options"])]
    criteria = item["criteria"] or {}
    false_crit, true_crit = criteria.get("false"), criteria.get("true")
    false_text = render_criterion(false_crit) if false_crit not in (None, "") else _NOUL_FALSE
    true_text = render_criterion(true_crit) if true_crit not in (None, "") else _NOUL_TRUE
    return ["false: " + false_text, "true: " + true_text]


class HubTok:
    """tokenizers.Tokenizer with the ids the multilingual graph was exported against."""

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.mask_token = "<mask>"
        self.mask_token_id = MASK
        self.cls_token_id = CLS
        self.sep_token_id = SEP

    def __call__(self, text, add_special_tokens=False, truncation=False, max_length=None):
        del add_special_tokens
        ids = self.tokenizer.encode(text, add_special_tokens=False).ids
        if truncation and max_length is not None:
            ids = ids[:max_length]
        return {"input_ids": ids}


def build_sequence(tok, state, item):
    opts = render_options(item)
    if len(opts) > KMAX:
        raise LimitError("Laya accepts at most %d options" % KMAX)
    ins = str(item["instructions"]).replace(tok.mask_token, " ")
    head_ids = tok("%s question: %s" % (item["kind"], ins))["input_ids"]
    opt_ids = []
    for opt in opts:
        opt_tokens = tok(" " + opt.replace(tok.mask_token, " "), truncation=True, max_length=48)["input_ids"]
        opt_ids.append([tok.mask_token_id] + opt_tokens)
    opt_budget = HEAD_MAX_LEN - sum(len(opt) for opt in opt_ids)
    if opt_budget < 16:
        per = max(4, (HEAD_MAX_LEN - 16) // max(1, len(opt_ids)))
        opt_ids = [opt[:per] for opt in opt_ids]
        opt_budget = HEAD_MAX_LEN - sum(len(opt) for opt in opt_ids)
    head_ids = head_ids[: max(8, opt_budget)]
    ids = [tok.cls_token_id] + head_ids + [tok.sep_token_id]
    markers = []
    for opt in opt_ids:
        markers.append(len(ids))
        ids.extend(opt)
    ids.append(tok.sep_token_id)
    room = MAX_LEN - len(ids) - 1
    if room < 0:
        raise LimitError("Laya question does not fit %d tokens" % MAX_LEN)
    state_ids = tok(serialize_state(state).replace(tok.mask_token, " "))["input_ids"]
    if len(state_ids) > room:
        raise LimitError("Laya state does not fit the remaining %d tokens" % room)
    ids = ids + state_ids + [tok.sep_token_id]
    if len(ids) > MAX_LEN or len(markers) != len(opts):
        raise LimitError("Laya sequence does not fit the compiled graph")
    return ids, markers


def pad(ids, markers, qtype):
    import numpy as np

    input_ids = np.full((1, MAX_LEN), PAD, np.int64)
    attention = np.zeros((1, MAX_LEN), np.int64)
    marker_pos = np.zeros((1, KMAX), np.int64)
    marker_mask = np.zeros((1, KMAX), np.int64)
    input_ids[0, : len(ids)] = ids
    attention[0, : len(ids)] = 1
    marker_pos[0, : len(markers)] = markers
    marker_mask[0, : len(markers)] = 1
    q = np.array([qtype], np.int64)
    return [input_ids, attention, marker_pos, marker_mask, q]
