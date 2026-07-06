# Phase 7 报告：Pending Writeback + Eval + Pipeline

## 实际新增文件

- `docs/重构计划/phase_07_writeback_and_eval.md`
- `docs/重构计划/reports/phase_07_report.md`
- `scripts/apply_review.py`
- `outputs/review_decisions.jsonl`
- `outputs/triples.enriched.jsonl`
- `outputs/evaluation_report.json`

## 实际修改文件

- `src/evidencekg/writeback.py`
- `src/evidencekg/eval/evaluator.py`
- `scripts/run_pipeline.py`

## 删除的旧链路或废弃接口

- `scripts/run_pipeline.py` 已从 v1 `TaskConfig/PipelineRunner` CLI 替换为 v2 主入口：
  - `--data-dir`
  - `--relation-schema`
  - `--llm-config`
  - `--out-dir`
- v2 主链路不再输出 `candidate_pairs.jsonl` / `predicted_edges.jsonl`。
- v2 writeback 使用 `pending_edges.jsonl` + `review_decisions.jsonl` + `triples.enriched.jsonl`，不覆盖原始 triples。

## 完成能力

- PendingWriteback 输出待审核补边。
- ReviewApplier 根据 review decisions 生成 enriched triples。
- V2Evaluator 输出 candidate、retrieval、llm、verifier、final 指标。
- v2 sample pipeline 端到端跑通。

## 验收命令与结果

完整 pipeline：

```powershell
python scripts/run_pipeline.py --data-dir data/processed --relation-schema configs/relation_schema.yaml --llm-config configs/llm.yaml --out-dir outputs
```

结果摘要：

```json
{
  "candidate": {
    "candidate_count": 60,
    "candidate_recall_if_gold_available": 1.0
  },
  "final": {
    "precision": 0.5,
    "recall": 1.0,
    "f1": 0.6667,
    "hit_count": 7,
    "pending_edge_count": 14,
    "gold_count": 7
  },
  "writeback": {
    "pending_count": 14,
    "review_decision_count": 14
  }
}
```

独立 apply_review：

```powershell
python scripts/apply_review.py --triples data/processed/triples.jsonl --pending outputs/pending_edges.jsonl --review outputs/review_decisions.jsonl --out outputs/triples.enriched.jsonl
```

结果：

```json
{
  "approved": 14,
  "output_count": 58,
  "rejected": 0,
  "skipped": 0
}
```

输出完整性检查：

```powershell
python -c "import json, pathlib; files=['candidate_edges.jsonl','evidence_contexts.jsonl','llm_predictions.jsonl','verified_predictions.jsonl','pending_edges.jsonl','review_decisions.jsonl','triples.enriched.jsonl']; root=pathlib.Path('outputs'); print({name: sum(1 for _ in open(root/name, encoding='utf-8')) for name in files}); print(json.load(open(root/'evaluation_report.json', encoding='utf-8'))['final']); print(sum(1 for _ in open('data/processed/triples.jsonl', encoding='utf-8')))"
```

结果：

```text
{'candidate_edges.jsonl': 60, 'evidence_contexts.jsonl': 60, 'llm_predictions.jsonl': 60, 'verified_predictions.jsonl': 60, 'pending_edges.jsonl': 14, 'review_decisions.jsonl': 14, 'triples.enriched.jsonl': 58}
{'f1': 0.6667, 'gold_count': 7, 'hit_count': 7, 'pending_edge_count': 14, 'precision': 0.5, 'recall': 1.0}
44
```

原始 `data/processed/triples.jsonl` 保持 44 条，未被覆盖。

## 未完成项

- 未启用真实 LLM provider。
- 未启用 dense embedding / cross-encoder retrieval。
- 未补齐全面单元测试；本轮按阶段要求执行 smoke 验证。

## 偏离原计划的地方

- sample smoke 自动生成 `review_decisions.jsonl` 且全部 approved，用于验证 `apply_review` 链路；真实使用时应人工审核。
- 写 `outputs/*` 时受限环境多次拒绝仓库内输出写入，完整 pipeline 和 apply_review smoke 使用提升权限执行。

## 是否建议进入下一阶段

Phase 7 已完成。建议以 `docs/重构计划/reports/final_report.md` 作为本轮 v2 重构最终报告。
