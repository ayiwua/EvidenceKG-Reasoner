# Phase 1: CSV -> JSONL DatasetBuilder

## 阶段目标

实现从半结构化企业资产 CSV 到 v2 标准 JSONL 的数据构建链路，产出 `entities.jsonl`、`triples.jsonl`、`evidence.jsonl`、`gold_hidden_edges.jsonl`。

## 本阶段范围

- 新增 sample raw CSV，使本地无需外部数据即可构建样例数据集。
- 新增 `configs/dataset_manifest.yaml` 描述 CSV 文件和字段。
- 新增 `EntityNormalizer`，稳定生成实体 `id`。
- 新增 `EvidenceBuilder`，生成标准 evidence 记录。
- 新增 `DatasetBuilder`，解析 CSV、归一实体、抽取基础关系、隐藏 gold 边。
- 新增 CLI：`scripts/build_dataset_from_csv.py`。
- 执行 smoke，确认生成的 JSONL 使用 v2 `id` schema。

## 明确不做什么

- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不改 GraphStore；GraphStore v2 留到 Phase 2。
- 不生成候选边；候选召回留到 Phase 3。
- 不做 RAG、LLM、Verifier、writeback 或 evaluation。
- 不兼容 v1 `entity_id/triple_id/evidence_id` 字段。

## 预计涉及文件

新增：

- `data/raw/teams.csv`
- `data/raw/assets.csv`
- `data/raw/services.csv`
- `data/raw/dns_records.csv`
- `data/raw/tickets.csv`
- `data/raw/alerts.csv`
- `data/raw/service_dependencies.csv`
- `configs/dataset_manifest.yaml`
- `scripts/build_dataset_from_csv.py`
- `src/evidencekg/data/__init__.py`
- `src/evidencekg/data/entity_normalizer.py`
- `src/evidencekg/data/evidence_builder.py`
- `src/evidencekg/data/dataset_builder.py`

输出：

- `data/processed/entities.jsonl`
- `data/processed/triples.jsonl`
- `data/processed/evidence.jsonl`
- `data/processed/gold_hidden_edges.jsonl`

## 输出产物

- 可复现 sample CSV。
- 标准 v2 JSONL 数据集。
- Phase 1 报告。

## 验收标准

- CLI 能从 `data/raw` 生成 `data/processed`。
- 生成的 entity/triple/evidence 主键字段统一为 `id`。
- `gold_hidden_edges.jsonl` 中隐藏边不进入 `triples.jsonl`。
- 字段缺失或配置错误 fail fast，不做静默 fallback。

## Smoke 命令

```powershell
python scripts/build_dataset_from_csv.py --manifest configs/dataset_manifest.yaml --raw-dir data/raw --out-dir data/processed
```

辅助检查：

```powershell
python -c "import json, pathlib; root=pathlib.Path('data/processed'); print(sum(1 for _ in open(root/'entities.jsonl', encoding='utf-8')), sum(1 for _ in open(root/'triples.jsonl', encoding='utf-8')), sum(1 for _ in open(root/'evidence.jsonl', encoding='utf-8')), sum(1 for _ in open(root/'gold_hidden_edges.jsonl', encoding='utf-8')))"
```

## 风险与注意事项

- Phase 1 生成的数据是 v2 数据源，Phase 2 之前不要尝试用 v1 GraphStore 读取。
- gold hidden edges 用于后续评估，应从 `triples.jsonl` 中排除。
- sample 数据规模保持小而完整，覆盖 owned_by、runs_on、depends_on 三类后续关系。
