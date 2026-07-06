# Phase 0: 仓库审查与重构边界确认

## 阶段目标

确认当前 EvidenceKG-Reasoner v1 代码结构、数据 schema、主流程和 v2 重构边界，为 Phase 1 到 Phase 7 的逐步迁移提供依据。

## 本阶段范围

- 阅读 `docs/重构计划/codex改进提示词.md`，并在 Phase 0 开始后冻结该总纲。
- 审查当前核心模块：GraphStore、CandidateGenerator、EvidenceRetriever、LLM Reasoner、Verifier、Writeback、Evaluator、PipelineRunner、CLI、sample JSONL。
- 输出当前模块理解、v1 可迁移能力、v1 可删除或替换链路、v2 新增和修改文件清单。
- 只产出阶段文档与报告，不修改运行代码。

## 明确不做什么

- 不改 Python 代码。
- 不改现有 `data/sample` JSONL。
- 不新增 v2 数据构建、GraphStore、候选召回、RAG、LLM adapter、Verifier 或 pipeline 实现。
- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不删除旧链路。

## 当前模块理解

当前项目是一条 v1 隐藏边恢复 pipeline：

```text
data/sample JSONL
-> GraphStore.from_dir
-> TaskConfig 单任务关系配置
-> CandidateGenerator 生成 candidate_pairs
-> EvidenceRetriever dense retrieval + cross-encoder rerank
-> PromptBuilder
-> MockReasoner 或 RealLLMReasoner(OpenAI-compatible)
-> Verifier
-> predicted_edges / pending_edges / evaluation_report
```

核心特点：

- v1 数据 schema 使用 `entity_id`、`triple_id`、`evidence_id` 字段。
- v1 配置以 `configs/task_*.yaml` 描述单一 `target_relation`，默认任务为 `likely_owned_by`。
- v1 GraphStore 可构建 NetworkX MultiDiGraph，并提供节点、边、证据、路径和邻居查询。
- v1 CandidateGenerator 已有类型过滤、路径、公共邻居和 evidence overlap 信号，但不是 relation schema driven。
- v1 EvidenceRetriever 已有 graph-aware query、dense retrieval、cross-encoder rerank，但没有 relation-aware context schema，也没有显式 keyword-only 降级记录。
- v1 Reasoner 已有 MockReasoner 和 OpenAI-compatible RealLLMReasoner，但缺少统一多 provider LLMClient。
- v1 Verifier 已做 schema、evidence grounding、confidence、conflict 检查，但缺少独立 SemanticVerifier。
- v1 Writeback 不覆盖原始 triples，方向正确，但输出仍使用 v1 `triple_id/evidence_ids` 语义。

## v1 可迁移能力

- `evidencekg.io` 的 JSON/JSONL 读写工具可继续保留。
- GraphStore 的 NetworkX MultiDiGraph、路径查询、邻居查询思路可迁移到 v2 schema。
- CandidateGenerator 的路径、公共邻居、证据共现评分思路可拆分成 v2 多路召回模块。
- EvidenceRetriever 的结构化 context 方向可迁移，但需要 relation-aware query、metadata filtering、support/conflict evidence 分区和显式 degraded 状态。
- MockReasoner 的本地 smoke 价值可保留，但应迁移到统一 LLMClient/Reasoner v2 输出 schema。
- Verifier 的硬校验能力可迁移为 HardVerifier。
- Writeback 的“不覆盖原始 triples”原则可迁移到 PendingWriteback + apply_review。
- Evaluator 的 precision/recall/f1 计算可迁移为 v2 evaluation report 的 final 部分。

## v1 可删除或替换链路

