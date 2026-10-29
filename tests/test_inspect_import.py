import json
import tempfile
import unittest
from pathlib import Path

import compare


class InspectImportTests(unittest.TestCase):
    def write_log(self, payload):
        temporary = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        with temporary:
            json.dump(payload, temporary)
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def valid_log(self):
        return {
            "status": "success",
            "eval": {
                "eval_id": "run-1",
                "task_id": "task-1",
                "task": "demo",
                "task_version": 1,
                "model": "mock/model",
                "dataset": {"name": "toy", "sample_ids": ["a", "b"]},
                "config": {"epochs": 1},
            },
            "samples": [
                {"id": "a", "epoch": 1, "scores": {"accuracy": {"value": 0.8}}},
                {"id": "b", "epoch": 1, "scores": {"accuracy": {"value": 1.0}}},
            ],
        }

    def test_imports_task_sample_epoch_and_numeric_score(self):
        path = self.write_log(self.valid_log())
        rows = compare.load_inspect_log(path, "baseline", "task-slice", "accuracy")
        self.assertEqual(rows, [
            {"variant": "baseline", "slice": "task-slice", "case_id": "demo:1:toy:a", "repeat": 1, "score": 0.8, "eval_id": "run-1", "task_id": "task-1", "task": "demo", "task_version": 1, "dataset_name": "toy", "model": "mock/model", "epochs": 1, "scorer": "accuracy"},
            {"variant": "baseline", "slice": "task-slice", "case_id": "demo:1:toy:b", "repeat": 1, "score": 1.0, "eval_id": "run-1", "task_id": "task-1", "task": "demo", "task_version": 1, "dataset_name": "toy", "model": "mock/model", "epochs": 1, "scorer": "accuracy"},
        ])

    def test_rejects_unsuccessful_log(self):
        payload = self.valid_log()
        payload["status"] = "error"
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "status must be 'success'"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_rejects_missing_scorer(self):
        payload = self.valid_log()
        payload["samples"][0]["scores"] = {}
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "missing scorer"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_rejects_non_numeric_score(self):
        payload = self.valid_log()
        payload["samples"][0]["scores"]["accuracy"]["value"] = "pass"
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "value must be numeric"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_rejects_sample_error(self):
        payload = self.valid_log()
        payload["samples"][0]["error"] = {"message": "failed"}
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "sample has an error"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_rejects_missing_explicit_dataset_ids(self):
        payload = self.valid_log()
        payload["eval"]["dataset"].pop("sample_ids")
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "explicit eval.dataset.sample_ids"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_rejects_missing_stable_id(self):
        payload = self.valid_log()
        payload["samples"][0].pop("id")
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "id must be"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_paired_cli_input_compares_two_inspect_logs(self):
        baseline = self.write_log(self.valid_log())
        candidate_data = self.valid_log()
        candidate_data["eval"]["model"] = "mock/candidate"
        candidate_data["samples"][1]["scores"]["accuracy"]["value"] = 0.5
        candidate = self.write_log(candidate_data)
        report = compare.compare(
            compare.load_inspect_log(baseline, "baseline", "all", "accuracy")
            + compare.load_inspect_log(candidate, "candidate", "all", "accuracy"),
            "baseline",
            "candidate",
            0.05,
            2000,
            3,
        )
        self.assertEqual(report["results"][0]["paired_cases"], 2)
        self.assertLess(report["results"][0]["candidate_minus_baseline"], 0)
        self.assertEqual(report["source_runs"]["baseline"]["model"], "mock/model")
        self.assertEqual(report["source_runs"]["candidate"]["eval_id"], "run-1")

    def test_rejects_mismatched_task_version_across_runs(self):
        baseline_data = self.valid_log()
        candidate_data = self.valid_log()
        candidate_data["eval"]["task_version"] = 2
        baseline = self.write_log(baseline_data)
        candidate = self.write_log(candidate_data)
        rows = compare.load_inspect_log(baseline, "baseline", "all", "accuracy")
        rows += compare.load_inspect_log(candidate, "candidate", "all", "accuracy")
        with self.assertRaisesRegex(compare.DataError, "mismatched task_version"):
            compare.compare(rows, "baseline", "candidate", 0.05, 2000, 3)

    def test_accepts_distinct_eval_task_ids_for_same_stable_task(self):
        baseline_data = self.valid_log()
        candidate_data = self.valid_log()
        candidate_data["eval"]["eval_id"] = "run-2"
        candidate_data["eval"]["task_id"] = "task-2"
        candidate_data["eval"]["model"] = "mock/candidate"
        baseline = self.write_log(baseline_data)
        candidate = self.write_log(candidate_data)
        rows = compare.load_inspect_log(baseline, "baseline", "all", "accuracy")
        rows += compare.load_inspect_log(candidate, "candidate", "all", "accuracy")
        report = compare.compare(rows, "baseline", "candidate", 0.05, 2000, 3)
        self.assertEqual(report["results"][0]["paired_cases"], 2)
        self.assertEqual(report["source_runs"]["baseline"]["task_id"], "task-1")
        self.assertEqual(report["source_runs"]["candidate"]["task_id"], "task-2")

    def test_rejects_inconsistent_run_identity_for_one_variant(self):
        baseline = self.write_log(self.valid_log())
        second_baseline_data = self.valid_log()
        second_baseline_data["eval"]["eval_id"] = "second-baseline-run"
        second_baseline = self.write_log(second_baseline_data)
        candidate_data = self.valid_log()
        candidate_data["eval"]["model"] = "mock/candidate"
        candidate = self.write_log(candidate_data)
        rows = compare.load_inspect_log(baseline, "baseline", "all", "accuracy")
        rows += compare.load_inspect_log(second_baseline, "baseline", "all", "accuracy")
        rows += compare.load_inspect_log(candidate, "candidate", "all", "accuracy")
        with self.assertRaisesRegex(compare.DataError, "inconsistent source log metadata"):
            compare.compare(rows, "baseline", "candidate", 0.05, 2000, 3)

    def test_rejects_missing_declared_epoch(self):
        payload = self.valid_log()
        payload["eval"]["config"]["epochs"] = 2
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "every declared sample/epoch"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_rejects_duplicate_sample_epoch(self):
        payload = self.valid_log()
        payload["samples"].append(dict(payload["samples"][0]))
        path = self.write_log(payload)
        with self.assertRaisesRegex(compare.DataError, "duplicate sample/epoch"):
            compare.load_inspect_log(path, "baseline", "task", "accuracy")

    def test_unpaired_sample_ids_fail_comparison(self):
        baseline_data = self.valid_log()
        candidate_data = self.valid_log()
        candidate_data["samples"][1]["id"] = "different"
        candidate_data["eval"]["dataset"]["sample_ids"][1] = "different"
        baseline = self.write_log(baseline_data)
        candidate = self.write_log(candidate_data)
        rows = compare.load_inspect_log(baseline, "baseline", "all", "accuracy")
        rows += compare.load_inspect_log(candidate, "candidate", "all", "accuracy")
        with self.assertRaisesRegex(compare.DataError, "case IDs do not match"):
            compare.compare(rows, "baseline", "candidate", 0.05, 2000, 3)


if __name__ == "__main__":
    unittest.main()
