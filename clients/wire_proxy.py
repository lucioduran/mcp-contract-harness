"""Record real SDK stdio bytes while relaying to the reference server."""

import json
import subprocess
import sys
import threading
from pathlib import Path


def main():
    trace_path = Path(sys.argv[1])
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_contract.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    lock = threading.Lock()
    with trace_path.open("w", encoding="utf-8", newline="\n") as trace:

        def record(direction, line):
            with lock:
                trace.write(
                    json.dumps({"direction": direction, "wire": line.decode("utf-8")})
                    + "\n"
                )
                trace.flush()

        def read_output():
            for line in process.stdout:
                record("server_to_client", line)
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            for line in sys.stdin.buffer:
                record("client_to_server", line)
                process.stdin.write(line)
                process.stdin.flush()
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            reader.join(timeout=2)
            process.stdout.close()


if __name__ == "__main__":
    main()
