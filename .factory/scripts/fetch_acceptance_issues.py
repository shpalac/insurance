#!/usr/bin/env python3
"""Credentialed metadata-only Issue fetching, isolated from acceptance execution."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib import request

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    base = "https://api.github.com/repos/" + repo
    def fetch(path):
        req = request.Request(base + path, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json"})
        with request.urlopen(req, timeout=25) as res:
            return json.load(res)
    if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
        body = (event.get("pull_request") or {}).get("body") or ""
        ids = sorted({int(x) for x in re.findall(
            r"(?im)^\s*Refs\s+#([1-9][0-9]*)\s*$", body)})
    else:
        ids = []
        for page in range(1, 11):
            batch = fetch(f"/issues?state=open&per_page=100&page={page}")
            ids.extend(x["number"] for x in batch if "pull_request" not in x)
            if len(batch) < 100:
                break
        else:
            raise ValueError("Issue pagination exceeded safe bound")
    if len(ids) > 1000:
        raise ValueError("Issue scan exceeded safe capacity")
    issues = {str(n): fetch(f"/issues/{n}") for n in ids}
    a.output.write_text(json.dumps(issues, sort_keys=True))
    print("Fetched metadata for", len(ids), "Issues")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("ERROR: metadata acquisition failed closed", type(exc).__name__,
              file=sys.stderr)
        raise SystemExit(1)
