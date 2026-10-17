import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

class CILaneOwnershipAcceptance(unittest.TestCase):
    def test_ac_1_deduplicate_bootstrap_factory_tests_without_removing_required_checks(self):
        selective = (ROOT / ".github/workflows/ci-selective.yml").read_text()
        bootstrap = (ROOT / ".github/workflows/factory-bootstrap.yml").read_text()
        scanner = (ROOT / ".github/workflows/ci.yml").read_text()
        policy = selective.split("  policy:\n", 1)[1].split("  scanner:\n", 1)[0]
        factory = selective.split("  factory:\n", 1)[1].split("  docs:\n", 1)[0]
        self.assertNotIn("unittest discover -s .factory/tests", policy)
        self.assertNotIn("unittest discover -s .factory/tests", factory)
        self.assertIn("unittest discover -s .factory/tests -v", bootstrap)
        self.assertIn("run_permanent_acceptance.py", policy)
        self.assertIn("compileall -q .factory/scripts .factory/acceptance", factory)
        self.assertIn("unit-tests:", scanner)
        self.assertIn("coverage run --source=insurance", selective)
        self.assertIn("factory-gate-preflight:", selective)
