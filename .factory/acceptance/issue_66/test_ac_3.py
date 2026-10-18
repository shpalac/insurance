"""Issue #66 AC-3: truthful package metadata and portable About copy."""

from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RepositoryMetadataAcceptance(unittest.TestCase):
    def test_ac_3_package_and_github_about_copy_match_research_scope(self):
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        profile = (ROOT / "docs/repository-profile.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        package_desc = config["project"]["description"]
        self.assertIn("Research-only", package_desc)
        self.assertIn("options mispricing", package_desc)
        self.assertIn("modeled expected payouts", package_desc)

        # The GitHub About description must fit the repository's 160-char field.
        after_heading = profile.split("## Description (copy into GitHub → About → Edit)", 1)[1]
        about = after_heading.split("## Topics", 1)[0].strip()
        self.assertLessEqual(len(about), 160)
        self.assertIn("Research-only", about)
        self.assertIn("no live orders", about)
        self.assertIn("options mispricing", about)

        topics = set(re.findall(r"^- `([a-z0-9-]+)`$", profile, flags=re.MULTILINE))
        self.assertTrue({
            "options-pricing", "quantitative-finance", "volatility",
            "market-data", "python",
        }.issubset(topics))
        self.assertNotIn("high-frequency-trading", topics)
        self.assertIn("docs/repository-profile.md", readme)
        self.assertIn("GitHub's **About**", profile)


if __name__ == "__main__":
    unittest.main()
