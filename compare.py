#!/usr/bin/env python3
"""Exploratory paired comparison for versioned LLM evaluation exports.

This prototype is descriptive research tooling, not a calibrated release gate.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


class DataError(ValueError):
    """Raised when input records cannot support the requested comparison."""


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    required = {"variant", "slice", "case_id", "repeat", "score"}

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DataError(f"cannot read {path}: {exc}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DataError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict) or set(row) != required:
            raise DataError(
                f"line {line_number}: each row must be an object with exactly "
                f"these keys: {', '.join(sorted(required))}"
            )

        for key in ("variant", "slice", "case_id"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise DataError(f"line {line_number}: {key} must be a non-empty string")
        if isinstance(row["repeat"], bool) or not isinstance(row["repeat"], (str, int)):
            raise DataError(f"line {line_number}: repeat must be a string or integer")
        score = row["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise DataError(f"line {line_number}: score must be a number")
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise DataError(f"line {line_number}: score must be finite and in [0, 1]")

        identity = (row["variant"], row["slice"], row["case_id"], str(row["repeat"]))
        if identity in seen:
            raise DataError(f"line {line_number}: duplicate variant/slice/case/repeat record")
        seen.add(identity)
        records.append(row)

    if not records:
        raise DataError("input contains no records")
    return records


def percentile(sorted_values: list[float], probability: float) -> float:
    """Return a linearly interpolated empirical percentile."""
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


# Widths at or below this are treated as no width at all. Resampled means of
# identical case differences can differ in float rounding only, so an exact
# equality test would miss a degenerate distribution.
DEGENERATE_WIDTH_TOLERANCE = 1e-12


def decide(low: float, high: float, margin: float) -> str:
    """Map an interval and a declared practical margin to a scoped decision."""
    if low >= -margin and high <= margin:
        return "WITHIN_DECLARED_BOUNDS"
    if high < -margin:
        return "MATERIAL_REGRESSION"
    if low > margin:
        return "MATERIAL_IMPROVEMENT"
    return "INCONCLUSIVE"


def compare(
    records: list[dict[str, Any]],
    baseline: str,
    candidate: str,
    margin: float,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    if baseline == candidate:
        raise DataError("baseline and candidate must be different variants")
    variants = {row["variant"] for row in records}
    unexpected = variants - {baseline, candidate}
    missing = {baseline, candidate} - variants
    if unexpected or missing:
        details = []
        if missing:
            details.append(f"missing variant(s): {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected variant(s): {', '.join(sorted(unexpected))}")
        raise DataError("; ".join(details))

    # First average repeats within each case. Resampling then occurs over cases,
    # preserving the baseline/candidate pairing without treating repeats as new cases.
    scores: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in records:
        scores[(row["slice"], row["variant"], row["case_id"])].append(float(row["score"]))

    source_fields = (
        "eval_id", "task_id", "task", "task_version", "dataset_name", "model", "epochs", "scorer"
    )
    source_runs: dict[str, dict[str, Any]] = {}
    for variant in sorted(variants):
        variant_rows = [row for row in records if row["variant"] == variant]
        metadata_rows = [
            {field: row[field] for field in source_fields if field in row}
            for row in variant_rows
            if any(field in row for field in source_fields)
        ]
        if metadata_rows:
            first_metadata = metadata_rows[0]
            if any(metadata != first_metadata for metadata in metadata_rows[1:]):
                raise DataError(f"variant {variant!r}: inconsistent source log metadata")
            source_runs[variant] = first_metadata

    if source_runs and set(source_runs) != {baseline, candidate}:
        raise DataError("source provenance must be present for both variants or neither")
    if source_runs:
        baseline_source = source_runs[baseline]
        candidate_source = source_runs[candidate]
        # Inspect assigns task_id per evaluation run; compare stable task/dataset
        # identity fields while retaining each distinct task_id in source provenance.
        identity_fields = ("task", "task_version", "dataset_name", "scorer")
        for field in identity_fields:
            if baseline_source.get(field) != candidate_source.get(field):
                raise DataError(f"Inspect source runs have mismatched {field}")

    slices = sorted({row["slice"] for row in records})
    results: list[dict[str, Any]] = []
    # Use the same deterministic random stream irrespective of slice order; each
    # slice still receives an independent stream derived from its stable name.
    for slice_name in slices:
        baseline_cases = {
            case_id for (name, variant, case_id) in scores
            if name == slice_name and variant == baseline
        }
        candidate_cases = {
            case_id for (name, variant, case_id) in scores
            if name == slice_name and variant == candidate
        }
        if baseline_cases != candidate_cases:
            raise DataError(f"slice {slice_name!r}: baseline and candidate case IDs do not match")
        case_ids = sorted(baseline_cases)
        if len(case_ids) < 2:
            raise DataError(f"slice {slice_name!r}: at least two paired cases are required")

        differences: list[float] = []
        baseline_means: list[float] = []
        candidate_means: list[float] = []
        baseline_repeats = 0
        candidate_repeats = 0
        for case_id in case_ids:
            baseline_values = scores[(slice_name, baseline, case_id)]
            candidate_values = scores[(slice_name, candidate, case_id)]
            if len(baseline_values) != len(candidate_values):
                raise DataError(
                    f"slice {slice_name!r}, case {case_id!r}: repeat counts differ "
                    f"({len(baseline_values)} vs {len(candidate_values)})"
                )
            baseline_repeats += len(baseline_values)
            candidate_repeats += len(candidate_values)
            baseline_mean = sum(baseline_values) / len(baseline_values)
            candidate_mean = sum(candidate_values) / len(candidate_values)
            baseline_means.append(baseline_mean)
            candidate_means.append(candidate_mean)
            differences.append(candidate_mean - baseline_mean)

        observed_delta = sum(differences) / len(differences)
        rng = random.Random(f"{seed}:{slice_name}")
        bootstrapped_deltas = []
        count = len(differences)
        for _ in range(bootstrap_samples):
            sample = [differences[rng.randrange(count)] for _ in range(count)]
            bootstrapped_deltas.append(sum(sample) / count)
        bootstrapped_deltas.sort()
        low = percentile(bootstrapped_deltas, 0.025)
        high = percentile(bootstrapped_deltas, 0.975)

        # A resample distribution with no width means every paired case difference
        # was identical. The decision still follows the observed data and the
        # declared margin, because that is the scoped claim the interval rule makes;
        # what it must never do is imply that an interval of no width is precision.
        # Suppressing a unanimous movement would hide a real signal, so the width is
        # flagged in the report instead of overriding the decision.
        degenerate = (high - low) <= DEGENERATE_WIDTH_TOLERANCE
        state = decide(low, high, margin)
        if degenerate:
            basis = (
                "every paired case difference was identical, so the interval has no "
                "width; the decision applies to these cases only and the width is not "
                "an estimate of precision"
            )
        else:
            basis = "interval compared against the declared practical margin"

        results.append({
            "slice": slice_name,
            "paired_cases": count,
            "baseline_repeats": baseline_repeats,
            "candidate_repeats": candidate_repeats,
            "baseline_mean": sum(baseline_means) / count,
            "candidate_mean": sum(candidate_means) / count,
            "candidate_minus_baseline": observed_delta,
            "bootstrap_95_percentile_interval": [low, high],
            "practical_margin": margin,
            "degenerate_interval": degenerate,
            "decision": state,
            "decision_basis": basis,
        })

    return {
        "analysis": "paired case-level mean difference; repeats averaged within case",
        "uncertainty": (
            "exploratory percentile bootstrap over paired cases only; repeated-run "
            "variation is not separately modeled"
        ),
        "bootstrap_method": "paired case-level percentile bootstrap",
        "baseline": baseline,
        "candidate": candidate,
        "source_runs": source_runs,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,

        "multiplicity": "not adjusted across slices; treat multiple slices as exploratory",
        "results": results,
        "limitations": [
            "Synthetic/demo or exported scores only; no model is executed by this tool.",
            "A small prototype bootstrap is not a calibrated inferential or release gate.",
            "WITHIN_DECLARED_BOUNDS applies only to these cases and this declared margin.",
            (
                "A slice whose resampled differences are all identical is marked "
                "degenerate_interval: its zero width is an absence of measured "
                "variation, not an estimate of precision."
            ),
            "The meaning, reliability, and provenance of input scores must be validated separately.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact human-readable summary of a comparison report."""
    lines = [
        "# Behavioral comparison",
        "",
        f"- **Baseline:** `{report['baseline']}`",
        f"- **Candidate:** `{report['candidate']}`",
        f"- **Analysis:** {report['analysis']}",
        f"- **Source runs:** `{json.dumps(report.get('source_runs', {}), sort_keys=True)}`",
        f"- **Uncertainty:** {report['uncertainty']}",
        f"- **Bootstrap draws:** {report['bootstrap_samples']}",
        f"- **Seed:** {report['seed']}",
        f"- **Multiplicity:** {report['multiplicity']}",
        "",
        "| Slice | Cases | Baseline mean | Candidate mean | Candidate − baseline | 95% interval | Margin | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in report["results"]:
        low, high = result["bootstrap_95_percentile_interval"]
        marker = " †" if result.get("degenerate_interval") else ""
        lines.append(
            f"| {result['slice']} | {result['paired_cases']} "
            f"| {result['baseline_mean']:.4f} | {result['candidate_mean']:.4f} "
            f"| {result['candidate_minus_baseline']:+.4f} "
            f"| [{low:+.4f}, {high:+.4f}] | ±{result['practical_margin']:.4f} "
            f"| **{result['decision']}**{marker} |"
        )
    degenerates = [result for result in report["results"] if result.get("degenerate_interval")]
    if degenerates:
        lines.extend(["", "† Degenerate resample distribution — every paired case difference was identical."])
        for result in degenerates:
            lines.append(f"- `{result['slice']}`: {result['decision_basis']}")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def load_inspect_log(
    path: Path,
    variant: str,
    slice_name: str,
    scorer: str,
) -> list[dict[str, Any]]:
    """Convert one Inspect AI JSON eval log into the comparison JSONL schema."""
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DataError(f"cannot read Inspect log {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"Inspect log {path}: invalid JSON: {exc.msg}") from exc

    if not isinstance(log, dict):
        raise DataError("Inspect log must be a JSON object")
    status = log.get("status")
    if status != "success":
        raise DataError(f"Inspect log status must be 'success', got {status!r}")
    spec = log.get("eval")
    if not isinstance(spec, dict):
        raise DataError("Inspect log is missing its eval header")
    dataset = spec.get("dataset")
    if not isinstance(dataset, dict):
        raise DataError("Inspect log is missing eval.dataset metadata")
    sample_ids = dataset.get("sample_ids")
    if not isinstance(sample_ids, list) or not sample_ids:
        raise DataError(
            "Inspect log must record explicit eval.dataset.sample_ids; "
            "automatic IDs cannot be verified as stable across runs"
        )
    if any(isinstance(item, bool) or not isinstance(item, (str, int)) for item in sample_ids):
        raise DataError("Inspect eval.dataset.sample_ids must contain only strings or integers")
    if any(not str(item).strip() for item in sample_ids):
        raise DataError("Inspect eval.dataset.sample_ids cannot contain empty values")
    if len({str(item) for item in sample_ids}) != len(sample_ids):
        raise DataError("Inspect eval.dataset.sample_ids must be unique")
    task_id = spec.get("task_id")
    if not isinstance(task_id, (str, int)) or isinstance(task_id, bool):
        raise DataError("Inspect log is missing a valid eval.task_id")
    model = spec.get("model")
    if not isinstance(model, str) or not model.strip():
        raise DataError("Inspect log is missing a valid eval.model")
    dataset_name = dataset.get("name")
    if dataset_name is not None and (not isinstance(dataset_name, str) or not dataset_name.strip()):
        raise DataError("Inspect eval.dataset.name must be a non-empty string when present")
    eval_id = spec.get("eval_id")
    if not isinstance(eval_id, str) or not eval_id.strip():
        raise DataError("Inspect log is missing a valid eval.eval_id")
    task = spec.get("task")
    if not isinstance(task, str) or not task.strip():
        raise DataError("Inspect log is missing a valid eval.task")
    task_version = spec.get("task_version")
    if isinstance(task_version, bool) or not isinstance(task_version, (str, int)):
        raise DataError("Inspect log is missing a valid eval.task_version")

    config = spec.get("config")
    expected_epochs = config.get("epochs") if isinstance(config, dict) else None
    if expected_epochs is not None and (
        isinstance(expected_epochs, bool) or not isinstance(expected_epochs, int) or expected_epochs < 1
    ):
        raise DataError("Inspect eval.config.epochs must be a positive integer when present")

    samples = log.get("samples")
    if not isinstance(samples, list) or not samples:
        raise DataError("Inspect log must contain a non-empty samples array")
    rows: list[dict[str, Any]] = []
    observed_samples: set[str] = set()
    observed_observations: set[tuple[str, int]] = set()
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise DataError(f"Inspect sample {index}: expected an object")
        sample_id = sample.get("id")
        epoch = sample.get("epoch", 1)
        if isinstance(sample_id, bool) or not isinstance(sample_id, (str, int)):
            raise DataError(f"Inspect sample {index}: id must be a string or integer")
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
            raise DataError(f"Inspect sample {index}: epoch must be a positive integer")
        if sample.get("error") is not None:
            raise DataError(f"Inspect sample {sample_id!r} epoch {epoch}: sample has an error")
        sample_id_key = str(sample_id)
        if sample_id_key not in {str(item) for item in sample_ids}:
            raise DataError(
                f"Inspect sample {sample_id!r}: id is absent from eval.dataset.sample_ids"
            )
        observed_samples.add(sample_id_key)
        observation = (sample_id_key, epoch)
        if observation in observed_observations:
            raise DataError(
                f"Inspect sample {sample_id!r} epoch {epoch}: duplicate sample/epoch"
            )
        observed_observations.add(observation)

        scores = sample.get("scores")
        if not isinstance(scores, dict) or scorer not in scores:
            raise DataError(
                f"Inspect sample {sample_id!r} epoch {epoch}: missing scorer {scorer!r}"
            )
        score_entry = scores[scorer]
        if not isinstance(score_entry, dict) or "value" not in score_entry:
            raise DataError(
                f"Inspect sample {sample_id!r} epoch {epoch}: scorer {scorer!r} "
                "must contain a value"
            )
        score = score_entry["value"]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise DataError(
                f"Inspect sample {sample_id!r} epoch {epoch}: scorer {scorer!r} "
                "value must be numeric"
            )
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise DataError(
                f"Inspect sample {sample_id!r} epoch {epoch}: scorer {scorer!r} "
                "value must be finite and in [0, 1]"
            )
        rows.append({
            "variant": variant,
            "slice": slice_name,
            "case_id": f"{task}:{task_version}:{dataset_name or ''}:{sample_id}",
            "repeat": epoch,
            "score": score,
            "eval_id": eval_id,
            "task_id": task_id,
            "task": task,
            "task_version": task_version,
            "dataset_name": dataset_name,
            "model": model,
            "epochs": expected_epochs,
            "scorer": scorer,
        })
    expected_samples = {str(item) for item in sample_ids}
    if observed_samples != expected_samples:
        missing = sorted(expected_samples - observed_samples)
        raise DataError(
            f"Inspect log samples do not cover eval.dataset.sample_ids; missing: {', '.join(missing)}"
        )
    if isinstance(expected_epochs, int):
        expected_observations = {
            (sample_id, epoch)
            for sample_id in expected_samples
            for epoch in range(1, expected_epochs + 1)
        }
        if observed_observations != expected_observations:
            missing = sorted(expected_observations - observed_observations)
            raise DataError(
                "Inspect log does not contain every declared sample/epoch; missing: "
                + ", ".join(f"{sample_id}@{epoch}" for sample_id, epoch in missing)
            )
    return rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", help="JSONL records to compare")
    parser.add_argument("--inspect-baseline", type=Path, help="Inspect AI JSON log for baseline")
    parser.add_argument("--inspect-candidate", type=Path, help="Inspect AI JSON log for candidate")
    parser.add_argument("--inspect-baseline-label", default="baseline", help="baseline variant label for Inspect logs")
    parser.add_argument("--inspect-candidate-label", default="candidate", help="candidate variant label for Inspect logs")
    parser.add_argument("--scorer", help="Inspect scorer name to import")
    parser.add_argument("--inspect-slice", default="all", help="shared slice label for imported Inspect logs")
    parser.add_argument("--baseline", help="baseline variant label for JSONL input")
    parser.add_argument("--candidate", help="candidate variant label for JSONL input")
    parser.add_argument(
        "--margin", required=True, type=float,
        help="predeclared practical equivalence margin on the [0, 1] score scale",
    )
    parser.add_argument("--bootstrap", type=int, default=10_000, help="bootstrap draws (default: 10000)")
    parser.add_argument("--seed", type=int, default=0, help="deterministic bootstrap seed")
    parser.add_argument(
        "--markdown", type=Path,
        help="also write a readable Markdown report to this path",
    )
    args = parser.parse_args(argv)
    inspect_inputs = (args.inspect_baseline is not None, args.inspect_candidate is not None)
    if any(inspect_inputs):
        if args.baseline is not None or args.candidate is not None:
            parser.error("use --inspect-baseline-label/--inspect-candidate-label with Inspect logs")
        if not all(inspect_inputs):
            parser.error("--inspect-baseline and --inspect-candidate must be used together")
        if args.input is not None:
            parser.error("use either positional JSONL input or Inspect log options, not both")
        if not args.scorer:
            parser.error("--scorer is required with Inspect log options")
    elif args.input is None:
        parser.error("provide positional JSONL input or both Inspect log options")
    elif not args.baseline or not args.candidate:
        parser.error("--baseline and --candidate are required with JSONL input")
    if not math.isfinite(args.margin) or not 0 < args.margin <= 1:
        parser.error("--margin must be finite and in (0, 1]")
    if args.bootstrap < 1_000:
        parser.error("--bootstrap must be at least 1000")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.inspect_baseline is not None:
            records = load_inspect_log(
                args.inspect_baseline, args.inspect_baseline_label, args.inspect_slice, args.scorer
            )
            records.extend(load_inspect_log(
                args.inspect_candidate, args.inspect_candidate_label, args.inspect_slice, args.scorer
            ))
        else:
            records = load_records(args.input)
            baseline_label = args.baseline
            candidate_label = args.candidate
        if args.inspect_baseline is not None:
            baseline_label = args.inspect_baseline_label
            candidate_label = args.inspect_candidate_label
        report = compare(
            records,
            baseline=baseline_label,
            candidate=candidate_label,
            margin=args.margin,
            bootstrap_samples=args.bootstrap,
            seed=args.seed,
        )
    except DataError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    if args.markdown is not None:
        try:
            args.markdown.write_text(render_markdown(report), encoding="utf-8")
        except OSError as exc:
            print(f"output error: cannot write {args.markdown}: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
