#!/usr/bin/env python3
"""Monte Carlo calibration harness for the exploratory comparison estimator.

This does not calibrate against real evaluation data. It measures how the shipped
interval and decision rules behave on synthetic data whose generating process is
known, so implementation errors and the cost of ignoring within-case correlation
become visible.

Two estimators are compared on identical simulated data:

* ``case_level`` — the shipped estimator: average repeats within a case, then
  resample cases (``compare.compare``).
* ``naive_repeat_level`` — a deliberately wrong baseline that resamples every
  repeat-pair observation as if repeats were independent cases.

Coverage is reported against two targets, because they are different claims:

* ``realized`` — the mean effect over the cases actually simulated in that draw
  (a claim about this exact suite).
* ``population`` — the generating mean effect, from which cases were drawn
  (a claim about the wider population the suite represents).

A suite-level decision is a ``realized`` claim; the interval is estimated from
case-level resampling, so whether it also holds its nominal rate for the
``population`` mean is a separate empirical question this harness measures.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from typing import Any

import compare

ESTIMATORS = ("case_level", "naive_repeat_level")
SCORERS = ("continuous", "binary")
DECISIONS = (
    "WITHIN_DECLARED_BOUNDS",
    "MATERIAL_REGRESSION",
    "MATERIAL_IMPROVEMENT",
    "INCONCLUSIVE",
)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def generate_pairs(
    rng: random.Random,
    cases: int,
    repeats: int,
    effect: float,
    effect_sd: float,
    noise_sd: float,
    ability: float = 0.5,
    scorer: str = "continuous",
) -> tuple[list[dict[str, Any]], float]:
    """Generate paired baseline/candidate scores with a known per-case effect.

    Each case has a stable ability shared by both variants, so the case effect
    cancels from the paired difference. ``effect_sd`` controls how much the
    candidate's improvement varies by case; that variation is shared by all
    repeats of a case, which is exactly the clustering the naive estimator
    ignores.

    ``scorer`` selects the observation model:

    * ``continuous`` — bounded continuous scores in ``[0, 1]`` (a graded or
      normalized rubric score), drawn around a per-case ability.
    * ``binary`` — pass/fail outcomes, where ability is the per-case success
      probability and the effect shifts that probability. Repeats of the same
      case then produce ties and lumpy ``-1/0/+1`` case differences, which is
      the regime where a percentile bootstrap is known to struggle.

    The returned truth is the mean *expected* candidate-minus-baseline
    difference over the simulated cases, so it is directly comparable across
    scorers and free of sampling noise within a repeat.
    """
    if scorer not in SCORERS:
        raise compare.DataError(f"unknown scorer {scorer!r}")

    rows: list[dict[str, Any]] = []
    effects: list[float] = []
    for index in range(cases):
        case_id = f"case-{index:03d}"
        case_ability = _clamp(ability + rng.gauss(0.0, 0.15))
        case_effect = effect + (rng.gauss(0.0, effect_sd) if effect_sd > 0 else 0.0)
        if scorer == "binary":
            baseline_probability = case_ability
            candidate_probability = _clamp(case_ability + case_effect)
            effects.append(candidate_probability - baseline_probability)
            for repeat in range(repeats):
                rows.append({
                    "variant": "baseline",
                    "slice": "all",
                    "case_id": case_id,
                    "repeat": repeat,
                    "score": 1.0 if rng.random() < baseline_probability else 0.0,
                })
                rows.append({
                    "variant": "candidate",
                    "slice": "all",
                    "case_id": case_id,
                    "repeat": repeat,
                    "score": 1.0 if rng.random() < candidate_probability else 0.0,
                })
            continue
        effects.append(case_effect)
        for repeat in range(repeats):
            baseline_score = _clamp(case_ability + rng.gauss(0.0, noise_sd))
            candidate_score = _clamp(case_ability + case_effect + rng.gauss(0.0, noise_sd))
            rows.append({
                "variant": "baseline",
                "slice": "all",
                "case_id": case_id,
                "repeat": repeat,
                "score": baseline_score,
            })
            rows.append({
                "variant": "candidate",
                "slice": "all",
                "case_id": case_id,
                "repeat": repeat,
                "score": candidate_score,
            })
    return rows, sum(effects) / len(effects)


def naive_repeat_level_estimator(
    rows: list[dict[str, Any]], baseline: str, candidate: str, bootstrap_samples: int, seed: int
) -> tuple[float, float, float]:
    """Bootstrap paired repeat-level differences, ignoring that repeats cluster by case."""
    pairs: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        key = (row["case_id"], str(row["repeat"]))
        observations = pairs.setdefault(key, {})
        if row["variant"] in observations:
            raise compare.DataError(f"case {key[0]!r} repeat {key[1]!r}: duplicate variant score")
        observations[row["variant"]] = float(row["score"])
    differences: list[float] = []
    for key in sorted(pairs):
        observations = pairs[key]
        if set(observations) != {baseline, candidate}:
            raise compare.DataError(f"case {key[0]!r}: expected one score per variant")
        differences.append(observations[candidate] - observations[baseline])
    if not differences:
        raise compare.DataError("no paired observations to resample")
    observed = sum(differences) / len(differences)
    rng = random.Random(f"{seed}:naive")
    count = len(differences)
    draws = sorted(
        sum(differences[rng.randrange(count)] for _ in range(count)) / count
        for _ in range(bootstrap_samples)
    )
    low = compare.percentile(draws, 0.025)
    high = compare.percentile(draws, 0.975)
    return observed, low, high


def _rate(events: int, total: int) -> float:
    return events / total if total else 0.0


def _rate_interval(events: int, total: int) -> list[float]:
    """Normal-approximation 95% Monte Carlo interval for a simulated rate."""
    if total == 0:
        return [0.0, 0.0]
    proportion = events / total
    half_width = 1.96 * math.sqrt(proportion * (1 - proportion) / total)
    return [max(0.0, proportion - half_width), min(1.0, proportion + half_width)]


def calibrate(
    cases: int,
    repeats: int,
    effect: float,
    effect_sd: float,
    noise_sd: float,
    margin: float,
    bootstrap_samples: int,
    simulations: int,
    seed: int,
    scorer: str = "continuous",
) -> dict[str, Any]:
    """Simulate datasets and record interval coverage and decision rates."""
    if simulations < 1:
        raise compare.DataError("simulations must be at least 1")
    if bootstrap_samples < 1:
        raise compare.DataError("bootstrap samples must be at least 1")
    if scorer not in SCORERS:
        raise compare.DataError(f"unknown scorer {scorer!r}")

    outcomes: dict[str, dict[str, Any]] = {
        name: {
            "covered_realized": 0,
            "covered_population": 0,
            "widths": [],
            "zero_width": 0,
            "decisions": dict.fromkeys(DECISIONS, 0),
        }
        for name in ESTIMATORS
    }
    rng = random.Random(f"{seed}:simulate")

    for simulation in range(simulations):
        rows, realized_truth = generate_pairs(
            rng,
            cases=cases,
            repeats=repeats,
            effect=effect,
            effect_sd=effect_sd,
            noise_sd=noise_sd,
            scorer=scorer,
        )
        case_report = compare.compare(
            rows, "baseline", "candidate", margin, bootstrap_samples, seed + simulation
        )
        case_result = case_report["results"][0]
        estimates = {
            "case_level": (
                case_result["candidate_minus_baseline"],
                *case_result["bootstrap_95_percentile_interval"],
            ),
            "naive_repeat_level": naive_repeat_level_estimator(
                rows, "baseline", "candidate", bootstrap_samples, seed + simulation
            ),
        }
        for name, (_observed, low, high) in estimates.items():
            record = outcomes[name]
            width = high - low
            record["widths"].append(width)
            # A zero-width interval asserts exact knowledge from resampled data;
            # with discrete scores it can appear even when the truth is uncertain.
            if width == 0.0:
                record["zero_width"] += 1
            if low <= realized_truth <= high:
                record["covered_realized"] += 1
            if low <= effect <= high:
                record["covered_population"] += 1
            record["decisions"][compare.decide(low, high, margin)] += 1

    summary: dict[str, Any] = {}
    for name, record in outcomes.items():
        covered_realized = record["covered_realized"]
        covered_population = record["covered_population"]
        summary[name] = {
            "coverage_of_realized_effect": _rate(covered_realized, simulations),
            "coverage_of_realized_95_monte_carlo_interval": _rate_interval(
                covered_realized, simulations
            ),
            "coverage_of_population_effect": _rate(covered_population, simulations),
            "coverage_of_population_95_monte_carlo_interval": _rate_interval(
                covered_population, simulations
            ),
            "mean_interval_width": sum(record["widths"]) / simulations,
            "zero_width_interval_rate": _rate(record["zero_width"], simulations),
            "decision_rates": {
                decision: _rate(record["decisions"][decision], simulations)
                for decision in DECISIONS
            },
        }

    return {
        "analysis": "Monte Carlo behavior of the shipped interval and decision rule",
        "estimands": {
            "realized": "mean candidate-minus-baseline difference over the cases in that draw",
            "population": "generating mean effect from which cases were drawn",
        },
        "parameters": {
            "scorer": scorer,
            "cases": cases,
            "repeats": repeats,
            "true_mean_effect": effect,
            "within_case_effect_sd": effect_sd,
            "observation_noise_sd": noise_sd,
            "practical_margin": margin,
            "bootstrap_samples": bootstrap_samples,
            "simulations": simulations,
            "seed": seed,
        },
        "estimators": summary,
        "limitations": [
            "Synthetic generator only; it does not represent any real evaluation score distribution.",
            (
                "Binary pass/fail outcomes only; multi-level and judge-graded ordinal scorers "
                "are not simulated."
                if scorer == "binary"
                else "Treats scores as bounded continuous quantities; real scorers may be binary or categorical."
            ),
            "Cases are drawn independently; real suites often contain near-duplicate and correlated cases.",
            "Scores are clipped to [0, 1], so effects near the boundary are attenuated.",
            "Reported rates carry Monte Carlo error shown by their own intervals.",
            "High coverage of the shipped estimator does not make it a calibrated release gate.",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=60, help="simulated cases per dataset")
    parser.add_argument("--repeats", type=int, default=3, help="repeats per case (nested)")
    parser.add_argument("--effect", type=float, default=0.1, help="true mean candidate improvement")
    parser.add_argument(
        "--effect-sd", type=float, default=0.05,
        help="between-case SD of the effect; 0 makes repeats independent within a case",
    )
    parser.add_argument("--noise-sd", type=float, default=0.1, help="per-observation noise SD")
    parser.add_argument(
        "--scorer",
        choices=SCORERS,
        default="continuous",
        help="observation model: continuous graded scores or binary pass/fail",
    )
    parser.add_argument("--margin", type=float, default=0.05, help="predeclared practical margin")
    parser.add_argument("--bootstrap", type=int, default=500, help="bootstrap draws per simulation")
    parser.add_argument("--simulations", type=int, default=200, help="simulated datasets")
    parser.add_argument("--seed", type=int, default=0, help="deterministic seed")
    args = parser.parse_args(argv)

    if args.cases < 2:
        parser.error("--cases must be at least 2")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.simulations < 1:
        parser.error("--simulations must be at least 1")
    if args.bootstrap < 1:
        parser.error("--bootstrap must be at least 1")
    if not math.isfinite(args.margin) or not 0 < args.margin <= 1:
        parser.error("--margin must be finite and in (0, 1]")
    if not math.isfinite(args.effect_sd) or args.effect_sd < 0:
        parser.error("--effect-sd must be finite and non-negative")
    if not math.isfinite(args.noise_sd) or args.noise_sd < 0:
        parser.error("--noise-sd must be finite and non-negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = calibrate(
            cases=args.cases,
            repeats=args.repeats,
            effect=args.effect,
            effect_sd=args.effect_sd,
            noise_sd=args.noise_sd,
            margin=args.margin,
            bootstrap_samples=args.bootstrap,
            simulations=args.simulations,
            seed=args.seed,
            scorer=args.scorer,
        )
    except compare.DataError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
