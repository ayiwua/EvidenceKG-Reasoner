# EvidenceKG-Reasoner 第一阶段 Mock Pipeline 实现方案（修订版）

## 1. 阶段目标

第一阶段目标是在不接入真实 LLM、不依赖 API key 的前提下，跑通一条完整、可复现、可评测的 Mock Pipeline。

主链路如下：

```text
JSONL KG 加载
  -> schema filter 与候选关系生成
  -> 图谱证据检索
  -> Mock LLM 推断
  -> Verifier 证据一致性审查
  -> verified_predictions 全量审查记录
  -> predicted_edges 最终候选补全边
  -> Hidden Edge Recovery 评测
```

本阶段重点不是追求模型推理能力，而是搭建稳定的工程闭环：配置驱动、模块分层、证据可追溯、推断可审查、结果可评测。

## 2. 第一阶段边界

### 2.1 本阶段做

- 使用 JSONL 文件加载合成企业 IP 与 IT 资产 KG。
- 使用 `networkx.MultiDiGraph` 构建内存图结构索引。
- 基于 schema filter 和结构 / 证据规则生成候选关系。
- 针对候选关系检索图谱证据上下文。
- 使用 Mock LLMReasoner 生成结构化推断结果。
- 使用 Verifier 检查 schema、证据引用、置信度和冲突关系。
- 输出候选、证据上下文、全量审查记录、最终补全边和评测报告。
- 使用 hidden edge recovery 计算 precision、recall、F1。
- 通过 CLI 完整运行 pipeline。
- 使用 `.venv` 管理 Python 环境。

### 2.2 本阶段不做

- 不接真实 LLM。
- 不需要 API key。
- 不做 Neo4j。
- 不做前端。
- 不做多模型投票。
- 不做复杂时空推理。
- 不建设 time pool / space pool。
- 不训练 GNN、TransE、RotatE 等传统 KG completion 模型。
- 不接真实企业数据。
- 不让 LLM 从全图自由生成候选关系。

## 3. 核心设计原则

### 3.1 目标关系不能写死

第一阶段默认任务可以是：

```yaml
target_relation: likely_owned_by
```

但代码结构必须从 `TaskConfig` 读取目标关系，不能在 `CandidateGenerator`、`EvidenceRetriever`、`Verifier`、`Evaluator` 或 Pipeline 主流程中写死 `likely_owned_by`。

后续如需切换到：

- `likely_belongs_to`
- `likely_depends_on`
- `likely_related_to_incident`

应优先通过新增或修改配置完成，而不是重写主流程。

### 3.2 type_rule 是 schema filter

`type_rule` 不应作为独立强召回规则使用。它只负责检查 head / tail 类型是否合法。

候选关系必须同时满足：

- head / tail 类型符合 `TaskConfig.allowed_head_types` 和 `TaskConfig.allowed_tail_types`。
- 至少命中以下结构 / 证据规则之一：
  - `two_hop_path`
  - `common_neighbor`
  - `evidence_overlap`

也就是说，系统不能仅因为某个 head 和 tail 类型合法，就枚举出候选关系。类型合法只是准入条件，不是候选成立的证据。

### 3.3 LLMReasoner 必须可替换

第一阶段只实现 mock mode：

```yaml
llm:
  mode: mock
  best_of_n: 1
```

真实 LLM 接入应作为第二阶段内容。后续真实 LLM 只能替换 provider 或 reasoner 实现，不允许重写 pipeline。

### 3.4 LLM 输出不能直接写回

Mock Reasoner 的输出必须经过 Verifier。所有候选的推断与审查记录写入 `verified_predictions.jsonl`。只有 `verifier_status=passed` 且 `decision=accept` 的记录，才能进入 `predicted_edges.jsonl`，作为最终候选补全边。

## 4. 建议目录结构

