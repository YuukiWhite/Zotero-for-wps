import os
import sys
import json
import time
import threading
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from proxy import create_server, VERSION


class MockZoteroHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress logging in tests

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # Record received request for assertions
        self.server.received_requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )

        # Handle simulated delay for long-polling test
        if hasattr(self.server, "delay") and self.server.delay > 0:
            time.sleep(self.server.delay)

        self.send_response(200, "OK")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Zotero-Version", "10.0.6")
        self.send_header("X-Zotero-Connector-API-Version", "3")
        resp_body = b'{"status": "ok"}'
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def do_GET(self):
        self.do_POST()


class MockZoteroServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass):
        self.received_requests = []
        self.delay = 0
        super().__init__(server_address, RequestHandlerClass)


class TestProxyServer(unittest.TestCase):
    def setUp(self):
        # Start mock Zotero server on ephemeral port
        self.zotero_server = MockZoteroServer(("127.0.0.1", 0), MockZoteroHandler)
        self.zotero_port = self.zotero_server.server_address[1]
        self.zotero_thread = threading.Thread(
            target=self.zotero_server.serve_forever, daemon=True
        )
        self.zotero_thread.start()

        # Start proxy server on ephemeral port forwarding to mock Zotero
        self.proxy_server = create_server(
            proxy_port=0, zotero_port=self.zotero_port, host="127.0.0.1"
        )
        self.proxy_port = self.proxy_server.server_address[1]
        self.proxy_thread = threading.Thread(
            target=self.proxy_server.serve_forever, daemon=True
        )
        self.proxy_thread.start()

    def tearDown(self):
        try:
            self.proxy_server.shutdown()
            self.proxy_server.server_close()
        except Exception:
            pass
        try:
            self.zotero_server.shutdown()
            self.zotero_server.server_close()
        except Exception:
            pass

    def test_health_endpoint(self):
        """1. Verify GET /health returns 200 with version 0.2.0."""
        url = f"http://127.0.0.1:{self.proxy_port}/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("version"), VERSION)
            self.assertEqual(data.get("version"), "0.2.0")

    def test_cors_preflight(self):
        """2. Verify OPTIONS /connector/document/execCommand returns 204 with required CORS headers."""
        url = f"http://127.0.0.1:{self.proxy_port}/connector/document/execCommand"
        req = urllib.request.Request(url, method="OPTIONS")
        req.add_header("Origin", "http://127.0.0.1:3889")
        req.add_header("Access-Control-Request-Method", "POST")
        req.add_header(
            "Access-Control-Request-Headers",
            "Content-Type, Zotero-Allowed-Request, X-Zotero-Connector-API-Version",
        )

        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))
            self.assertIn("OPTIONS", resp.headers.get("Access-Control-Allow-Methods", ""))
            allowed_headers = resp.headers.get("Access-Control-Allow-Headers", "")
            self.assertIn("Content-Type", allowed_headers)
            self.assertIn("Zotero-Allowed-Request", allowed_headers)
            self.assertIn("X-Zotero-Connector-API-Version", allowed_headers)

    def test_forward_injects_headers(self):
        """3. Verify proxy injects required Zotero headers and strips Origin/Sec-Fetch-*."""
        url = f"http://127.0.0.1:{self.proxy_port}/connector/document/execCommand"
        req = urllib.request.Request(url, data=b'{"cmd": "test"}', method="POST")
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
        req.add_header("Origin", "http://127.0.0.1:3889")
        req.add_header("Sec-Fetch-Site", "cross-site")
        req.add_header("Sec-Fetch-Mode", "cors")
        req.add_header("Referer", "http://127.0.0.1:3889/index.html")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertEqual(resp.headers.get("X-Zotero-Version"), "10.0.6")

        self.assertEqual(len(self.zotero_server.received_requests), 1)
        zotero_req = self.zotero_server.received_requests[0]
        headers = zotero_req["headers"]

        # Injected required headers
        self.assertEqual(headers.get("Zotero-Allowed-Request"), "1")
        self.assertEqual(headers.get("X-Zotero-Connector-API-Version"), "3")
        self.assertEqual(headers.get("Host"), f"127.0.0.1:{self.zotero_port}")
        self.assertEqual(headers.get("User-Agent"), f"WPS-Zotero-Proxy/{VERSION}")

        # Stripped unsafe browser headers
        self.assertNotIn("Origin", headers)
        self.assertNotIn("origin", headers)
        self.assertNotIn("Referer", headers)
        self.assertNotIn("referer", headers)
        self.assertNotIn("Sec-Fetch-Site", headers)
        self.assertNotIn("Sec-Fetch-Mode", headers)

    def test_zotero_unreachable_returns_502(self):
        """4. Verify proxy returns 502 with CORS headers when Zotero is stopped."""
        # Stop mock Zotero
        self.zotero_server.shutdown()
        self.zotero_server.server_close()

        url = f"http://127.0.0.1:{self.proxy_port}/connector/document/execCommand"
        req = urllib.request.Request(url, data=b"{}", method="POST")
        try:
            urllib.request.urlopen(req, timeout=2.0)
            self.fail("Expected HTTPError 502")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 502)
            self.assertEqual(e.headers.get("Access-Control-Allow-Origin"), "*")
            body = json.loads(e.read().decode("utf-8"))
            self.assertIn("error", body)
            self.assertIn("Zotero is not running", body["error"])

    def test_stopproxy_command(self):
        """5. Verify POST /stopproxy returns 200 and cleanly stops the proxy."""
        url = f"http://127.0.0.1:{self.proxy_port}/stopproxy"
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(body.get("status"), "stopping")

        # Wait for thread to terminate
        self.proxy_thread.join(timeout=3.0)
        self.assertFalse(self.proxy_thread.is_alive())

    def test_long_poll_concurrency(self):
        """6. Verify concurrent requests (health check while long poll transaction in flight)."""
        # Configure mock Zotero to delay for 2 seconds
        self.zotero_server.delay = 2.0

        long_poll_finished = threading.Event()
        long_poll_status = []

        def run_long_poll():
            url = f"http://127.0.0.1:{self.proxy_port}/connector/document/execCommand"
            req = urllib.request.Request(url, data=b"{}", method="POST")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                long_poll_status.append(resp.status)
            long_poll_finished.set()

        lp_thread = threading.Thread(target=run_long_poll, daemon=True)
        lp_thread.start()

        # Wait 0.2s for long poll request to enter mock Zotero
        time.sleep(0.2)
        self.assertFalse(long_poll_finished.is_set(), "Long poll should still be waiting")

        # Ping health endpoint during long poll transaction
        t0 = time.time()
        health_url = f"http://127.0.0.1:{self.proxy_port}/health"
        req_health = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req_health, timeout=1.0) as resp:
            elapsed = time.time() - t0
            self.assertEqual(resp.status, 200)
            # Health check must respond immediately (< 0.5s), not blocked by the 2s transaction
            self.assertLess(elapsed, 0.5)

        # Wait for long poll to finish
        lp_thread.join(timeout=3.0)
        self.assertTrue(long_poll_finished.is_set())
        self.assertEqual(long_poll_status, [200])


if __name__ == "__main__":
    unittest.main()
