"""Executable acceptance for Issue #25: README experience and safety contract."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class ReadmeAcceptance(unittest.TestCase):
    def test_readme_experience_and_fail_closed_demo(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        contribution = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertIn('media="(max-width: 720px)"', readme)
        self.assertIn("docs/assets/scanner-preview.svg", readme)
        self.assertIn("scripts/readme_demo.py", readme)
        self.assertIn("docs/research-validation.md", readme)
        self.assertIn("docs/market-data-operations.md", readme)
        self.assertIn("CONTRIBUTING.md", readme)
        self.assertIn("MIT License", license_text)
        self.assertIn("Refs #N", contribution)
        self.assertIn("python scripts/readme_demo.py --check", ci)
        self.assertIn("python scripts/check_readme.py", ci)

        for relative in (
            "docs/assets/insurance-hero.svg",
            "docs/assets/insurance-hero-mobile.svg",
            "docs/assets/scanner-preview.svg",
        ):
            svg = ET.parse(ROOT / relative).getroot()
            ns = "{http://www.w3.org/2000/svg}"
            self.assertIsNotNone(svg.find(ns + "title"))
            self.assertIsNotNone(svg.find(ns + "desc"))

        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join((
            str(ROOT / "src"), environment.get("PYTHONPATH", "")
        ))
        demo = subprocess.run(
            [sys.executable, str(ROOT / "scripts/readme_demo.py"), "--check"],
            cwd=ROOT, env=environment, capture_output=True, text=True,
            timeout=60, check=False,
        )
        self.assertEqual(demo.returncode, 0, demo.stderr)
        result = json.loads(demo.stdout)
        self.assertEqual(result["quotes_received"], 4)
        self.assertEqual(result["market_data_eligible"], 0)
        self.assertEqual(result["statistically_supported_candidates"], 0)
        self.assertEqual(result["recommendation"], "NO TRADE")

        links = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_readme.py")],
            cwd=ROOT, env=environment, capture_output=True, text=True,
            timeout=60, check=False,
        )
        self.assertEqual(links.returncode, 0, links.stdout + links.stderr)

        # Emit a nonempty JUnit report with real assertions, only after success.
        report = ROOT / "reports/readme-acceptance.xml"
        report.parent.mkdir(parents=True, exist_ok=True)
        suite = ET.Element(
            "testsuite",
            tests="1", failures="0", errors="0", skipped="0", assertions="22",
        )
        ET.SubElement(
            suite, "testcase",
            name=self._testMethodName,
            classname=type(self).__name__,
        )
        ET.ElementTree(suite).write(
            report, encoding="utf-8", xml_declaration=True,
        )


if __name__ == "__main__":
    unittest.main()
