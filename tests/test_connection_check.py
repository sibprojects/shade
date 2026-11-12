import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from shade.llm.check import check_connection


class _Models(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"object": "list", "data": [
            {"id": "gemma3:12b", "object": "model", "created": 0, "owned_by": "x"},
            {"id": "gpt-oss:20b", "object": "model", "created": 0, "owned_by": "x"},
        ]}).encode()
        self.send_response(200 if self.path == "/v1/models" else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_check_lists_models_and_finds_the_chosen_one():
    srv = HTTPServer(("127.0.0.1", 0), _Models)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/v1"
        ok, msg = check_connection(url, "local", "gemma3:12b")
        assert ok and "gemma3:12b" in msg and "gpt-oss:20b" in msg
        ok, msg = check_connection(url, "local", "llama9")
        assert not ok and "llama9" in msg and "not found" in msg
    finally:
        srv.shutdown()


def test_check_reports_unreachable_server_quickly():
    import time
    t = time.monotonic()
    ok, msg = check_connection("http://127.0.0.1:9/v1", "local", "m", timeout=2)
    assert not ok and "Cannot connect" in msg
    assert time.monotonic() - t < 5
