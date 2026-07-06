# Phase 2: GraphStore v2

## 阶段目标

将 GraphStore 迁移为只读取 v2 标准 JSONL 的运行时 KG/索引层，支持实体、关系、证据、类型、别名/名称和路径查询。

## 本阶段范围

- 修改 `src/evidencekg/graph/graph_store.py`，使用 `id` schema。
- 构建 `entity_dict`、`triple_list`、`graph`、`evidence_dict`、`entity_to_evidence`、`entity_by_type`、`relation_index`、`alias/name index`。
- 提供 v2 基础方法：`get_entity`、`get_entities_by_type`、`get_neighbors`、`get_shortest_path`、`get_common_neighbors`、`get_evidence`、`get_evidence_by_entity`、`has_edge`。
- 执行 smoke，确认可读取 Phase 1 的 `data/processed`。

## 明确不做什么

- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不继续兼容 v1 `entity_id/triple_id/evidence_id` 输入。
- 不改 CandidateGenerator；Phase 3 会迁移候选生成。
- 不改 EvidenceRetriever；Phase 4 会迁移 RAG。
- 不改 LLM、Verifier、writeback、evaluation。

## 预计涉及文件

修改：

- `src/evidencekg/graph/graph_store.py`

新增：

- `docs/重构计划/reports/phase_02_report.md`

## 输出产物

- v2 GraphStore。
- Phase 2 报告。

## 验收标准

- `GraphStore.from_dir("data/processed")` 成功。
- 读取结果统计为 36 entities、44 triples、15 evidence。
- `has_edge("svc_payment_api", "runs_on", "ip_10_2_3_4")` 为 True。
- `get_evidence_by_entity("svc_payment_api")` 返回非空。
- `get_shortest_path("svc_payment_api", "team_payment", max_depth=3)` 可通过 ticket/alert 等上下文关系返回路径。

## Smoke 命令

```powershell
python -B -c "import sys; sys.path.insert(0, 'src'); from evidencekg.graph.graph_store import GraphStore; g=GraphStore.from_dir('data/processed'); print(len(g.entity_dict), len(g.triple_list), len(g.evidence_dict)); print(g.has_edge('svc_payment_api','runs_on','ip_10_2_3_4')); print(len(g.get_evidence_by_entity('svc_payment_api'))); print(g.get_shortest_path('svc_payment_api','team_payment',3))"
```

## 风险与注意事项

- v1 tests and pipeline using `data/sample` will fail until later phases migrate or stop using v1 schema.
- This is intentional: v2 does not keep long-term dual schema compatibility.