```text
EvidenceKG-Reasoner/
  README.md
  requirements.txt
  .env.example

  configs/
    task_owned_by.yaml

  data/
    sample/
      entities.jsonl
      triples.jsonl
      evidence.jsonl
      gold_hidden_edges.jsonl

  outputs/
    candidate_pairs.jsonl
    evidence_contexts.jsonl
    verified_predictions.jsonl
    predicted_edges.jsonl
    evaluation_report.json

  src/
    evidencekg/
      __init__.py

      config/
        task_config.py

      graph/
        graph_store.py

      candidate/
        generator.py
        rules.py

      retrieval/
        evidence_retriever.py

      prompting/
        prompt_builder.py
        templates.py

      llm/
        base.py
        mock_client.py
        reasoner.py

      verify/
        verifier.py
        checks.py

      eval/
        evaluator.py
        metrics.py

      pipeline/
        runner.py

  scripts/
    run_pipeline.py
    run_evaluation.py

  tests/
    test_task_config.py
    test_graph_store.py
    test_candidate_generator.py
    test_evidence_retriever.py
    test_prompt_builder.py
    test_mock_reasoner.py
    test_verifier.py
    test_evaluator.py
    test_pipeline_runner.py
```

## 5. Sample Data 规模

第一阶段 sample data 不应只是极小 demo，也不应过大。建议规模如下：

| 文件 | 建议规模 |
|---|---:|
| `entities.jsonl` | 60-100 个实体 |
| `triples.jsonl` | 120-250 条已有关系 |
| `evidence.jsonl` | 40-80 条证据 |
| `gold_hidden_edges.jsonl` | 15-30 条隐藏 gold edges |
| `candidate_pairs.jsonl` | 控制在 50-150 条候选左右 |

该规模应能展示候选生成、证据检索、verifier 和评测闭环，同时保持本地运行轻量。

## 6. TaskConfig 设计

`TaskConfig` 是第一阶段最重要的防写死机制。目标关系、合法实体类型、候选生成规则、证据检索策略、LLM 模式、Verifier 阈值和评测文件都应由配置控制。

建议配置结构：

```yaml
task_name: owned_by_discovery
target_relation: likely_owned_by

allowed_head_types:
  - ip
  - host
  - service
  - api
  - database
  - application

allowed_tail_types:
  - team
  - department
  - person

candidate_rules:
  - two_hop_path
  - common_neighbor
  - evidence_overlap

schema_filter:
  enabled: true

evidence_retrieval:
  max_hops: 3
  max_paths: 5
  max_evidence_snippets: 8
  include_entity_profiles: true
  include_common_neighbors: true
  include_related_triples: true

llm:
  mode: mock
  provider: mock
  temperature: 0.2
  best_of_n: 1

verifier:
  confidence_threshold: 0.7
  require_supporting_evidence: true
  check_schema_consistency: true
  check_evidence_grounding: true
  check_conflict: true

evaluation:
  gold_file: gold_hidden_edges.jsonl
```

关键要求：

- `target_relation` 由配置读取。
- `allowed_head_types` 和 `allowed_tail_types` 控制 schema filter。
- `candidate_rules` 只包含结构 / 证据规则，不把 `type_rule` 作为独立召回规则。
- `llm.mode` 第一阶段固定使用 `mock`。
- `best_of_n` 保留字段，但第一阶段默认 `1`，不做多模型投票。

## 7. 工程模块拆解

### 7.1 GraphStore

职责：

- 从 JSONL 文件加载实体、已有关系和证据文本。
- 内部使用 `networkx.MultiDiGraph` 构建图结构索引。
- 提供实体、关系、证据、邻居、路径和 evidence 查询能力。

设计约束：

- 企业 IP 与 IT 资产 KG 中，同一对实体之间可能存在多种关系，因此使用 `networkx.MultiDiGraph`。
- triples 仍然由 `triple_id` 作为主索引管理。
- NetworkX 图主要作为邻居、路径和结构查询索引。
- 不要把 NetworkX 边数据作为唯一数据源；关系详情应以 `triple_id -> triple` 的索引为准。

