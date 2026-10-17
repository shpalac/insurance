#!/usr/bin/env python3
"""Verify same-SHA hosted macOS/Windows proof, JUnit and immutable artifact."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
from urllib import error, request, parse
import zipfile

from run_acceptance_manifest import verify_report

NAMES = {"macos-latest": "acceptance-macos",
         "windows-latest": "acceptance-windows"}

class CrossOSProofError(ValueError):
    pass

def verify_payload(payload, runner, sha, names, files, run_id):
    if not isinstance(payload, dict) or (payload.get("version"),
            payload.get("runner"), payload.get("sha"),
            payload.get("run_id")) != (1, runner, sha, run_id):
        raise CrossOSProofError("Cross-OS identity differs from trusted CI")
    rows = payload.get("records")
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise CrossOSProofError("Malformed hosted report index")
    pairs = [(r.get("issue"), r.get("id")) for r in rows]
    if len(pairs) != len(set(pairs)):
        raise CrossOSProofError("Duplicate hosted acceptance rows")
    result = {}
    for issue, criterion in names:
        selected = [r for r in rows if (r.get("issue"), r.get("id")) ==
                    (issue, criterion)]
        if len(selected) != 1:
            raise CrossOSProofError("Missing hosted acceptance proof")
        row = selected[0]
        path = f"reports/cross_os/issue_{issue}_ac_{criterion.split('-')[1]}.xml"
        if (row.get("report") != path or row.get("head_sha") != sha
                or row.get("runner") != runner or row.get("status") != "PASS"
                or path not in files):
            raise CrossOSProofError("Wrong runner, SHA or required JUnit")
        raw = files[path]
        if hashlib.sha256(raw).hexdigest() != row.get("report_sha256"):
            raise CrossOSProofError("JUnit digest does not match index")
        with tempfile.TemporaryDirectory() as temp:
            xml = Path(temp) / "proof.xml"
            xml.write_bytes(raw)
            report = verify_report(xml)
        if (report["testcases"] != row.get("testcases")
                or report["assertions"] != row.get("assertions")):
            raise CrossOSProofError("Hosted assertions are unproven")
        result[(issue, criterion)] = {"id": criterion, "head_sha": sha,
            "status": "PASS", "runner": runner,
            "testcases": report["testcases"], "assertions": report["assertions"],
            "report_sha256": row["report_sha256"]}
    return result

def download_artifact(api, artifact):
    url = api.base + f"/actions/artifacts/{artifact['id']}/zip"
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = request.build_opener(NoRedirect())
    try:
        with opener.open(request.Request(url, headers={
                "Authorization": "Bearer " + api.token}), timeout=20) as res:
            raw = res.read(8_000_001)
    except error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise
        signed_url = exc.headers.get("Location", "")
        dest = parse.urlparse(signed_url)
        if dest.scheme != "https" or not dest.hostname or dest.username:
            raise CrossOSProofError("Unsafe storage redirect")
        # Never forward the GitHub Authorization header to blob storage.
        with request.urlopen(request.Request(signed_url), timeout=25) as res:
            raw = res.read(8_000_001)
    if len(raw) > 8_000_000:
        raise CrossOSProofError("Oversized hosted acceptance artifact")
    if artifact.get("digest") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise CrossOSProofError("Hosted archive digest mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        names = zipped.namelist()
        if (len(names) > 500 or len(names) != len(set(names))
                or any(n.startswith("/") or ".." in n.split("/") for n in names)):
            raise CrossOSProofError("Unsafe hosted archive contents")
        return {name: zipped.read(name) for name in names}

def verified_hosted_rows(api, sha, required):
    if not required:
        return {}
    runs = api.get(f"/actions/runs?head_sha={sha}&event=push&per_page=100")
    candidates = [run for run in runs.get("workflow_runs", [])
                  if run.get("name") == "Factory selective CI"
                  and run.get("head_sha") == sha
                  and run.get("conclusion") == "success"]
    if not candidates:
        raise CrossOSProofError("Missing successful current-main CI run")
    run = candidates[0]
    jobs = api.get(f"/actions/runs/{run['id']}/jobs?per_page=100")
    artifacts = api.get(f"/actions/runs/{run['id']}/artifacts?per_page=100")
    if jobs.get("total_count", 101) > 100 or artifacts.get("total_count", 101) > 100:
        raise CrossOSProofError("Truncated runner evidence")
    evidence = {}
    for runner, criteria in required.items():
        name = NAMES.get(runner)
        if not name:
            raise CrossOSProofError("Unsupported acceptance runner")
        if not any(j.get("name") == name and j.get("status") == "completed"
                   and j.get("conclusion") == "success"
                   for j in jobs.get("jobs", [])):
            raise CrossOSProofError("Hosted runner did not complete")
        available = [a for a in artifacts.get("artifacts", [])
                     if a.get("name") == name and not a.get("expired")]
        if len(available) != 1:
            raise CrossOSProofError("Missing unique immutable hosted archive")
        files = download_artifact(api, available[0])
        if "evidence.json" not in files:
            raise CrossOSProofError("Hosted artifact lacks evidence index")
        try:
            indexed = json.loads(files["evidence.json"])
        except ValueError as exc:
            raise CrossOSProofError("Unparseable hosted report") from exc
        evidence.update(verify_payload(indexed, runner, sha, criteria, files, run["id"]))
    return evidence
