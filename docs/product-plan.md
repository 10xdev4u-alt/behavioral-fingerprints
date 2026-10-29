# Behavioral Fingerprints for Model Updates

**Research and development blueprint**  
**Prepared:** 2026-10-29  
**Workspace:** research plan at `/tmp/behavioral-fingerprints-plan.md`; local prototype at `/tmp/behavioral-fingerprints`  
**Status:** research + tested exploratory implementation in a public GitHub repository; issues #1 and #2 are open. No commit, push, PR, or deployment has yet been created.

---

## 1. Executive summary

Build a reproducible, local-first evaluation tool that compares a *known baseline* and a *candidate version* of an LLM-backed system, then reports whether observed behavior changed beyond ordinary run-to-run noise—and where that change appears.

The core contribution is not a single scalar “model fingerprint,” a certification that weights are clean, or a detector for arbitrary hidden triggers. It is a **versioned experimental protocol** and an interpretable report that:

1. captures the exact system under test (weights/artifact, tokenizer/template, inference runtime, prompt, tool schema, sampling settings, and tool environment);
2. measures baseline variability by repeated runs;
3. compares baseline and candidate on paired, versioned behavioral slices;
4. distinguishes statistical evidence from practical impact;
5. tests whether the report can identify seeded, controlled changes without over-alerting on unchanged systems; and
6. makes no claim about prompts, triggers, or behaviors not exercised by the finite suite.

**Working name:** `ModelDiff` (placeholder; do a name/package search before adopting).

**One-line thesis:** *A model update should ship with a behavioral change report, not just a new version string and an aggregate benchmark score.*

---

## 2. What prompted this—and what it does not establish

ProjectDiscovery’s October 2026 article reports a proof-of-concept where a fine-tuned tool-using model behaves normally on clean prompts and requests a harmful tool action when a chosen trigger appears. Its important systems lesson is that clean-task performance does not establish that an agent’s behavior is unchanged or that its available actions are safely bounded. It is the authors’ reported demonstration, not an independently validated prevalence estimate. The article discusses abliterated weights, but **abliteration is not synonymous with a conditional backdoor**.

The useful project question is broader and defensive:

> When a team changes a model artifact or one layer of its serving stack, can it detect and characterize behavior changes that ordinary aggregate benchmarks or exact-output tests miss?

The experiment must not reproduce credential theft, run attacker payloads, or contact external sinks. Any conditional behavior in this project is a **synthetic, benign, deterministic test condition** that requests a harmless mock action against a local fake environment.

---

## 3. Research landscape and honest novelty claim

### Relevant existing work and tools