输入文件：

- `entities.jsonl`
- `triples.jsonl`
- `evidence.jsonl`

关键接口：

```python
class GraphStore:
    def load_entities(self, path: str) -> None
    def load_triples(self, path: str) -> None
    def load_evidence(self, path: str) -> None

    def get_entity(self, entity_id: str) -> dict | None
    def iter_entities_by_type(self, entity_types: list[str]) -> list[dict]

    def iter_triples(self) -> list[dict]
    def get_triple(self, triple_id: str) -> dict | None
    def get_triples_between(self, head: str, tail: str) -> list[dict]
    def get_triples_for_entities(self, entity_ids: list[str]) -> list[dict]
    def get_related_triples(self, entity_id: str) -> list[dict]
    def has_relation(self, head: str, relation: str, tail: str) -> bool

    def get_evidence(self, evidence_id: str) -> dict | None
    def get_evidence_for_triple(self, triple_id: str) -> list[dict]
    def get_evidence_for_entities(self, entity_ids: list[str]) -> list[dict]

    def get_neighbors(self, entity_id: str) -> list[str]
    def find_paths(self, head: str, tail: str, max_hops: int, max_paths: int) -> list[list[str]]
```

验收标准：

- 能按 ID 查询实体、关系和证据。
- 能遍历指定类型实体。
- 能按 `triple_id` 查询 triple。
- 能查询两实体之间的多条关系。
- 能查询多个实体相关 triples。
- 能根据 triple 找到 evidence。
- 能查询 1 到 3 跳路径。
- evidence 查询结果必须保留 `evidence_id`。

### 7.2 CandidateGenerator

职责：

- 根据 `TaskConfig` 和 `GraphStore` 生成候选关系。
- 输出 `candidate_pairs.jsonl`。

候选生成逻辑：

1. 从 `allowed_head_types` 和 `allowed_tail_types` 获取候选实体池。
2. 使用 schema filter 检查 head / tail 类型合法性。
3. 对合法实体对应用结构 / 证据规则。
4. 只有命中 `two_hop_path`、`common_neighbor` 或 `evidence_overlap` 至少一项的实体对，才能成为 candidate。
5. 过滤已有同类关系和重复 candidate。
6. 计算 `rule_scores` 与 `candidate_score`。

结构 / 证据规则：

- `two_hop_path`：head 与 tail 之间存在 2 到 `max_hops` 范围内的图路径。
- `common_neighbor`：head 与 tail 存在共同邻居。
- `evidence_overlap`：head 与 tail 出现在同一证据或相关证据中。

注意：`type_rule` 只作为 schema filter，不写入 `generation_rules`，也不能单独生成候选。

关键接口：

```python
class CandidateGenerator:
    def generate(self, config: TaskConfig, graph: GraphStore) -> list[Candidate]
```

候选结构：

```json
{
  "candidate_id": "c_001",
  "head": "ip_001",
  "relation": "likely_owned_by",
  "tail": "team_payment",
  "generation_rules": ["two_hop_path", "common_neighbor"],
  "rule_scores": {
    "two_hop_path": 0.4,
    "common_neighbor": 0.3,
    "evidence_overlap": 0.2
  },
  "candidate_score": 0.9,
  "paths": [
    ["ip_001", "service_payment_api", "ticket_023", "team_payment"]
  ],
  "common_neighbors": ["service_payment_api", "ticket_023"]
}
```

`rule_scores` 和 `candidate_score` 用途：

- 表示候选关系由哪些规则支撑，以及每类规则贡献的简单分数。
- 后续接真实 LLM 时，可以按 `candidate_score` 排序或截断 top-K，减少 API 成本。
- 第一阶段不需要复杂排序模型，使用简单规则分数即可。

验收标准：

