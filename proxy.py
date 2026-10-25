#!/usr/bin/env python3
"""
WPS-Zotero HTTP Proxy (v0.2.0)

Forwards WPS Office JavaScript API requests to Zotero's local HTTP integration server.
Provides CORS preflight, header rewriting (bypassing browser gating and DNS rebinding checks),
and non-blocking concurrent request handling.
"""

import sys
import os
import errno
import logging
import logging.handlers
import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.client import HTTPConnection

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 21931
ZOTERO_HOST = "127.0.0.1"
ZOTERO_PORT = 23119
VERSION = "0.2.0"

# Determine log file location
if sys.platform == "win32":
    appdata = os.environ.get("APPDATA")
    if appdata:
        log_dir = os.path.join(appdata, "kingsoft", "wps", "jsaddons")
    else:
        log_dir = os.path.expanduser("~")
    os.makedirs(log_dir, exist_ok=True)
    LOG_FILE = os.path.join(log_dir, "wps-zotero-proxy.log")
else:
    LOG_FILE = os.path.expanduser("~/.wps-zotero-proxy.log")

logger = logging.getLogger("wps-zotero-proxy")


def setup_logging():
    logger.setLevel(logging.INFO)
    try:
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=100 * 1024, backupCount=1, encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(threadName)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except Exception as e:
        sys.stderr.write(f"Failed to initialize rotating file handler for {LOG_FILE}: {e}\n")


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        logger.info("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def do_OPTIONS(self):
        self.send_response(204, "No Content")
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Zotero-Allowed-Request, X-Zotero-Connector-API-Version",
        )
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._handle_health()
        elif self.path.startswith("/connector/"):
            self._forward_request()
        else:
            self._handle_not_found()

    def do_POST(self):
        if self.path == "/stopproxy":
            self._handle_stopproxy()
        elif self.path.startswith("/connector/"):
            self._forward_request()
        else:
            self._handle_not_found()

    def _handle_health(self):
        body = json.dumps({"status": "ok", "version": VERSION}).encode("utf-8")
        self.send_response(200, "OK")
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_stopproxy(self):
        body = json.dumps({"status": "stopping"}).encode("utf-8")
        self.send_response(200, "OK")
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

        logger.info("Received /stopproxy request, shutting down server")
        # Schedule shutdown in background daemon thread
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _handle_not_found(self):
        body = json.dumps({"error": "Not Found"}).encode("utf-8")
        self.send_response(404, "Not Found")
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _forward_request(self):
        # Read incoming request body if any
        content_length = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(content_length) if content_length > 0 else b""

        zotero_port = getattr(self.server, "zotero_port", ZOTERO_PORT)

        # Build headers to send to Zotero
        target_host = f"127.0.0.1:{zotero_port}"
        forward_headers = {
            "Host": target_host,
            "Content-Length": str(len(req_body)),
            "Zotero-Allowed-Request": "1",
            "X-Zotero-Connector-API-Version": "3",
            "User-Agent": f"WPS-Zotero-Proxy/{VERSION}",
        }

        # Keep client Content-Type if present, otherwise default to JSON
        client_content_type = self.headers.get("Content-Type")
        if client_content_type:
            forward_headers["Content-Type"] = client_content_type
        else:
            forward_headers["Content-Type"] = "application/json; charset=utf-8"

        # Forward non-blacklisted headers from client
        blocked_headers = {
            "host",
            "user-agent",
            "content-length",
            "content-type",
            "origin",
            "referer",
            "zotero-allowed-request",
            "x-zotero-connector-api-version",
        }
        for k, v in self.headers.items():
            k_lower = k.lower()
            if k_lower.startswith("sec-fetch-") or k_lower in blocked_headers:
                continue
            forward_headers[k] = v

        # Connect to Zotero: try 127.0.0.1 first, fallback to ::1 on connection refused
        conn = None
        resp = None
        for host in ("127.0.0.1", "::1"):
            try:
                # timeout=None: Zotero's execCommand blocks waiting for user input in dialogs
                conn = HTTPConnection(host, zotero_port, timeout=None)
                conn.request(self.command, self.path, body=req_body, headers=forward_headers)
                resp = conn.getresponse()
                break
            except (ConnectionRefusedError, OSError) as e:
                logger.warning("Failed connecting to Zotero on %s:%d: %s", host, zotero_port, e)
                if conn:
                    conn.close()
                conn = None
            except Exception as e:
                logger.error("Unexpected error connecting to Zotero on %s:%d: %s", host, zotero_port, e)
                if conn:
                    conn.close()
                conn = None
                break

        if resp is None:
            # Both failed
            err_body = json.dumps({"error": "Zotero is not running or unreachable"}).encode("utf-8")
            self.send_response(502, "Bad Gateway")
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
            return

        try:
            resp_body = resp.read()
            self.send_response(resp.status, resp.reason)
            self._send_cors_headers()

            # Forward response headers excluding hop-by-hop
            hop_by_hop = {
                "connection",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailers",
                "transfer-encoding",
                "upgrade",
                "content-length",
                "access-control-allow-origin",
            }
            for header, value in resp.getheaders():
                if header.lower() not in hop_by_hop:
                    self.send_header(header, value)

            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
        finally:
            if conn:
                conn.close()


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, zotero_port=ZOTERO_PORT):
        self.zotero_port = zotero_port
        super().__init__(server_address, RequestHandlerClass)


def is_proxy_healthy(proxy_port=PROXY_PORT, host=PROXY_HOST, timeout=1.0) -> bool:
    url = f"http://{host}:{proxy_port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "ok"
    except Exception:
        return False
    return False


def stop_proxy(proxy_port=PROXY_PORT, host=PROXY_HOST, timeout=2.0) -> bool:
    url = f"http://{host}:{proxy_port}/stopproxy"
    try:
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def create_server(proxy_port=PROXY_PORT, zotero_port=ZOTERO_PORT, host=PROXY_HOST):
    return ProxyServer((host, proxy_port), ProxyHandler, zotero_port=zotero_port)


def run_server(proxy_port=PROXY_PORT, zotero_port=ZOTERO_PORT, host=PROXY_HOST):
    setup_logging()
    logger.info("Starting WPS-Zotero proxy server on %s:%d (forwarding to %d)...", host, proxy_port, zotero_port)
    try:
        server = create_server(proxy_port=proxy_port, zotero_port=zotero_port, host=host)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            if is_proxy_healthy(proxy_port=proxy_port, host=host):
                logger.info("Proxy already running and healthy on %s:%d. Exiting cleanly.", host, proxy_port)
                sys.exit(0)
            else:
                logger.error("Port %d is in use, but /health did not respond.", proxy_port)
                sys.exit(1)
        raise

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user.")
    finally:
        server.server_close()
        logger.info("Server closed.")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "kill":
            if stop_proxy():
                print("Proxy stopped successfully.")
                sys.exit(0)
            else:
                print("Proxy was not running or failed to stop.")
                sys.exit(0)
        elif cmd == "status":
            if is_proxy_healthy():
                print(f"Proxy is running (version {VERSION}).")
                sys.exit(0)
            else:
                print("Proxy is stopped.")
                sys.exit(1)
        else:
            print(f"Usage: {sys.argv[0]} [kill|status]")
            sys.exit(1)

    run_server()


if __name__ == "__main__":
    main()
