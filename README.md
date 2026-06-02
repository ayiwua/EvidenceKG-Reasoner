# EvidenceKG-Reasoner

EvidenceKG-Reasoner is a GraphRAG-based evidence reasoning system for enterprise IP and IT asset knowledge graphs.

The first stage implements a fully local Mock Pipeline. It does not call a real LLM, does not require an API key, and uses structured graph evidence plus a rule-based mock reasoner to produce verifiable candidate relation predictions.

## Main Pipeline

```text
JSONL KG loading
  -> schema filter and candidate generation
  -> graph evidence retrieval
  -> structured context and prompt preparation
  -> MockReasoner
  -> Verifier
  -> verified_predictions.jsonl
  -> predicted_edges.jsonl
  -> hidden edge recovery evaluation
```

The target relation is read from `configs/task_owned_by.yaml`. The default first-stage task uses `likely_owned_by`, but the pipeline code is configuration-driven and does not hard-code that relation.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run Mock Pipeline

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs
```

Run candidate generation only:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs --stage candidates
```

Run evaluation only:

```powershell
python scripts/run_evaluation.py --predicted outputs/predicted_edges.jsonl --verified outputs/verified_predictions.jsonl --gold data/sample/gold_hidden_edges.jsonl --output outputs/evaluation_report.json
```

Run tests:

```powershell
python -m pytest
```

## Input Files

The sample KG lives in `data/sample/`.

- `entities.jsonl`: entity nodes such as IPs, hosts, services, APIs, databases, applications, teams, departments, people, tickets, documents, and alerts.
- `triples.jsonl`: existing KG relations. These do not include the hidden target `likely_owned_by` edges.
- `evidence.jsonl`: traceable evidence snippets from tickets, documents, alerts, scan logs, CMDB records, and operation notes.
- `gold_hidden_edges.jsonl`: hidden gold edges used for hidden edge recovery evaluation.

Sample data scale:

- entities: 76
- triples: 131
- evidence: 42
- gold hidden edges: 15

## Output Files

The pipeline writes outputs to `outputs/`.

- `candidate_pairs.jsonl`: generated candidate relations. Each candidate includes `generation_rules`, `rule_scores`, and `candidate_score`.
- `evidence_contexts.jsonl`: graph paths, related triples, entity profiles, common neighbors, and evidence snippets for each candidate.
- `verified_predictions.jsonl`: all candidate predictions after verifier review, including `accept`, `reject`, and `uncertain`.
- `predicted_edges.jsonl`: only final accepted edges where `decision=accept` and `verifier_status=passed`.
- `evaluation_report.json`: hidden edge recovery metrics.

## Sample Evaluation

Latest sample run:

```json
{
  "accepted_count": 22,
  "average_confidence": 0.5985,
  "candidate_count": 102,
  "f1": 0.6486,
  "gold_count": 15,
  "hit_count": 12,
  "precision": 0.5455,
  "predicted_edge_count": 22,
  "recall": 0.8,
  "rejected_count": 9,
  "uncertain_count": 71,
  "verifier_pass_rate": 0.9118
}
```

Precision, recall, and F1 are computed only from `predicted_edges.jsonl`. Rejected and uncertain records are used for statistics and verifier behavior analysis through `verified_predictions.jsonl`.

## First-Stage Constraints

This stage intentionally does not include:

- real LLM calls
- API keys
- Neo4j
- frontend UI
- multi-model voting
- complex temporal or spatial reasoning
- time pool or space pool
- GNN, TransE, RotatE, or other traditional KG completion training
- real enterprise data ingestion
- free-form LLM candidate generation from the whole graph

`type_rule` is only a schema filter. A candidate must have a legal head / tail type pair and must also match at least one structure or evidence rule: `two_hop_path`, `common_neighbor`, or `evidence_overlap`.

## Real LLM Plan

The next stage should add a real LLM provider without changing the main pipeline shape:

- keep `PipelineRunner` orchestration stable
- keep `TaskConfig` as the control surface
- extend `PromptBuilder.prompt_text`
- add an OpenAI-compatible client under `src/evidencekg/llm/`
- implement JSON parsing, retries, timeout handling, and parse-failure recovery
- keep Verifier mandatory before writing final predicted edges