- `relation` 字段来自 `TaskConfig.target_relation`。
- `type_rule` 只作为 schema filter。
- 不能仅靠类型合法生成候选。
- 候选必须至少命中一个结构 / 证据规则。
- 不生成已有同类关系。
- 不生成 schema 非法实体对。
- 不生成重复 candidate。
- 每个 candidate 记录触发的 `generation_rules`。
- 每个 candidate 包含 `rule_scores` 和 `candidate_score`。

### 7.3 EvidenceRetriever

职责：

- 针对每个 candidate 检索证据上下文。
- 输出 `evidence_contexts.jsonl`。

Evidence Context 应包含：

- candidate
- head profile
- tail profile
- graph paths
- common neighbors
- related triples
- evidence snippets

关键接口：

```python
class EvidenceRetriever:
    def retrieve(self, candidate: Candidate, config: TaskConfig, graph: GraphStore) -> EvidenceContext
```

输出结构：

```json
{
  "candidate_id": "c_001",
  "candidate": {
    "head": "ip_001",
    "relation": "likely_owned_by",
    "tail": "team_payment"
  },
  "head_profile": {},
  "tail_profile": {},
  "graph_paths": [],
  "common_neighbors": [],
  "related_triples": [],
  "evidence_snippets": []
}
```

验收标准：

- 每个 candidate 都能生成 evidence context。
- graph paths 数量不超过 `max_paths`。
- evidence snippets 数量不超过 `max_evidence_snippets`。
- 每条 evidence snippet 必须有真实可追溯的 `evidence_id`。
- related triples 应从 GraphStore 的 triple 索引读取，而不是只依赖 NetworkX 边数据。

### 7.4 PromptBuilder

职责：

- 把 evidence context 组织成标准推理输入。
- 同时支持 Mock Reasoner 和第二阶段真实 LLM 接入。

PromptBuilder 可以输出两类内容：

- `structured_context`：结构化上下文，供第一阶段 MockReasoner 使用。
- `prompt_text`：自然语言 prompt，供第二阶段真实 LLM 接入预留。

第一阶段 MockReasoner 不应解析自然语言 prompt。MockReasoner 应优先基于 `EvidenceContext` 或 `structured_context` 进行规则化模拟推断。

结构化输出 schema：

```json
{
  "decision": "accept | reject | uncertain",
  "confidence": 0.0,
  "reason": "short explanation",
  "supporting_evidence_ids": []
}
```

验收标准：

- `structured_context` 包含 candidate、entity profiles、graph paths、related triples、evidence snippets。
- `prompt_text` 为第二阶段真实 LLM 接入预留。
- MockReasoner 不依赖自然语言 prompt 解析。
- 输出 schema 明确要求 evidence id 引用。

### 7.5 Mock LLMReasoner

职责：

- 在不接真实 LLM 的情况下模拟结构化推断结果。
- 输入 `EvidenceContext` 或 `structured_context`。
- 输出 decision、confidence、reason、supporting_evidence_ids。

关键接口：

```python
class BaseReasoner:
    def predict(self, context: EvidenceContext | dict) -> ReasonerOutput
```

```python
class MockReasoner(BaseReasoner):
    def predict(self, context: EvidenceContext | dict) -> ReasonerOutput
```

建议 mock 规则：

- 若存在路径、共同邻居和相关 evidence，则倾向 `accept`。
- 若仅类型合法但缺少图路径或证据，则倾向 `uncertain`。实际候选生成阶段不应产生仅类型合法的候选，但该逻辑可作为防御性处理。
- 若缺少 evidence snippets，则不应高置信 accept。
- supporting evidence ids 只能来自当前 evidence context。
- confidence 根据证据强度和 `candidate_score` 生成。

验收标准：

- 不需要 API key。
- 输出 JSON 结构稳定。
- `decision` 只能是 `accept`、`reject`、`uncertain`。
- `confidence` 在 `0.0` 到 `1.0` 之间。
- `supporting_evidence_ids` 必须来自 evidence context。
- 不从自然语言 prompt 中反向解析结构信息。

