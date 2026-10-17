# Sample executable Issue manifest

```yaml factory-acceptance-manifest
schema_version: "1.0"
issue_id: 142
title: "Example deterministic rate limiter"
scope:
  allowed_paths: ["src/middleware/**", "tests/middleware/**"]
  protected_paths: [".github/workflows/**", ".factory/**"]
dependencies:
  depends_on_issues: []
  multi_pr_allowed: false
acceptance_criteria:
  - id: "AC-1"
    description: "Requests within burst capacity return success."
    verification_type: unit
    runner_os: ubuntu-latest
    command: "pytest tests/middleware/test_bucket.py"
    expected_exit_code: 0
    required_report: "reports/ac-1.xml"
    timeout_seconds: 120
  - id: "AC-2"
    description: "Requests exceeding burst capacity are rejected."
    verification_type: unit
    runner_os: ubuntu-latest
    command: "pytest tests/middleware/test_rejection.py"
    expected_exit_code: 0
    required_report: "reports/ac-2.xml"
    timeout_seconds: 120
definition_of_done:
  require_new_or_updated_tests: true
  min_diff_coverage_percent: 90
  require_architecture_doc_sync: true
```

The commands are static metadata only. They are never trusted as runner shell commands.
