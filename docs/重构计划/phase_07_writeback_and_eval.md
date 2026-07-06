# Phase 7: Pending Writeback + Eval + Pipeline

## 阶段目标

实现待审核写回、review apply、evaluation_report，并跑通 sample data 的完整 v2 pipeline。

## 本阶段范围

- 新增 `PendingWriteback`，从 verified predictions 输出 `pending_edges.jsonl`。
- 新增 `scripts/apply_review.py`，根据 `review_decisions.jsonl` 生成 `triples.enriched.jsonl`，不覆盖原始 triples。
- 新增 v2 evaluation report。
- 将 `scripts/run_pipeline.py` 改为 v2 主入口，串联 candidate、RAG、MockLLM reasoner、verifier、pending writeback、evaluation。
- 执行完整 sample pipeline smoke。

## 明确不做什么

- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不直接覆盖 `data/processed/triples.jsonl`。
- 不调用真实 LLM。
- 不引入 Agent、Neo4j、微调或外部服务。

## 预计涉及文件

新增：

- `scripts/apply_review.py`
- `docs/重构计划/reports/phase_07_report.md`
- `docs/重构计划/reports/final_report.md`

修改：

- `src/evidencekg/writeback.py`
- `src/evidencekg/eval/evaluator.py`
- `scripts/run_pipeline.py`

## 输出产物

- `outputs/candidate_edges.jsonl`
- `outputs/evidence_contexts.jsonl`
- `outputs/llm_predictions.jsonl`
- `outputs/verified_predictions.jsonl`
- `outputs/pending_edges.jsonl`
- `outputs/review_decisions.jsonl`
- `outputs/triples.enriched.jsonl`
- `outputs/evaluation_report.json`

## 验收标准

- `scripts/run_pipeline.py` 跑通 sample pipeline。
- evaluation_report 包含 candidate、retrieval、llm、verifier、final。
- pending_edges 只包含 accept + hard passed + semantic supported 的边。
- apply_review 不覆盖原始 triples。

## Smoke 命令

```powershell
python scripts/run_pipeline.py --data-dir data/processed --relation-schema configs/relation_schema.yaml --llm-config configs/llm.yaml --out-dir outputs
```

```powershell
python scripts/apply_review.py --triples data/processed/triples.jsonl --pending outputs/pending_edges.jsonl --review outputs/review_decisions.jsonl --out outputs/triples.enriched.jsonl
```

## 风险与注意事项

- MockLLM 用于 smoke，真实 LLM 质量不在本阶段评估。
- review_decisions 在 sample smoke 中自动生成 approved，以验证 apply_review 链路；真实使用时应由人工审核。
