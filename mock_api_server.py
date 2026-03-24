"""
Mock API server for testing API Key Provider + Static Parameters.
 
Endpoints:
  POST /auth/login      - Returns a nested token: {"data": {"token": "..."}}
  POST /api/flights     - Protected endpoint requiring Bearer token; accepts static + dynamic params
 
Run:  python mock_api_server.py
Server listens on http://localhost:9876
"""
 
import json
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
 
HOST = "0.0.0.0"
PORT = 9876
 
# Simulated valid token (generated once per server start)
VALID_TOKEN = secrets.token_hex(32)
 
# Valid credentials
VALID_USERNAME = "admin"
VALID_PASSWORD = "secret123"
 
 
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
 
    # -----------------------------------------------------------------
    # POST /auth/login  --  API Key Provider endpoint
    # Accepts: {"username": "admin", "password": "secret123"}
    # Returns: {"status": "success", "data": {"token": "<token>", "expires_in": 3600}}
    #
    # The token is NESTED under "data.token" -- this tests dot-notation extraction.
    # -----------------------------------------------------------------
    def _handle_login(self, body: dict):
        username = body.get("username", "")
        password = body.get("password", "")
 
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            self._send_json(200, {
                "status": "success",
                "data": {
                    "token": VALID_TOKEN,
                    "expires_in": 3600
                }
            })
            print(f"[LOGIN] OK -- issued token: {VALID_TOKEN[:16]}...")
        else:
            self._send_json(401, {
                "status": "error",
                "message": "Invalid credentials"
            })
            print(f"[LOGIN] FAILED -- user={username}")
 
    # -----------------------------------------------------------------
    # POST /api/flights  --  Protected endpoint with static + dynamic params
    # Requires: Authorization: Bearer <token>
    # Body: {"type": "14", "query": "<search term>"}
    #   - "type" should be a STATIC param (value="14", dataType=String)
    #   - "query" should be a DYNAMIC param (filled by LLM)
    #
    # This endpoint VALIDATES that "type" is exactly "14" (string).
    # If the LLM overwrites it (e.g., sends "airline" or 14 as int), it fails.
    # -----------------------------------------------------------------
    def _handle_flights(self, body: dict):
        if not self._check_auth():
            self._send_json(401, {"error": "Unauthorized. Provide a valid Bearer token."})
            print("[FLIGHTS] REJECTED -- missing/invalid auth token")
            return
 
        param_type = body.get("type")
        query = body.get("query", "")
 
        print(f"[FLIGHTS] Received -- type={param_type!r} (python type: {type(param_type).__name__}), query={query!r}")
 
        # Validate static param
        if param_type != "14":
            self._send_json(400, {
                "error": f"Invalid 'type' parameter. Expected exactly '14' (string), got {param_type!r} ({type(param_type).__name__})",
                "hint": "The 'type' parameter is a static value and should not be modified by the LLM."
            })
            return
 
        # Return mock flight results
        self._send_json(200, {
            "status": "success",
            "results": [
                {"flight": "TK101", "from": "IST", "to": "JFK", "price": 850, "query_match": query},
                {"flight": "TK203", "from": "IST", "to": "LHR", "price": 420, "query_match": query},
                {"flight": "TK305", "from": "IST", "to": "CDG", "price": 380, "query_match": query},
            ],
            "total": 3,
            "params_received": {
                "type": param_type,
                "type_python_type": type(param_type).__name__,
                "query": query
            }
        })
 
    def do_POST(self):
        body = self._read_body()
        path = self.path.rstrip("/")
 
        if path == "/auth/login":
            self._handle_login(body)
        elif path == "/api/flights":
            self._handle_flights(body)
        else:
            self._send_json(404, {"error": f"Unknown endpoint: {path}"})
 
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
 
    def log_message(self, format, *args):
        # Suppress default HTTP log noise
        pass
 
 
def main():
    server = HTTPServer((HOST, PORT), MockAPIHandler)
    print(f"Mock API server running on http://{HOST}:{PORT}")
    print(f"Valid credentials: username={VALID_USERNAME}, password={VALID_PASSWORD}")
    print(f"Generated token: {VALID_TOKEN}")
    print()
    print("Endpoints:")
    print(f"  POST http://localhost:{PORT}/auth/login")
    print(f"       Body: {{\"username\": \"admin\", \"password\": \"secret123\"}}")
    print(f"       Response: {{\"data\": {{\"token\": \"...\"}}}}")
    print()
    print(f"  POST http://localhost:{PORT}/api/flights")
    print(f"       Headers: Authorization: Bearer <token>")
    print(f"       Body: {{\"type\": \"14\", \"query\": \"istanbul to london\"}}")
    print()
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
 
 
if __name__ == "__main__":
    main()
