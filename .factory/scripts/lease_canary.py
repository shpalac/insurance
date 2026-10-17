#!/usr/bin/env python3
"""Isolated hosted Git-ref CAS race; only workflow_dispatch on trusted main."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

from github_ref_leases import GitHubRefLeaseStore
from lease_state import LeaseConflict, acquire


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("init", "claim", "verify"), required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--contender", choices=("one", "two"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.run_id < 1:
        raise ValueError("Canary must bind to a positive run identity")
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    branch = f"factory-lease-canary-{args.run_id}"
    store = GitHubRefLeaseStore(repo, token, branch=branch,
                               write_enabled=args.mode != "verify")
    if args.mode == "init":
        created = store.initialize_isolated()
        result = {"created": created, "ref": branch}
    elif args.mode == "claim":
        if not args.contender:
            raise ValueError("Missing contender identity")
        try:
            lease = acquire(store, entity=args.run_id,
                            owner="canary-" + args.contender,
                            role="developer", now=datetime.now(timezone.utc),
                            ttl=timedelta(minutes=30))
            result = {"won": True, "owner": lease.owner,
                      "epoch": lease.epoch, "revision": lease.revision}
        except LeaseConflict:
            result = {"won": False, "owner": "canary-" + args.contender}
    else:
        state = store.read_all()
        lease = state.get(args.run_id)
        if lease is None or lease.epoch != 1 or lease.revision != 1 or                 lease.owner not in {"canary-one", "canary-two"} or len(state) != 1:
            raise ValueError("Hosted CAS state did not yield one durable lease")
        result = {"proof": "single_winner", "issue": args.run_id,
                  "owner": lease.owner, "epoch": lease.epoch,
                  "revision": lease.revision, "ref": branch}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, sort_keys=True))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, TypeError) as exc:
        print("ERROR: hosted lease canary blocked (" + type(exc).__name__ + ")",
              file=sys.stderr)
        raise SystemExit(1)
