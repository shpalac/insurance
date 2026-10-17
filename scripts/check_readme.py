"""Validate local README links, illustrative assets and demo safety contract."""

from __future__ import annotations

import re
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def local_targets(markdown: str) -> set[str]:
    """Extract local Markdown links plus HTML media paths; ignore remote links."""
    markdown_links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", markdown)
    image_sources = re.findall(
        r"""(?:src|srcset)=["']([^"']+)["']""", markdown, flags=re.IGNORECASE
    )
    targets: set[str] = set()
    for value in markdown_links + image_sources:
        candidate = value.strip().split()[0]
        if candidate.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        path = unquote(urlsplit(candidate).path)
        if path and not path.startswith("/"):
            targets.add(path)
    return targets


def main() -> int:
    markdown = README.read_text(encoding="utf-8")
    missing = sorted(
        path for path in local_targets(markdown)
        if not (ROOT / path).exists()
    )
    if missing:
        print("README points to missing files:\n" + "\n".join(missing), file=sys.stderr)
        return 1

    for required in (
        "scripts/readme_demo.py",
        "docs/assets/scanner-preview.svg",
        "docs/assets/insurance-hero-mobile.svg",
        "CONTRIBUTING.md",
        "LICENSE",
        "docs/research-validation.md",
        "docs/market-data-operations.md",
    ):
        if required not in markdown:
            print(f"README is missing reference to {required}", file=sys.stderr)
            return 1

    demo = subprocess.run(
        [sys.executable, str(ROOT / "scripts/readme_demo.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if demo.returncode:
        print(demo.stdout + demo.stderr, file=sys.stderr)
        return demo.returncode

    print(f"README: {len(local_targets(markdown))} local references exist")
    print("README: recorded fixture retains NO TRADE fail-closed behavior")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
