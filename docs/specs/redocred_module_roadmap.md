# Re-DocRED Module Roadmap

## Purpose

This document is the module-level roadmap for the Re-DocRED pipeline.

It does not replace detailed module specifications. Each implementation module still needs its own approved spec under `docs/specs/` before coding begins.

This roadmap only defines:

- module development order;
- module dependencies;
- expected inputs and outputs;
- gold-access boundaries;
- acceptance gates;
- stop conditions before moving to the next module.

## Development Order

Development must proceed in this order:

1. schema inspection
2. redocred_adapter
3. redocred_candidate_generator
4. redocred_sentence_retriever
5. redocred_document_graph / redocred_graph_context
6. redocred_prompt_builder
7. mock / real reasoner integration
8. redocred_verifier
9. redocred_evaluator
10. redocred_pipeline_runner
11. experiment / smoke scripts

Each module must pass its acceptance gate before the next module starts.

## Module Dependency Table

| Module | Depends on | Consumes | Produces | Allowed gold access | Forbidden access | Acceptance gate |
| --- | --- | --- | --- | --- | --- | --- |
| schema inspection | raw Re-DocRED files | raw train/dev/test files, relation metadata if available | schema summary, evidence coverage summary, relation summary | May inspect labels/evidence to report coverage | Must not create inference outputs | Raw fields, label shape, evidence coverage, and split availability are documented |
| redocred_adapter | schema inspection | raw Re-DocRED, relation metadata | `documents.jsonl`, `entities.jsonl`, `evidence.jsonl`, `gold_triples.jsonl` | May read labels and evidence to build gold files | Must not perform retrieval, prompting, reasoning, verification, or evaluation decisions | Processed JSONL schemas are deterministic, stable, and validated on a small sample |
| redocred_candidate_generator | redocred_adapter | `documents.jsonl`, `entities.jsonl`, `gold_triples.jsonl`, relation metadata | `candidates.jsonl`, candidate stats | May use gold triples to create positives and controlled negatives | Must not use gold evidence for inference ranking; must not perform retrieval | All gold positives are covered; negatives do not duplicate gold; sanitized inference view is defined |
| redocred_sentence_retriever | redocred_candidate_generator | `documents.jsonl`, `entities.jsonl`, `evidence.jsonl`, sanitized candidates, relation metadata | `evidence_contexts.jsonl`, retrieval stats | No gold access during retrieval; evaluator may later compare to gold evidence | Must not read `gold_evidence_ids` as retrieval input; must not read `gold_triples.jsonl` during inference | Top-k evidence contexts exist for candidates; retrieval metadata records scores and reasons; no oracle fields enter context |
| redocred_document_graph / redocred_graph_context | redocred_adapter, redocred_candidate_generator | documents, sentences, entities, mentions, sanitized candidates | document-local graph context inside `evidence_contexts.jsonl` or sidecar context | No gold access for inference context | Must not inject current candidate gold label or gold evidence into graph context | Head/tail mention sentences, common sentences, bridge entities, and co-occurrence paths are available without leakage |
| redocred_prompt_builder | sentence retriever, graph context | sanitized candidate, retrieved evidence, graph context, relation metadata | structured context, prompt text | No gold access | Must not expose `gold`, `label`, `gold_evidence_ids`, or gold triples to the model | Prompt contains allowed evidence ids, relation definition, candidate, graph context, and strict JSON schema |
| mock / real reasoner integration | prompt builder | structured context, prompt text, LLM config | raw predictions | No gold access | Must not read evaluator files or gold labels | Mock path and real LLM path both return normalized parseable prediction records or controlled `uncertain` fallback |
| redocred_verifier | reasoner integration | candidate, evidence context, graph context, relation metadata, raw prediction | `verified_predictions.jsonl` records | No gold access for correctness decisions | Must not compare predictions to gold; must not use labels to decide pass/fail | Schema, grounding, sufficiency, conflict, and abstention checks produce explainable verifier details |
| redocred_evaluator | verifier | `verified_predictions.jsonl`, `predicted_triples.jsonl`, `gold_triples.jsonl`, optional gold evidence | `evaluation_report.json`, optional per-relation/evidence metrics | May compare predictions to gold labels and gold evidence | Must not feed evaluation gold back into retriever, prompt, reasoner, or verifier | Relation metrics, evidence metrics when available, and risk-control metrics are computed correctly |
| redocred_pipeline_runner | adapter through evaluator | module configs, processed data, candidates, contexts | complete run outputs, run metadata, timing if enabled | Only routes gold to candidate construction and evaluator according to spec | Must not pass gold fields into prompt/reasoner/verifier | End-to-end small run works with sanitized inference objects and reproducible outputs |
| experiment / smoke scripts | pipeline runner | small processed split, configs | smoke outputs, logs, documented commands | Evaluator may access gold for reports | Must not tune on test data | Smoke command is runnable, documented, and produces expected files |

