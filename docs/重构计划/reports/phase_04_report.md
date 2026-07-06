# Phase 4 报告：Relation-aware Graph Evidence RAG

## 实际新增文件

- `docs/重构计划/phase_04_relation_aware_rag.md`
- `docs/重构计划/reports/phase_04_report.md`
- `scripts/retrieve_evidence_contexts.py`
- `outputs/evidence_contexts.jsonl`

## 实际修改文件

- `src/evidencekg/retrieval/evidence_retriever.py`

## 删除的旧链路或废弃接口

- EvidenceRetriever 不再使用 v1 `TaskConfig` 接口。
- 删除旧 dense-only 默认检索路径；本阶段 smoke 使用显式 keyword-only degraded 模式。
- 不再输出旧 `evidence_snippets`，改为 `supporting_evidence_candidates`、`conflict_evidence_candidates` 和 `packed_context`。

## 完成能力

- relation-aware query builder。
- preferred source、head/tail、reliability 和 keyword overlap scoring。
- evidence expansion。
- supporting/conflict evidence 分区。
- 结构化 context packing。
- keyword-only degraded 状态显式记录。

## 验收命令与结果

执行：

```powershell
python scripts/retrieve_evidence_contexts.py --data-dir data/processed --relation-schema configs/relation_schema.yaml --candidates outputs/candidate_edges.jsonl --out outputs/evidence_contexts.jsonl --allow-keyword-only
```

结果：

```json
{
  "avg_supporting_evidence_count": 2.5167,
  "context_count": 60,
  "degraded_count": 60
}
```

结构检查：

```powershell
python -c "import json; rows=[json.loads(l) for l in open('outputs/evidence_contexts.jsonl', encoding='utf-8') if l.strip()]; print(len(rows)); print(rows[0]['retrieval_metadata']); print(len(rows[0]['supporting_evidence_candidates'])); print({'candidate','relation_query','retrieval_metadata','supporting_evidence_candidates','conflict_evidence_candidates','packed_context'} <= set(rows[0]))"
```

结果：

```text
60
{'degraded': True, 'expanded_evidence_count': 10, 'fallback_reason': 'keyword_only_explicitly_enabled_for_smoke', 'initial_evidence_count': 5, 'mode': 'keyword_only', 'preferred_sources': ['ticket', 'alert', 'dns', 'service_dependency'], 'top_k': 5}
3
True
```

gold 候选 evidence 覆盖：

```powershell
python -c "import json; gold={(r['head'],r['relation'],r['tail']) for r in map(json.loads, open('data/processed/gold_hidden_edges.jsonl', encoding='utf-8'))}; rows=[json.loads(l) for l in open('outputs/evidence_contexts.jsonl', encoding='utf-8') if l.strip()]; hits=0; total=0; details=[]; [None for row in rows for c in [row['candidate']] if (c['head'],c['relation'],c['tail']) in gold for ok in [any(c['head'] in ev['related_entities'] and c['tail'] in ev['related_entities'] for ev in row['supporting_evidence_candidates'])] for _ in [details.append(((c['head'],c['relation'],c['tail']), ok)), globals().__setitem__('hits', hits + int(ok)), globals().__setitem__('total', total + 1)]]; print(total, hits, details)"
```

实际检查结果：`7 7`，sample gold 候选均检索到同时包含 head/tail 的 supporting evidence。

## 未完成项

- 未启用 dense embedding 或 cross-encoder；后续如启用必须显式配置，不可静默降级。
- LLM adapter、Reasoner、Verifier、writeback/eval 尚未迁移。

## 偏离原计划的地方

- 本地 smoke 使用 keyword-only degraded 模式，原因已写入每条 context 的 `retrieval_metadata`。
- 写 `outputs/evidence_contexts.jsonl` 时受限环境拒绝仓库内输出写入，已使用提升权限重跑同一命令。

## 是否建议进入下一阶段

建议进入 Phase 5：LLMClient Adapter。
