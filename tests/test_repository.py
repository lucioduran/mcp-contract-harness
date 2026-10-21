import subprocess
import unittest
from pathlib import Path


class RepositoryTests(unittest.TestCase):
    def test_readme_sections(self):
        sections = [
            line[3:]
            for line in Path("README.md").read_text().splitlines()
            if line.startswith("## ")
        ]
        self.assertEqual(
            sections,
            [
                "Problem",
                "Scope",
                "Quick start",
                "Usage",
                "Architecture",
                "Reproduction",
                "Results",
                "Testing",
                "Limitations",
                "Contributing",
                "License",
            ],
        )

    def test_tracked_text_uses_no_em_dash(self):
        files = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
        for name in filter(None, files):
            with self.subTest(path=name):
                self.assertNotIn(chr(0x2014), Path(name).read_text(encoding="utf-8"))
