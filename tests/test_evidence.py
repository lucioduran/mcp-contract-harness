import json
import tempfile
import unittest
from pathlib import Path

from clients.evidence import inspect_trace
from clients.raw import run


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.trace = run()

    def inspect(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return inspect_trace(path)

    def test_actual_raw_trace(self):
        result = self.inspect(self.trace)
        self.assertEqual(result["cancelled_requests"], 1)
        self.assertEqual(result["protocol"], "2025-06-18")

    def test_reject_missing_page_wrong_version_duplicate_and_cancel_response(self):
        mutations = []
        for target in ["page", "version", "duplicate", "cancelled"]:
            rows = json.loads(json.dumps(self.trace))
            if target == "cancelled":
                rows.append(
                    {
                        "direction": "server_to_client",
                        "wire": json.dumps(
                            {"jsonrpc": "2.0", "id": "cancel-me", "result": {}}
                        )
                        + "\n",
                    }
                )
            else:
                for index, row in enumerate(rows):
                    if row["direction"] != "server_to_client":
                        continue
                    msg = json.loads(row["wire"])
                    result = msg.get("result", {})
                    if target == "page" and "resources" in result:
                        del rows[index]
                        break
                    if target == "version" and "protocolVersion" in result:
                        result["protocolVersion"] = "wrong"
                        row["wire"] = json.dumps(msg) + "\n"
                        break
                    if target == "duplicate" and "resources" in result:
                        rows.insert(index, row.copy())
                        break
            mutations.append(rows)
        for rows in mutations:
            smoke_accepts = any(
                row["direction"] == "server_to_client"
                and "protocolVersion" in json.loads(row["wire"]).get("result", {})
                for row in rows
            )
            self.assertTrue(smoke_accepts)
            with self.assertRaises(ValueError):
                self.inspect(rows)

    def test_reject_bad_direction_and_framing(self):
        for row in [
            {"direction": "bad", "wire": "{}\n"},
            {"direction": "server_to_client", "wire": "{}"},
        ]:
            with self.assertRaises(ValueError):
                self.inspect([row])


class ReportTests(unittest.TestCase):
    def test_reference_hashes_and_source_identity(self):
        from clients.reproduce import verify

        report = verify(Path("results/reference"))
        self.assertEqual(len(report["clients"]), 3)

    def test_reject_tampered_report_and_trace(self):
        import shutil
        from unittest.mock import patch

        from clients.reproduce import verify

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "copy"
            shutil.copytree("results/reference", root)
            with patch("clients.reproduce.source_hashes", return_value={}):
                with self.assertRaisesRegex(ValueError, "Source"):
                    verify(root)
            trace = root / "raw.jsonl"
            trace.write_bytes(trace.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify(root)
