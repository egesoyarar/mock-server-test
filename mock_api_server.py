"""
Mock API server for testing API Key Provider + Static Parameters + Auto-Injection.
Deployed on Render.
"""

import json
import os
import secrets
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 9876))  # Render sets PORT env var

VALID_TOKEN = os.environ.get("API_TOKEN", secrets.token_hex(32))
VALID_USERNAME = "admin"
VALID_PASSWORD = "secret123"

request_counter = 0


class MockAPIHandler(BaseHTTPRequestHandler):

    def _send_json(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body, indent=2).encode())

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {VALID_TOKEN}"

    def _log_request(self, method: str, body: dict | None = None):
        global request_counter
        request_counter += 1
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"\n{'='*70}")
        print(f"[#{request_counter}] {ts} | {method} {self.path}")
        print(f"[HEADERS]")
        for key, val in self.headers.items():
            masked = val
            if key.lower() == "authorization" and len(val) > 20:
                masked = val[:20] + "..." + val[-8:]
            print(f"  {key}: {masked}")
        if body:
            safe_body = dict(body)
            if "password" in safe_body:
                safe_body["password"] = "***"
            print(f"[BODY] {json.dumps(safe_body, indent=2)}")
        print(f"{'='*70}")

    def _handle_login(self, body: dict):
        username = body.get("username", "")
        password = body.get("password", "")

        if username == VALID_USERNAME and password == VALID_PASSWORD:
            self._send_json(200, {
                "status": "success",
                "data": {
                    "token": VALID_TOKEN,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                }
            })
            print(f"  -> LOGIN OK | token issued: {VALID_TOKEN[:16]}...")
        else:
            self._send_json(401, {
                "status": "error",
                "message": "Invalid credentials",
                "received": {
                    "username": username,
                    "password": "***",
                }
            })
            print(f"  -> LOGIN FAILED | user={username!r}")

    def _handle_flights(self, body: dict):
        if not self._check_auth():
            auth_header = self.headers.get("Authorization", "<missing>")
            self._send_json(401, {
                "error": "Unauthorized",
                "message": "Valid Bearer token required in Authorization header",
                "received_auth": auth_header if auth_header != "<missing>" else None,
                "hint": "The login function should be called first. "
                        "The token should be auto-injected by the adapter.",
            })
            print(f"  -> FLIGHTS REJECTED | auth={auth_header!r}")
            return

        param_type = body.get("type")
        query = body.get("query", "")

        validation_errors = []

        if param_type is None:
            validation_errors.append({
                "field": "type",
                "error": "Missing required static parameter 'type'",
                "expected": "14",
                "expected_python_type": "str",
            })
        elif param_type != "14":
            validation_errors.append({
                "field": "type",
                "error": f"Static param 'type' was modified",
                "expected": "14",
                "expected_python_type": "str",
                "received": param_type,
                "received_python_type": type(param_type).__name__,
                "hint": "Static parameters must not be altered by the LLM. "
                        "Check _coerce_static_value and _get_static_param_keys.",
            })

        if validation_errors:
            self._send_json(400, {
                "error": "Static parameter validation failed",
                "validation_errors": validation_errors,
                "body_received": {
                    "type": {"value": param_type, "python_type": type(param_type).__name__},
                    "query": {"value": query, "python_type": type(query).__name__},
                }
            })
            print(f"  -> FLIGHTS VALIDATION FAILED | type={param_type!r} ({type(param_type).__name__})")
            return

        print(f"  -> FLIGHTS OK | type={param_type!r} ({type(param_type).__name__}), query={query!r}")

        self._send_json(200, {
            "status": "success",
            "results": [
                {"flight": "TK101", "from": "IST", "to": "LHR", "price": 420, "currency": "USD"},
                {"flight": "TK203", "from": "SAW", "to": "STN", "price": 280, "currency": "USD"},
                {"flight": "TK305", "from": "IST", "to": "LGW", "price": 350, "currency": "USD"},
            ],
            "total": 3,
            "query_used": query,
            "params_validated": {
                "type": {"value": param_type, "python_type": type(param_type).__name__, "status": "OK"},
                "query": {"value": query, "python_type": type(query).__name__, "status": "OK"},
                "auth": {"status": "OK", "method": "Bearer token"},
            }
        })

    def _handle_health(self):
        self._send_json(200, {
            "status": "healthy",
            "server": "mock-api-server",
            "request_count": request_counter,
            "token_preview": VALID_TOKEN[:8] + "...",
        })

    def do_GET(self):
        path = self.path.rstrip("/")
        self._log_request("GET")

        if path == "/api/health" or path == "/":
            self._handle_health()
        else:
            self._send_json(404, {"error": f"Unknown endpoint: {path}"})

    def do_POST(self):
        body = self._read_body()
        path = self.path.rstrip("/")
        self._log_request("POST", body)

        if path == "/auth/login":
            self._handle_login(body)
        elif path == "/api/flights":
            self._handle_flights(body)
        else:
            self._send_json(404, {"error": f"Unknown endpoint: {path}"})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    server = HTTPServer((HOST, PORT), MockAPIHandler)
    print(f"Mock API Server started on port {PORT}")
    print(f"Token: {VALID_TOKEN[:16]}...")
    print(f"Credentials: {VALID_USERNAME} / {VALID_PASSWORD}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