### 7.6 Verifier

职责：

- 对 Mock Reasoner 输出进行证据一致性审查。
- 防止无证据推断直接写入最终补全边。
- 生成全量 `verified_predictions.jsonl`。

检查项：

| 检查项 | 内容 | 不通过处理 |
|---|---|---|
| schema consistency | head / tail 类型是否符合 TaskConfig | reject |
| evidence grounding | supporting evidence ids 是否真实存在，是否与 candidate 相关 | reject 或 uncertain |
| confidence threshold | accept 的 confidence 是否达到阈值 | 降级为 uncertain 或 reject |
| conflict check | 是否与已有关系或已接受预测冲突 | reject |

关键接口：

```python
class Verifier:
    def verify(
        self,
        candidate: Candidate,
        context: EvidenceContext,
        prediction: ReasonerOutput,
        config: TaskConfig,
        graph: GraphStore,
    ) -> VerifiedPrediction
```

`verified_predictions.jsonl` 输出结构：

```json
{
  "prediction_id": "p_001",
  "candidate_id": "c_001",
  "head": "ip_001",
  "relation": "likely_owned_by",
  "tail": "team_payment",
  "decision": "accept",
  "confidence": 0.84,
  "reason": "The IP exposes a payment-related service and evidence links it to the payment team.",
  "supporting_evidence_ids": ["ev_001", "ev_008"],
  "verifier_status": "passed",
  "verifier_details": {
    "schema_consistency": true,
    "evidence_grounding": true,
    "confidence_threshold": true,
    "conflict_check": true
  },
  "source": "mock_llm_inference"
}
```

验收标准：

- Mock Reasoner 输出不能绕过 Verifier。
- 所有候选都应在 `verified_predictions.jsonl` 中留下审查记录。
- accepted prediction 必须通过 schema 和 evidence grounding。
- 低于置信度阈值的 accept 必须被降级或拒绝。
- verifier details 必须写入全量审查记录。
- `predicted_edges.jsonl` 只能包含 `verifier_status=passed` 且 `decision=accept` 的最终补全边。

### 7.7 Evaluator

职责：

- 根据 `gold_hidden_edges.jsonl` 做 hidden edge recovery 评测。
- 输出 `evaluation_report.json`。

评测口径：

- precision / recall / F1 只基于 `predicted_edges.jsonl` 中的 accepted edges 计算。
- rejected / uncertain 只进入统计项，不参与 precision / recall / F1 命中计算。
- `verified_predictions.jsonl` 用于分析 verifier 行为，并统计 accepted_count、rejected_count、uncertain_count、verifier_pass_rate。

基础指标：

- precision
- recall
- F1
- candidate_count
- accepted_count
- rejected_count
- uncertain_count
- verifier_pass_rate
- average_confidence

关键接口：

```python
class Evaluator:
    def evaluate(
        self,
        predicted_edges_path: str,
        gold_edges_path: str,
        verified_predictions_path: str | None = None,
    ) -> dict
```

验收标准：

- precision / recall / F1 只对最终 accepted edges 计算。
- 能与 gold hidden edges 对比。
- 空预测时不报错。
- 能从 `verified_predictions.jsonl` 统计 reject / uncertain 和 verifier pass rate。
- 输出 JSON 格式评测报告。

### 7.8 PipelineRunner

职责：

- 串联完整 Mock Pipeline。
- 管理输入路径、输出路径和阶段执行。

关键接口：

```python
class PipelineRunner:
    def run(self, config_path: str, data_dir: str, output_dir: str) -> PipelineResult
```

执行顺序：

```text
load config
load graph
generate candidates
write candidate_pairs.jsonl
retrieve evidence contexts
write evidence_contexts.jsonl
build structured_context and prompt_text
run mock reasoner
verify predictions
write verified_predictions.jsonl
filter accepted passed edges
write predicted_edges.jsonl
run evaluation
write evaluation_report.json
```

