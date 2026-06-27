# EvidenceKG-Reasoner

EvidenceKG-Reasoner is a GraphRAG-based evidence reasoning system for enterprise IP and IT asset knowledge graphs.

The first stage implements a fully local Mock Pipeline. It does not call a real LLM, does not require an API key, and uses structured graph evidence plus a rule-based mock reasoner to produce verifiable candidate relation predictions.

## Main Pipeline

```text
JSONL KG loading
  -> schema filter and candidate generation
  -> graph / BM25 / optional embedding evidence retrieval
  -> structured context and prompt preparation
  -> MockReasoner
  -> Verifier
  -> verified_predictions.jsonl
  -> predicted_edges.jsonl
  -> hidden edge recovery evaluation
```

The target relation is read from `configs/task_owned_by.yaml`. The default first-stage task uses `likely_owned_by`, but the pipeline code is configuration-driven and does not hard-code that relation.

## Evidence Retrieval

`EvidenceRetriever` now uses a fixed two-stage Evidence RAG flow:

```text
candidate relation
  -> graph-aware candidate query construction
  -> bi-encoder dense retrieval over evidence corpus
  -> cross-encoder evidence reranking
  -> evidence-grounded LLM reasoning
  -> verifier grounding check
```

The graph still matters: candidate generation, graph paths, common neighbors, entity profiles, and related triples remain part of the pipeline. They are used to construct a richer retrieval query and to populate the prompt context, but evidence selection is no longer BM25 or related-entity overlap.

The default retrieval config is:

```yaml
evidence_retrieval:
  top_k_before_rerank: 30
  top_k_after_rerank: 8
  bi_encoder_model: sentence-transformers/all-MiniLM-L6-v2
  cross_encoder_model: cross-encoder/ms-marco-MiniLM-L-6-v2
```

Each evidence document is encoded from its text, source, related entities, timestamp, reliability, and related entity names/types/descriptions. For each candidate, the retriever builds a query from the target relation, head/tail profiles, common neighbors, graph path summaries, and related triples.

At runtime, the bi-encoder recalls `top_k_before_rerank` evidence snippets with cosine similarity. The cross-encoder then scores `(candidate_query, evidence_text)` pairs and the retriever returns `top_k_after_rerank` snippets. Returned snippets keep their original evidence fields and add `embedding_score`, `rerank_score`, `retrieval_query`, and `retrieval_rank`.

This is still local in-memory retrieval, not an external vector database system: there is no Chroma, Milvus, or FAISS service. There is also no BM25 mode and no retrieval-mode switch. If `sentence-transformers` or the configured models are unavailable, the error is exposed so the environment can be fixed.

The LLM still cannot cite arbitrary evidence. `supporting_evidence_ids` must come from the current context's `evidence_snippets`, and the Verifier keeps checking that grounding before an accepted relation is written.

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

This uses:

```yaml
llm:
  mode: mock
```

Mock mode is fully local and does not require an API key.

## Run Real LLM Pipeline

Real mode uses an OpenAI-compatible chat completions interface. "OpenAI-compatible" means the provider exposes an OpenAI-style `/chat/completions` API, while `base_url`, `api_key`, and `model` can point to different providers.

Examples include:

- OpenAI
- DeepSeek
- local LM Studio server

The default config still uses:

```yaml
llm:
  mode: real
  provider: openai_compatible
```

Copy `.env.example` to `.env` and set the provider values:

```powershell
Copy-Item .env.example .env
notepad .env
```

Example `.env` for OpenAI:

```text
LLM_API_KEY=your_provider_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Example `.env` for DeepSeek:

```text
LLM_API_KEY=your_deepseek_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

Example `.env` for LM Studio:

```text
LLM_API_KEY=lm-studio
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=local-model
```

Then run real mode:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real
```

For a small real LLM acceptance run, limit only the candidates that enter evidence retrieval and reasoning:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real --max-candidates 10
```

`--max-candidates` does not change full candidate generation. It still writes the full `candidate_pairs.jsonl`, then truncates the list before evidence retrieval, LLM reasoning, verifier review, and evaluation. By default it is unset, so mock and real pipelines run all generated candidates.

Use `--candidate-offset` with `--max-candidates` to inspect non-top candidates:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real_offset40 --candidate-offset 40 --max-candidates 10
```

Top-k small runs are useful for high-confidence candidate validation. Offset runs are useful for checking weaker-evidence candidates and verifier stability beyond the top-ranked slice.

Real mode shows a compact tqdm progress bar during LLM reasoning so long provider calls have visible progress without printing one line per candidate.
It also logs candidate-level call start/end messages, elapsed time, decision, confidence, and warning messages for timeout, retry, or degradation to `uncertain`.

The real LLM receives `PromptBuilder.prompt_text` and must return JSON with:

```json
{
  "decision": "accept | reject | uncertain",
  "confidence": 0.0,
  "reason": "short explanation",
  "supporting_evidence_ids": []
}
```

If the provider is unavailable, times out, or returns invalid JSON after retries, the reasoner degrades the prediction to `uncertain` with `confidence=0.0`. Real LLM outputs still pass through the same Verifier before final edges are written.

## Real LLM Small Run

Use `--max-candidates` for low-cost real LLM acceptance checks:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real_10 --max-candidates 10
```

