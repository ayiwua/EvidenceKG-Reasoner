# Phase 0 报告：仓库审查与重构边界确认

## 实际新增文件

- `docs/重构计划/phase_00_repo_audit.md`
- `docs/重构计划/reports/phase_00_report.md`

## 实际修改文件

- 无运行代码修改。

## 删除的旧链路或废弃接口

- 本阶段未删除任何旧链路。
- 已标记后续可替换链路：
  - `TaskConfig` 单目标关系配置。
  - `entity_id/triple_id/evidence_id` v1 字段体系。
  - `CandidateGenerator` 单任务候选生成。
  - 强依赖 `sentence_transformers` 的普通 dense rerank retrieval。
  - `RealLLMReasoner` 直接依赖 OpenAI-compatible client。
  - 只做 schema/evidence id/confidence/conflict 的旧 `Verifier`。
  - `candidate_pairs.jsonl`、`predicted_edges.jsonl` 等 v1 输出命名。

## 完成能力

- 完整阅读并冻结 `docs/重构计划/codex改进提示词.md`。
- 审查当前仓库结构、核心代码、sample JSONL 和 README。
- 明确当前 v1 pipeline 与 v2 目标之间的 schema、模块和输出差异。
- 形成 Phase 1 到 Phase 7 的边界依据。

## 验收命令与结果

实际执行：

```powershell
python -c "import sys; sys.path.insert(0, 'src'); from evidencekg.graph.graph_store import GraphStore; from evidencekg.candidate.generator import CandidateGenerator; from evidencekg.retrieval.evidence_retriever import EvidenceRetriever; from evidencekg.llm.reasoner import MockReasoner; from evidencekg.verify.verifier import Verifier; from evidencekg.pipeline.runner import PipelineRunner; store = GraphStore.from_dir('data/sample'); print(len(store.entities), len(store.triples), len(store.evidence))"
```

结果：

- 输出 `76 131 42`。
- 核心模块可导入。
- 当前 sample JSONL 可由 v1 GraphStore 读取。
- 未触发真实 LLM、embedding 模型下载或外部网络访问。

## 未完成项

- 尚未执行 Phase 1 DatasetBuilder。
- 尚未迁移 v2 schema。
- 尚未运行完整 v2 sample pipeline。

## 偏离原计划的地方

- 无。

## 是否建议进入下一阶段

建议进入 Phase 1：CSV -> JSONL DatasetBuilder。
