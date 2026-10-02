import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from app.fake_engine import FakeEngine
from app.server import Runtime, make_handler


def _post(url, payload):
    data = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engines = [
            FakeEngine("laya-multilingual", "fake laya", "2026-09-30"),
            FakeEngine("kev-0.8b", "fake kev", "2026-09-30"),
        ]
        cls.runtime = Runtime(engines)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.runtime))
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)

    def test_models_and_health(self):
        with urllib.request.urlopen(self.base + "/health") as response:
            health = json.loads(response.read().decode())
        self.assertTrue(health["ok"])
        with urllib.request.urlopen(self.base + "/v1/models") as response:
            body = json.loads(response.read().decode())
        names = [item["name"] for item in body["models"]]
        self.assertEqual(names, ["laya-multilingual", "kev-0.8b"])

    def test_systemone_three_types(self):
        status, body = _post(
            self.base + "/v1/systemone",
            {
                "model": "multilingual",
                "state": "lag",
                "questions": {
                    "intent": {
                        "type": "choice",
                        "instructions": "domain",
                        "criteria": {"infrastructure": "db", "billing": "pay"},
                    },
                    "urgent": {"type": "noul", "instructions": "now?"},
                    "severity": {
                        "type": "score",
                        "instructions": "how bad",
                        "criteria": ["Low", "Medium", "High"],
                    },
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["model"], "laya-multilingual")
        self.assertEqual(body["answers"]["intent"]["choice"], "billing")
        self.assertIn("confidence", body["answers"]["intent"])
        self.assertNotIn("confidence", body["answers"]["urgent"])
        self.assertGreater(body["answers"]["urgent"]["noul"], 0.5)
        self.assertEqual(body["answers"]["severity"]["type"], "score")
        self.assertIn("input_tokens", body["usage"])
        self.assertIn("output_tokens", body["usage"])

    def test_empty_body_is_422(self):
        status, body = _post(self.base + "/v1/systemone", {})
        self.assertEqual(status, 422)
        self.assertIn("detail", body)

    def test_page(self):
        with urllib.request.urlopen(self.base + "/") as response:
            html = response.read().decode()
        self.assertIn("/v1/systemone", html)
        self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
