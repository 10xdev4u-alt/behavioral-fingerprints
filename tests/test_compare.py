import contextlib
import io
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


class GateExitCodeTests(unittest.TestCase):
    """Exit codes are a public contract that pipelines branch on."""

    def report_with(self, decisions):
        return {"results": [{"slice": f"s{i}", "decision": decision} for i, decision in enumerate(decisions)]}

    def test_default_policy_never_fails(self):
        report = self.report_with(["MATERIAL_REGRESSION", "INCONCLUSIVE"])
        self.assertEqual(compare.gate_exit_code(report, "never"), compare.EXIT_OK)

    def test_material_regression_fails_only_on_regression(self):
        self.assertEqual(
            compare.gate_exit_code(self.report_with(["MATERIAL_REGRESSION"]), "material_regression"),
            compare.EXIT_GATE_FAILED,
        )
        self.assertEqual(
            compare.gate_exit_code(self.report_with(["MATERIAL_IMPROVEMENT"]), "material_regression"),
            compare.EXIT_OK,
        )

    def test_equivalence_policy_fails_unless_every_slice_is_within_bounds(self):
        within = self.report_with(["WITHIN_DECLARED_BOUNDS", "WITHIN_DECLARED_BOUNDS"])
        self.assertEqual(compare.gate_exit_code(within, "any_not_within_bounds"), compare.EXIT_OK)
        for decision in ("INCONCLUSIVE", "MATERIAL_IMPROVEMENT", "MATERIAL_REGRESSION"):
            self.assertEqual(
                compare.gate_exit_code(self.report_with([decision]), "any_not_within_bounds"),
                compare.EXIT_GATE_FAILED,
                decision,
            )

    def test_unknown_policy_is_rejected(self):
        with self.assertRaisesRegex(compare.DataError, "unknown gate policy"):
            compare.gate_exit_code(self.report_with(["INCONCLUSIVE"]), "sometimes")


class CliContractTests(unittest.TestCase):
    def write(self, rows) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".jsonl", delete=False)
        with handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return Path(handle.name)

    def regressing(self):
        rows = []
        for case_id, before, after in (("a", 0.9, 0.2), ("b", 0.8, 0.1), ("c", 0.85, 0.3)):
            rows.append({"variant": "baseline", "slice": "s", "case_id": case_id, "repeat": 0, "score": before})
            rows.append({"variant": "candidate", "slice": "s", "case_id": case_id, "repeat": 0, "score": after})
        return rows

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = compare.main(argv)
        return code, out.getvalue(), err.getvalue()

    def base_args(self, path):
        return [str(path), "--baseline", "baseline", "--candidate", "candidate",
                "--margin", "0.05", "--bootstrap", "2000", "--seed", "1"]

    def test_report_is_written_before_a_gate_failure(self):
        args = self.base_args(self.write(self.regressing()))
        code, out, err = self.run_main(args + ["--fail-on", "material_regression"])
        self.assertEqual(code, compare.EXIT_GATE_FAILED)
        # The evidence must survive the failure: a gated build still needs its report.
        self.assertEqual(json.loads(out)["results"][0]["decision"], "MATERIAL_REGRESSION")
        self.assertIn("gate failed", err)
        self.assertIn("s", err)

    def test_same_input_passes_with_the_default_policy(self):
        args = self.base_args(self.write(self.regressing()))
        code, out, _ = self.run_main(args)
        self.assertEqual(code, compare.EXIT_OK)
        self.assertEqual(json.loads(out)["results"][0]["decision"], "MATERIAL_REGRESSION")

    def test_input_error_is_distinct_from_gate_failure(self):
        rows = [row for row in self.regressing() if not (row["variant"] == "candidate" and row["case_id"] == "c")]
        code, out, err = self.run_main(self.base_args(self.write(rows)))
        self.assertEqual(code, compare.EXIT_INPUT_ERROR)
        self.assertEqual(out, "")
        self.assertIn("input error", err)

    def test_gate_policy_is_echoed_in_stderr_not_the_report(self):
        args = self.base_args(self.write(self.regressing()))
        _, out, _ = self.run_main(args + ["--fail-on", "material_regression"])
        # The report must stay reproducible: the caller's gate choice is not data.
        self.assertNotIn("fail_on", json.loads(out))


if __name__ == "__main__":
    unittest.main()
