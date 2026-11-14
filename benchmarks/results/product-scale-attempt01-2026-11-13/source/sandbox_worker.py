"""Standalone stdlib agent loop executed only in the disposable Linux container.

Model inference and protected effects are controller RPCs. Native Python runs
inside this container; it never inherits the host's filesystem or credentials.
"""

import json
import os
import stat
import subprocess
import sys
from typing import Any

MAX_MESSAGE = 64 * 1024


def send(message: dict[str, Any]) -> None:
    encoded = json.dumps(message, separators=(",", ":"))
    if len(encoded.encode()) > MAX_MESSAGE:
        raise ValueError("worker output exceeds message limit")
    print(encoded, flush=True)


def receive() -> dict[str, Any]:
    line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
    if not line.endswith(b"\n") or len(line) > MAX_MESSAGE:
        raise ValueError("missing or oversized controller message")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("controller message must be an object")
    return value


def main() -> int:
    initialization = receive()
    limit = initialization.get("max_steps")
    if type(limit) is not int or not 1 <= limit <= 16:
        raise ValueError("invalid step limit")
    observation: dict[str, Any] = {"state": "ready"}
    for step in range(limit):
        send({"kind": "model_request", "step": step, "observation": observation})
        response = receive()
        if response.get("kind") != "model_response" or response.get("step") != step:
            raise ValueError("model response sequence mismatch")
        action = response["action"]
        if action["tool"] == "finish":
            send({"kind": "finished", "step": step})
            return 0
        if action["tool"] == "copy_named":
            send({"kind": "gateway_request", "step": step, "action": action})
            result = receive()
            if result.get("kind") != "gateway_response" or result.get("step") != step:
                raise ValueError("gateway response sequence mismatch")
            observation = result["result"]
        elif action["tool"] in {"read_file", "write_file"}:
            try:
                flags = (
                    os.O_RDONLY
                    if action["tool"] == "read_file"
                    else os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                )
                descriptor = os.open(action["path"], flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
                try:
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        raise ValueError("workspace entry must be a regular file")
                    if action["tool"] == "read_file":
                        data = os.read(descriptor, 8193)
                        if len(data) > 8192:
                            raise ValueError("workspace file exceeds read limit")
                        observation = {"state": "file_read", "content": data.decode("utf-8")}
                    else:
                        data = action["content"].encode("utf-8")
                        with os.fdopen(os.dup(descriptor), "wb") as output:
                            output.write(data)
                            output.flush()
                            os.fsync(output.fileno())
                        observation = {"state": "file_written", "bytes": len(data)}
                finally:
                    os.close(descriptor)
            except (OSError, ValueError) as error:
                observation = {"state": "file_error", "error": type(error).__name__}
        elif action["tool"] == "python":
            try:
                completed = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", action["code"]],
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
                observation = {
                    "state": "native_completed",
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout[:8192].decode("utf-8", errors="replace"),
                    "stderr": completed.stderr[:8192].decode("utf-8", errors="replace"),
                    "truncated": len(completed.stdout) > 8192 or len(completed.stderr) > 8192,
                }
            except subprocess.TimeoutExpired:
                observation = {"state": "native_timeout"}
        else:
            raise ValueError("unsupported action")
    send({"kind": "exhausted", "step": limit})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