- `TaskConfig` 单目标关系配置在 v2 中由 `relation_schema.yaml` 和 pipeline/LLM 配置替换。
- `entity_id/triple_id/evidence_id` 字段不再作为 v2 内部 schema 扩散，后续阶段应迁移为 `id`。
- `CandidateGenerator` 单文件单任务实现应替换为 `src/evidencekg/candidate/*` 多路召回结构。
- `candidate_pairs.jsonl` 输出命名应替换为 `candidate_edges.jsonl`。
- `RealLLMReasoner` 直接绑定 OpenAI-compatible client 的方式应替换为 `BaseLLMClient` + provider adapter。
- 旧 `Verifier` 不应继续承担语义支持判断，应拆为 HardVerifier + SemanticVerifier。
- 当前 `KGWritebackManager` 的 approved 直接合并方式应迁移为 pending review 再 apply_review。

## v2 需要新增或修改文件列表

预计新增：

- `data/raw/*.csv`
- `data/processed/entities.jsonl`
- `data/processed/triples.jsonl`
- `data/processed/evidence.jsonl`
- `data/processed/gold_hidden_edges.jsonl`
- `configs/dataset_manifest.yaml`
- `configs/relation_schema.yaml`
- `configs/llm.yaml`
- `scripts/build_dataset_from_csv.py`
- `scripts/generate_candidates.py`
- `scripts/apply_review.py`
- `src/evidencekg/data/dataset_builder.py`
- `src/evidencekg/data/entity_normalizer.py`
- `src/evidencekg/data/evidence_builder.py`
- `src/evidencekg/candidate/base.py`
- `src/evidencekg/candidate/schema_recall.py`
- `src/evidencekg/candidate/path_recall.py`
- `src/evidencekg/candidate/common_neighbor_recall.py`
- `src/evidencekg/candidate/evidence_cooccurrence_recall.py`
- `src/evidencekg/candidate/attribute_similarity_recall.py`
- `src/evidencekg/candidate/source_specific_recall.py`
- `src/evidencekg/candidate/multi_route_generator.py`
- `src/evidencekg/llm/base_client.py`
- `src/evidencekg/llm/anthropic_client.py`
- `src/evidencekg/llm/local_client.py`
- `src/evidencekg/llm/mock_client.py`
- `src/evidencekg/llm/client_factory.py`

预计修改：

- `src/evidencekg/graph/graph_store.py`
- `src/evidencekg/retrieval/evidence_retriever.py`
- `src/evidencekg/llm/openai_compatible_client.py`
- `src/evidencekg/llm/reasoner.py`
- `src/evidencekg/verify/verifier.py`
- `src/evidencekg/writeback.py`
- `src/evidencekg/eval/evaluator.py`
- `src/evidencekg/pipeline/runner.py`
- `scripts/run_pipeline.py`

## 输出产物

- 本 phase 文件。
- `docs/重构计划/reports/phase_00_report.md`。

## 验收标准

- Phase 0 文档写清目标、范围、不做什么、验收标准。
- 阶段报告记录新增文件、修改文件、删除旧链路、验收命令与结果、未完成项、是否进入下一阶段。
- 核心 v1 模块可导入，sample JSONL 可读取。

## Smoke 命令

```powershell
python -c "import sys; sys.path.insert(0, 'src'); from evidencekg.graph.graph_store import GraphStore; from evidencekg.candidate.generator import CandidateGenerator; from evidencekg.retrieval.evidence_retriever import EvidenceRetriever; from evidencekg.llm.reasoner import MockReasoner; from evidencekg.verify.verifier import Verifier; from evidencekg.pipeline.runner import PipelineRunner; store = GraphStore.from_dir('data/sample'); print(len(store.entities), len(store.triples), len(store.evidence))"
```

期望输出：`76 131 42`。

## 风险与注意事项

- v2 schema 与 v1 sample schema 不兼容，Phase 1/2 需要明确迁移，不做长期双字段兼容。
- 当前 retrieval 默认依赖外部模型包和模型文件，后续 v2 smoke 不应因 embedding 不可用而静默降级。
- 当前仓库存在未跟踪中文文档与 `docs/重构计划/`，后续修改应避免误删用户已有文件。
