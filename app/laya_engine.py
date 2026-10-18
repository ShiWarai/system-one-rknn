"""Laya multilingual FP16 graph on RKNN runtime 2.3.2."""
import ctypes
import json
import os
import time

import numpy as np
from tokenizers import Tokenizer

from app.laya_encode import QTYPES, HubTok, build_sequence, pad

RKNN_QUERY_IN_OUT_NUM = 0
RKNN_QUERY_INPUT_ATTR = 1
RKNN_NPU_CORE_ALL = 0xFFFF
RKNN_MAX_DIMS = 16
RKNN_MAX_NAME_LEN = 256


class _InputOutputNum(ctypes.Structure):
    _fields_ = [("n_input", ctypes.c_uint32), ("n_output", ctypes.c_uint32)]


class _TensorAttr(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("n_dims", ctypes.c_uint32),
        ("dims", ctypes.c_uint32 * RKNN_MAX_DIMS),
        ("name", ctypes.c_char * RKNN_MAX_NAME_LEN),
        ("n_elems", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("fmt", ctypes.c_int),
        ("type", ctypes.c_int),
        ("qnt_type", ctypes.c_int),
        ("fl", ctypes.c_int8),
        ("zp", ctypes.c_int32),
        ("scale", ctypes.c_float),
        ("w_stride", ctypes.c_uint32),
        ("size_with_stride", ctypes.c_uint32),
        ("pass_through", ctypes.c_uint8),
        ("h_stride", ctypes.c_uint32),
    ]


class _RknnInput(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("buf", ctypes.c_void_p),
        ("size", ctypes.c_uint32),
        ("pass_through", ctypes.c_uint8),
        ("type", ctypes.c_int),
        ("fmt", ctypes.c_int),
    ]


class _RknnOutput(ctypes.Structure):
    _fields_ = [
        ("want_float", ctypes.c_uint8),
        ("is_prealloc", ctypes.c_uint8),
        ("index", ctypes.c_uint32),
        ("buf", ctypes.c_void_p),
        ("size", ctypes.c_uint32),
    ]


class LayaEngine:
    name = "laya-multilingual"
    description = "Laya multilingual FP16 RKNN, sequence 512, RK3588 toolkit 2.3.2"
    release_date = "2026-09-30"

    def __init__(self, root, lib_path):
        temp_path = os.path.join(root, "temperature.json")
        with open(temp_path, encoding="utf-8") as handle:
            self._temps = json.load(handle)["temperature"]
        self._tok = HubTok(Tokenizer.from_file(os.path.join(root, "tokenizer.json")))
        self._lib = ctypes.CDLL(lib_path)
        self._bind()
        self._ctx = ctypes.c_uint64(0)
        model = os.path.join(root, "laya-multilingual-fp16-seq512.rknn")
        ret = self._lib.rknn_init(ctypes.byref(self._ctx), model.encode(), 0, 0, None)
        if ret != 0:
            raise SystemExit("rknn_init %s" % ret)
        ret = self._lib.rknn_set_core_mask(self._ctx.value, RKNN_NPU_CORE_ALL)
        if ret != 0:
            raise SystemExit("rknn_set_core_mask %s" % ret)
        io = _InputOutputNum()
        self._lib.rknn_query(self._ctx.value, RKNN_QUERY_IN_OUT_NUM, ctypes.byref(io), ctypes.sizeof(io))
        self._attrs = []
        for index in range(io.n_input):
            attr = _TensorAttr()
            attr.index = index
            self._lib.rknn_query(
                self._ctx.value, RKNN_QUERY_INPUT_ATTR, ctypes.byref(attr), ctypes.sizeof(attr)
            )
            self._attrs.append(attr)

    def _bind(self):
        lib = self._lib
        lib.rknn_init.argtypes = [
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        lib.rknn_init.restype = ctypes.c_int
        lib.rknn_query.argtypes = [ctypes.c_uint64, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        lib.rknn_query.restype = ctypes.c_int
        lib.rknn_inputs_set.argtypes = [ctypes.c_uint64, ctypes.c_uint32, ctypes.POINTER(_RknnInput)]
        lib.rknn_inputs_set.restype = ctypes.c_int
        lib.rknn_run.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
        lib.rknn_run.restype = ctypes.c_int
        lib.rknn_outputs_get.argtypes = [ctypes.c_uint64, ctypes.c_uint32, ctypes.POINTER(_RknnOutput), ctypes.c_void_p]
        lib.rknn_outputs_get.restype = ctypes.c_int
        lib.rknn_outputs_release.argtypes = [ctypes.c_uint64, ctypes.c_uint32, ctypes.POINTER(_RknnOutput)]
        lib.rknn_outputs_release.restype = ctypes.c_int
        lib.rknn_set_core_mask.argtypes = [ctypes.c_uint64, ctypes.c_int]
        lib.rknn_set_core_mask.restype = ctypes.c_int

    def temperature(self, kind):
        return float(self._temps[QTYPES[kind]])

    def forward(self, state, item):
        ids, markers = build_sequence(self._tok, state, item)
        arrays = pad(ids, markers, QTYPES[item["kind"]])
        logits, elapsed = self._run(arrays)
        return logits[: len(item["labels"])].tolist(), len(ids), elapsed

    def _run(self, arrays):
        inputs = (_RknnInput * len(arrays))()
        holders = []
        for index, arr in enumerate(arrays):
            attr = self._attrs[index]
            if attr.type in (0, 1):
                arr = np.ascontiguousarray(arr.astype(np.float16))
                inputs_type = 1
            else:
                arr = np.ascontiguousarray(arr)
                inputs_type = attr.type
            holders.append(arr)
            inputs[index].index = index
            inputs[index].buf = arr.ctypes.data_as(ctypes.c_void_p)
            inputs[index].size = arr.nbytes
            inputs[index].pass_through = 1
            inputs[index].type = inputs_type
            inputs[index].fmt = attr.fmt
        ret = self._lib.rknn_inputs_set(self._ctx.value, len(arrays), inputs)
        if ret != 0:
            raise RuntimeError("rknn_inputs_set %s" % ret)
        started = time.perf_counter()
        ret = self._lib.rknn_run(self._ctx.value, None)
        elapsed = (time.perf_counter() - started) * 1000
        if ret != 0:
            raise RuntimeError("rknn_run %s" % ret)
        outputs = (_RknnOutput * 1)()
        outputs[0].want_float = 1
        ret = self._lib.rknn_outputs_get(self._ctx.value, 1, outputs, None)
        if ret != 0:
            raise RuntimeError("rknn_outputs_get %s" % ret)
        count = outputs[0].size // 4
        logits = np.ctypeslib.as_array(
            ctypes.cast(outputs[0].buf, ctypes.POINTER(ctypes.c_float)), shape=(count,)
        ).copy()
        self._lib.rknn_outputs_release(self._ctx.value, 1, outputs)
        return logits, elapsed
