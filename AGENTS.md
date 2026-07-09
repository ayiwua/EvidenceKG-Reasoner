# AGENTS.md

## Project Working Mode

This repository follows **Specification Driven Development**.

The source of truth is not whatever the current code happens to do.
The source of truth is the approved design/specification documents.

Codex must implement the approved specifications.
Codex must not redesign the system without explicit user approval.

---

## Roles

### User

The user is the final architect and decision maker.

The user decides:

* research direction;
* dataset choice;
* task definition;
* module design approval;
* implementation plan approval;
* final code acceptance.

### ChatGPT / Chief Architect

ChatGPT helps the user design modules, compare alternatives, define specifications, and review whether Codex implementation follows the approved design.

### Codex / Software Engineer

Codex is responsible for implementation.

Codex should:

* read the relevant specifications;
* inspect the current code;
* produce gap analysis;
* produce implementation plans;
* write code only after approval;
* run tests or smoke checks;
* self-review implementation against the specification.

Codex must not act as the system designer unless explicitly asked.

---

## Required Reading Before Any Work

Before making any non-trivial change, Codex must read:

1. `AGENTS.md`
2. `docs/architecture.md`
3. The relevant module specification under `docs/specs/`
4. The relevant existing source files
5. Any task-specific design document referenced by the user

For Re-DocRED work, Codex must also read:

* `docs/redocred_pipeline_design.md`

---

## Mandatory Development Process

For every module or feature, follow this process:

```text
1. Read specifications and relevant code.
2. Summarize the current implementation.
3. Summarize the target behavior.
4. Identify the gap.
5. Propose an implementation plan.
6. Wait for user approval.
7. Implement in small steps.
8. Run tests or smoke checks.
9. Self-review against the specification.
10. Report what changed, what was validated, and what remains risky.
```

Codex must not skip directly from reading the request to editing code unless the user explicitly asks for a tiny edit.

---

## Required Implementation Plan Format

Before coding, Codex must output an implementation plan with these sections:

```text
## Current

Describe the current relevant code and behavior.

## Target

Describe the intended behavior according to the approved specification.

## Gap

List what is missing, incompatible, or risky.

## Files to Change

List files to add or modify.

## Step-by-Step Plan

Describe the implementation steps in order.

## Tests / Validation

Describe how to validate the change.

## Risks

List potential risks, edge cases, or unresolved assumptions.
```

Only after the user approves this plan should Codex modify code.

---

## Project Pipelines

This repository currently contains two pipeline families, but only one is the active research and development direction.

### 1. Re-DocRED Primary Research Pipeline

The Re-DocRED pipeline is the primary and only active research/development pipeline going forward.

It is a document-level, multi-relation, evidence-aware triple verification system.

Target flow:

```text
Raw Re-DocRED
→ Adapter
→ Processed JSONL
→ Candidate Generator
→ Sentence Evidence Retriever
→ Document Local Graph / Graph Context Retriever
→ Prompt Builder
→ Reasoner
→ Verifier
→ Evaluator
```

The first-stage Re-DocRED task is:

```text
Given document D, head entity h, relation r, and tail entity t,
decide whether candidate triple (h, r, t) is supported by the document,
and return evidence sentence ids when possible.
```

The first-stage output should include:

```text
decision = accept | reject | uncertain
confidence
risk
reason
supporting_evidence_ids
optional conflict_evidence_ids
verifier details
```

### 2. Enterprise Asset Legacy Reference Pipeline

The original pipeline performs enterprise asset / IT asset hidden edge recovery.

It includes:

```text
entities / triples / evidence
→ candidate generation
→ evidence retrieval
→ prompt construction
→ reasoner
→ verifier
→ hidden edge recovery evaluation
```

This pipeline is now legacy/reference only.

It is kept temporarily to:

* understand the first version of the workflow;
* borrow small utility code where appropriate;
* avoid immediately breaking repository history.

It is no longer a long-term parallel mainline.

New code does not need to force compatibility with it.

Old enterprise-pipeline assumptions must not constrain Re-DocRED module design.

After the Re-DocRED small pipeline runs, the enterprise pipeline may be moved into `legacy/` or removed after explicit approval.

---

## Source of Truth Hierarchy

When documents and code disagree, follow this order:

```text
1. User's latest explicit decision
2. Approved module specification in docs/specs/
3. docs/architecture.md
4. docs/redocred_pipeline_design.md
5. Existing code behavior
```

Existing code is not automatically authoritative if it conflicts with the approved specification.

---

## Re-DocRED First-Stage Non-Goals

Do not implement these unless explicitly approved:

* full entity-pair × all-relation brute-force expansion;
* LLM full-document relation extraction that directly outputs all relations;
* Neo4j integration;
* GNN models;
* cross-encoder training;
* multi-agent debate;
* best-of-N LLM voting;
* complex temporal/spatial reasoning;
* premature large-scale refactoring of the enterprise legacy pipeline before the Re-DocRED small pipeline runs;
* deleting or moving the enterprise legacy pipeline before explicit approval;
* using test data for prompt or threshold tuning.

---

## Anti-Leakage Rules

Gold labels and gold evidence must be handled carefully.

### Allowed

The evaluator may read gold labels and gold evidence.

The dataset builder may read raw labels to construct:

* `gold_triples.jsonl`;
* positive candidates;
* gold evidence fields for evaluation.

### Forbidden

The retriever must not use `gold_evidence_ids` to retrieve evidence.

