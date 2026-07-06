# EvidenceKG-Reasoner v2 重构最终报告

## 完成结论

已按 Phase 0 -> Phase 7 完成 EvidenceKG-Reasoner v2 重构，并跑通 sample data 完整 pipeline。

v2 主流程：

```text
raw CSV
-> DatasetBuilder
-> v2 JSONL
-> GraphStore v2
-> RelationSchema
-> MultiRouteCandidateGenerator
-> Relation-aware Evidence RAG
-> LLMReasoner via LLMClient
-> HardVerifier
-> SemanticVerifier
-> PendingWriteback
-> ReviewApplier
-> Evaluation report
```

## 最终验收命令

```powershell
python scripts/build_dataset_from_csv.py --manifest configs/dataset_manifest.yaml --raw-dir data/raw --out-dir data/processed
python scripts/run_pipeline.py --data-dir data/processed --relation-schema configs/relation_schema.yaml --llm-config configs/llm.yaml --out-dir outputs
python scripts/apply_review.py --triples data/processed/triples.jsonl --pending outputs/pending_edges.jsonl --review outputs/review_decisions.jsonl --out outputs/triples.enriched.jsonl
```

## 最终结果

- candidates: 60
- evidence contexts: 60
- llm predictions: 60
- verified predictions: 60
- pending edges: 14
- review decisions: 14
- enriched triples: 58
- original triples: 44

Final metrics:

```json
{
  "precision": 0.5,
  "recall": 1.0,
  "f1": 0.6667,
  "hit_count": 7,
  "pending_edge_count": 14,
  "gold_count": 7
}
```

## 重要约束执行情况

- Phase 0 后未修改 `docs/重构计划/codex改进提示词.md`。
- v2 JSONL 使用 `id` schema，不继续扩散 v1 `entity_id/triple_id/evidence_id`。
- `gold_hidden_edges.jsonl` 未进入 `triples.jsonl`。
- MockLLM 仅用于 smoke run。
- keyword-only retrieval 显式记录 `degraded=true` 和 `fallback_reason`。
- writeback 不覆盖原始 triples。
- 未引入 Agent、Neo4j、微调或外部服务。

## 已知未完成

- 真实 LLM provider 未在本轮执行。
- dense embedding / cross-encoder retrieval 未启用。
- v1 旧测试未整体迁移到 v2 schema。
