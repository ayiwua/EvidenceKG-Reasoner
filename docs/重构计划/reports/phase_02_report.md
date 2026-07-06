# Phase 2 报告：GraphStore v2

## 实际新增文件

- `docs/重构计划/phase_02_graph_store.md`
- `docs/重构计划/reports/phase_02_report.md`

## 实际修改文件

- `src/evidencekg/graph/graph_store.py`

## 删除的旧链路或废弃接口

- GraphStore 不再读取 v1 `entity_id/triple_id/evidence_id` schema。
- GraphStore v2 只接受标准 `id`、`head`、`relation`、`tail`、`source_file/source_row_id` 等 Phase 1 输出字段。
- 旧 `get_evidence_for_triple` 被移除；v2 triples 不在本阶段携带 `evidence_ids`，证据通过 `entity_to_evidence` 和后续 RAG 组织。

## 完成能力

- 构建 `entity_dict`、`triple_list`、`triple_dict`。
- 构建 NetworkX `MultiDiGraph`。
- 构建 `evidence_dict`、`entity_to_evidence`、`entity_by_type`、`relation_index`。
- 构建 name/alias index。
- 支持 `get_entity`、`get_entities_by_type`、`get_neighbors`、`get_shortest_path`、`find_paths`、`get_common_neighbors`、`get_evidence`、`get_evidence_by_entity`、`has_edge`。
- 对缺失字段、重复 ID、未知实体引用 fail fast。

## 验收命令与结果

执行：

```powershell
python -B -c "import sys; sys.path.insert(0, 'src'); from evidencekg.graph.graph_store import GraphStore; g=GraphStore.from_dir('data/processed'); print(len(g.entity_dict), len(g.triple_list), len(g.evidence_dict)); print(g.has_edge('svc_payment_api','runs_on','ip_10_2_3_4')); print(len(g.get_evidence_by_entity('svc_payment_api'))); print(g.get_shortest_path('svc_payment_api','team_payment',3)); print(g.search_entities('payment-api'))"
```

结果：

```text
36 44 15
True
4
['svc_payment_api', 'alert_alt_2001', 'team_payment']
['svc_payment_api']
```

## 未完成项

- CandidateGenerator 仍是 v1 单任务实现，尚未迁移到 relation schema driven 多路召回。
- EvidenceRetriever、LLM、Verifier、writeback/eval 尚未迁移。
- 旧 `data/sample` v1 schema 不再适用于 GraphStore v2。

## 偏离原计划的地方

- 保留了 `entities/triples/evidence` 属性作为 v2 dict 别名，便于后续阶段逐步迁移模块；这些别名不支持 v1 字段，不构成双 schema 兼容。

## 是否建议进入下一阶段

建议进入 Phase 3：RelationSchema + MultiRouteCandidateGenerator。