The prompt builder must not read gold labels.

The reasoner must not see gold labels.

The verifier must not use gold labels to decide whether a prediction is correct.

The candidate generator may use gold labels only to create positive candidates and controlled negatives during dataset construction.

During formal evaluation, any module before the evaluator must not use gold labels as oracle information.

---

## Data Contract Principles

All JSONL outputs must have stable, documented fields.

Re-DocRED processed data should use deterministic ids:

```text
doc_id
sentence_id
entity_id
mention_id
candidate_id
gold_id
prediction_id
```

IDs must be reproducible from split, document index, sentence index, entity index, or candidate index.

Do not generate random IDs unless explicitly justified.

---

## Required Re-DocRED Processed Files

The Re-DocRED adapter should produce or support:

```text
documents.jsonl
entities.jsonl
evidence.jsonl
gold_triples.jsonl
candidates.jsonl
```

Later stages may produce:

```text
evidence_contexts.jsonl
verified_predictions.jsonl
predicted_triples.jsonl
evaluation_report.json
timing_report.jsonl
```

Each module should consume only the files it is allowed to consume.

---

## Module Boundary Rules

### Adapter

The adapter reads raw Re-DocRED files and relation metadata.

It produces processed JSONL files.

It may read labels because it constructs gold triples and positive candidates.

It must not perform LLM reasoning.

### Candidate Generator

The candidate generator creates positive, negative, and hard negative candidate triples.

It may use gold triples during dataset construction.

It must record candidate generation rules and negative types.

It must not perform evidence retrieval.

### Sentence Evidence Retriever

The retriever retrieves top-k sentence evidence for each candidate.

It may use:

* document sentences;
* entity mentions;
* relation metadata;
* graph context features;
* text similarity.

It must not use `gold_evidence_ids` as retrieval input.

### Document Graph / Graph Context Retriever

The graph module constructs document-local graph context.

It may use:

* document;
* sentences;
* entities;
* mentions;
* candidate triple.

It must not inject the current candidate's gold label into inference context.

### Prompt Builder

The prompt builder constructs structured LLM prompts.

It may use:

* candidate;
* retrieved evidence;
* graph context;
* relation metadata.

It must not read gold labels or gold evidence.

### Reasoner

The reasoner calls mock or real LLMs.

It must return parseable structured output.

It must not access evaluator files or gold labels.

### Verifier

The verifier checks prediction validity.

It may use:

* candidate;
* evidence context;
* graph context;
* relation metadata;
* LLM prediction.

It must not use gold labels to determine correctness.

The verifier may downgrade `accept` to `uncertain` or `reject` according to specification.

### Evaluator

The evaluator is the only module that compares predictions to gold labels.

It computes relation metrics, evidence metrics, and risk-control metrics.

---

## Coding Principles

Re-DocRED is the primary implementation target.

Design Re-DocRED modules independently.

The original enterprise asset pipeline is legacy/reference only; it may be used for understanding and small utility reuse, but it is not a required compatibility target.

Use Re-DocRED-specific modules when behavior differs substantially:

```text
redocred_adapter.py
redocred_candidate_generator.py
redocred_sentence_retriever.py
redocred_document_graph.py
redocred_graph_context.py
redocred_prompt_builder.py
redocred_verifier.py
redocred_evaluator.py
```

Avoid forcing Re-DocRED logic into old modules if it makes the original code fragile.

Also avoid forcing old enterprise-pipeline assumptions into Re-DocRED modules.

Prefer small, testable changes.

Prefer explicit schemas over implicit dictionaries.

Prefer deterministic behavior.

Do not hide major assumptions inside helper functions.

---

## Testing and Validation Expectations

Every implementation step should include at least one validation method.

Examples:

```text
python scripts/inspect_redocred.py --input ...
python scripts/build_redocred_dataset.py --max-docs 5 ...
python scripts/generate_redocred_candidates.py --max-docs 5 ...
python scripts/run_redocred_pipeline.py --max-docs 3 --mock
python scripts/evaluate_redocred.py --input ...
```

If a full test is not possible, Codex must provide a smoke check or dry-run validation.

Codex must report:

* commands run;
* whether they passed;
* relevant output files;
* known limitations.

---

## Documentation Requirements

When adding a module, update or create the relevant specification under:

```text
docs/specs/
```

Do not rely only on code comments.

If implementation deviates from the specification, Codex must stop and ask for approval before proceeding.

---

## Self-Review Checklist

Before reporting completion, Codex must check:

```text
[ ] Did I read the relevant specification?
[ ] Did I follow the approved implementation plan?
[ ] Did I avoid changing the task definition?
[ ] Did I keep Re-DocRED as the primary design target?
[ ] Did I avoid letting legacy enterprise-pipeline assumptions constrain Re-DocRED design?
[ ] Did I avoid gold evidence leakage?
[ ] Did I keep JSONL schemas stable?
[ ] Did I add or update smoke checks?
[ ] Did I document new assumptions?
[ ] Did I report risks or incomplete parts honestly?
```

---

## Reporting Format After Implementation

After coding, Codex should report:

```text
## Changes Made

List files changed and summarize each change.

## Validation

List commands run and results.

## Specification Compliance

Explain how the implementation matches the approved spec.

## Risks / Follow-ups

List unresolved risks, edge cases, or recommended next steps.
```

---

## Important Principle

Codex should implement the approved design.

Codex should not reinterpret the research direction, redesign the pipeline, or expand the project scope without explicit approval.
