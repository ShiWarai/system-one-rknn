"""HTTP runtime: one page, GET /v1/models, POST /v1/systemone."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.api import ApiError, LimitError, assemble, parse_request, response, softmax

PAGE = Path(__file__).resolve().parent / "static" / "index.html"

_MODEL_KEYS = {
    "laya": "laya",
    "laya-multilingual": "laya",
    "kev": "kev",
    "kev-0.8b": "kev",
}


def selected_models(raw=None):
    """Names to download and load. Unset MODELS means both."""
    if raw is None:
        raw = os.environ.get("MODELS", "laya,kev")
    chosen = []
    for part in raw.split(","):
        key = part.strip().lower()
        if not key:
            continue
        if key not in _MODEL_KEYS:
            raise SystemExit("unknown MODELS entry %r; use laya, kev, or both" % part.strip())
        name = _MODEL_KEYS[key]
        if name not in chosen:
            chosen.append(name)
    if not chosen:
        raise SystemExit("MODELS is empty; use laya, kev, or both")
    return chosen


def load_engines():
    names = selected_models()
    mode = os.environ.get("SYSTEM_ONE_ENGINE", "npu")
    if mode == "fake":
        from app.fake_engine import FakeEngine

        engines = []
        if "laya" in names:
            engines.append(FakeEngine("laya-multilingual", "Fake Laya engine for tests", "2026-09-30"))
        if "kev" in names:
            engines.append(FakeEngine("kev-0.8b", "Fake Kev engine for tests", "2026-09-30", temperature=2.351))
        return engines
    from app.download import ensure_models
    from app.kev_engine import KevEngine
    from app.laya_engine import LayaEngine

    root = os.environ.get("MODELS_DIR", "/models")
    laya_repo = os.environ.get("LAYA_REPO", "ShiWarai/laya-multilingual-rknn")
    kev_repo = os.environ.get("KEV_REPO", "ShiWarai/kev-0.8b-rknn")
    ensure_models(root, laya_repo, kev_repo, names)
    engines = []
    if "laya" in names:
        engines.append(LayaEngine(os.path.join(root, "laya"), os.environ["RKNN_LIB"]))
    if "kev" in names:
        engines.append(KevEngine(os.path.join(root, "kev"), os.environ["RKLLM_LIB"]))
    return engines


class Runtime:
    def __init__(self, engines):
        self.engines = {engine.name: engine for engine in engines}
        self._lock = threading.Lock()

    def models(self):
        return {
            "models": [
                {
                    "name": engine.name,
                    "description": engine.description,
                    "release_date": engine.release_date,
                }
                for engine in self.engines.values()
            ]
        }

    def systemone(self, payload):
        model_name, state, items = parse_request(payload, self.engines)
        engine = self.engines[model_name]
        answers = {}
        tokens = 0
        started = time.perf_counter()
        with self._lock:
            for item in items:
                logits, used, _elapsed = engine.forward(state, item)
                probs = softmax(logits, engine.temperature(item["kind"]))
                answers[item["id"]] = assemble(item, probs)
                tokens += used
        elapsed_ms = (time.perf_counter() - started) * 1000
        return response(model_name, answers, tokens, 0, elapsed_ms)


def make_handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload, content_type):
            if isinstance(payload, str):
                body = payload.encode()
            else:
                body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/health":
                self._send(200, {"ok": True, "models": list(runtime.engines)}, "application/json")
                return
            if path == "/v1/models":
                self._send(200, runtime.models(), "application/json")
                return
            if path == "/":
                self._send(200, PAGE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
                return
            self._send(404, "not found", "text/plain; charset=utf-8")

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path != "/v1/systemone":
                self._send(404, "not found", "text/plain; charset=utf-8")
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode() or "null")
                body = runtime.systemone(payload)
            except json.JSONDecodeError:
                body = {"detail": [{"loc": ["body"], "msg": "invalid JSON", "type": "json_invalid"}]}
                self._send(422, body, "application/json")
                return
            except (ApiError, LimitError) as exc:
                if isinstance(exc, LimitError):
                    detail = [{"loc": ["body"], "msg": str(exc), "type": "value_error"}]
                    status = 422
                else:
                    detail = exc.detail
                    status = exc.status
                self._send(status, {"detail": detail}, "application/json")
                return
            self._send(200, body, "application/json")

        def log_message(self, fmt, *args):
            print(fmt % args, flush=True)

    return Handler


def serve(runtime, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(runtime))
    print("listening %s:%s" % (host, httpd.server_port), flush=True)
    httpd.serve_forever()
    return httpd


def main():
    runtime = Runtime(load_engines())
    port = int(os.environ.get("PORT", "8080"))
    serve(runtime, "0.0.0.0", port)


if __name__ == "__main__":
    main()
