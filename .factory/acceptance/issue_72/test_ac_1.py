import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[3]
class Acceptance(unittest.TestCase):
    def test_ac_1_template_has_full_acceptance_spec_scaffold(self):
        template=yaml.safe_load((ROOT/".github/ISSUE_TEMPLATE/factory_executable_issue.yml").read_text())
        fields=[f["id"] for f in template["body"] if "id" in f]
        for required in ("objective","factory_alignment","observable_criteria","acceptance"):
            self.assertIn(required,fields)
        scaffold=next(f["attributes"]["value"] for f in template["body"] if f.get("id")=="acceptance")
        self.assertIn("factory-acceptance-manifest",scaffold)
        self.assertIn("depends_on_issues:",scaffold)
        self.assertIn("multi_pr_allowed: false",scaffold)
