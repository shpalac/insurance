"""AC-3: update and merge are distinct serialized actions."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from pr_merge_coordinator import select, REQUIRED

class Issue47AC3(unittest.TestCase):
    def test_ac_3_up_to_date_merge_requires_fresh_checks(self):
        sha="a"*40
        pr={"number":47,"state":"open","draft":False,"created_at":"2026-10-18T00:00:00Z","head":{"sha":sha,"repo":{"full_name":"shpalac/insurance"}},"base":{"ref":"main"},"mergeable":True,"mergeable_state":"behind"}
        checks={47:[{"name":n,"head_sha":sha,"status":"completed","conclusion":"success"} for n in REQUIRED]}
        args=([pr],"b"*40,"shpalac/insurance",{47:["src/insurance/strategy.py"]},{47:[]},checks,"shpalac")
        self.assertEqual(select(*args)["action"],"update")
        pr["mergeable_state"]="clean"
        self.assertEqual(select(*args)["action"],"merge")
        checks[47][0]["conclusion"]="failure"
        self.assertEqual(select(*args)["action"],"idle")
