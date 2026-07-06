# Phase 1 报告：CSV -> JSONL DatasetBuilder

## 实际新增文件

- `docs/重构计划/phase_01_dataset_builder.md`
- `configs/dataset_manifest.yaml`
- `data/raw/teams.csv`
- `data/raw/assets.csv`
- `data/raw/services.csv`
- `data/raw/dns_records.csv`
- `data/raw/tickets.csv`
- `data/raw/alerts.csv`
- `data/raw/service_dependencies.csv`
- `data/processed/entities.jsonl`
- `data/processed/triples.jsonl`
- `data/processed/evidence.jsonl`
- `data/processed/gold_hidden_edges.jsonl`
- `scripts/build_dataset_from_csv.py`
- `src/evidencekg/data/__init__.py`
- `src/evidencekg/data/entity_normalizer.py`
- `src/evidencekg/data/evidence_builder.py`
- `src/evidencekg/data/dataset_builder.py`

## 实际修改文件

- 无既有运行代码修改。

## 删除的旧链路或废弃接口

- 本阶段未删除旧链路。
- 新 DatasetBuilder 不输出 v1 `entity_id/triple_id/evidence_id` 字段；后续 v2 链路应直接消费 `id` schema。

## 完成能力

- 提供可复现 sample raw CSV。
- 从 CSV 构建 v2 标准 JSONL。
- 生成实体、三元组、证据和隐藏 gold 边。
- 显式校验 manifest、必需 CSV 文件和必需列。
- 校验隐藏 gold 边不泄漏进 `triples.jsonl`。

## 验收命令与结果

执行：

```powershell
python scripts/build_dataset_from_csv.py --manifest configs/dataset_manifest.yaml --raw-dir data/raw --out-dir data/processed
```

结果：

```json
{
  "entity_count": 36,
  "evidence_count": 15,
  "gold_hidden_edge_count": 7,
  "triple_count": 44
}
```

辅助检查：

```powershell
python -c "import json, pathlib; root=pathlib.Path('data/processed'); print(sum(1 for _ in open(root/'entities.jsonl', encoding='utf-8')), sum(1 for _ in open(root/'triples.jsonl', encoding='utf-8')), sum(1 for _ in open(root/'evidence.jsonl', encoding='utf-8')), sum(1 for _ in open(root/'gold_hidden_edges.jsonl', encoding='utf-8')))"
```

输出：`36 44 15 7`

```powershell
python -c "import json, pathlib; root=pathlib.Path('data/processed'); ents=[json.loads(l) for l in open(root/'entities.jsonl', encoding='utf-8') if l.strip()]; triples=[json.loads(l) for l in open(root/'triples.jsonl', encoding='utf-8') if l.strip()]; ev=[json.loads(l) for l in open(root/'evidence.jsonl', encoding='utf-8') if l.strip()]; gold=[json.loads(l) for l in open(root/'gold_hidden_edges.jsonl', encoding='utf-8') if l.strip()]; print(all('id' in x and 'entity_id' not in x for x in ents), all('id' in x and 'triple_id' not in x for x in triples), all('id' in x and 'evidence_id' not in x for x in ev), not ({(x['head'],x['relation'],x['tail']) for x in triples} & {(x['head'],x['relation'],x['tail']) for x in gold}))"
```

输出：`True True True True`

新增模块导入检查：

```powershell
python -B -c "import sys; sys.path.insert(0, 'src'); from evidencekg.data import DatasetBuilder, EntityNormalizer, EvidenceBuilder; print(DatasetBuilder.__name__, EntityNormalizer().entity_id('service', 'payment-api'), EvidenceBuilder.__name__)"
```

输出：`DatasetBuilder svc_payment_api EvidenceBuilder`

## 未完成项

- GraphStore 尚未迁移到 v2 `id` schema。
- 候选生成、RAG、LLM adapter、Reasoner/Verifier、writeback/eval 尚未执行。

## 偏离原计划的地方

- 创建 `src/evidencekg/data`、`data/raw`、`data/processed` 和写入 `data/processed` 时，受限环境拒绝了仓库内新目录/输出写入，已使用提升权限完成同一仓库内目标路径创建与 smoke 输出。
- `python -m compileall` 因写 `scripts/__pycache__` 被拒绝，改用 `python -B` 导入检查，避免生成 pyc。

## 是否建议进入下一阶段

建议进入 Phase 2：GraphStore v2。
