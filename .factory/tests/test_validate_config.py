"""Policy regression tests for public, provider-agnostic bootstrap config."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".factory/scripts"))

from validate_config import validate_config  # noqa: E402


class ConfigPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load(
            (ROOT / ".factory/config.yaml").read_text(encoding="utf-8")
        )
        self.schema = json.loads(
            (ROOT / ".factory/schemas/config.schema.json").read_text(
                encoding="utf-8"
            )
        )

    def check_modified(self, mutator):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".factory/schemas").mkdir(parents=True)
            config = copy.deepcopy(self.config)
            mutator(config)
            (root / ".factory/config.yaml").write_text(
                yaml.safe_dump(config), encoding="utf-8"
            )
            (root / ".factory/schemas/config.schema.json").write_text(
                json.dumps(self.schema), encoding="utf-8"
            )
            return validate_config(root)

    def test_current_config_is_valid(self):
        self.assertEqual(validate_config(), [])

    def test_public_repository_is_required(self):
        self.assertTrue(self.check_modified(
            lambda config: config["repository"].update(visibility="private")
        ))

    def test_ci_only_review_policy_is_required(self):
        self.assertEqual(self.config["repository"]["review_policy"], "ci_only")
        self.assertTrue(self.check_modified(
            lambda config: config["repository"].update(review_policy="independent")
        ))

    def test_agents_disabled_by_default(self):
        self.assertFalse(self.config["orchestration"]["enabled"])

    def test_unapproved_agents_cannot_activate(self):
        self.assertTrue(self.check_modified(
            lambda config: config["orchestration"].update(enabled=True)
        ))

    def test_heartbeat_must_precede_expiration(self):
        self.assertTrue(self.check_modified(
            lambda config: config["limits"].update(heartbeat_interval_minutes=30)
        ))

    def test_native_merge_queue_rejected(self):
        self.assertTrue(self.check_modified(
            lambda config: config["repository"].update(merge_strategy="merge_queue")
        ))

    def test_runner_must_be_allowlisted(self):
        self.assertTrue(self.check_modified(
            lambda config: config["runners"].update(default="private-runner")
        ))


if __name__ == "__main__":
    unittest.main()
