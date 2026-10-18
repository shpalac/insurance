#!/usr/bin/env python3
"""Validate repository factory configuration without executing any commands."""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def validate_config(root: Path = ROOT) -> list[str]:
    """Return all configuration errors; do not mutate repo or enable agents."""
    try:
        config = yaml.safe_load(
            (root / ".factory/config.yaml").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (root / ".factory/schemas/config.schema.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [f"Cannot load config/schema: {exc}"]

    errors = [
        f"{'.'.join(map(str, error.absolute_path))}: {error.message}"
        for error in Draft202012Validator(schema).iter_errors(config)
    ]
    if errors or not isinstance(config, dict):
        return sorted(errors)

    runners = config["runners"]
    if runners["default"] not in runners["allowed"]:
        errors.append("Default runner must be included in allowed runners")

    limits = config["limits"]
    if limits["heartbeat_interval_minutes"] >= limits["lease_ttl_minutes"]:
        errors.append("Heartbeat interval must be shorter than lease TTL")

    repo = config["repository"]
    if repo["visibility"] != "public":
        errors.append("This repository must remain public")
    if repo["merge_strategy"] == "merge_queue":
        errors.append("Native merge queue is unavailable for this account")

    # Fail closed until there is a tested dispatch runtime and credential model.
    orchestration = config["orchestration"]
    if orchestration["enabled"] and not orchestration["approved_agent_logins"]:
        errors.append("Autonomous execution requires approved agent identities")
    if orchestration["enabled"] and not orchestration["agent_providers"]:
        errors.append("Autonomous execution requires an explicit external provider allowlist")

    return sorted(errors)


def main() -> int:
    errors = validate_config()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("PASS: factory config validated (no autonomous actions performed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
