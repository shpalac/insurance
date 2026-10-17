#!/usr/bin/env python3
"""Unprivileged per-criterion unittest executor with measured JUnit evidence."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

from acceptance_discovery import DiscoveryError, named_path, validate_named_test

ROOT = Path(__file__).resolve().parents[2]
TOKEN_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")


@contextmanager
def instrument_assertions():
    """Count assertions actually called, not merely mentioned in source."""
    originals = {}
    for name in dir(unittest.TestCase):
        original = getattr(unittest.TestCase, name, None)
        if name.startswith("assert") and callable(original):
            originals[name] = original

            def wrapped(self, *args, __original=original, **kwargs):
                # An assertion that fails correctly still fails the suite.
                self.__dict__["_factory_assertions"] = (
                    self.__dict__.get("_factory_assertions", 0) + 1
                )
                return __original(self, *args, **kwargs)

            setattr(unittest.TestCase, name, wrapped)
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(unittest.TestCase, name, original)


class MeasuredResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.case_counts = {}

    def startTest(self, test):
        test.__dict__["_factory_assertions"] = 0
        super().startTest(test)

    def addSuccess(self, test):
        self.case_counts[test.id()] = test.__dict__.get("_factory_assertions", 0)
        super().addSuccess(test)


def _cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _cases(item)
        else:
            yield item


def execute(*, root: Path, issue: int, criterion: str, report: Path) -> dict:
    if any(os.environ.get(key) for key in TOKEN_ENV):
        raise DiscoveryError("Acceptance execution must not have a GitHub write/read token")
    path = named_path(root, issue, criterion)
    expected = validate_named_test(path, criterion)
    reports_dir = (root / "reports").resolve()
    if (not reports_dir.is_relative_to(root.resolve())
            or not report.resolve().is_relative_to(reports_dir)):
        raise DiscoveryError("Report must stay within trusted reports/")
    name = f"_factory_issue_{issue}_{criterion.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DiscoveryError("Cannot load named acceptance test")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    cases = list(_cases(suite))
    number = criterion.split("-")[1]
    if len(cases) != expected or not all(
        isinstance(test, unittest.TestCase)
        and test._testMethodName.startswith(f"test_ac_{number}_")
        for test in cases
    ):
        raise DiscoveryError("Runtime test suite differs from statically validated criteria")
    with instrument_assertions():
        runner = unittest.TextTestRunner(
            stream=io.StringIO(), verbosity=1, resultclass=MeasuredResult
        )
        result = runner.run(suite)
    assertions = sum(result.case_counts.values())
    zero_assertions = any(count < 1 for count in result.case_counts.values())
    success = (
        result.wasSuccessful() and not result.skipped
        and not result.expectedFailures and not result.unexpectedSuccesses
        and result.testsRun == expected
        and len(result.case_counts) == expected and not zero_assertions
    )
    # Produce honest JUnit also on failure; the calling gate rejects it.
    suite_xml = ET.Element("testsuite", {
        "name": f"issue-{issue}-{criterion}",
        "tests": str(result.testsRun),
        "failures": str(len(result.failures) + int(zero_assertions)),
        "errors": str(len(result.errors)),
        "skipped": str(len(result.skipped) + len(result.expectedFailures)),
        "assertions": str(assertions),
    })
    for test in cases:
        testcase = ET.SubElement(suite_xml, "testcase", {
            "classname": type(test).__name__, "name": test._testMethodName
        })
        for failures, tag in ((result.failures, "failure"), (result.errors, "error"),
                              (result.skipped, "skipped"),
                              (result.expectedFailures, "skipped")):
            for failed_test, _ in failures:
                if failed_test is test:
                    ET.SubElement(testcase, tag).text = "Acceptance did not pass"
        if not result.case_counts.get(test.id(), 0):
            ET.SubElement(testcase, "failure").text = "No runtime assertions recorded"
    report.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite_xml).write(report, encoding="utf-8", xml_declaration=True)
    return {
        "issue": issue, "criterion": criterion, "passed": success,
        "tests": result.testsRun, "assertions": assertions
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--criterion", required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = execute(
            root=ROOT, issue=args.issue, criterion=args.criterion,
            report=ROOT / args.report
        )
    except (DiscoveryError, OSError, ValueError, ImportError) as exc:
        print(f"ERROR: acceptance was not verified ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
