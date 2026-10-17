import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from pr_merge_coordinator import resync_summary,approved
class Acceptance(unittest.TestCase):
    def test_ac_3_measure_repeat_races_and_require_owner_on_new_head(self):
        sha="a"*40
        self.assertTrue(resync_summary(0,[])["under_one"])
        self.assertFalse(resync_summary(1,[(sha,"b"*40)])["under_one"])
        self.assertEqual(resync_summary(0,[(sha,"b"*40),(sha,"b"*40)])["resync_count"],1)
        c=[{"user":{"login":"shpalac"},"body":"FACTORY-OWNER-AUTH sha="+sha+" reason=Approved protected diff"}]
        self.assertTrue(approved(c,"shpalac",sha))
        self.assertFalse(approved(c,"shpalac","b"*40))
