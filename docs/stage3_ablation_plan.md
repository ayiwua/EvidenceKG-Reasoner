# Stage 3 Ablation Experiment Plan

## Goal

Stage 3 evaluates which parts of EvidenceKG-Reasoner improve hidden edge recovery and reliability. The scope remains unchanged: no Neo4j, no frontend, no multi-model voting, no best-of-N, no complex temporal or spatial reasoning, and no traditional KG completion training.

Every experiment should report precision, recall, F1, candidate_count, accepted_count, rejected_count, uncertain_count, verifier_pass_rate, average_confidence, hit_count, and predicted_edge_count.

## 1. Full Pipeline

Use the default pipeline with all candidate rules, graph evidence, MockReasoner or real LLM, Verifier, and hidden edge evaluation.

Config:

- `configs/task_owned_by.yaml` for reproducible mock full run.
- `configs/task_owned_by_real.yaml --max-candidates 10` for low-cost real LLM qualitative checks.
- Candidate rules: `two_hop_path`, `common_neighbor`, `evidence_overlap`.
- Evidence context includes graph paths, common neighbors, related triples, entity profiles, and evidence snippets.

Outputs:

- `candidate_pairs.jsonl`
- `evidence_contexts.jsonl`
- `verified_predictions.jsonl`
- `predicted_edges.jsonl`
- `evaluation_report.json`

Expected observation:

This should be the strongest default setting. Mock full run is the reproducible baseline; real top-k run checks JSON quality, evidence grounding, and verifier compatibility.

## 2. Without Verifier

Purpose:

Show why LLM outputs should not be written directly into final predictions.

Config changes:

- Add an ablation-specific runner option or config that bypasses Verifier only for this experiment.
- Write raw reasoner outputs directly into ablation predicted edges.
- Do not change CandidateGenerator, EvidenceRetriever, or Evaluator.

Outputs:

- raw predictions
- ablation `predicted_edges.jsonl`
- ablation `evaluation_report.json`

Metrics:

- precision, recall, F1
- accepted_count
- invalid_evidence_id_count
- schema_violation_count

Expected observation:

Recall may rise because fewer outputs are filtered, but precision and evidence reliability should drop. This should make the Verifier's reliability role visible.

## 3. Without Graph Evidence

Purpose:

Measure whether graph paths, common neighbors, and related triples improve reasoning beyond entity profiles and text snippets.

Config changes:

- Create an ablation retrieval config that excludes `graph_paths`, `common_neighbors`, and `related_triples`.
- Keep `head_profile`, `tail_profile`, and `evidence_snippets`.
- Keep candidate generation and Verifier unchanged.

Outputs:

- evidence contexts without graph evidence
- verified predictions
- predicted edges
- evaluation report

Metrics:

- precision, recall, F1
- accepted_count
- uncertain_count
- average_confidence

Expected observation:

The LLM should become less confident or produce more uncertain decisions. Precision may remain acceptable for direct evidence cases, but recall and confidence should drop when ownership depends on multi-hop graph structure.

## 4. Full Candidate Rules vs Weak Candidate Baseline

Purpose:

Evaluate candidate generation quality.

Full candidate rules:

- `two_hop_path`
- `common_neighbor`
- `evidence_overlap`

Weak candidate baseline:

- Use only one weaker structure/evidence rule, such as `evidence_overlap` only or `two_hop_path` only.
- Keep `type_rule` as schema filter only. It must not become a standalone candidate generator.

Outputs:

- candidate pairs for each setting
- evaluation report for each setting
- candidate_count comparison

Metrics:

- candidate_count
- precision, recall, F1
- hit_count
- verifier_pass_rate

Expected observation:

Full rules should improve recall by generating more recoverable hidden edges. Weak baselines may have fewer candidates and possibly higher precision in narrow cases, but should miss more gold edges.

## 5. Mock Full Run vs Real Top-10 Qualitative Comparison

Purpose:

Compare the deterministic mock full run with low-cost real LLM top-k reasoning.

Commands:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real_10 --max-candidates 10
```

Outputs:

- mock `evaluation_report.json`
- real top-10 `evaluation_report.json`
- selected real `verified_predictions.jsonl` examples

Metrics:

- precision, recall, F1
- accepted_count, rejected_count, uncertain_count
- JSON parse failure count
- timeout/retry count
- missing supporting evidence id count

Expected observation:

Mock full run is the reproducible baseline and covers all candidates. Real top-10 should not be treated as full real evaluation because recall is limited by `--max-candidates`; it is mainly useful for qualitative reasoning and evidence-grounding checks.

## Notes

- Keep `best_of_n=1`.
- Do not add multi-model voting.
- Do not train KG embedding or GNN models.
- Keep target relation controlled by `TaskConfig`.
- All LLM outputs must pass through Verifier except in the explicit `without verifier` ablation.