## Data Flow

```text
raw Re-DocRED
  -> schema summary
  -> processed JSONL
  -> candidates
  -> evidence_contexts
  -> prompts / raw predictions
  -> verified_predictions
  -> predicted_triples
  -> evaluation_report
```

Expanded flow:

```text
raw train/dev/test JSON + relation metadata
  -> schema inspection
  -> documents.jsonl / entities.jsonl / evidence.jsonl / gold_triples.jsonl
  -> candidates.jsonl
  -> evidence_contexts.jsonl
  -> structured prompts
  -> raw_predictions
  -> verified_predictions.jsonl
  -> predicted_triples.jsonl
  -> evaluation_report.json
```

Gold labels and gold evidence may enter only:

- adapter outputs for gold files;
- candidate construction for positives and controlled negatives;
- evaluator metric computation.

They must not enter:

- retrieval ranking;
- graph context inference payloads;
- prompt text;
- reasoner inputs;
- verifier correctness decisions.

## Implementation Rule

Every module must follow this sequence:

1. Create or update `docs/specs/<module>.md`.
2. Review and approve the module spec.
3. Only after spec approval, Codex may output an implementation plan.
4. Only after implementation plan approval, Codex may edit code.
5. Run the module validation or smoke check.
6. Self-review against the approved spec.
7. Move to the next module only after acceptance.

No module may be implemented directly from this roadmap alone. This roadmap is an execution constraint and dependency map, not a detailed implementation spec.

## Critical Architecture Decisions

- Re-DocRED is the only active main development direction.
- The legacy enterprise pipeline is reference only.
- The new Re-DocRED pipeline should be implemented independently.
- Old code may be reused only for generic utilities such as JSONL IO, config loading, LLM clients, logging, or JSON parsing.
- Old enterprise hidden-edge assumptions must not constrain Re-DocRED data schemas, runner design, evaluator design, or module boundaries.
- Gold leakage must be prevented by both the runner and every individual module.
- The first stage is controlled evidence-aware triple verification.
- The first stage is not full document-level extraction and not full entity-pair x all-relation expansion.

## Stop Conditions

Stop before entering the next module if any of the following is true:

- Raw Re-DocRED fields are not clear.
- Evidence field coverage is unknown.
- Relation metadata source is unknown or incompatible with prompt/evaluation needs.
- Processed JSONL schema has not been confirmed.
- Deterministic ID rules are not documented.
- Candidate `label`, `gold`, or `gold_evidence_ids` fields do not have a sanitized inference view.
- Negative sampling policy is unclear.
- Evaluation setting is unclear, especially controlled verification versus full extraction.
- Gold evidence handling is unclear or mixed with retrieval input.
- Prompt inputs contain oracle fields.
- Verifier rules require gold labels to decide correctness.
- Smoke test command cannot run.
- Required output files are missing after a module smoke run.

When a stop condition is hit, Codex must report the blocker and ask for user approval before changing the task definition, data contract, or module order.

## Non-Goals

This roadmap does not:

- write implementation code;
- generate all detailed module specs;
- modify the legacy enterprise pipeline;
- design detailed paper experiment tables;
- introduce GNNs;
- introduce Neo4j;
- introduce cross-encoder training;
- introduce multi-agent debate;
- introduce full-document LLM extraction;
- introduce full entity-pair x all-relation brute-force expansion.

## Expected Detailed Specs

Future module specs should be created incrementally:

```text
docs/specs/redocred_schema_inspection.md
docs/specs/redocred_adapter.md
docs/specs/redocred_candidate_generator.md
docs/specs/redocred_sentence_retriever.md
docs/specs/redocred_document_graph.md
docs/specs/redocred_graph_context.md
docs/specs/redocred_prompt_builder.md
docs/specs/redocred_reasoner_integration.md
docs/specs/redocred_verifier.md
docs/specs/redocred_evaluator.md
docs/specs/redocred_pipeline_runner.md
docs/specs/redocred_smoke_scripts.md
```

Each detailed spec should state its exact input files, output files, sanitized view rules, validation commands, and acceptance criteria.