This is useful for checking provider connectivity, JSON output quality, verifier behavior, and rough precision on the top-ranked candidates.

Important caveats:

- `--max-candidates` only limits candidates entering evidence retrieval, LLM reasoning, verifier review, and evaluation.
- `--candidate-offset` skips N generated candidates before applying `--max-candidates`, so non-top candidates can be sampled without changing candidate generation.
- `candidate_pairs.jsonl` is still generated from the full candidate set.
- Recall from a small run should not be compared directly with full mock or full real experiments, because most candidates were intentionally not reasoned over.
- A small real run is not the final full real evaluation.
- Mock mode remains the default fully reproducible result because it requires no API key and runs all candidates.

Run candidate generation only:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs --stage candidates
```

Run with KG writeback staging enabled:

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs --enable-writeback --writeback-mode pending
```

`pending` mode writes verified accepted edges to `pending_edges.jsonl` for review. `approved` mode writes `triples.enriched.jsonl`, which contains the original triples plus approved prediction edges. The source `data/sample/triples.jsonl` is never overwritten.

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
- `pending_edges.jsonl`: optional writeback staging file when `--enable-writeback --writeback-mode pending` is used.
- `triples.enriched.jsonl`: optional enriched KG file when `--enable-writeback --writeback-mode approved` is used.
- `writeback_report.json`: optional writeback counts for `pending`, `skipped_duplicate`, `skipped_conflict`, `approved`, and `written_count`.

## Stage 1 Mock Pipeline Result

The default reproducible mock run uses all 102 generated candidates:

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

## Stage 2 Real LLM Small Run

Real mode has been validated with low-cost small runs. These runs are not full real evaluations; they are used to check provider connectivity, JSON output shape, evidence grounding, verifier compatibility, and degradation behavior.

| Setting | Reasoned Candidates | Accepted | Rejected | Uncertain | Precision | Recall | F1 | JSON Failures | Timeout |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Flash Top-10 | 10 | 10 | 0 | 0 | 0.7000 | 0.4667 | 0.5600 | 0 | 0 |
| Flash Offset-10 | 10 | 2 | 8 | 0 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 |

`--max-candidates` small-run recall should not be compared directly with full experiments, because the run intentionally reasons over only a slice of the generated candidate set.

## Stage 3 Ablation Results

The main Stage 3 ablations use MockReasoner for full, reproducible 102-candidate module analysis.

| Setting | Candidate Count | Accepted | Rejected | Uncertain | Precision | Recall | F1 | Verifier Pass Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full Mock Pipeline | 102 | 22 | 9 | 71 | 0.5455 | 0.8000 | 0.6486 | 0.9118 |
| w/o Verifier | 102 | 31 | 0 | 71 | 0.3871 | 0.8000 | 0.5217 | 0.0000 |
| Entity-text Only | 102 | 0 | 0 | 102 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| Evidence-only Candidate | 63 | 0 | 0 | 63 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| Structure-only Candidate | 87 | 17 | 9 | 61 | 0.7059 | 0.8000 | 0.7500 | 0.8966 |

See `docs/stage3_results.md` for the full result table and interpretation.

## Real LLM Full Run Result

MiMo-v2.5-Pro has completed a valid full real LLM baseline with all 102 generated candidates:

```json
{
  "accepted_count": 58,
  "average_confidence": 0.7186,
  "candidate_count": 102,
  "f1": 0.411,
  "gold_count": 15,
  "hit_count": 15,
  "precision": 0.2586,
  "predicted_edge_count": 58,
  "recall": 1.0,
  "rejected_count": 21,
  "uncertain_count": 23,
  "verifier_pass_rate": 0.9412
}
```

The valid model ID is `mimo-v2.5-pro`. The earlier `MIMO-v2.5-pro` attempt was a provider model-id mismatch and is recorded only as a safe degradation test, not as a model quality result.

MiMo-v2.5-Pro achieved recall `1.0`, recovering all 15 hidden gold edges, but precision was lower at `0.2586`. This shows the real LLM is biased toward high recall in this task and accepts many plausible ownership candidates. The Verifier is still necessary, and later work should add reranking or stricter acceptance calibration to reduce false positives.

Mock is used for reproducible module ablation. Flash is used for low-cost real LLM integration checks. MiMo-v2.5-Pro is the current full real inference baseline. Stage 3 now includes mock ablations, real LLM small-sample validation, and the Pro full run.

## Project Constraints

The current scope intentionally does not include:

- Neo4j
- frontend UI
- multi-model voting
- best-of-N
- complex temporal or spatial reasoning
- time pool or space pool
- GNN, TransE, RotatE, or other traditional KG completion training
- real enterprise data ingestion
- free-form LLM candidate generation from the whole graph

`type_rule` is only a schema filter. A candidate must have a legal head / tail type pair and must also match at least one structure or evidence rule: `two_hop_path`, `common_neighbor`, or `evidence_overlap`.
