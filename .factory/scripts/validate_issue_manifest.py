#!/usr/bin/env python3
"""Validate issue acceptance metadata. NEVER execute commands from issue bodies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sys

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
FENCE = re.compile(r"^\x60{3}yaml\s+factory-acceptance-manifest\s*\n(.*?)^\x60{3}\s*$", re.MULTILINE | re.DOTALL)
MANUAL = re.compile(r"\b(manually|manual qa|human visual|visually inspect|by hand|physical device|look(s)? good|click through manually)\b", re.IGNORECASE)
SHELL_METACHARS = re.compile(r"[;&|<>\x60$\n\r\\]")
DENIED_ARGS = {"-c", "--pyargs", "-p", "--override-ini", "--confcutdir", "--rootdir"}


class StrictLoader(yaml.SafeLoader):
    """Disallow duplicate YAML mapping keys to avoid ambiguous specifications."""


def _unique_mapping(loader: StrictLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def extract_manifest(body: str) -> dict:
    """Read exactly one acceptance manifest fenced block from untrusted Markdown."""
    matches = FENCE.findall(body)
    if len(matches) != 1:
        raise ValueError("Expected exactly one yaml factory-acceptance-manifest block")
    try:
        manifest = yaml.load(matches[0], Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed acceptance YAML: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Acceptance manifest must be a mapping")
    return manifest


def safe_path(value: str) -> bool:
    """Forbid absolute paths, traversal, empty components and Windows paths."""
    if not value or "\\" in value or "\x00" in value or ":" in value:
        return False
    if PurePosixPath(value).is_absolute():
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _safe_command(value: str) -> bool:
    """Lint illustrative commands only; the executor MUST use a trusted registry."""
    if SHELL_METACHARS.search(value):
        return False
    try:
        tokens = shlex.split(value)
    except ValueError:
        return False
    if len(tokens) < 2 or any(token in DENIED_ARGS for token in tokens):
        return False
    return (tokens[:1] == ["pytest"] or tokens[:3] in (
        ["python", "-m", "pytest"], ["python3", "-m", "pytest"],
        ["python", "-m", "unittest"], ["python3", "-m", "unittest"],
    ))


def validate_manifest(
    manifest: dict, *, root: Path = ROOT, expected_issue_id: int | None = None
) -> list[str]:
    """Return policy errors. No arbitrary command or file mutation is performed."""
    try:
        schema = json.loads(
            (root / ".factory/schemas/acceptance.schema.json").read_text(encoding="utf-8")
        )
        config = yaml.safe_load(
            (root / ".factory/config.yaml").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [f"Cannot load trusted schema/config: {exc}"]

    errors = [
        f"{'.'.join(map(str, error.absolute_path))}: {error.message}"
        for error in Draft202012Validator(schema).iter_errors(manifest)
    ]
    if errors:
        return sorted(errors)

    if expected_issue_id is not None and manifest["issue_id"] != expected_issue_id:
        errors.append("Manifest issue_id does not match GitHub Issue")

    criteria = manifest["acceptance_criteria"]
    ids = [criterion["id"] for criterion in criteria]
    if len(set(ids)) != len(ids):
        errors.append("Criterion IDs must be unique")
    if ids != [f"AC-{index}" for index in range(1, len(ids) + 1)]:
        errors.append("Criterion IDs must be sequential starting from AC-1")

    dependencies = manifest["dependencies"]["depends_on_issues"]
    if manifest["issue_id"] in dependencies:
        errors.append("An Issue cannot depend on itself")

    for value in (
        manifest["scope"]["allowed_paths"] + manifest["scope"]["protected_paths"]
    ):
        if not safe_path(value):
            errors.append(f"Unsafe scope path: {value}")

    for criterion in criteria:
        ac_id = criterion["id"]
        if MANUAL.search(criterion["description"]):
            errors.append(f"{ac_id}: manual-only acceptance criterion")
        if not _safe_command(criterion["command"]):
            errors.append(f"{ac_id}: unsafe or unsupported illustrative test command")
        if not safe_path(criterion["required_report"]):
            errors.append(f"{ac_id}: unsafe report path")
        if criterion["runner_os"] not in config["runners"]["allowed"]:
            errors.append(f"{ac_id}: runner not allowed by repository configuration")
        if not criterion["required_report"].startswith("reports/"):
            errors.append(f"{ac_id}: report must be under reports/")

    if (manifest["definition_of_done"]["min_diff_coverage_percent"]
            < config["verification"]["min_diff_coverage_percent"]):
        errors.append("Acceptance coverage below repository coverage floor")
    return sorted(errors)


def validate_body(
    body: str, *, root: Path = ROOT, expected_issue_id: int | None = None
) -> list[str]:
    try:
        return validate_manifest(
            extract_manifest(body), root=root, expected_issue_id=expected_issue_id
        )
    except ValueError as exc:
        return [str(exc)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--issue", type=int)
    args = parser.parse_args(argv)
    try:
        content = args.file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errors = validate_body(content, expected_issue_id=args.issue)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("PASS: static manifest validation (NO commands executed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
