"""Issue #66 AC-1: first-screen positioning and honest maturity labeling."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


class ReadmePositioningAcceptance(unittest.TestCase):
    def test_ac_1_research_scope_and_maturity_are_explicit(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        introduction = readme.split("## The idea", 1)[0]
        project_idea = readme.split("## The idea", 1)[1].split(
            "## Scanner preview", 1
        )[0]

        self.assertIn("Quantitative options mispricing research", introduction)
        self.assertIn("expensive to sell or cheap to buy", introduction)
        self.assertIn("Research-only today", introduction)
        self.assertIn("No live orders", introduction)
        self.assertIn("UNVERIFIED", introduction)
        self.assertIn("NO TRADE", introduction)

        self.assertIn("Project maturity at a glance", project_idea)
        self.assertIn("Working code", project_idea)
        self.assertIn("Experimental research", project_idea)
        self.assertIn("Not yet available", project_idea)
        self.assertIn("does not autonomously monitor live markets", project_idea)
        self.assertIn("No validated trading signals today", introduction)


if __name__ == "__main__":
    unittest.main()