验收标准：

- 一条 CLI 命令能完整跑通。
- 无 API key 也能运行。
- 输出所有阶段文件。
- `verified_predictions.jsonl` 保存全量推断和审查结果。
- `predicted_edges.jsonl` 只保存最终 accepted passed edges。

## 8. 数据流

```text
configs/task_owned_by.yaml
        |
        v
TaskConfig
        |
        v
data/sample/entities.jsonl
data/sample/triples.jsonl     -> GraphStore using networkx.MultiDiGraph
data/sample/evidence.jsonl
        |
        v
CandidateGenerator
  schema filter + structural/evidence rules
        |
        v
outputs/candidate_pairs.jsonl
        |
        v
EvidenceRetriever
        |
        v
outputs/evidence_contexts.jsonl
        |
        v
PromptBuilder
  structured_context + prompt_text
        |
        v
MockReasoner
        |
        v
Verifier
        |
        v
outputs/verified_predictions.jsonl
        |
        v
filter decision=accept and verifier_status=passed
        |
        v
outputs/predicted_edges.jsonl
        |
        v
Evaluator + data/sample/gold_hidden_edges.jsonl
        |
        v
outputs/evaluation_report.json
```

## 9. CLI 命令设计

### 9.1 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 9.2 完整运行 Mock Pipeline

```powershell
python scripts/run_pipeline.py `
  --config configs/task_owned_by.yaml `
  --data-dir data/sample `
  --output-dir outputs
```

### 9.3 只生成候选关系

```powershell
python scripts/run_pipeline.py `
  --config configs/task_owned_by.yaml `
  --data-dir data/sample `
  --output-dir outputs `
  --stage candidates
```

### 9.4 只运行评测

```powershell
python scripts/run_evaluation.py `
  --predicted outputs/predicted_edges.jsonl `
  --verified outputs/verified_predictions.jsonl `
  --gold data/sample/gold_hidden_edges.jsonl `
  --output outputs/evaluation_report.json
