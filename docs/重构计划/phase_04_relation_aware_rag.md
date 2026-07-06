# Phase 4: Relation-aware Graph Evidence RAG

## 阶段目标

将 EvidenceRetriever 迁移为 relation-aware evidence context builder，为每条候选关系输出结构化 `evidence_contexts.jsonl`。

## 本阶段范围

- 基于 relation schema 构造 relation-aware query。
- 支持 preferred source、head/tail 相关实体和 reliability 的 metadata scoring。
- 支持 keyword-only smoke 模式，并显式记录 `degraded=true` 与 `fallback_reason`。
- 支持 evidence expansion：从初始证据的 related entities 扩展相关 evidence。
- 区分 `supporting_evidence_candidates` 和 `conflict_evidence_candidates`。
- 输出结构化 context，而不是简单 topK 拼接。
- 新增 CLI：`scripts/retrieve_evidence_contexts.py`。

## 明确不做什么

- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不引入外部向量库。
- 不联网下载 embedding 或 reranker 模型。
- 不调用 LLM。
- 不做最终 verifier 判断；Phase 6 负责。
- 不做 writeback/eval；Phase 7 负责。

## 预计涉及文件

新增：

- `scripts/retrieve_evidence_contexts.py`
- `docs/重构计划/reports/phase_04_report.md`

修改：

- `src/evidencekg/retrieval/evidence_retriever.py`

## 输出产物

- `outputs/evidence_contexts.jsonl`
- Phase 4 报告。

## 验收标准

- 能读取 `outputs/candidate_edges.jsonl` 并输出同数量 contexts。
- 每个 context 包含 `candidate`、`relation_query`、`retrieval_metadata`、`supporting_evidence_candidates`、`conflict_evidence_candidates`、`packed_context`。
- keyword-only smoke 必须显式记录 degraded。
- 至少部分 gold 候选能检索到包含 head/tail 的 supporting evidence。

## Smoke 命令

```powershell
python scripts/retrieve_evidence_contexts.py --data-dir data/processed --relation-schema configs/relation_schema.yaml --candidates outputs/candidate_edges.jsonl --out outputs/evidence_contexts.jsonl --allow-keyword-only
```

辅助检查：

```powershell
python -c "import json; rows=[json.loads(l) for l in open('outputs/evidence_contexts.jsonl', encoding='utf-8') if l.strip()]; print(len(rows)); print(rows[0]['retrieval_metadata']); print(len(rows[0]['supporting_evidence_candidates']))"
```

## 风险与注意事项

- 本阶段不做 dense embedding，因为 smoke 不能依赖外部模型；keyword-only 是显式配置的 degraded 模式。
- 后续如启用 embedding 或 cross-encoder，不可在模型不可用时静默降级。
