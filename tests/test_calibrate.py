import contextlib
import io
import random
import unittest

import calibrate
import compare


class SharedDecisionRuleTests(unittest.TestCase):
    def test_decision_mapping_matches_report_semantics(self):
        self.assertEqual(compare.decide(-0.01, 0.01, 0.05), "WITHIN_DECLARED_BOUNDS")
        self.assertEqual(compare.decide(-0.30, -0.10, 0.05), "MATERIAL_REGRESSION")
        self.assertEqual(compare.decide(0.10, 0.30, 0.05), "MATERIAL_IMPROVEMENT")
        self.assertEqual(compare.decide(-0.20, 0.20, 0.05), "INCONCLUSIVE")
        self.assertEqual(compare.decide(0.049, 0.20, 0.05), "INCONCLUSIVE")

    def test_compare_decision_is_derived_from_its_own_interval(self):
        margin = 0.05
        rows = [
            {"variant": "baseline", "slice": "s", "case_id": "a", "repeat": 0, "score": 0.0},
            {"variant": "candidate", "slice": "s", "case_id": "a", "repeat": 0, "score": 1.0},
            {"variant": "baseline", "slice": "s", "case_id": "b", "repeat": 0, "score": 0.0},
            {"variant": "candidate", "slice": "s", "case_id": "b", "repeat": 0, "score": 1.0},
        ]
        result = compare.compare(rows, "baseline", "candidate", margin, 2000, 3)["results"][0]
        low, high = result["bootstrap_95_percentile_interval"]
        self.assertEqual(result["decision"], compare.decide(low, high, margin))


class GeneratePairsTests(unittest.TestCase):
    def test_generates_matched_paired_cases(self):
        rows, realized = calibrate.generate_pairs(
            random.Random(0), cases=4, repeats=2, effect=0.1, effect_sd=0.0, noise_sd=0.0
        )
        self.assertEqual(len(rows), 4 * 2 * 2)
        baseline = {(r["case_id"], r["repeat"]) for r in rows if r["variant"] == "baseline"}
        candidate = {(r["case_id"], r["repeat"]) for r in rows if r["variant"] == "candidate"}
        self.assertEqual(baseline, candidate)
        self.assertAlmostEqual(realized, 0.1)

    def test_scores_stay_inside_the_supported_range(self):
        rows, _ = calibrate.generate_pairs(
            random.Random(5), cases=30, repeats=3, effect=0.0, effect_sd=0.5, noise_sd=0.6
        )
        for row in rows:
            self.assertGreaterEqual(row["score"], 0.0)
            self.assertLessEqual(row["score"], 1.0)

    def test_homogeneous_effect_makes_realized_mean_identical(self):
        rows, realized = calibrate.generate_pairs(
            random.Random(1), cases=5, repeats=2, effect=0.0, effect_sd=0.0, noise_sd=0.1
        )
        self.assertAlmostEqual(realized, 0.0)
        self.assertTrue(all(isinstance(row["repeat"], int) for row in rows))

    def test_heterogeneous_effect_varies_around_the_generating_mean(self):
        rows, realized = calibrate.generate_pairs(
            random.Random(1), cases=40, repeats=2, effect=0.05, effect_sd=0.3, noise_sd=0.1
        )
        self.assertEqual(len(rows), 40 * 2 * 2)
        # The realized mean is a draw around the generating mean, not that mean itself.
        self.assertLess(abs(realized - 0.05), 4 * 0.3 / 40**0.5)


class NaiveEstimatorTests(unittest.TestCase):
    def rows(self):
        return [
            {"variant": "baseline", "slice": "s", "case_id": "a", "repeat": 0, "score": 0.2},
            {"variant": "candidate", "slice": "s", "case_id": "a", "repeat": 0, "score": 0.6},
            {"variant": "baseline", "slice": "s", "case_id": "b", "repeat": 0, "score": 0.5},
            {"variant": "candidate", "slice": "s", "case_id": "b", "repeat": 0, "score": 0.5},
        ]

    def test_difference_is_candidate_minus_baseline(self):
        observed, low, high = calibrate.naive_repeat_level_estimator(
            self.rows(), "baseline", "candidate", 500, 2
        )
        self.assertAlmostEqual(observed, 0.2)
        self.assertLessEqual(low, observed)
        self.assertGreaterEqual(high, observed)

    def test_rejects_duplicate_variant_observation(self):
        rows = self.rows()
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(compare.DataError, "duplicate variant score"):
            calibrate.naive_repeat_level_estimator(rows, "baseline", "candidate", 100, 2)

    def test_rejects_unpaired_observations(self):
        rows = [row for row in self.rows() if not (row["case_id"] == "b" and row["variant"] == "candidate")]
        with self.assertRaisesRegex(compare.DataError, "one score per variant"):
            calibrate.naive_repeat_level_estimator(rows, "baseline", "candidate", 100, 2)


class CalibrationReportTests(unittest.TestCase):
    def run_small(self, **overrides):
        options = dict(
            cases=10, repeats=4, effect=0.1, effect_sd=0.3, noise_sd=0.1,
            margin=0.05, bootstrap_samples=200, simulations=40, seed=3,
        )
        options.update(overrides)
        return calibrate.calibrate(**options)

    def test_report_is_deterministic_for_a_fixed_seed(self):
        self.assertEqual(self.run_small(), self.run_small())

    def test_report_contains_both_estimands_and_estimators(self):
        report = self.run_small()
        self.assertEqual(set(report["estimators"]), set(calibrate.ESTIMATORS))
        for estimate in report["estimators"].values():
            self.assertGreaterEqual(estimate["coverage_of_realized_effect"], 0.0)
            self.assertLessEqual(estimate["coverage_of_realized_effect"], 1.0)
            self.assertEqual(sum(estimate["decision_rates"].values()), 1.0)
            low, high = estimate["coverage_of_population_95_monte_carlo_interval"]
            self.assertLessEqual(low, high)

    def test_ignoring_nested_repeats_narrows_the_interval(self):
        report = self.run_small()
        case_width = report["estimators"]["case_level"]["mean_interval_width"]
        naive_width = report["estimators"]["naive_repeat_level"]["mean_interval_width"]
        self.assertLess(naive_width, case_width)

    def test_rejects_invalid_simulation_count(self):
        with self.assertRaisesRegex(compare.DataError, "simulations must be at least 1"):
            self.run_small(simulations=0)


class CliTests(unittest.TestCase):
    def test_invalid_arguments_exit_with_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                calibrate.parse_args(["--cases", "1", "--margin", "0.05"])
        self.assertEqual(raised.exception.code, 2)

    def test_parsed_defaults_are_consistent(self):
        args = calibrate.parse_args(["--simulations", "5", "--bootstrap", "10"])
        self.assertEqual(args.simulations, 5)
        self.assertEqual(args.bootstrap, 10)
        self.assertGreaterEqual(args.cases, 2)


if __name__ == "__main__":
    unittest.main()
