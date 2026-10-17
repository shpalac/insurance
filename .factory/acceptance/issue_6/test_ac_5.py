"""AC-5: audited closure needs Refs association, not native closing keywords."""
import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from pr_completion_gate import CompletionError, parse_intent

class RefsOnlyAcceptance(unittest.TestCase):
    def test_ac_5_refs_only_associates_issue_without_native_closure(self):
        refs, completes = parse_intent("Refs #6")
        self.assertEqual(refs, [6])
        self.assertEqual(completes, [])

    def test_ac_5_native_close_keyword_is_rejected(self):
        with self.assertRaises(CompletionError):
            parse_intent("Refs #6\nCloses #6")
