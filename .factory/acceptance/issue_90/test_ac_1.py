"""Issue #90 AC-1: optional fixture contract and independent accounting."""
import csv
from pathlib import Path
import tempfile
import tomllib
import unittest

from research.lambdaclass_probe import EXPECTED, write_fixture


ROOT = Path(__file__).resolve().parents[3]


class Acceptance(unittest.TestCase):
    def test_ac_1_synthetic_fixture_is_complete_and_core_remains_dependency_free(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["dependencies"], [])
        with tempfile.TemporaryDirectory() as directory:
            stock_path, option_path = write_fixture(Path(directory))
            with stock_path.open(newline="", encoding="utf-8") as handle:
                stocks = list(csv.DictReader(handle))
            with option_path.open(newline="", encoding="utf-8") as handle:
                options = list(csv.DictReader(handle))
        self.assertEqual(len(stocks), 9)
        self.assertEqual(len(options), 9)
        self.assertEqual({row["underlying"] for row in options}, {"XYZ"})
        self.assertEqual(float(options[0]["ask"]), 1.00)
        self.assertEqual(float(options[0]["bid"]), 0.90)
        self.assertEqual(EXPECTED["entry_nav"], 30 + 950 * 100 + 50 * 100 * 0.90)
        self.assertEqual(EXPECTED["crash_day_nav"], 30 + 950 * 80 + 50 * 100 * 5.00)
        self.assertEqual(EXPECTED["final_nav"], 30 + 950 * 50 + 50 * 100 * 30.00)


if __name__ == "__main__":
    unittest.main()
