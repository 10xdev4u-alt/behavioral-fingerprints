# Behavioral Fingerprints

Paired comparison of behavior between two versions of the same evaluation suite.

> **Status: pre-alpha research.** The estimator, its calibration evidence, and the
> ingestion adapters are being built in the open. Nothing here is a release gate yet,
> and no result from this tool should be treated as a publishable claim about a model.

## What this is

A small, dependency-free tool for answering one narrow question:

> Given the same behavioral evaluation suite run against a baseline and a candidate,
> did the candidate's score change by more than a predeclared practical margin?

It keeps observations paired by case, averages repeated runs within a case, and
reports a case-level interval for candidate-minus-baseline, plus one scoped decision
per slice.

## What this is not

- Not a capability benchmark.
- Not a model fingerprint or a distance metric between models.
- Not a substitute for inspecting the cases that moved.

## Repository status

The staged product plan, research notes, and every open design question live in
[docs/product-plan.md](docs/product-plan.md). Work is tracked as issues and delivered
through reviewed pull requests; see the issue list for the current backlog.

## License

MIT. See [LICENSE](LICENSE).
