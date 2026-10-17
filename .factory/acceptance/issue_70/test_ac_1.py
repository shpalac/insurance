import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from pr_merge_coordinator import select
class Acceptance(unittest.TestCase):
    def test_ac_1_behind_updates_without_force_and_rechecks_sha(self):
        p={"number":1,"state":"open","draft":False,"base":{"ref":"main"},"head":{"sha":"a"*40,"repo":{"full_name":"shpalac/insurance"}},"mergeable":True,"mergeable_state":"behind"}
        selected=select([p],"b"*40,"shpalac/insurance",{1:["docs/example.md"]},{1:[]},{1:[]},"shpalac")
        self.assertEqual(selected["action"],"update")
        source=(ROOT/".factory/scripts/pr_merge_coordinator.py").read_text()
        self.assertIn("expected_head_sha",source)
        self.assertNotIn("force-push",source.split('if action["action"] == "update":')[1])
        self.assertIn('latest["head"]["sha"] != action["head_sha"]',source)
        workflow=(ROOT/".github/workflows/factory-serialized-merge.yml").read_text()
        self.assertIn("ref: main",workflow)
        self.assertIn("cancel-in-progress: false",workflow)
