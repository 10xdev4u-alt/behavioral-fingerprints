# Behavioral Fingerprints: paired comparison spike

This repository is the first small, offline experiment from the research plan. It tests whether a thin analysis layer over existing evaluation outputs is a more defensible direction than building another evaluation runner. It is **not** a finished product, a model adapter, or a calibrated release gate.

## What it does

`compare.py` consumes synthetic or previously exported numeric scores, keeps baseline/candidate observations paired by behavioral slice and case ID, averages repeats within each case, and reports a case-level percentile-bootstrap interval for candidate-minus-baseline. It requires a practical margin chosen by the operator and emits one of four scoped decisions per slice. Slices are not multiplicity-adjusted. JSON is written to stdout; an optional Markdown summary can be saved with `--markdown PATH`.

The program executes no model, tools, shell payload, or network request. It has no dependencies beyond Python's standard library.

## Input

One JSON object per nonblank line, with exactly these keys:

```json
{"variant":"baseline","slice":"task","case_id":"order-01","repeat":0,"score":1.0}
```

Each `(variant, slice, case_id, repeat)` must be unique. Each slice must have the same case IDs in both variants, at least two cases, and equal repeat counts for paired cases. Scores must be finite numbers in `[0, 1]`. These constraints make missing or mismatched pairing visible rather than silently dropping cases.

## Run with JSONL scores

```sh
python3 compare.py sample.jsonl \
  --baseline baseline \
  --candidate candidate \
  --margin 0.05 \
  --bootstrap 10000 \
  --seed 0 \
  --markdown report.md
```

## Compare Inspect AI JSON logs

Export an Inspect log to plain JSON with the Inspect log commands/API, then provide one successful JSON log per variant:

```sh
python3 compare.py \
  --inspect-baseline sample-inspect-baseline.json \
  --inspect-candidate sample-inspect-candidate.json \
  --scorer accuracy \
  --margin 0.05 \
  --bootstrap 10000 \
  --seed 0 \
  --markdown inspect-report.md
```

The importer uses task name/version, dataset name and explicit sample IDs, eval ID/model/epoch configuration, each sample's `id` and `epoch`, and the selected scorer's numeric `value`. Case identity combines task name/version, dataset name, and sample ID; epoch is the repeat ID. (Inspect's `task_id` is a per-evaluation run ID, so the report preserves it as provenance but does not require equality across independently executed baseline/candidate runs.) Both logs must report matching stable task/dataset identity and complete samples; failed logs, sample errors, duplicate sample/epoch records, missing scores, and incomplete declared epochs are rejected. The JSON report retains source run IDs and model names, and mismatched task/dataset/scorer provenance is rejected. It does not parse Inspect's compressed `.eval` format; use Inspect's log conversion/export to JSON first. Model labels are supplied by the CLI rather than inferred from metadata.

The importer was tested end-to-end with two distinct Inspect AI `0.3.286` mock evaluation runs converted from `.eval` to JSON. Inspect AI is not a runtime dependency of this tool.

Both modes write machine-readable JSON to stdout; `--markdown PATH` additionally writes a readable summary. Exit code `0` means the report was produced; `2` means inputs/arguments or output path are invalid. A produced report can still be `INCONCLUSIVE` and must not be treated as a release approval.

## Validate the estimator on simulated data

`calibrate.py` simulates paired datasets whose generating process is known and measures whether the interval covers the truth at its nominal rate. It compares the shipped estimator (average repeats within a case, resample cases) with a deliberately wrong one that resamples every repeat as if repeats were independent cases.

```sh
python3 calibrate.py --cases 30 --repeats 6 --effect 0.05 \
  --effect-sd 0.20 --noise-sd 0.10 --margin 0.05 \
  --bootstrap 500 --simulations 400 --seed 11
```

Coverage is reported against two targets: the **realized** mean effect over the simulated cases, and the **population** mean the cases were drawn from. `--effect-sd` controls how much the effect varies between cases; when it is zero, repeats are independent and clustering is irrelevant.

Recorded result (standard library only; 400 simulations, 500 bootstrap draws, 30 cases, 6 repeats, nominal 95%):

| Scenario | Estimator | Population coverage [95% MC] | Mean interval width |
|---|---|---|---:|
| `--effect-sd 0` (control) | case-level (shipped) | 0.927 [0.902, 0.953] | 0.0398 |
| `--effect-sd 0` (control) | naive repeat-level | 0.922 [0.896, 0.949] | 0.0404 |
| `--effect-sd 0.20` (nested repeats) | case-level (shipped) | 0.950 [0.929, 0.971] | 0.1355 |
| `--effect-sd 0.20` (nested repeats) | naive repeat-level | 0.637 [0.590, 0.685] | 0.0665 |

What this supports: with correlated repeats, ignoring the case clustering halves the interval and destroys coverage (0.64 against a nominal 0.95), while averaging repeats within a case and resampling cases holds its nominal rate. What it does not support: any claim about real evaluators, binary or judge-scored outcomes, correlated or near-duplicate real cases, or calibration status as a release gate. In the control the shipped estimator sat slightly under nominal (0.927), which is ordinary small-sample percentile-bootstrap undercoverage, not a guarantee.

Run the dependency-free regression tests and syntax check with:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile compare.py calibrate.py tests/test_compare.py tests/test_inspect_import.py tests/test_calibrate.py
```

## Important limitations

- The case-level bootstrap does not estimate a separate within-case variance component; repeats are averaged first. Simulation shows this holds nominal coverage when repeats are correlated through between-case effect variation, but that is a synthetic result, not calibration on real evaluation data.
- It does not prove its input scores are reliable, model versions are correctly identified, or cases are independently sampled.
- The Markdown report is a presentation of the same exploratory JSON result; it does not add validation or a release decision.
- A small case count, weak score, subjective judge, missing provenance, multiple slices, or an unsuitable score scale can make the interval misleading.
- `WITHIN_DECLARED_BOUNDS` means only that this exploratory interval fell within this operator-supplied margin for these tested cases. It does not mean safe, clean, equivalent in every respect, or backdoor-free.

See the accompanying plan for the research gate, protocol, safety boundary, decision semantics, and proposed next tickets.
