"""Issue #93: required-check lookup must survive aggregate check history saturation."""
import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".factory/scripts"))
from post_merge_closure import require_main_checks, ReconcileError, REQUIRED_JOBS

SHA = "a" * 40


def emit(index):
    target = ROOT / "reports" / f"ac-{index}.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite", tests="1", failures="0",
                       errors="0", skipped="0", assertions="4")
    ET.SubElement(suite, "testcase", classname="Issue93", name=f"test_ac_{index}")
    ET.ElementTree(suite).write(target, encoding="utf-8", xml_declaration=True)


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.missing = None
        self.failure = None
        self.wrong_app = None
        self.wrong_head = None
        self.stale_main = False

    def get(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == "/git/ref/heads/main":
            return {"object": {"sha": "b" * 40 if self.stale_main else SHA}}
        assert "/check-runs?check_name=" in endpoint, endpoint
        assert "&filter=latest&per_page=100" in endpoint, endpoint
        name = endpoint.split("check_name=", 1)[1].split("&", 1)[0]
        if name == self.missing:
            return {"total_count": 0, "check_runs": []}
        check = {
            "name": name, "head_sha": "b" * 40 if name == self.wrong_head else SHA,
            "app": {"slug": "other-app" if name == self.wrong_app else "github-actions"},
            "status": "completed",
            "conclusion": "failure" if name == self.failure else "success",
        }
        return {"total_count": 1, "check_runs": [check]}


class Issue93Acceptance(unittest.TestCase):
    def test_ac_1_aggregate_over_100_never_queried(self):
        api = FakeAPI()
        require_main_checks(api, SHA)
        self.assertEqual(len([x for x in api.calls if "check_name=" in x]),
                         len(REQUIRED_JOBS))
        self.assertFalse(any(x.endswith("/check-runs?per_page=100")
                             for x in api.calls))
        emit(1)



if __name__ == "__main__":
    unittest.main()
