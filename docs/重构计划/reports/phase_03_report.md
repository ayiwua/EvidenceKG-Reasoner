# Phase 3 报告：RelationSchema + MultiRouteCandidateGenerator

## 实际新增文件

- `docs/重构计划/phase_03_candidate_generation.md`
- `docs/重构计划/reports/phase_03_report.md`
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
- `outputs/candidate_edges.jsonl`

## 实际修改文件

- `src/evidencekg/candidate/__init__.py`

## 删除的旧链路或废弃接口

- 本阶段未删除旧 `src/evidencekg/candidate/generator.py`，但 v2 主链路已切到 `MultiRouteCandidateGenerator`。
- v2 候选输出不使用 `generation_rules/rule_scores/paths/common_neighbors` 旧 schema，改为 `recall_sources` 和 `debug`。

## 完成能力

- relation schema 覆盖 `owned_by`、`runs_on`、`depends_on`。
- 多路召回覆盖 schema type、path、common neighbor、evidence cooccurrence、attribute similarity、source specific。
- 相同 `(head, relation, tail)` 候选合并计分。
- 默认过滤 `triples.jsonl` 中已存在的同关系边。
- 每个 relation 按 `max_candidates` 限流。

## 验收命令与结果

执行：

```powershell
python scripts/generate_candidates.py --data-dir data/processed --relation-schema configs/relation_schema.yaml --out outputs/candidate_edges.jsonl
```

结果：

```json
{
  "candidate_count": 60,
  "candidate_count_by_relation": {
    "depends_on": 20,
    "owned_by": 20,
    "runs_on": 20
  }
}
```

schema 检查：

```powershell
python -c "import json; rows=[json.loads(l) for l in open('outputs/candidate_edges.jsonl', encoding='utf-8') if l.strip()]; print(len(rows)); print(rows[0]); print(all({'candidate_id','head','relation','tail','candidate_score','recall_sources','debug'} <= set(r) for r in rows))"
```

结果：`60`，首条候选字段完整，字段检查为 `True`。

gold 召回检查：

```powershell
python -c "import json; cand={(r['head'],r['relation'],r['tail']) for r in map(json.loads, open('outputs/candidate_edges.jsonl', encoding='utf-8'))}; gold={(r['head'],r['relation'],r['tail']) for r in map(json.loads, open('data/processed/gold_hidden_edges.jsonl', encoding='utf-8'))}; print(len(cand & gold), sorted(cand & gold))"
```

结果：`7`，sample gold 全部召回。

已存在边过滤检查：

```powershell
python -c "import json; triples={(r['head'],r['relation'],r['tail']) for r in map(json.loads, open('data/processed/triples.jsonl', encoding='utf-8'))}; cand={(r['head'],r['relation'],r['tail']) for r in map(json.loads, open('outputs/candidate_edges.jsonl', encoding='utf-8'))}; print(len(triples & cand))"
```

结果：`0`。

## 未完成项

- 候选证据组织尚未完成，Phase 4 实现 relation-aware RAG。
- LLM adapter、Reasoner、Verifier、writeback/eval 尚未迁移。

## 偏离原计划的地方

- 写 `outputs/candidate_edges.jsonl` 时受限环境拒绝仓库内输出写入，已使用提升权限重跑同一命令。

## 是否建议进入下一阶段

建议进入 Phase 4：Relation-aware RAG。
