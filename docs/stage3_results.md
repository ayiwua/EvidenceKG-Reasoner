# Stage 3 Results

Stage 3 keeps the project scope unchanged: no Neo4j, no frontend, no multi-model voting, no best-of-N, no complex temporal or spatial reasoning, and no KG embedding training. Mock runs are the reproducible ablation experiments. Real LLM runs validate provider-compatible JSON reasoning, verifier compatibility, and the final full Pro baseline.

## Mock Ablation Results

| Setting | Candidate Count | Accepted | Rejected | Uncertain | Precision | Recall | F1 | Verifier Pass Rate | Hit Count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full Mock Pipeline | 102 | 22 | 9 | 71 | 0.5455 | 0.8000 | 0.6486 | 0.9118 | 12 |
| w/o Verifier | 102 | 31 | 0 | 71 | 0.3871 | 0.8000 | 0.5217 | 0.0000 | 12 |
| Entity-text Only | 102 | 0 | 0 | 102 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0 |
| Evidence-only Candidate | 63 | 0 | 0 | 63 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0 |
| Structure-only Candidate | 87 | 17 | 9 | 61 | 0.7059 | 0.8000 | 0.7500 | 0.8966 | 12 |

Additional w/o Verifier risk statistics:

- invalid_evidence_id_count: 9
- low_confidence_accept_count: 0
- conflict_count: 0
- schema_violation_count: 0

## Real LLM Results

| Setting | Reasoned Candidates | Accepted | Rejected | Uncertain | Precision | Recall | F1 | JSON Failures | Timeout | Verifier Failed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Flash Top-10 | 10 | 10 | 0 | 0 | 0.7000 | 0.4667 | 0.5600 | 0 | 0 | 0 |
| Flash Offset-10 | 10 | 2 | 8 | 0 | 0.0000 | 0.0000 | 0.0000 | 0 | 0 | 0 |
| MiMo-v2.5-Pro Full | 102 | 58 | 21 | 23 | 0.2586 | 1.0000 | 0.4110 | 0 | 0 | 6 |

Flash Top-10 and Flash Offset-10 are qualitative small runs. They validate provider connectivity, JSON output, evidence grounding, and verifier compatibility. Recall under `--max-candidates` is not directly comparable with full runs because most candidates are intentionally skipped before reasoning.

MiMo-v2.5-Pro Full is the valid full real LLM baseline. It recovered all 15 hidden gold edges, but accepted 58 final edges, so recall reached 1.0000 while precision stayed low at 0.2586. This suggests the real LLM is biased toward high recall in this task: it is willing to accept many plausible ownership edges when graph and text evidence are present. The Verifier remains necessary for schema, evidence, confidence, and conflict checks, and later stages should add reranking or stricter acceptance calibration to reduce false positives without losing recall.

## Historical MiMo Debug Attempts

The initial MiMo full run used `MIMO-v2.5-pro`. The provider rejected that exact model ID for all 102 candidates, so the real reasoner degraded each candidate to `uncertain`. This run is an invalid model-id rejection / safe degradation test, not a model quality result.

Corrected model IDs were then tested before the full run:

| Model ID | Reasoned Candidates | Accepted | Rejected | Uncertain | Provider Model Error | Timeout | JSON Failures | Missing Supporting Evidence IDs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `mimo-v2.5-pro` | 3 | 0 | 0 | 3 | 0 | 3 | 0 | 0 |
| `xiaomi/mimo-v2.5-pro` | 3 | 0 | 0 | 3 | 0 | 3 | 0 | 0 |

Those timeout tests used an earlier 15-second timeout setting. A later no-retry latency check showed `mimo-v2.5-pro` returns successfully with longer waits, so the full run was executed with `timeout_seconds=120` and `max_retries=0`. The failed `MIMO-v2.5-pro` run is retained only as a safe-degradation check and is not included in the main Real LLM Results table.

## Stability Checks

- Flash Top-10: JSON parse failures 0, provider errors 0, timeouts 0, inferred retry attempts 0, missing supporting evidence IDs 0.
- Flash Offset-10: JSON parse failures 0, provider errors 0, timeouts 0, inferred retry attempts 0, missing supporting evidence IDs 0.
- MiMo-v2.5-Pro Full: accepted 58, rejected 21, uncertain 23, verifier pass rate 0.9412, average confidence 0.7186.
- Initial `MIMO-v2.5-pro` full attempt: JSON parse failures 0, provider model errors 102, timeouts 0, inferred retry attempts 102, missing supporting evidence IDs 0.
- Corrected `mimo-v2.5-pro` max-3 test: JSON parse failures 0, provider model errors 0, timeouts 3, inferred retry attempts 3, missing supporting evidence IDs 0.
- Corrected `xiaomi/mimo-v2.5-pro` max-3 test: JSON parse failures 0, provider model errors 0, timeouts 3, inferred retry attempts 3, missing supporting evidence IDs 0.

## Interpretation

Mock Full is the main reproducible result for module analysis. The w/o Verifier run shows why raw accept outputs should not be written directly to final predictions: accepted edges increase from 22 to 31, but precision drops from 0.5455 to 0.3871 and invalid supporting evidence IDs appear. Entity-text-only and evidence-only settings are intentionally weak in this mock setup. Structure-only candidate generation performs well on the sample KG because the hidden ownership edges are strongly represented by two-hop paths and shared graph neighborhoods.

Stage 3 is complete: the project now has full mock ablations, real LLM small-sample validation, and a valid MiMo-v2.5-Pro full run. The main next improvement is precision control for real LLM mode, likely through stronger verifier thresholds, candidate reranking, or calibrated acceptance policies.
