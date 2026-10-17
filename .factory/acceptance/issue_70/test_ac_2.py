import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/".factory/scripts"))
from pr_merge_coordinator import select,REQUIRED,ordered
class Acceptance(unittest.TestCase):
    def test_ac_2_oldest_eligible_one_merge_and_fail_closed_checks(self):
        def pr(n):
            return {"number":n,"created_at":f"2026-10-17T00:00:{n:02d}Z","state":"open","draft":False,"base":{"ref":"main"},"head":{"sha":str(n)*40,"repo":{"full_name":"shpalac/insurance"}},"mergeable":True,"mergeable_state":"clean"}
        one,two=pr(1),pr(2)
        checks={n:[{"name":name,"head_sha":str(n)*40,"status":"completed","conclusion":"success"} for name in REQUIRED] for n in (1,2)}
        args=([two,one],"a"*40,"shpalac/insurance",{1:["README.md"],2:["README.md"]},{1:[],2:[]},checks,"shpalac")
        result=select(*args)
        self.assertEqual((result["action"],result["number"] ),("merge",1))
        checks[1][0]["conclusion"]="failure"
        self.assertEqual(select(*args)["number"],2)
        self.assertEqual([p["number"] for p in ordered([two,one])],[1,2])
        self.assertEqual(len([p for p in (result,) if p["action"]=="merge"]),1)
