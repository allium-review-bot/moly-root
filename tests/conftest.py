"""Local HTTP responses for download/cache failure injection."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest


@pytest.fixture
def http_source():
    replies, requests = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = {"path": self.path, "range": self.headers.get("Range"),
                       "if_range": self.headers.get("If-Range"),
                       "accept_encoding": self.headers.get("Accept-Encoding")}
            requests.append(request)
            reply = replies.pop(0) if replies else {"status": 500, "body": b"unexpected request"}
            if callable(reply):
                reply = reply(request)
            body = reply.get("body", b"")
            headers = {"Content-Length": str(len(body)), **reply.get("headers", {})}
            self.send_response(reply.get("status", 200))
            for name, value in headers.items():
                if value is not None:
                    self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", replies, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
