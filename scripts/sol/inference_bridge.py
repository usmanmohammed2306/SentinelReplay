"""Trusted, authenticated Slurm-allocation bridge to a loopback inference server.

This carries synthetic model requests only; it never executes agent code.
The token stays in a mode-0600 project file and must not enter result artifacts.
"""

import argparse
import hmac
import http.client
import http.server
import os
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    descriptor = os.open(args.token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(secrets.token_urlsafe(32))
    token = args.token_file.read_text()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *values: object) -> None:
            pass

        def do_POST(self) -> None:
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_error(401)
                return
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return
            if not 0 < length <= 1024 * 1024:
                self.send_error(413)
                return
            self.connection.settimeout(30)
            body = self.rfile.read(length)
            connection = http.client.HTTPConnection("127.0.0.1", 8767, timeout=25)
            try:
                connection.request("POST", self.path, body, {"Content-Type": "application/json"})
                response = connection.getresponse()
                data = response.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    self.send_error(502)
                    return
                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                connection.close()

    print("SENTINEL_AUTHENTICATED_BRIDGE_READY", flush=True)
    http.server.HTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