```

### 9.5 运行测试

```powershell
python -m pytest
```

## 10. 输出文件

### 10.1 candidate_pairs.jsonl

保存候选关系生成结果。

核心字段：

- `candidate_id`
- `head`
- `relation`
- `tail`
- `generation_rules`
- `rule_scores`
- `candidate_score`
- `paths`
- `common_neighbors`

注意：

- `generation_rules` 不包含 `type_rule`。
- `type_rule` 只是 schema filter。
- 每个 candidate 至少命中一个结构 / 证据规则。

### 10.2 evidence_contexts.jsonl

保存每个候选关系对应的证据上下文。

核心字段：

- `candidate_id`
- `candidate`
- `head_profile`
- `tail_profile`
- `graph_paths`
- `common_neighbors`
- `related_triples`
- `evidence_snippets`

### 10.3 verified_predictions.jsonl

保存所有候选关系的推断和 verifier 审查结果，包括 accept、reject、uncertain。

核心字段：

- `prediction_id`
- `candidate_id`
- `head`
- `relation`
- `tail`
- `decision`
- `confidence`
- `reason`
- `supporting_evidence_ids`
- `verifier_status`
- `verifier_details`
- `source`

### 10.4 predicted_edges.jsonl

只保存最终候选补全边。

进入条件：

- `decision=accept`
- `verifier_status=passed`

该文件是 hidden edge recovery 中 precision / recall / F1 的直接输入。

### 10.5 evaluation_report.json

保存 hidden edge recovery 评测结果。

核心字段：

- `precision`
- `recall`
- `f1`
- `candidate_count`
- `accepted_count`
- `rejected_count`
- `uncertain_count`
- `verifier_pass_rate`
- `average_confidence`

## 11. README 第一阶段要求

第一阶段 `README.md` 至少包含：

- 项目一句话介绍。
- 主链路说明。
- 第一阶段 Mock Pipeline 运行命令。
- 输入文件说明。
- 输出文件说明。
- sample evaluation 结果。
- 第一阶段不做事项。
- 后续真实 LLM 接入计划。

README 应明确本阶段不接真实 LLM、不需要 API key，并说明目标关系由 `TaskConfig` 控制。

## 12. 测试计划

### 12.1 test_task_config.py

验证内容：

- 能加载 YAML 配置。
- `target_relation` 来自配置。
- `allowed_head_types` 和 `allowed_tail_types` 正确解析。
- `candidate_rules` 不依赖 `type_rule` 作为召回规则。
- `llm.mode` 为 `mock`。
- `best_of_n` 默认为 `1`。

### 12.2 test_graph_store.py

验证内容：

- 内部图类型为 `networkx.MultiDiGraph`。
- 能加载 entities、triples、evidence。
- triples 以 `triple_id` 为主索引。
- 能按 ID 查询实体、关系和证据。
- 能遍历指定类型实体。
- 能查询两实体之间的多条关系。
- 能查询多个实体相关 triples。
- 能根据 triple 查询 evidence。
- 能查询邻居。
- 能查询 1 到 3 跳路径。
- evidence 查询结果保留 `evidence_id`。

### 12.3 test_candidate_generator.py

验证内容：

- candidate relation 使用 `TaskConfig.target_relation`。
- `type_rule` 只作为 schema filter。
- 不允许仅靠类型合法生成候选。
- 候选必须至少命中 `two_hop_path`、`common_neighbor`、`evidence_overlap` 之一。
- 不生成已有同类关系。
- 不生成 schema 非法实体对。
- 不生成重复 candidate。
- 触发规则能写入 `generation_rules`。
- `generation_rules` 不包含 `type_rule`。
- 每个 candidate 包含 `rule_scores` 和 `candidate_score`。

### 12.4 test_evidence_retriever.py

验证内容：

- 每个 candidate 能生成 evidence context。
- context 包含 head profile 和 tail profile。
- graph paths 不超过配置限制。
- evidence snippets 不超过配置限制。
- evidence snippets 都包含真实 `evidence_id`。
- related triples 从 GraphStore triple 索引读取。

### 12.5 test_prompt_builder.py

验证内容：

- 能输出 `structured_context`。
- 能输出 `prompt_text`。
- `structured_context` 包含 candidate、entity profiles、paths、triples、evidence snippets。
- MockReasoner 可以直接使用 `structured_context`，不需要解析自然语言 prompt。

### 12.6 test_mock_reasoner.py

验证内容：

- Mock 输出结构符合 schema。
- decision 只可能是 `accept`、`reject`、`uncertain`。
- confidence 在 `0.0` 到 `1.0` 之间。
- supporting evidence ids 来自 evidence context。
- MockReasoner 不依赖自然语言 prompt 解析。

### 12.7 test_verifier.py

验证内容：

- schema 不合法时 reject。
- supporting evidence ids 不存在时 reject 或 uncertain。
- accept 但 confidence 低于阈值时降级。
- 通过 verifier 的 accepted prediction 必须有合法证据引用。
- 所有候选都能产生 verified prediction 记录。

### 12.8 test_evaluator.py

验证内容：

- precision、recall、F1 只基于 `predicted_edges.jsonl` 计算。
- rejected / uncertain 不参与 precision、recall、F1 命中计算。
- 能从 `verified_predictions.jsonl` 统计 accepted、rejected、uncertain。
- 空预测不会报错。
- 无 gold edge 时处理稳定。

### 12.9 test_pipeline_runner.py

验证内容：

- 无 API key 可完整运行。
- 能生成五个输出文件：
  - `candidate_pairs.jsonl`
  - `evidence_contexts.jsonl`
  - `verified_predictions.jsonl`
  - `predicted_edges.jsonl`
  - `evaluation_report.json`
- `predicted_edges.jsonl` 只包含 accepted passed edges。
- pipeline 不依赖真实 LLM。

## 13. 第一阶段验收标准

第一阶段完成后，应满足以下条件：

1. 使用 `.venv` 环境即可运行，不依赖 conda。
2. 不需要 API key。
3. 不接真实 LLM。
4. 能从 sample JSONL KG 加载实体、关系和证据。
5. GraphStore 内部使用 `networkx.MultiDiGraph`。
6. triples 由 `triple_id` 作为主索引管理。
7. NetworkX 图只作为结构查询索引，不作为唯一数据源。
8. 能根据 `TaskConfig` 生成候选关系。
9. `target_relation` 不写死，默认只是配置为 `likely_owned_by`。
10. `type_rule` 只作为 schema filter。
11. 不能仅靠类型合法生成候选。
12. 候选必须至少命中一个结构 / 证据规则。
13. 候选生成不产生 schema 非法实体对。
14. 候选生成不重复生成已有同类关系。
15. 每个 candidate 包含 `rule_scores` 和 `candidate_score`。
16. 能为每个候选关系检索 evidence context。
17. evidence context 中的证据必须可追溯到 `evidence_id`。
18. PromptBuilder 同时输出 `structured_context` 和 `prompt_text`。
19. MockReasoner 基于 EvidenceContext 或 `structured_context` 进行规则化模拟推断。
20. MockReasoner 不解析自然语言 prompt。
21. Mock 输出必须经过 Verifier。
22. `verified_predictions.jsonl` 保存所有候选的推断和审查结果。
23. `predicted_edges.jsonl` 只保存 `verifier_status=passed` 且 `decision=accept` 的最终补全边。
24. Verifier 至少完成 schema consistency、evidence grounding、confidence threshold 和 conflict check。
25. Evaluator 基于 `predicted_edges.jsonl` 计算 precision、recall、F1。
26. rejected / uncertain 只进入统计项，不参与 precision、recall、F1 命中计算。
27. 能生成 `candidate_pairs.jsonl`、`evidence_contexts.jsonl`、`verified_predictions.jsonl`、`predicted_edges.jsonl`、`evaluation_report.json`。
28. Sample data 规模合理，不是极小 demo，也不是过大数据集。
29. README 包含第一阶段运行、输入输出、评测结果、边界和后续真实 LLM 接入计划。
30. 不包含 Neo4j、前端、多模型投票、复杂时空推理、time pool / space pool。
31. 不训练 GNN、TransE、RotatE。
32. 不接真实企业数据。
33. 不让 LLM 从全图自由生成候选关系。
34. 后续接真实 LLM 时，只替换 reasoner/provider，不重写主 pipeline。

## 14. 阶段总结

第一阶段的目标是让 EvidenceKG-Reasoner 先成为一个完整的、配置驱动的、可验证的 GraphRAG 证据推理工程骨架。

本阶段不追求真实 LLM 效果，而是确保以下工程事实成立：

- KG 可以加载，并使用 `networkx.MultiDiGraph` 支持多关系结构查询。
- 目标关系通过 `TaskConfig` 控制，不写死在代码中。
- `type_rule` 是 schema filter，不是独立强召回规则。
- 候选关系必须由结构或证据规则支撑。
- 候选关系可以带有简单 `rule_scores` 和 `candidate_score`。
- 图谱证据可以检索，且 evidence id 可追溯。
- Mock Reasoner 使用结构化上下文进行模拟推断。
- 推断结果必须经过 Verifier。
- 全量审查记录和最终补全边分离输出。
- 最终结果可以和 hidden gold edges 做评测。

完成第一阶段后，第二阶段接入真实 LLM 时，只需要替换 LLM provider，并完善 PromptBuilder、JSON 解析、重试和异常处理，不应改动主 pipeline 结构。
