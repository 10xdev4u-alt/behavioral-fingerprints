import json
import tempfile
import unittest
from pathlib import Path

import compare


class LoadRecordsTests(unittest.TestCase):
    def write_jsonl(self, text: str) -> Path:
        temporary = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        with temporary:
            temporary.write(text)
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_rejects_malformed_json(self):
        path = self.write_jsonl('{"variant":\n')
        with self.assertRaisesRegex(compare.DataError, "invalid JSON"):
            compare.load_records(path)

    def test_rejects_duplicate_observation(self):
        row = {"variant": "baseline", "slice": "task", "case_id": "a", "repeat": 0, "score": 1.0}
        path = self.write_jsonl(json.dumps(row) + "\n" + json.dumps(row) + "\n")
        with self.assertRaisesRegex(compare.DataError, "duplicate"):
            compare.load_records(path)

    def test_rejects_non_finite_or_out_of_range_score(self):
        row = {"variant": "baseline", "slice": "task", "case_id": "a", "repeat": 0, "score": 1.1}
        path = self.write_jsonl(json.dumps(row) + "\n")
        with self.assertRaisesRegex(compare.DataError, "finite and in \\[0, 1\\]"):
            compare.load_records(path)


class CompareTests(unittest.TestCase):
    def rows(self):
        return [
            {"variant": "baseline", "slice": "stable", "case_id": "a", "repeat": 0, "score": 1.0},
            {"variant": "candidate", "slice": "stable", "case_id": "a", "repeat": 0, "score": 1.0},
            {"variant": "baseline", "slice": "stable", "case_id": "b", "repeat": 0, "score": 0.9},
            {"variant": "candidate", "slice": "stable", "case_id": "b", "repeat": 0, "score": 0.9},
            {"variant": "baseline", "slice": "changed", "case_id": "c", "repeat": 0, "score": 0.0},
            {"variant": "candidate", "slice": "changed", "case_id": "c", "repeat": 0, "score": 1.0},
            {"variant": "baseline", "slice": "changed", "case_id": "d", "repeat": 0, "score": 0.0},
            {"variant": "candidate", "slice": "changed", "case_id": "d", "repeat": 0, "score": 1.0},
        ]

    def test_reports_expected_slice_decisions_and_global_seed(self):
        report = compare.compare(self.rows(), "baseline", "candidate", 0.05, 2000, 11)
        results = {row["slice"]: row for row in report["results"]}
        self.assertEqual(results["stable"]["decision"], "WITHIN_DECLARED_BOUNDS")
        self.assertEqual(results["changed"]["decision"], "MATERIAL_IMPROVEMENT")
        self.assertEqual(report["seed"], 11)
        self.assertNotIn("slice_seed", report)

    def test_markdown_report_contains_decisions_and_limitations(self):
        report = compare.compare(self.rows(), "baseline", "candidate", 0.05, 2000, 5)
        markdown = compare.render_markdown(report)
        self.assertIn("# Behavioral comparison", markdown)
        self.assertIn("WITHIN_DECLARED_BOUNDS", markdown)
        self.assertIn("MATERIAL_IMPROVEMENT", markdown)
        self.assertIn("## Limitations", markdown)
        self.assertIn("not separately modeled", markdown)

    def test_output_is_deterministic(self):
        first = compare.compare(self.rows(), "baseline", "candidate", 0.05, 2000, 5)
        second = compare.compare(self.rows(), "baseline", "candidate", 0.05, 2000, 5)
        self.assertEqual(first, second)

    def test_slice_interval_does_not_depend_on_other_slice_order(self):
        rows = self.rows()
        first = compare.compare(rows, "baseline", "candidate", 0.05, 2000, 5)
        reordered = list(reversed(rows))
        second = compare.compare(reordered, "baseline", "candidate", 0.05, 2000, 5)
        first_stable = next(row for row in first["results"] if row["slice"] == "stable")
        second_stable = next(row for row in second["results"] if row["slice"] == "stable")
        self.assertEqual(first_stable["bootstrap_95_percentile_interval"], second_stable["bootstrap_95_percentile_interval"])

    def test_identical_case_differences_are_flagged_without_implying_precision(self):
        # Every case moves by exactly the same amount, so the resample distribution
        # has no width. With only a handful of cases (or pass/fail scores) this is
        # routine, and the zero width must not be published as precision.
        rows = []
        for case_id in ("a", "b", "c"):
            rows.append({"variant": "baseline", "slice": "tied", "case_id": case_id, "repeat": 0, "score": 1.0})
            rows.append({"variant": "candidate", "slice": "tied", "case_id": case_id, "repeat": 0, "score": 1.0})
        result = compare.compare(rows, "baseline", "candidate", 0.05, 2000, 7)["results"][0]
        self.assertTrue(result["degenerate_interval"])
        self.assertEqual(result["bootstrap_95_percentile_interval"], [0.0, 0.0])
        self.assertIn("no width", result["decision_basis"])
        self.assertIn("not an estimate of precision", result["decision_basis"])

    def test_unanimous_improvement_keeps_its_signal(self):
        # The flag must not swallow a real, unanimous movement: the decision still
        # follows the interval and the declared margin.
        rows = []
        for case_id in ("a", "b", "c"):
            rows.append({"variant": "baseline", "slice": "lift", "case_id": case_id, "repeat": 0, "score": 0.0})
            rows.append({"variant": "candidate", "slice": "lift", "case_id": case_id, "repeat": 0, "score": 1.0})
        result = compare.compare(rows, "baseline", "candidate", 0.05, 2000, 7)["results"][0]
        self.assertTrue(result["degenerate_interval"])
        self.assertEqual(result["decision"], "MATERIAL_IMPROVEMENT")

    def test_degenerate_slice_is_marked_in_markdown(self):
        rows = []
        for case_id in ("a", "b"):
            rows.append({"variant": "baseline", "slice": "tied", "case_id": case_id, "repeat": 0, "score": 0.5})
            rows.append({"variant": "candidate", "slice": "tied", "case_id": case_id, "repeat": 0, "score": 0.5})
        markdown = compare.render_markdown(compare.compare(rows, "baseline", "candidate", 0.05, 500, 7))
        self.assertIn("†", markdown)
        self.assertIn("Degenerate resample distribution", markdown)

    def test_rejects_mismatched_case_sets(self):
        rows = [row for row in self.rows() if not (row["slice"] == "stable" and row["variant"] == "candidate" and row["case_id"] == "b")]
        with self.assertRaisesRegex(compare.DataError, "case IDs do not match"):
            compare.compare(rows, "baseline", "candidate", 0.05, 2000, 5)

    def test_rejects_unequal_repeat_counts(self):
        rows = self.rows()
        rows.append({"variant": "baseline", "slice": "stable", "case_id": "a", "repeat": 1, "score": 1.0})
        with self.assertRaisesRegex(compare.DataError, "repeat counts differ"):
            compare.compare(rows, "baseline", "candidate", 0.05, 2000, 5)

    def test_repeat_averages_remain_paired_by_case(self):
        rows = self.rows()
        for variant, value in (("baseline", 0.0), ("candidate", 0.2)):
            rows.append({"variant": variant, "slice": "stable", "case_id": "a", "repeat": 1, "score": value})
        report = compare.compare(rows, "baseline", "candidate", 0.05, 2000, 5)
        stable = next(row for row in report["results"] if row["slice"] == "stable")
        self.assertEqual(stable["baseline_repeats"], 3)
        self.assertEqual(stable["candidate_repeats"], 3)


if __name__ == "__main__":
    unittest.main()
