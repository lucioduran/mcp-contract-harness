"""Run small local contract checks and preserve their wire evidence."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from clients.evidence import inspect_trace


def source_hashes():
    paths = sorted(
        [
            *Path("mcp_contract").glob("*.py"),
            *Path("clients").glob("*.py"),
            *Path("clients").glob("*.mjs"),
            Path("requirements-dev.lock"),
            Path("package-lock.json"),
        ]
    )
    return {
        str(path).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def reproduce(output):
    output.mkdir(parents=True, exist_ok=False)
    commands = [
        ("raw", [sys.executable, "-m", "clients.raw", "--trace"]),
        ("python", [sys.executable, "-m", "clients.python_sdk", "--trace"]),
        ("typescript", ["node", "clients/typescript-sdk.mjs"]),
    ]
    reports = []
    for name, command in commands:
        trace = output / f"{name}.jsonl"
        result = subprocess.run(
            [*command, str(trace)],
            env={**os.environ, "MCP_PYTHON": sys.executable},
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        report = json.loads(result.stdout)
        report["trace"] = trace.name
        report["trace_sha256"] = hashlib.sha256(trace.read_bytes()).hexdigest()
        report["wire_validation"] = inspect_trace(trace)
        report["stderr"] = result.stderr
        reports.append(report)
    cpu = platform.processor()
    if sys.platform == "darwin":
        cpu = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip()
    result = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "source_sha256": source_hashes(),
        "environment": {
            "python": platform.python_version(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu": cpu,
            "logical_cpus": os.cpu_count(),
            "python_sdk": importlib.metadata.version("mcp"),
            "cpu_work_threads": 1,
        },
        "measurement": "Local correctness checks; no load or performance measurements",
        "paid_api_calls": 0,
        "model_calls": 0,
        "seed": None,
        "clients": reports,
    }
    (output / "report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def verify(output):
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    if report["source_sha256"] != source_hashes():
        raise ValueError("Source or dependency lock drift")
    if {client["client"] for client in report["clients"]} != {
        "raw-reference",
        "official-python-sdk",
        "official-typescript-sdk",
    }:
        raise ValueError("Client set mismatch")
    for client in report["clients"]:
        name = client["trace"]
        if Path(name).name != name:
            raise ValueError("Unsafe trace name")
        trace = output / name
        if hashlib.sha256(trace.read_bytes()).hexdigest() != client["trace_sha256"]:
            raise ValueError("Trace hash mismatch")
        if inspect_trace(trace) != client["wire_validation"]:
            raise ValueError("Trace summary mismatch")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "verify"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            reproduce(args.output) if args.command == "run" else verify(args.output)
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"Evidence failed: {exc}\n")
    print(json.dumps({"clients": len(result["clients"]), "status": "passed"}))
