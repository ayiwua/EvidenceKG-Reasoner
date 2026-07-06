# Phase 3: RelationSchema + MultiRouteCandidateGenerator

## 阶段目标

实现 schema-driven 多关系候选召回，基于 v2 GraphStore 和 `configs/relation_schema.yaml` 输出 `candidate_edges.jsonl`。

## 本阶段范围

- 新增 `configs/relation_schema.yaml`，覆盖 `owned_by`、`runs_on`、`depends_on`。
- 新增候选召回模块：schema type、path、common neighbor、evidence cooccurrence、attribute similarity、source specific。
- 新增 `MultiRouteCandidateGenerator` 合并多路召回结果。
- 新增 CLI：`scripts/generate_candidates.py`。
- 执行 smoke，确认候选生成可单独运行。

## 明确不做什么

- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不改 DatasetBuilder 和 GraphStore。
- 不做 RAG context；Phase 4 负责。
- 不调用 LLM；Phase 5/6 负责。
- 不做 writeback/eval；Phase 7 负责。
- 不保留旧 `TaskConfig + CandidateGenerator` 作为 v2 主链路。

## 预计涉及文件

新增：

- `configs/relation_schema.yaml`
- `scripts/generate_candidates.py`
- `src/evidencekg/candidate/base.py`
- `src/evidencekg/candidate/schema_recall.py`
- `src/evidencekg/candidate/path_recall.py`
- `src/evidencekg/candidate/common_neighbor_recall.py`
- `src/evidencekg/candidate/evidence_cooccurrence_recall.py`
- `src/evidencekg/candidate/attribute_similarity_recall.py`
- `src/evidencekg/candidate/source_specific_recall.py`
- `src/evidencekg/candidate/multi_route_generator.py`

修改：

- `src/evidencekg/candidate/__init__.py`

## 输出产物

- `outputs/candidate_edges.jsonl`
- Phase 3 报告。

## 验收标准

- 能从 `data/processed` 和 relation schema 生成候选。
- 候选包含 `candidate_id`、`head`、`relation`、`tail`、`candidate_score`、`recall_sources`、`debug`。
- 已存在于 `triples.jsonl` 的同关系边默认不输出。
- 每个 relation 遵守 `max_candidates`。
- 输出中至少包含 sample gold 中的若干 `owned_by` 和 `depends_on` 候选。

## Smoke 命令

```powershell
python scripts/generate_candidates.py --data-dir data/processed --relation-schema configs/relation_schema.yaml --out outputs/candidate_edges.jsonl
```

辅助检查：

```powershell
python -c "import json; rows=[json.loads(l) for l in open('outputs/candidate_edges.jsonl', encoding='utf-8') if l.strip()]; print(len(rows)); print(rows[:3])"
```

## 风险与注意事项

- `schema_type` 会产生低分候选，需由 `max_candidates` 和排序控制规模。
- 后续 Phase 4/6 才会判断证据是否真正支持候选；本阶段只负责召回。
