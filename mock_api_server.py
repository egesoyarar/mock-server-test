"""
Mock API server for testing API Key Provider + Static Parameters.

Endpoints:
  POST /auth/login      - Returns a nested token: {"data": {"token": "..."}}
  POST /api/flights     - Protected endpoint requiring Bearer token; accepts static + dynamic params
  GET  /api/health      - Health check
  GET  /                - Health check (alias)

Run:  python mock_api_server.py
"""

import json
import os
import secrets
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 9876))

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
        if body:
            safe_body = dict(body)
            if "password" in safe_body:
                safe_body["password"] = "***"
            print(f"[BODY] {json.dumps(safe_body, indent=2)}")
        print(f"{'='*70}")

    # -----------------------------------------------------------------
    # POST /auth/login
    # -----------------------------------------------------------------
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
                "message": "Invalid credentials"
            })
            print(f"  -> LOGIN FAILED | user={username!r}")

    # -----------------------------------------------------------------
    # POST /api/flights
    #
    # Body parameters:
    #   type      - String, STATIC, must be exactly "14"
    #   query     - String, DYNAMIC, filled by LLM
    #   max_price - Number, DYNAMIC, filled by LLM (max ticket price filter)
    # -----------------------------------------------------------------
    def _handle_flights(self, body: dict):
        if not self._check_auth():
            self._send_json(401, {
                "error": "Unauthorized",
                "message": "Valid Bearer token required in Authorization header",
            })
            print(f"  -> FLIGHTS REJECTED | no valid auth")
            return

        param_type = body.get("type")
        query = body.get("query", "")
        max_price = body.get("max_price")

        # Validate static param "type"
        if param_type != "14":
            self._send_json(400, {
                "error": f"Invalid 'type' parameter. Expected exactly '14' (string), got {param_type!r} ({type(param_type).__name__})",
                "hint": "The 'type' parameter is a static value and should not be modified by the LLM."
            })
            print(f"  -> FLIGHTS VALIDATION FAILED | type={param_type!r}")
            return

        # Validate max_price is a number if provided
        if max_price is not None and not isinstance(max_price, (int, float)):
            self._send_json(400, {
                "error": f"Invalid 'max_price' parameter. Expected a number, got {max_price!r} ({type(max_price).__name__})",
                "hint": "The 'max_price' parameter should be a numeric value (Integer or Float)."
            })
            print(f"  -> FLIGHTS VALIDATION FAILED | max_price={max_price!r} ({type(max_price).__name__})")
            return

        # Mock flight data
        all_flights = [
            {"flight": "TK101", "from": "IST", "to": "JFK", "price": 850, "currency": "USD"},
            {"flight": "TK203", "from": "IST", "to": "LHR", "price": 420, "currency": "USD"},
            {"flight": "TK305", "from": "IST", "to": "CDG", "price": 380, "currency": "USD"},
            {"flight": "TK407", "from": "SAW", "to": "STN", "price": 280, "currency": "USD"},
            {"flight": "TK509", "from": "IST", "to": "FCO", "price": 950, "currency": "USD"},
        ]

        # Filter by max_price if provided
        if max_price is not None:
            results = [f for f in all_flights if f["price"] <= max_price]
        else:
            results = all_flights

        print(f"  -> FLIGHTS OK | type={param_type!r}, query={query!r}, max_price={max_price!r} ({type(max_price).__name__}), results={len(results)}")

        self._send_json(200, {
            "status": "success",
            "results": results,
            "total": len(results),
            "query_used": query,
            "params_validated": {
                "type": {"value": param_type, "python_type": type(param_type).__name__, "status": "OK"},
                "query": {"value": query, "python_type": type(query).__name__, "status": "OK"},
                "max_price": {"value": max_price, "python_type": type(max_price).__name__, "status": "OK", "filtered": max_price is not None},
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

        if path == "/api/health" or path == "":
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
    print(f"Mock API Server running on port {PORT}")
    print(f"Token: {VALID_TOKEN[:16]}...")
    print(f"Credentials: {VALID_USERNAME} / {VALID_PASSWORD}")
    print()
    print("Endpoints:")
    print(f"  GET  /api/health")
    print(f"  POST /auth/login")
    print(f"       Body: {{\"username\": \"admin\", \"password\": \"secret123\"}}")
    print()
    print(f"  POST /api/flights")
    print(f"       Headers: Authorization: Bearer <token>")
    print(f"       Body: {{\"type\": \"14\", \"query\": \"istanbul to london\", \"max_price\": 500}}")
    print()
    print("Parameters:")
    print("  type      - String, STATIC (must be '14')")
    print("  query     - String, DYNAMIC (LLM fills)")
    print("  max_price - Number, DYNAMIC (LLM fills, filters flights by price)")
    print()
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