| Work/tool | What it contributes | What it does not establish for this project |
|---|---|---|
| [ProjectDiscovery: How abliterated models can get you pwned](https://projectdiscovery.io/research/how-abliterated-models-can-get-you-pwned) | Agent-level case motivating clean-vs-conditional behavior and tool-boundary testing. | Not a general prevalence study, an update-comparison protocol, or proof a finite detector can find unknown triggers. |
| [NeurIPS: Watch Out for Your Agents!](https://papers.nips.cc/paper_files/paper/2024/hash/b6e9d6f4f3428cd5f3f9e9bbae2cab10-Abstract-Conference.html) | Studies backdoors in agent trajectories, including intermediate behavior and triggers in user/environment context. | Does not make ordinary clean benchmarks a universal detector or define this project’s update attribution protocol. |
| [Anthropic: Sleeper Agents](https://www.anthropic.com/research/sleeper-agents-training-deceptive-llms-that-persist-through-safety-training) | Constructed backdoors can persist through tested safety-training procedures. | Does not show every backdoor survives every training method. |
| [Anthropic: Simple probes can catch sleeper agents](https://www.anthropic.com/research/probes-catch-sleeper-agents) | Activation probes performed well on the paper’s constructed settings. | The authors leave transfer to naturally occurring deceptive models open; this is not a general certification test. |
| [The Trigger in the Haystack](https://arxiv.org/html/2602.03085v1) | Proposes inference-time trigger discovery under a particular sleeper-agent setting. | Detection scope and assumptions are bounded; trigger scanning is not runtime containment. |
| [BackdoorLLM (NeurIPS 2025)](https://proceedings.neurips.cc/paper_files/paper/2025/hash/20ffc2b42c7de4a1960cfdadf305bbe2-Abstract-Datasets_and_Benchmarks_Track.html) | Standardized benchmark of attack modalities and mitigations. | Passing a finite benchmark cannot establish absence of unknown conditional behavior. |
| [AgentDojo](https://arxiv.org/abs/2406.13352) | Agent evaluation under untrusted tool-returned content; useful for environment-observation test channels. | Primarily prompt injection, not model-weight backdoors or update fingerprinting. |
| [Agent Security Bench](https://arxiv.org/abs/2410.02644) | Broad agent security evaluation, including tool use and memory. | Does not by itself isolate update effects and runtime noise as proposed here. |
| [Inspect AI](https://inspect.aisi.org.uk/) | MIT-licensed evaluation execution framework with tasks, solvers, scorers, tools, sandboxes, and local model support. Good candidate execution adapter. | It is not this project's calibrated change-decision methodology. Verify current API/version before implementation. |
| [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) | Broad benchmark suite and model adapters. Useful capability baseline. | Aggregate benchmark comparison is not a system fingerprint or factor attribution. |
| [promptfoo](https://www.promptfoo.dev/docs/intro/) | Convenient model/prompt matrices, regression tests, red-team tests, and CI ergonomics. | This plan’s added research emphasis is repeated-run noise calibration, controlled single-factor changes, behavioral slices, and explicit decision semantics. Compare directly; do not rebuild its generic features unnecessarily. |
| [garak](https://github.com/NVIDIA/garak) | Security probes for known classes of LLM vulnerabilities. | A vulnerability scanner is not a general update-drift measurement protocol. |
| [DeepEval](https://github.com/confident-ai/deepeval) | Pytest-like LLM and agent evaluation framework. | Evaluator metrics need calibration; LLM-as-judge alone is not reliable ground truth. |
| [CheckList](https://arxiv.org/html/2005.04118v1) | Behavioral testing via capability types, invariance, and directional expectations. | Not a turnkey model-update fingerprinting/release-gate system. |
| [MT-Bench / Chatbot Arena judge analysis](https://arxiv.org/abs/2306.05685) | Documents judge biases and limitations. | LLM-as-judge scores should not be treated as objective truth without validation. |
| [OpenAI Codex sandbox docs](https://learn.chatgpt.com/docs/sandboxing) | Concrete example of separating model proposals from filesystem/network authority. | A configured sandbox must be verified; a sandbox does not establish model purity. |
| User’s existing private [`hackproof-grpo`](https://github.com/10xdev4u-alt/hackproof-grpo) | Reports a single-model backdoor study and documents small probes, missing controls, scorer hazards, and context-gating observations. A valuable motivating case and source of lessons. | It is a different research question. Treat reported results as project-owned results pending replication; do not import unsafe payloads or imply independent validation. |
| User’s [`harnessprobe`](https://github.com/10xdev4u-alt/harnessprobe) | Measures decision-logic coverage/mutations in the code around LLM outputs. | This proposed tool measures behavior across model/system versions, not source-code coverage of the harness. Complement, do not duplicate. |

### Defensible novelty statement

> We investigate a reproducible, statistically calibrated method for comparing behavioral profiles of versioned LLM systems across controlled model and serving-stack changes, including benign conditional probes and agent tool behavior. We evaluate detection of seeded changes and false-alert rates under repeated baseline runs. We do not claim universal trigger discovery, model integrity certification, or proof of safety.

Before publishing or naming a novelty claim, do a fresh search of papers, repositories, and product docs for “LLM regression testing,” “behavioral fingerprint,” “model drift,” “agent evaluation CI,” and “paired repeated evaluation.” Report overlap honestly.

---

## 4. Product/research goals and non-goals

### Goals for v0.1

- Compare two pinned versions/configurations with the same versioned test suite.
- Capture text plus structured tool-call traces and mock environment state.
- Repeat tests enough to estimate stochastic variation.
- Produce per-slice, interpretable results with effect sizes and uncertainty.
- Catch seeded behavioral changes while maintaining a measured false-alert rate on identical systems.
- Keep evaluation offline/local by default; prohibit external network and real secrets in the included fixture pack.
- Export a machine-readable report and readable Markdown/HTML summary.

### Explicit non-goals

- Certifying a model as backdoor-free, safe, honest, or trustworthy.
- Searching the unbounded space of all possible triggers.
- Training or distributing a malicious/backdoored model, payload, credential collector, or exploit.
- Automatically fixing model behavior, fine-tuning away a backdoor, or deciding that a model is safe to deploy.
- Replacing Inspect, promptfoo, garak, AgentDojo, or harnessprobe.
- Supporting every model API, cloud provider, agent framework, or multimodal modality in v0.1.
- Using an LLM judge as sole source of truth.
- Enforcing an organization’s production release policy in the first prototype.

---

## 5. Threat model and safety envelope

### In scope

- An evaluator has a baseline and candidate artifact/configuration and can run both.
- Differences may come from weights, a benign fine-tune/adapter, quantization, inference backend, system prompt, tokenizer/chat template, tool schema, or tool implementation.
- Output can be stochastic; runtime versions and hardware may affect outputs.
- A conditional response may be introduced as a synthetic, harmless test behavior to validate that a test detects a seeded difference.
- Test inputs and tool observations are untrusted data; the runner must not allow them to escape the fixture sandbox.

### Out of scope / assumptions

- An adversary who knows the entire test suite can potentially evade it.
- A finite test set cannot cover every trigger, language, context, multi-turn distance, or tool trajectory.
- Model weights may be opaque and inaccessible; activation analysis is optional and not needed for v0.1.
- The tool reports observations, not causal certainty, unless only one experimental factor was changed and the controls support attribution.

### Safety controls (release blockers)

1. All default tools are inert mocks over an in-memory/local fixture store.
2. No shell tool, arbitrary Python execution, public network access, real credentials, or real external API integrations in the test harness.
3. The dummy sink stores only generated fixture markers locally and has no route to the network.
4. Test triggers and conditional actions are synthetic and benign; never include exfiltration payloads or instructions.
5. Any optional model adapter executes with no secrets in process/environment and documents isolation limits.
6. Include tests that fail if a fixture attempts DNS/network access or reads outside its temporary workspace, where feasible for supported platforms.
7. Reports redact configured sensitive fields and never persist environment variables or raw credentials.
8. Prominent report language: “No change detected in tested cases” is not “model is clean/safe.”

---

## 6. MVP definition

### Example system under test

A local fictional customer-support agent with synthetic orders and three harmless tools:

- `lookup_order(order_id)` — read-only lookup in fake data;
- `set_delivery_note(order_id, note)` — constrained write to fake state;
- `record_label(label)` — benign test sink that records an allowed synthetic label in the report.

The baseline and candidate see the same seeded task fixtures. The “conditional probe” is benign: a specific synthetic context asks the agent to record a different test label. It validates conditional-change measurement only; it does not represent or execute credential theft.

### Test families (initial, each with explicit expectations)

1. **Task behavior:** resolve a fake order status correctly.
2. **Tool correctness:** select expected mock tool, valid arguments, no unnecessary calls, correct final fake state.
3. **Policy behavior:** honor fixture policy; refuse a narrowly defined disallowed synthetic request; do not make a real-world safety claim.
4. **Format/contract:** valid JSON or structured output; parse success and schema conformance.
5. **Metamorphic invariance:** harmless paraphrase/order changes preserve the expected result.
6. **Directional pair:** a controlled change in one input fact causes the specified output/state change.
7. **Context channel:** same benign synthetic marker in user input, mock observation, and irrelevant fixture text; record whether results differ.
8. **Operational:** latency and token usage where adapters can measure them; present separately from behavioral equivalence.

The immutable core suite and exploratory suite must be separate. Version and hash each. Do not use a mutable online benchmark as the sole basis for longitudinal comparison.

### Minimum experiment matrix

| Run | Baseline | Candidate | Purpose |
|---|---|---|---|
| A | same pinned configuration | same pinned configuration | estimate ordinary stochastic/runtime noise and false-alert rate |
| B | reference | same weights, changed system prompt | prompt-layer sensitivity |
| C | reference | benign adapter or supervised fine-tune | weights/adaptation sensitivity |
| D | reference | quantized artifact | numerical/quantization sensitivity |
| E | reference | alternate inference backend | serving-layer sensitivity |
| F | reference | changed tool schema | interface-contract sensitivity |
| G | reference | seeded benign conditional behavior | verify conditional-probe detection |

Begin with A, B, F, G using a scripted deterministic backend; add local-model adapters once the protocol is stable. Do not confound variables in primary experiments. Later, test selected two-factor interactions.

---

## 7. Measurement protocol and statistical decision rules

### The estimand comes first

The object being compared is a **versioned LLM system**, not weights in isolation. For a named test suite and execution protocol, estimate the difference in observed outcomes between a pinned baseline and candidate. If more than one configuration factor changes, report a system-level difference; do not attribute the cause to weights.

For each case and behavioral slice, define the primary outcome before running: e.g. task success, valid tool action, expected fake-world end state, or a specified relation between a pair of prompts. Keep operational outcomes (latency/tokens) separate. The unit of analysis is the test case; repeats are nested observations, not independent new cases.

### Interpretable behavioral profile

For each slice, report:

- task success / failure and outcome category;
- tool choice, argument validity, unnecessary calls, and fake-world end state;
- structured-output contract validity;
- policy outcome on the explicitly synthetic policy cases;
- metamorphic-pair relation pass/fail;
- response-category or score distributions only where scoring is validated;
- latency and token use as separate operational measures;
- uncertainty intervals, denominators, missing/invalid runs, and artifact provenance.

Do not collapse this into a single “fingerprint score.” Hashes identify artifacts and test inputs; they are not behavioral evidence. Exact text diff is a diagnostic, not the primary equivalence test for stochastic natural-language output.

### Experimental protocol

1. Freeze the suite, scorer, primary outcomes, practical margins, exclusions, and analysis before the confirmatory run. Keep an immutable core suite separate from any exploratory/held-out probes.
2. Verify baseline and candidate identity/configuration. Capture unknown provenance as `unknown`; do not infer artifact identity from a friendly model name.
3. Reset fake-world state for every attempt. Pair runs on case and fixture seed; use common random seeds only when both runtimes give them a meaningful shared interpretation.
4. Randomize or counterbalance baseline/candidate execution order to avoid order, cache, warmup, or host-load effects. Record failures and retries; do not silently drop them.
5. Run repeated same-configuration baseline trials to estimate run-to-run variability, then paired candidate trials. Stochastic repeats remain clustered by case.
6. Change one factor at a time for attribution experiments. Label any multi-factor comparison as a system bundle; test interactions only after main effects are understood.
7. Preserve raw observations locally with explicit retention/redaction settings; provide a normalized deterministic report for the same inputs.

### Pilot sizing and inference

The earlier 50–100 cases × 5–10 repeats is **only a feasibility pilot**, not evidence of adequate power or a low false-alert rate. Rare false alerts cannot be estimated precisely from a small pilot. Use a pilot to estimate variance, then calculate the sample size needed for predeclared practical margins and confidence/power targets. If the required run budget is infeasible, narrow the claim or report `INCONCLUSIVE`; do not weaken the threshold after seeing results.

Use paired effect estimates and confidence intervals. For nested repeats, resample/cluster at the test-case level (or justify another model). For paired binary outcomes, McNemar-style analysis can be appropriate when its assumptions fit. Correct confirmatory multi-slice testing (e.g. Holm); label exploratory analyses explicitly. Validate the chosen interval/test implementation on simulated data with known null/effect distributions, including small denominators and missing runs.

Do not use “p > 0.05” as evidence of no change. To say behavior is **within declared bounds**, use a predeclared equivalence/non-inferiority design with an interval wholly inside the practical margin, and sufficient power. If a valid equivalence test is not implemented or its assumptions fail, result is `INCONCLUSIVE`, even if no difference test is significant.

LLM-as-judge is not ground truth. Prefer deterministic scorers for synthetic tasks. If a judge is needed, preregister rubric and prompt, blind model/version and response order, audit a human-labeled sample, measure judge disagreement, and report the judge as a limitation.

### Result states

- **WITHIN DECLARED BOUNDS:** all primary outcomes meet the preregistered equivalence criteria; this applies only to tested cases/configuration.
- **CHANGE DETECTED:** a primary outcome exceeds its predeclared practical threshold with the stated uncertainty and multiplicity treatment.
- **INCONCLUSIVE:** confidence/equivalence interval crosses both meaningful-change and acceptable bounds; runs/power are insufficient; or design assumptions fail.
- **INVALID RUN:** provenance/configuration mismatch, fixture/scorer failure, or execution corruption prevents interpretation.

A threshold may be a user policy, not a universal safe default. Never call any state “safe,” “clean,” “unpoisoned,” or “backdoor-free.”

---

## 8. Architecture choices and experimental data model

### Alternatives considered

1. **Build a new full evaluation runner.** Rejected for v0.1: duplicates model execution, tool integration, and reporting features before there is evidence those are the research contribution.
2. **Wrap one existing framework end-to-end (promptfoo or Inspect AI).** Not selected as the foundation yet: risks inheriting a framework’s run semantics and making the statistical protocol hard to test independently.
3. **Own a small protocol/core plus a scripted runner; add an adapter only when a second real runner is needed.** Recommended. It gives a no-GPU deterministic executable experiment and keeps the research contribution in pairing, provenance, analysis, and report semantics. The seam stays hypothetical until a second adapter proves it is real.

Run a small comparison spike against promptfoo and Inspect before locking this choice. If either can express the required paired repetitions, provenance, and result semantics cleanly, prefer extending it over maintaining a parallel runner.

### Domain language

- **System version:** a precisely recorded model plus serving configuration under test; includes weights, tokenizer/template, runtime, prompt, tool schema, and tools as applicable.
- **Behavioral profile:** per-slice outcomes and uncertainty observed for a system version on a named suite/protocol. Not an identity hash or safety certificate.
- **Probe case:** one input/trajectory with a predeclared expected outcome or relation.
- **Slice:** a named family of probe cases measuring one behavior.
- **Repeat:** another execution of the same case/configuration; not a new independent case.
- **Practical margin:** the largest change considered negligible for a specific primary outcome, chosen before confirmatory data.
- **Benign conditional probe:** a synthetic context pair with a harmless expected difference, used to validate measurement sensitivity.
- **System-level change:** a measured difference where multiple update factors changed or causal attribution is otherwise unsupported.

### Minimal conceptual modules

1. **Protocol** — validated manifest, suite, frozen analysis plan, and hashes.
2. **Execution** — first a deterministic scripted adapter and local fake tools; model adapters remain optional.
3. **Recorder** — one normalized attempt record with version, case, repeat, trace, result, and safe errors.
4. **Comparator** — paired case/slice summaries, uncertainty, practical margins, and result state.
5. **Report** — machine-readable evidence plus readable per-slice explanation and limitations.
6. **CLI** — run, compare, and render only after the vertical slice is proven useful; CI gate is later.

Keep the public interface narrow. Do not split these into packages or create generic plugin infrastructure until a second concrete use case requires it.

### Minimum provenance

Record run/suite/scorer version and hashes; baseline/candidate labels and model artifact IDs/hashes if exposed; tokenizer/template/runtime and versions; system-prompt/tool-schema hashes (not secret values); hardware/precision when available; sampling settings, seed, limits/timeouts; fake-world starting state hash; case/repeat IDs; raw or redacted output and tool trace; status/errors. Treat timestamps as provenance, not semantic report-diff fields.

### Candidate file shape (illustrative, not committed)

```text
modeldiff/
  README.md
  pyproject.toml
  src/modeldiff/       # keep modules cohesive until seams are justified
  suites/core-v1/      # immutable cases, expectations, suite manifest
  schemas/             # versioned run/result/report contracts
  tests/               # observable behavior + statistical simulation
  docs/                # protocol, threat model, limitations, research record
```

Avoid pre-allocating a module for each future idea. No dashboard, activation hooks, hosted service, or general-purpose model registry in the MVP.

---

## 9. Decision gates and development phases

This is a research effort, so phases decide whether to continue—not just what to build next. Each phase ends with an artifact a reviewer can inspect and a go/no-go question.

### Gate 0 — Does a real gap remain? (research, 1–2 days)

**Work:** compare the exact user problem against current promptfoo, Inspect AI, lm-eval, garak, and relevant agent/model-backdoor evaluation papers using primary docs/repositories/papers. Build a capability matrix against paired repeats, variance calibration, slice-level comparisons, provenance, equivalence decisions, and tool-trace outcomes. Record versions/access date and one reproducible sample flow for the closest incumbent.

**Deliverable:** short cited comparison and a narrowed claim, or a stop/pivot recommendation.

**Proceed only if:** at least one important requirement is not already supported well, and there is a concrete user/research workflow that benefits. If not, contribute a test suite/plugin to an incumbent or stop; do not ship a wrapper just to have a project.

### Phase 1 — Research contract (1 day)

**Work:** fix the user/job, system-version definition, safety envelope, and three falsifiable questions. Choose one primary outcome and one practical margin for the first demonstration. Draft analysis plan, exclusions, randomization, sample-size estimation method, and result-state wording before collecting confirmatory results.

**Deliverable:** preregistration/protocol memo with unresolved assumptions listed.

**Proceed only if:** the outcomes have an independent ground truth and a finite testable scope. If not, prototype the scorer/question first, not the product.

### Phase 2 — One runnable tracer bullet (1–3 days)

**Work:** scripted mock agent, 5–10 fictional tasks, paired clean and benign-conditional cases, fake tool state, one command to compare baseline/candidate, one evidence report. No GPU, remote model API, secrets, shell, or external network.

**Deliverable:** reproducible run artifacts showing input → tool request → mock result → scored outcome; one harmless known change while aggregate task success stays stable.

**Proceed only if:** a person can understand what changed from the per-case evidence and repeat the run. If a plain fixture test would answer the question just as well, narrow/stop the fingerprinting claim.

### Phase 3 — Calibrate the decision rule (1–2 weeks, driven by sample-size needs)

**Work:** repeated same-config null runs, paired candidate runs, simulated null/alternative calibration, cluster-aware uncertainty, equivalence testing for the primary outcome, and a predeclared alert threshold. Report sample-size rationale and uncertainty; do not claim low false-alert rates from underpowered pilots.

**Deliverable:** calibration report containing false-alert estimate with interval, sensitivity to seeded benign changes, power/sample-size rationale, and known failure cases.

**Proceed only if:** the method separates the predeclared change from baseline variability at the agreed operating point, or the null result leads to a narrower claim.

### Phase 4 — Agent trace/channel study (conditional, 1–3 weeks)

**Work:** tool actions and fake-world effects; run benign paired probes through user input and mock observations. Add only a second runner/framework if the comparison spike justified it. Keep action request distinct from attempted and successful effect.

**Deliverable:** controlled report showing which channels/slices detect seeded changes and where the evaluator misses them.

**Proceed only if:** added trace-level outcomes provide information beyond text/per-case diffs and can be scored reliably.

### Phase 5 — One local-model case study (conditional, compute/licence permitting)

**Work:** select one locally runnable, appropriately licensed model after fresh review. Change exactly one low-risk factor (e.g. prompt version or quantization), pin runtime and tokenizer/template, run without secrets or external network. No backdoor training.

**Deliverable:** rerunnable case study with hardware/runtime caveats, success/failure, raw safe traces, and limitations.

**Proceed only if:** the protocol works beyond the scripted adapter and another operator can reproduce it at a documented cost.

### Phase 6 — Release workflow (only after validation)

**Work:** stable local CLI and JSON/Markdown output; optional CI gate only if thresholds have validated semantics and inconclusive results fail/require an explicit policy. Document raw trace privacy/retention.

**Deliverable:** sample project can compare a candidate update offline and archive a reproducible report.

**No automatic publication, hosted dashboard, model registry, or universal safety gate is in v0.1.**

---

## 10. Dependency-linked tracer-bullet backlog

Do not optimize for “thousands of PRs.” Use the smallest reviewable change that leaves a verifiable state; split work when independent acceptance/review is valuable. The graph below is a candidate work map, not permission to open issues or PRs. Each item is a vertical outcome, and the later items are conditional on decision gates.

### Research/decision tickets (no code unless needed to answer)

**D1 — Compare the closest existing workflows**  
**Blocked by:** none.  
**Delivers:** cited, versioned matrix for promptfoo, Inspect AI, and the closest research tooling.  
**Accept when:** one example evaluation is run/reconstructed for the strongest incumbent; matrix explicitly covers repeats, pairing, uncertainty/equivalence, traces, provenance, offline mode; conclude build / extend / stop.

**D2 — Lock the measurement claim and safe fixture**  
**Blocked by:** D1.  
**Delivers:** one target user/workflow, glossary, threat model, fixture concept, explicit out-of-scope, and one primary measurable behavior.  
**Accept when:** every metric has a ground-truth source; “fingerprint” is not presented as integrity/safety certification; conditional effect is harmless and local.

**D3 — Preregister pilot and decision semantics**  
**Blocked by:** D2.  
**Delivers:** analysis note with primary estimand/outcome, practical margin, null/alternative, repeat/randomization method, sample-size/power approach, multiplicity, missing-run treatment, and PASS/CHANGE/INCONCLUSIVE/INVALID definitions.  
**Accept when:** a reviewer can determine which result would falsify the central claim before seeing the confirmatory run.

### Build tracer bullets

**B1 — Scripted end-to-end comparison**  
**Blocked by:** D2.  
**Delivers:** a local command compares baseline/candidate on a few fictional tasks, resets mock state, records tool trace, and renders a per-case report.  
**Accept when:** a clean rerun is semantically identical; no model download, network, shell, or secret access; seeded benign change is visible without relying on prose-only scoring.

**B2 — Core suite and independently checkable scorers**  
**Blocked by:** B1.  
**Delivers:** versioned task, tool-contract, metamorphic, directional, and benign conditional pairs with explicit expectations.  
**Accept when:** each case has a stable ID, slice, expected relation/outcome, fixture hash, and at least one test showing a deliberately wrong result fails.

**B3 — Provenance and paired repeat runs**  
**Blocked by:** B1, D3.  
**Delivers:** repeated same-config and baseline/candidate attempts paired by case/fixture; captures actual system version/config and run errors.  
**Accept when:** order is randomized/counterbalanced; reset verified; missing runs remain visible; repeats are not counted as independent cases.

**B4 — Statistical null/effect simulator and calibration**  
**Blocked by:** B3.  
**Delivers:** tested analysis on simulated null, seeded practical shift, nested repeats, and missingness.  
**Accept when:** tests demonstrate interval/decision behavior for known generated distributions; equivalence is distinguished from failure to reject; pilot uncertainty/sample-size is explicit.

**B5 — Per-slice evidence report and decision states**  
**Blocked by:** B2, B4.  
**Delivers:** machine-readable and Markdown report with per-slice effects, intervals, denominators, primary/exploratory labels, provenance, and limitations.  
**Accept when:** result can be INCONCLUSIVE; no aggregate score masks a primary regression; report text never calls the model safe/clean.

**B6 — Tool-effect and observation-channel study**  
**Blocked by:** B5.  
**Delivers:** same benign test condition introduced via user input and mock observation; track requested, denied, and successful mock effects.  
**Accept when:** external effects are impossible; trace outcome is independently checkable; added channel data gives measurable information beyond text diff or is explicitly dropped.

### Conditional extension tickets

**X1 — Runner/framework comparison**  
**Blocked by:** D1, B5.  **Delivers:** written adapter cost/feature comparison against the closest runner.  **Accept when:** second concrete runner need exists and minimal seam remains smaller than framework duplication; otherwise do not build an adapter.

**X2 — Local model case study**  
**Blocked by:** B5, D3, licence/resource review.  **Delivers:** one pinned local model and one-factor, benign update comparison.  **Accept when:** offline, secret-free, reproducible run and a documented resource budget; no adversarial/backdoor training.

**X3 — CI gate**  
**Blocked by:** B5 and successful calibration in B4.  **Delivers:** opt-in CI status for configured policy.  **Accept when:** null behavior is calibrated, INCONCLUSIVE policy explicit, artifacts safe to retain, and a sample CI run demonstrates correct exit codes.

**X4 — Independent replication and public claims**  
**Blocked by:** B5 plus any claimed X2 study.  **Delivers:** clean-environment rerun and claims audit.  **Accept when:** report can be regenerated from pinned inputs and failures/limitations are included; novelty language is limited to demonstrated evidence.

### Dependency graph

```text
D1 -> D2 -> D3
       |     |
       v     v
       B1 -> B2
        |     |
        +-> B3 -> B4
                             B5 <- B2, B4
                |                | +-> X1 (with D1)
                +---> B6
                +---> X2 (with D3/licence review)
                +---> X3 (only after B4 calibration)
                +---> X4
```

Only the unblocked frontier should be started. A stopped/pivoted decision is a valid completion; no ticket count target overrides evidence.

---

## 11. Research questions and falsifiers

### RQ1 — Is the change decision calibrated?
Can a paired, repeated, per-slice comparison distinguish a predeclared practical shift from unchanged-system variability at an agreed false-alert operating point?

- **Evidence for:** null replications remain within equivalence bounds at a rate consistent with uncertainty; seeded shifts are detected with adequate power.
- **Falsifier:** null systems frequently trigger change or seeded changes are missed at the preregistered design.
- **Fallback:** report raw paired evidence only; drop the release-gate claim.

### RQ2 — What can be attributed?
Does changing exactly one declared factor produce a stable signature, and can the method avoid attributing a bundled change to weights?

- **Evidence for:** factor-isolated runs can be described reliably; interactions are separately tested.
- **Falsifier:** signatures overlap or runtime noise dominates. Then claim only system-level comparison, not factor attribution.

### RQ3 — Do slices expose changes hidden by aggregate scores?
Can benign paired conditional cases reveal a seeded conditional difference while ordinary task success remains stable, and do observation-channel probes add information?

- **Evidence for:** preregistered per-slice outcome identifies the seeded change; held-out cases avoid trivial lexical artifacts.
- **Falsifier:** only literal training artifacts are detected, or per-case baseline testing already exposes all relevant differences without the proposed profile.

Every hypothesis needs an outcome, threshold, sample-size rationale, and stop rule written before confirmatory collection. Publish null findings and cases where the closest incumbent is sufficient.

---

## 12. Verification and evidence quality gates

### Per tracer bullet

- Prove the user-visible path, not only schema/type correctness: run the command on the stated fixture and inspect its result artifact.
- Keep one before/after known pair and one known-negative pair, each with independent expected outcomes.
- Verify resets, pairing, stable case ordering, and safe error/missing-repeat behavior.
- Statistical changes require simulated known-null and known-effect checks before interpreting model results.

### Before a public v0.1 claim

- Unit/property tests for manifest validation, fixture reset, pairing, aggregation, uncertainty, and result states.
- Integration test demonstrates input → tool request → mock result/state → scorer → report.
- Simulation study checks interval coverage/decision behavior approximately under declared assumptions; include nested data and missing attempts.
- Sensitivity analysis on thresholds, repeats, suite size, and counterbalanced execution order.
- Tests ensure case order and report generation are deterministic; missing evidence can never silently become WITHIN BOUNDS.
- Built-in runner has no shell/network/secret-reading path; attempted forbidden actions fail closed and are observable.
- Reproducibility: a fresh run produces a semantically equal normalized report; explain hardware/runtime variability for real models.
- Blinded/human audit for any subjective scorer; publish disagreement and exclusions.

### Publish as measured evidence

Report false-alert estimate **with interval and denominator**, seeded-change sensitivity **with interval and denominator**, practical effect and margins, required sample-size rationale, run-to-run variance, invalid/missing attempts, compute/runtime cost, and reproducibility result. Do not convert a small number of null runs into a strong “low false-positive rate” claim.

---

## 13. Risks, unknowns, and mitigation

| Risk | Why it matters | Mitigation |
|---|---|---|
| Existing tools already cover the apparent feature | Could be a thin wrapper with no contribution. | Compare promptfoo/Inspect/etc. early; pivot to protocol/research question or stop if not distinct. |
| “Fingerprint” implies identity/security certainty | A score/hash can create false assurance. | Use interpretable vector; call it a behavioral profile; explicit limitations. |
| Test-suite overfitting | Known probes can be memorized or gamed. | Immutable core + separately held-out, versioned set; disclose finite coverage. |
| Stochastic noise | False alarms or missed changes. | Repeats, same-case pairing, pilot power, uncertainty, inconclusive state. |
| Confounding | Cannot tell model weights from template/runtime changes. | One-factor primary comparisons; capture full provenance; label interactions. |
| Judge bias | LLM evaluator may favor style/verbosity or one version. | Deterministic synthetic scoring first; blinded judge validation and human sample audit only when necessary. |
| Model license / compute burden | Could stall development or make replication inaccessible. | Scripted MVP first; license review and hardware budget gate before local model. |
| Unsafe expansion into backdoor training | Could cause harm and swamp original contribution. | Synthetic benign conditional probes only; no malicious weights/payloads in the project. |
| Private prior results treated as ground truth | Overclaiming weak evidence undermines credibility. | Cite as project context; independently replicate safe results or clearly label as reported. |
| Data/privacy exposure | Prompts/traces may contain secrets. | Local-first, no credentials, redaction, opt-in raw trace retention. |

---

## 14. Decisions, assumptions, and skill-derived process

### Original recommended defaults (superseded by the development start recorded in §18)

1. **Project/repo:** the original plan was drafted before a local repository existed. The plan remains in `/tmp`; §18 now records a local `main` repository. Do not create or modify a GitHub repo, issue, PR, commit, or push without explicit authorization.
2. **Name:** keep `ModelDiff` as a placeholder; check collision and communicate the product’s limited claim before branding.
3. **Build order:** research gate → preregistered protocol → scripted vertical slice → statistics → optional local model → optional CI.
4. **Language:** Python is a hypothesis for the eventual implementation, not a commitment; decide after the runner comparison and package/license check.
5. **Execution:** scripted local adapter and fake tools first. Network and GPU not required for the first demonstration.
6. **Dependencies:** no model/framework/statistics dependencies until a spike establishes they are needed and license/API fit is checked.
7. **Security:** harmless synthetic conditional behavior only; no backdoor training, malicious payload, real credential, shell tool, or external sink.
8. **Delivery:** target useful tracer bullets, not thousands of PRs. A ticket is accepted only with an independently verifiable outcome and blockers; split/merge tickets based on reviewability, not count.
9. **Gate:** if existing tooling already meets the narrow workflow, integrate or stop rather than building a redundant product.

### Domain terms to preserve

Use the glossary in §8 consistently. In particular, say **behavioral profile** for measured outcomes, **system version** for the entire configured stack, **practical margin** for the user-defined tolerance, and **WITHIN DECLARED BOUNDS** only after equivalence evidence. Avoid calling an artifact a fingerprint if that implies identity or trustworthiness.

### Planning practices applied from the cloned skills

- **Matt Pocock `research` / `to-spec`:** prioritize primary sources, cite claims, state user-visible problem/scope, decisions, tests, and explicit non-goals.
- **Matt Pocock `to-tickets` / `wayfinder`:** separate decision questions from build tickets; work only the unblocked frontier; use tracer-bullet deliverables with explicit blockers; don’t pre-plan fog that decisions may invalidate. This plan proposes tickets only and does not publish them.
- **Matt Pocock `codebase-design` / `domain-modeling`:** define domain terms; keep the public seam small; do not invent a generic adapter/plugin interface before a second implementation is justified.
- **Matt Pocock `prototype` / `tdd`:** answer the uncertainty with one cheap runnable vertical slice; define observable seams and independent expected outcomes before broad implementation.
- **Poteto planning/review/testing principles:** each phase must end with direct evidence; use explicit stop conditions; inspect design from competing approaches; challenge assumptions, scope, dependencies, and verification.
- **Sequence-verifiable-units / prove-it-works / subtract-before-you-add:** order each unit so it leaves a runnable/checkable artifact; remove unsupported scope; verify the actual output rather than trusting a report about it.

I cloned six skill-bearing repositories under `/tmp/behavioral-fingerprint-skills` and inventoried 151 `SKILL.md` files. I read the task-relevant research, planning, ticketing, design, prototype, TDD, adversarial-review, testing, quality, and verification guidance. Irrelevant UI/framework/deploy skills were not applied mechanically. Repository snapshots are recorded in their local Git metadata; no skill scripts were executed.

---

## 15. Immediate next session: 30-minute decision sprint

**Minute 0–5 — name the destination:** decide if the outcome is (a) a research protocol, (b) an open-source local tool, or (c) an extension to an incumbent. Default: prove the protocol before productizing.

**Minute 5–12 — close Gate 0:** reproduce the closest promptfoo/Inspect comparison from current docs/source. Write the exact unsupported workflow, if any. If there is no concrete gap, stop/pivot.

**Minute 12–18 — freeze one question:** choose one primary behavior, one outcome with ground truth, one practical margin, and one harmless conditional pair. Leave other metric families exploratory.

**Minute 18–25 — define experiment:** describe same-config null runs, randomized paired baseline/candidate runs, repeats nested by case, missing-run handling, and how sample size will be selected. No confirmatory results before this is written.

**Minute 25–30 — pick B1 acceptance:** specify the one command, inputs, and report artifact that prove the scripted vertical slice. Don’t start the full 6-week plan or create a repo until the vertical slice’s value is demonstrated.

This next session is meant to make decisions; the build backlog starts only after the evidence gate.

---

## 16. References

- ProjectDiscovery, [How abliterated models can get you pwned](https://projectdiscovery.io/research/how-abliterated-models-can-get-you-pwned), 2026-10-06.
- NeurIPS 2024, [Watch Out for Your Agents!](https://papers.nips.cc/paper_files/paper/2024/hash/b6e9d6f4f3428cd5f3f9e9bbae2cab10-Abstract-Conference.html).
- Anthropic, [Sleeper Agents: Training Deceptive LLMs that Persist Through Safety Training](https://www.anthropic.com/research/sleeper-agents-training-deceptive-llms-that-persist-through-safety-training).
- Anthropic, [Simple probes can catch sleeper agents](https://www.anthropic.com/research/probes-catch-sleeper-agents).
- UK AISI / Anthropic / Alan Turing Institute, [Poisoning Attacks on LLMs Require a Near-constant Number of Poison Samples](https://arxiv.org/abs/2510.07192).
- Microsoft, [The Trigger in the Haystack](https://arxiv.org/html/2602.03085v1).
- NeurIPS 2025, [BackdoorLLM](https://proceedings.neurips.cc/paper_files/paper/2025/hash/20ffc2b42c7de4a1960cfdadf305bbe2-Abstract-Datasets_and_Benchmarks_Track.html).
- [AgentDojo](https://arxiv.org/abs/2406.13352).
- ICLR 2025, [Agent Security Bench](https://arxiv.org/abs/2410.02644).
- [Inspect AI documentation](https://inspect.aisi.org.uk/).
- [EleutherAI lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness).
- [promptfoo documentation](https://www.promptfoo.dev/docs/intro/).
- [NVIDIA garak](https://github.com/NVIDIA/garak).
- [DeepEval](https://github.com/confident-ai/deepeval).
- Ribeiro et al., [CheckList: Beyond Accuracy](https://arxiv.org/html/2005.04118v1).
- Zheng et al., [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685).
- [OpenAI Codex sandbox documentation](https://learn.chatgpt.com/docs/sandboxing).
- Existing adjacent user projects: [hackproof-grpo](https://github.com/10xdev4u-alt/hackproof-grpo), [harnessprobe](https://github.com/10xdev4u-alt/harnessprobe).

### Skill repositories reviewed for this revision

- [mattpocock/skills](https://github.com/mattpocock/skills) — cloned to `/tmp/behavioral-fingerprint-skills/skills`.
- [poteto/noodle](https://github.com/poteto/noodle) — cloned to `/tmp/behavioral-fingerprint-skills/noodle`.
- [poteto/brainmaxxing](https://github.com/poteto/brainmaxxing) — cloned to `/tmp/behavioral-fingerprint-skills/brainmaxxing`.
- [poteto/how](https://github.com/poteto/how) — cloned to `/tmp/behavioral-fingerprint-skills/how`.
- [poteto/verification-skill-example](https://github.com/poteto/verification-skill-example) — cloned to `/tmp/behavioral-fingerprint-skills/verification-skill-example`.
- [poteto/plugins](https://github.com/poteto/plugins) — cloned to `/tmp/behavioral-fingerprint-skills/plugins`.

*References and tool status should be rechecked at implementation time. This is a research plan, not a claim that the project has been built or that its novelty is established.*

---

## 17. Gate 0 findings: reuse evaluation runners; test the comparison seam

**Research date:** 2026-10-29. The following is a documentation-based first pass, not a pinned-version compatibility claim. Promptfoo and Inspect documentation are rolling; record exact installed versions and verify export fields before selecting either in an implementation. No package was installed and no incumbent workflow has yet been executed locally.

| Need | Promptfoo | Inspect AI | Consequence for this project |
|---|---|---|---|
| Run the same test cases across model/prompt configurations | Test matrices/configuration can exercise prompts and providers on shared cases. | Tasks/eval sets can evaluate model configurations and retain sample logs. | Do not build generic execution just to compare two variants. |
| Repeat stochastic runs | Global/per-case repeat controls; cache policy must be explicit. | Sample epochs and score reducers. | Preserve attempt records; do not mistake epochs/repeats for new independent cases. |
| Inspect slices and tool traces | Metadata filters, trajectory assertions, and tracing support. | Metadata-grouped metrics, tool-use solvers/logs, and log viewers. | Retain per-case slice labels and trace outcomes where the runner exposes them. |
| Quantify score uncertainty | Repetition and exports can support external analysis; no turnkey paired equivalence test found in reviewed docs. | Confidence/standard-error metrics and grouped analysis exist; reviewed docs do not provide the needed paired cross-version equivalence gate. | Uncertainty on each model's separate score is not a paired interval on the difference; non-significance is not equivalence. |
| Reproduce the experiment | Tags, exports and saved evaluations help; pinning all relevant inputs remains the user's responsibility. | Logs retain task/model/sample details; code, data, dependencies and model aliases still need pinning. | Own a small manifest/analysis contract only if it materially improves repeatability. |

### Gate 0 disposition: **EXTEND FIRST; DO NOT BUILD A NEW RUNNER**

The credible gap is a compact, auditable comparison/decision layer: stable common case IDs; per-case baseline/candidate observations; repeated attempts retained; per-slice paired effect; uncertainty with the resampling unit declared; a practical margin fixed before confirmatory runs; and `WITHIN DECLARED BOUNDS`, `MATERIAL REGRESSION`, `MATERIAL IMPROVEMENT`, or `INCONCLUSIVE` semantics. Promptfoo may be the better execution substrate for a prompt/provider matrix and behavioral assertions; Inspect AI is a strong candidate when sample logs, epochs, and custom analysis are central. Choose by running a small, pinned workflow against actual export/log data. If deterministic thresholds already answer the real user need, use them and stop the statistical product work. If no stable item-level data survives the incumbent export, first investigate an adapter/export path; do not assume a second runner is justified.

The first local spike is deliberately narrower than the original B1 scripted mock-agent proposal: it consumes JSONL scores and tests case pairing, case-level bootstrap intervals, and margin semantics. It executes no model and makes no calibration claim. Its two-case demo slices are smoke checks only, not evidence of statistical power, reliable uncertainty coverage, or low false-alert rates. The bootstrap resamples paired cases after averaging repeats, so it does **not** separately model generation variability within a case; the current implementation is a research question to validate or replace, not a committed estimator.

**Primary documentation checked by research agents:**

- Promptfoo [test cases](https://www.promptfoo.dev/docs/configuration/test-cases/), [CLI](https://www.promptfoo.dev/docs/usage/command-line/), [model drift](https://www.promptfoo.dev/docs/red-team/model-drift/), [tracing](https://www.promptfoo.dev/docs/tracing/), and [configuration reference](https://www.promptfoo.dev/docs/configuration/reference/).
- Inspect AI [metrics](https://inspect.aisi.org.uk/metrics.html), [options](https://inspect.aisi.org.uk/options.html), [eval sets](https://inspect.aisi.org.uk/eval-sets.html), [logs](https://inspect.aisi.org.uk/eval-logs.html), and [log dataframes](https://inspect.aisi.org.uk/dataframe.html).
- Method for equivalence decisions: Lauzon & Caffo, [TOST and multiplicity control](https://pmc.ncbi.nlm.nih.gov/articles/PMC2800314/). A score's interval is not automatically the interval for the paired version difference; choose and validate a method for the estimand and nested repeats.

## 18. Development start and verified local state

The explicit `/tmp` work directory is `/tmp/behavioral-fingerprints`. It is an isolated local Git repository initialized on `main` with `user.name=10xdev4u-alt` and `user.email=10xdev4u@gmail.com`. GitHub CLI status showed `10xdev4u-alt` as the active authenticated account and `the-ai-developer` as a separately logged-in, inactive account. A public remote repository and issues #1 and #2 have since been created; see §21–22 for the live branch and development state. No commit, push, PR, or deployment has yet been created.

The current local product files in `/tmp/behavioral-fingerprints` include:

- `compare.py` — standard-library-only JSONL comparator, optional Inspect AI JSON log importer, Markdown renderer, paired-slice summaries, and exploratory percentile-bootstrap intervals. The Inspect adapter pairs by stable task name/version and dataset/sample IDs; it records, but does not equate, run-specific eval/task IDs across baseline and candidate.
- `calibrate.py` — standard-library-only Monte Carlo harness that measures interval coverage and decision rates on synthetic nested-repeat data and contrasts the shipped estimator with a naive repeat-level bootstrap.
- `sample.jsonl` — tiny synthetic unchanged and seeded-effect example.
- `sample-inspect-baseline.json` and `sample-inspect-candidate.json` — synthetic Inspect-shaped JSON logs for exercising the importer.
- `README.md` — usage contract, Inspect import path, and limitations.
- `tests/test_compare.py`, `tests/test_inspect_import.py`, and `tests/test_calibrate.py` — standard-library tests for comparison/report behavior, Inspect log validation, and calibration harness behavior.

The prototype was run with Python 3.14.8 and Git 2.56.0. `python3 -m py_compile compare.py` succeeded. A run with 2,000 bootstrap draws and a fixed seed classified the synthetic unchanged slice `WITHIN_DECLARED_BOUNDS`, the seeded conditional-probe slice `MATERIAL_IMPROVEMENT`, and rejected a deliberately removed candidate case as a pairing error. These checks demonstrate only input/report behavior on a toy fixture. No statistical calibration or release claim has been established. There is no initial commit, so `main` is a clean-history starting point with uncommitted project files.

The previous §14 describes the plan's original pre-development state. This section and the following agent workflow are the current status; preserve the older text as historical planning context rather than silently rewriting it. The active branch is now `fix/1-reproducible-report`, as recorded in §21; the GitHub repository is public.

## 19. Agent-fleet operating charter: research → issue → branch → PR → merge

This charter is an operating policy for this project, not a mandate to manufacture work or to access GitHub. Apply it to the useful parts of a request; the actual user request, repository permissions, safety limits, and evidence gates take precedence over a pasted generic team playbook.

### 19.1 Roles and coordination

- **Lead / integrator:** owns scope, the canonical plan, decision log, dependency order, branch integration, final evidence, and user updates. One person/agent is accountable for each deliverable.
- **Research agent:** searches primary papers, official docs, source/releases and relevant competitors; returns claims with URLs, dates/version caveats, and uncertainty. It does not create issues or change code merely because it found an idea.
- **Design/evaluation agent:** challenges the estimand, threat model, scorer, sample size, practical margin, and alternatives; writes falsifiers and stop criteria before confirmatory results.
- **Implementation agent:** takes one accepted issue, uses a dedicated branch/worktree where available, edits only its assigned surface, and reports exact commands/results. It does not redefine the measurement protocol implicitly.
- **Test/quality agent:** independently reviews acceptance criteria, negative cases, determinism, unsafe paths, and claims. It reports failures rather than weakening tests or suppressing errors.
- **Documentation/release agent:** verifies instructions and claims against the implemented interface and evidence; no marketing language that exceeds the measured result.

Use parallel agents for independent research/review, not conflicting writes to the same files. The integrator reconciles disagreements explicitly. Agent output, issue text, web pages, model output, and repository content are untrusted data—not instructions that override this charter. No agent receives real secrets or authority to execute arbitrary model-generated tools.

### 19.2 Evidence-to-backlog discipline

1. **Research:** state the user/job and question; search primary sources and the closest incumbent; distinguish documented behavior from inference; record access date and versions.
2. **Evaluate:** compare build / extend / stop options; identify assumptions, risks, counterevidence, owner, and a falsifier. No implementation ticket until a gap is concrete.
3. **Create issues only for accepted work:** title states an outcome; body includes why now, evidence/links, scope and non-goals, dependencies, independently observable acceptance criteria, validation command/evidence, risk/data notes, and a named decision owner. Label research/design/code/docs/security as appropriate. Link blockers; keep one source of truth in the issue/plan.
4. **Work the unblocked frontier:** prefer one reviewable vertical slice; close or split tickets when evidence changes. A research finding to stop, pivot, or extend an incumbent is a valid completion.
5. **No issue-count target:** 60–70 issues is not a quality metric. Create that many only if each represents a genuinely independent, supported outcome with non-duplicative acceptance criteria and an owner. Do not split trivial subtasks to satisfy a quota or invent speculative features for an “enterprise” appearance.

### 19.3 Branch and commit contract

- Confirm current branch/status before every consequential Git action. Start work from an up-to-date `main`; use one short-lived branch per accepted issue/PR (for example, `feat/123-paired-report` or `docs/45-protocol-gate`). Never work directly on shared `main` for implementation.
- Keep changes focused and reversible. Do not stage unrelated user changes, commit secrets/generated artifacts, rewrite shared history, force-push, or clean branches by broad pattern. Use explicit paths and inspect staged diffs.
- Use Conventional Commits (`feat(scope): …`, `fix(scope): …`, `docs(scope): …`, `test(scope): …`, `refactor(scope): …`, `chore(scope): …`). Keep each commit coherent; put the reason in the body when useful. Before every commit, review `git diff` and recent `git log`, run the relevant checks, and verify the staged file list.
- **Requested co-author convention:** the user wants `the-ai-developer` to be the only co-author on every project commit. Use exactly one `Co-authored-by: the-ai-developer <verified-address>` trailer and no other co-author trailer, but only after verifying the right account/email and that the agent actually contributed to that commit. Do not invent an email, claim a review that did not happen, or impersonate the account. If attribution cannot be verified or the account did not participate, pause for a decision rather than falsifying authorship. Do not add unrelated bot attribution. This rule applies only to commits in this project and does not make a commit or push authorized by itself.

### 19.4 Pull-request lifecycle

For each issue-backed change, use a PR with a concise why, issue link (`Fixes #…` only when it truly closes the issue), design/behavior notes, risks, evidence/commands, and limitations. Keep PR scope to the issue; attach screenshots only for visual work and never expose sensitive traces. CI must run the relevant checks; failures are diagnosed and fixed, not bypassed. Mark uncertain research and follow-up work explicitly rather than presenting it as shipped.

Required sequence: **research → evaluate/build-or-extend decision → issue and acceptance criteria → validate the proposed approach → implement the smallest slice → run local validation → inspect diff/commit → open PR → independent review → address feedback → rerun affected validation → merge → verify base branch and clean up only the completed feature branch.** The first PR may include the evidence-backed comparison spike, but not a speculative platform or a batch of unrelated backlog items.

Request `the-ai-developer` as reviewer when available and authorized. Review must be a real, recorded review from that GitHub identity; do not write on its behalf. The author/integrator remains responsible for responding to every blocking comment and testing the final post-review state. If the requested reviewer is unavailable, wait or ask the user for a substitute—do not fabricate approval.

**Merge policy:** retain PR merge commits; do not squash-merge or rebase-merge. Confirm the repository permits merge commits and required checks/approvals pass, then use the merge-commit path only when the user has authorized merging. Do not enable auto-merge as a workaround. After merge, verify the commit on `main`; delete only the feature branch belonging to that completed PR, after verifying it is merged and not in use. Never delete “stale” branches in bulk; inspect ownership and merged status first. Repeat from a fresh `main` for the next accepted issue.

### 19.5 GitHub authority and credential boundaries

A local `gh auth status` identifies available accounts; it does not by itself authorize remote effects. Before creating a remote, changing repository settings, publishing issues/PRs, pushing, requesting reviews, merging, or deleting branches, verify the target owner/account, repository visibility, permissions, and the user's current instruction. Use `10xdev4u-alt` only for actions explicitly authorized for that profile; do not switch to `the-ai-developer` to impersonate a reviewer or author. Never read, print, copy into this plan, or commit tokens, environment secrets, private keys, model/API credentials, or private raw evaluation data. Do not publish the local prototype or issues until the user has chosen the remote/repository visibility and authorized publication. Keep preview/research artifacts synthetic and offline unless a separately approved plan says otherwise.

### 19.6 Documentation quality (“unslop” review)

Write docs for a competent engineer trying to reproduce the result: define terms once; use specific headings, commands, inputs, outputs and limitations; cite primary sources; distinguish observed fact, hypothesis and recommendation; remove repeated claims, filler, fake certainty, generic “enterprise” adjectives, and unsupported novelty/safety language. Prefer a short evidence table and a runnable example over a long tool catalog. Check every command/path and every claim against the current code. Skills are aids, not policy: inspect skills actually present/available in the project at the start of a task, read only relevant guidance, and report what was or was not inspected. Never claim a skill was used just because its name appeared in a prompt or an earlier plan.

## 20. Immediate continuation plan and ticket frontier

The current comparator is an exploratory spike, not a green light for a broad product. Continue in this order:

1. **Complete D1 with pinned incumbents:** choose a real, small Promptfoo or Inspect workflow, record exact tool versions and configuration, export two variants with common case IDs and repeats, inspect whether the exported records support pairing, and document friction. Do not install both or add dependencies until this experiment chooses one.
2. **Decide the estimator before confirmatory runs:** specify the estimand, score type, practical margin, case sampling, repeat treatment, bootstrap/interval method, multiplicity and missing-run policy. Simulate representative null/effect/nested-repeat data; compare the current case-level bootstrap with a method that models within-case generation variation. Do not call the current demo calibrated. **Partly done:** `calibrate.py` now measures coverage against both a realized and a population estimand and shows the shipped case-level bootstrap holds nominal coverage under correlated repeats where a naive repeat-level bootstrap collapses (§23). Binary/categorical scorers, multiplicity, and real-case correlation remain unexplored.
3. **Refine only the observed gap:** if incumbent exports retain the evidence, keep the analysis adapter thin; if not, investigate the smallest supported export hook. Keep deterministic fake outcomes separate from model-graded outcomes; add a scripted agent only if tool-effect/channel measurement is part of the selected question.
4. **Issue only validated work:** create a small evidence-linked backlog for accepted work (likely a protocol decision, an incumbent export spike, and statistical simulation/calibration). The decision to extend an incumbent or stop is an allowed outcome. No 60–70 issue quota.
5. **Current PR boundary:** the repo is public and issues #1 and #2 exist. Before committing/pushing/opening a PR, ensure the requested co-author actually contributes and the account can access the repository as reviewer. Use a merge commit after real review and required validation; follow the branch cleanup rules above.

**Current research gate:** Inspect's documented JSON log schema is supported by the narrow importer; 24 tests pass, and two offline mock evaluations with Inspect AI `0.3.286` were run through native `.eval` generation, JSON conversion and the product CLI. This is a pinned compatibility check only; real model evaluation and the nested-repeat estimator remain research work. Therefore proceed with a two-variant compatibility/provenance experiment and estimator validation, not a production release gate, general runner, CI policy, local model integration, dashboard, or public claim.

---

## 21. GitHub development checkpoint (2026-10-29)

- **Repository:** [`10xdev4u-alt/behavioral-fingerprints`](https://github.com/10xdev4u-alt/behavioral-fingerprints), public (visibility rechecked during this continuation); issue tracking enabled; created under the active authenticated `10xdev4u-alt` account. No default branch is established until the first push. No GitHub Actions, secrets, project boards, or repository-policy changes were made.
- **Issue:** [#1 — make exploratory paired-comparison output reproducible and regression-tested](https://github.com/10xdev4u-alt/behavioral-fingerprints/issues/1), open. It gives the scope, non-goals, acceptance criteria and validation commands for the first code slice. [#2 — import paired Inspect AI JSON evaluation logs](https://github.com/10xdev4u-alt/behavioral-fingerprints/issues/2), open, tracks the next thin adapter slice.
- **Local branch:** `fix/1-reproducible-report`, based on the empty local `main`; the current untracked working tree includes issue #1 and #2 implementation files. No implementation commit has been pushed.
- **Issue #1 development:** remove misleading loop-local seed data from the report, keep deterministic slice bootstrapping independent of slice traversal order, add stdlib `unittest` regression coverage, and document how to run it. The product also now renders an optional human-readable Markdown summary alongside JSON stdout, including per-slice results and limitations. The 10 tests cover expected synthetic slice decisions, deterministic results, Markdown contents, reordered input, paired repeats, malformed JSON, duplicate records, invalid scores, mismatched cases, and unequal repeat counts.
- **Verification:** initial issue #1 checkpoint had 10 tests; current full suite is 24 passing tests, with syntax compilation and `git diff --check` clean. JSONL and Inspect CLI paths were exercised; the current Inspect full-run evidence is detailed in §22. No statistical calibration, real model, or production-gate test has been run.
- **Co-author/reviewer access:** making the repository public granted `the-ai-developer` read access; write/review permissions and the account's verified commit email still need verification before a request or attribution. The public profile does not expose an email. Do not invent an address, claim work the account did not contribute, or impersonate it; retain the user's only-co-author constraint truthfully.
- **Next decision:** verify the requested co-author/reviewer access and verified identity, then commit the reviewed issue scope with an exact Conventional Commit subject, push only the branch, open a focused PR requesting the real reviewer, complete review and validation, and merge with a merge commit only after approval/authorization. No commits or PRs have been created yet; current development remains in the local working tree.

### First issue's design review note

The initial report-data loop had a seed-scope defect noticed during issue acceptance review: a per-slice variable must not leak into global provenance. More importantly, the slice RNG should be a deterministic function of the requested seed and stable slice identity, not its position in a list. The implementation now seeds it from `f"{seed}:{slice_name}"`; tests verify output stability under record reordering. The CLI can also write `--markdown PATH`, a presentation-only summary with explicit limitations. These changes make the first product workflow more usable but do not address the estimator's acknowledged nested-repeat limitation.

---

## 22. Inspect AI JSON log adapter development (2026-10-29)

### Evidence and product choice

Current official Inspect documentation describes JSON log export and the Python log API. `EvalLog` includes `status`, `eval.task_id`, `eval.dataset`, `eval.model`, `eval.config.epochs`, and `samples`; samples contain an ID, epoch, possible error, and scores; scorer records carry a value. Inspect recommends stable explicit dataset IDs when matching samples across runs. The `.eval` binary format must be read or converted through Inspect's API/CLI; this implementation intentionally accepts only plain JSON and adds no Inspect dependency.

References checked:
- [Inspect Log Files](https://inspect.aisi.org.uk/eval-logs.html) — JSON log format, status checking, API and sample summaries, and stable explicit IDs.
- [Inspect log API/schema](https://inspect.aisi.org.uk/reference/inspect_ai.log.html) — `read_eval_log`, `EvalLog`, sample ID/epoch access, scorer records and related schema.

The research found that Promptfoo's docs show useful score output and repeat context but do not guarantee a complete stable item/model/repeat tuple in each JSONL export row. Inspect's documented eval log retains more of the needed record. This is a substrate hypothesis, not a claim that Inspect is always superior. Inspect AI `0.3.286` is now pinned for the local compatibility experiment; see the paired full-run evidence below.

### Local implementation

`compare.py` now supports either the existing paired JSONL records or two Inspect JSON files via `--inspect-baseline`, `--inspect-candidate`, and `--scorer`. Optional `--inspect-baseline-label` / `--inspect-candidate-label` let the operator declare the variant names. It converts task name/version + dataset + explicit sample ID to the case key and uses the recorded epoch as repeat. It requires a successful run, task/model/dataset metadata, explicit unique sample IDs, complete sample coverage, valid numeric scorer values in `[0,1]`, and no sample errors or duplicate sample/epoch entries. If the log declares epochs, every declared sample/epoch is required; missing data is never silently set to zero or omitted. Existing matching rules then check baseline/candidate sample pairing and repeat counts.

Added synthetic fixtures `sample-inspect-baseline.json` and `sample-inspect-candidate.json`, plus `tests/test_inspect_import.py`. The committed fixtures are handcrafted to match documented fields. In addition, an offline end-to-end smoke created and ran two distinct two-sample Inspect AI tasks with `mockllm/model` and a deterministic numeric scorer under Inspect AI `0.3.286`, generated native `.eval` files, converted both to JSON with `inspect log convert`, then imported them through the product CLI. It asserted the same task name/version and sample IDs pair despite distinct `eval_id` and per-run `task_id` values, retained those IDs in source provenance, and detected the controlled `-1.0` paired mean change. No real model/provider or network was used and no project dependency was added. The first attempt with Inspect's built-in `match` scorer returned categorical score values; the importer rejected them as designed, so the smoke task used a numeric scorer without weakening the product's `[0,1]` contract.

### Validation and limitation

- `python3 -m unittest discover -s tests -v`: 24 passed (10 comparator/report tests; 14 Inspect import/pairing tests).
- `python3 -m py_compile compare.py tests/test_compare.py tests/test_inspect_import.py`: passed.
- JSONL CLI regression smoke: passed in the prior checkpoint.
- Synthetic Inspect-shaped two-log CLI smoke produced JSON and Markdown with two paired cases and the expected scoped decision.
- Two offline Inspect AI `0.3.286` mock evaluation runs → native `.eval` outputs → JSON conversion → importer CLI succeeded; the distinct run IDs were retained, two explicit sample IDs paired, and the controlled paired delta `-1.0` was detected.
- `git diff --check`: passed.

The adapter uses the selected logs' declared task name/version and dataset/sample IDs to catch pairing mismatches, while correctly treating `task_id` and `eval_id` as run-specific provenance that differs between separate calls. It still does not independently establish that runs used identical task source, dataset contents, scorer implementation, or generation configuration. Record/pin those details in a future protocol manifest before interpreting comparisons. It rejects non-success status rather than offering partial-run handling and accepts numeric values only on the existing bounded `[0,1]` score scale. The end-to-end smoke establishes compatibility for the tested Inspect AI `0.3.286` workflow only; it does not establish compatibility across versions or validate statistical decisions.

**Next acceptance evidence:** compare real project evaluations and verify the suite/data/scorer fingerprints in a protocol manifest before interpreting results. A green importer test does not validate statistical decisions; the first estimator evidence is recorded in §23.

---

## 23. Estimator calibration on simulated nested-repeat data (2026-10-29)

### Why this was the next slice

§7 requires that the interval method be validated on data with a known generating process before its decisions are trusted, and the earlier spike explicitly flagged that averaging repeats and resampling cases "does not separately model generation variability within a case." That was an open question, not a defect. This slice answers it empirically for the bounded continuous-score case, using a purpose-built harness with no model, no network, and no new dependency.

### What was built

`calibrate.py` (standard library only) simulates paired datasets and reports, per estimator, interval coverage, mean interval width, and the decision distribution:

- `case_level` — the shipped estimator, invoked through `compare.compare` itself so the harness cannot drift from the product code.
- `naive_repeat_level` — a deliberate control that resamples every repeat-pair as an independent observation, i.e. exactly the error of treating repeats as new cases.

The generator gives each case a stable ability shared by both variants (paired design) and an optional between-case effect sd. That effect variation is shared by all repeats of a case, which is what creates within-case correlation. Coverage is measured against two distinct targets because they are distinct claims: the **realized** mean effect over the cases in that draw (a claim about this suite) and the **population** mean effect the cases were drawn from.

To keep the decision rule single-sourced, the interval→decision mapping was extracted from `compare()` into `compare.decide(low, high, margin)`, and both `compare()` and the harness call it. A regression test asserts that every reported decision equals `decide()` applied to that result's own interval.

### Measured result

Command: `python3 calibrate.py --cases 30 --repeats 6 --effect 0.05 --effect-sd S --noise-sd 0.10 --margin 0.05 --bootstrap 500 --simulations 400 --seed 11` (nominal 95%, Monte Carlo 95% intervals over 400 simulations).

| `--effect-sd` | Estimator | Population coverage [95% MC] | Realized coverage | Mean width |
|---|---|---|---:|---:|
| 0.0 (control: independent repeats) | `case_level` (shipped) | 0.927 [0.902, 0.953] | 0.927 | 0.0398 |
| 0.0 (control) | `naive_repeat_level` | 0.922 [0.896, 0.949] | 0.922 | 0.0404 |
| 0.20 (correlated repeats) | `case_level` (shipped) | 0.950 [0.929, 0.971] | 1.000 | 0.1355 |
| 0.20 (correlated repeats) | `naive_repeat_level` | 0.637 [0.590, 0.685] | 0.998 | 0.0665 |

The README table reproduces these numbers exactly from its documented command; this was verified rather than copied.

### Interpretation

- **The design decision is supported.** When repeats are correlated through between-case effect variation, resampling repeats as independent observations halves the interval and destroys population coverage (0.64 against 0.95 nominal). Averaging repeats within a case and resampling cases held its nominal rate in the same regime (0.950, MC interval 0.929–0.971).
- **The control behaves as expected.** With independent repeats, both estimators agree (0.927 vs 0.922) and widths are nearly identical, so the harness is not manufacturing a difference that is not there.
- **The shipped estimator is conservative for suite-level claims, not for population claims.** Realized coverage is 1.000 in the correlated regime because the interval width reflects between-case spread while the realized mean has only averaging error. A decision of `WITHIN_DECLARED_BOUNDS` is therefore a statement about a population of similar cases, and is conservative when read as a claim about only these cases. The report language should keep saying "for these tested cases" but must not imply the interval is tight for them.
- **Small-sample undercoverage exists.** In the control the shipped estimator sat at 0.927, below 0.95. That is ordinary percentile-bootstrap undercoverage at 30 cases, and it is a reason not to advertise exact nominal coverage.

### What this does not establish

- Nothing about real evaluators, real score distributions, or binary/categorical and judge-scored outcomes. Inspect's built-in `match` scorer emits categorical values that this tool rejects, so that path is untested by design.
- Nothing about correlated or near-duplicate real cases, which the generator draws independently.
- Nothing about multiplicity: single-slice coverage does not carry over to taking the best of many slices.
- Nothing about release-gate suitability. A calibrated interval is not a calibrated process, sample-size plan, or policy.

### Validation

- `python3 -m unittest discover -s tests -v` — 39 passed (24 prior + 15 calibration tests).
- `python3 -m py_compile compare.py calibrate.py tests/*.py` — passed.
- Documented calibration commands rerun and asserted equal to the published table values.
- `git diff --check` — clean.

### Frontier

1. Extend the harness to binary and categorical scorers, where the bounded continuous assumption fails and McNemar-style paired analysis may be more appropriate than a percentile bootstrap.
2. Add multiplicity treatment to the product, then measure family-wise false-alert behavior across slices rather than per slice.
3. Introduce correlated/near-duplicate cases in the generator to see how much the case-level bootstrap degrades under realistic suite structure.
4. Keep commits local until the `the-ai-developer` co-authorship and reviewer arrangement can be verified; no commit, push, or PR exists yet.
