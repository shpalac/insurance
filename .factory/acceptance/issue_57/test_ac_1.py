"""AC-1: repository convention, no per-issue handwritten registration."""
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from acceptance_discovery import (
    DiscoveryError, available_criteria, named_path, validate_named_test
)

VALID = """import unittest
class Sample(unittest.TestCase):
    def test_ac_1_behavior(self):
        self.assertEqual(2 + 2, 4)
"""


class DiscoveryAcceptance(unittest.TestCase):
    def test_ac_1_new_issue_test_is_auto_discovered(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = named_path(root, 938, "AC-1")
            path.parent.mkdir(parents=True)
            path.write_text(VALID)
            self.assertEqual(validate_named_test(path, "AC-1"), 1)
            self.assertEqual(
                available_criteria(root, 938, ["AC-1"], {}),
                {"AC-1": "co-shipped"}
            )

    def test_ac_1_missing_file_stays_unverified(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(
                available_criteria(Path(folder), 938, ["AC-1", "AC-2"], {}),
                {}
            )

    def test_ac_1_bad_name_or_no_assertion_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = named_path(root, 938, "AC-1")
            path.parent.mkdir(parents=True)
            path.write_text(VALID.replace("test_ac_1_behavior", "test_ac_2_wrong"))
            with self.assertRaises(DiscoveryError):
                available_criteria(root, 938, ["AC-1"], {})
            path.write_text(VALID.replace("self.assertEqual(2 + 2, 4)", "pass"))
            with self.assertRaises(DiscoveryError):
                validate_named_test(path, "AC-1")

    def test_ac_1_symlink_escape_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = named_path(root, 938, "AC-1")
            path.parent.mkdir(parents=True)
            outside = root / "outsider.py"
            outside.write_text(VALID)
            path.symlink_to(outside)
            with self.assertRaises(DiscoveryError):
                available_criteria(root, 938, ["AC-1"], {})

    def test_ac_1_previous_reviewed_targets_still_resolve(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(
                available_criteria(Path(folder), 938, ["AC-1"],
                                   {"938/AC-1": {"runner_os": "ubuntu-latest"}}),
                {"AC-1": "reviewed"}
            )


if __name__ == "__main__":
    unittest.main()
