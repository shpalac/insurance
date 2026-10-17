#!/usr/bin/env python3
"""Check local Markdown links without following remote URLs or executing content."""

from pathlib import Path
import re
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def broken_links(root: Path = ROOT) -> list[str]:
    errors = []
    for document in list(root.rglob("*.md")):
        if ".git" in document.parts or ".venv" in document.parts:
            continue
        for target in LINK.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            destination = unquote(target.split("#", 1)[0])
            if not destination or destination.startswith("/"):
                if destination.startswith("/"):
                    errors.append(f"{document.relative_to(root)}: absolute link {target}")
                continue
            candidate = (document.parent / destination).resolve()
            if not candidate.is_relative_to(root.resolve()) or not candidate.exists():
                errors.append(f"{document.relative_to(root)}: broken {target}")
    return sorted(errors)


if __name__ == "__main__":
    failures = broken_links()
    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)
    sys.exit(1 if failures else 0)
