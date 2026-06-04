# 数据流与文件字段说明

这份文档解释 EvidenceKG-Reasoner 中输入、中间产物、输出文件的字段，以及字段由哪个模块生成、被哪个模块使用。

## 1. 输入文件

### entities.jsonl

实体文件由 `GraphStore.load_entities()` 读取。

核心字段：

- `entity_id`: 实体主键，例如 `service_payment_api`。
- `type`: 实体类型，例如 `ip`、`host`、`service`、`api`、`application`、`team`。
- `name`: 展示名称。
- `description`: 简短描述。
- `attributes`: 额外属性。

使用位置：

- `CandidateGenerator` 按 `type` 选择候选 head/tail。
- `Verifier` 用实体类型做 schema consistency。
- `EvidenceRetriever` 输出 `head_profile` / `tail_profile`。
- `PromptBuilder` 把 profile 写入 real LLM prompt。

### triples.jsonl

已有 KG 边文件由 `GraphStore.load_triples()` 读取。

核心字段：

- `triple_id`: triple 主键。
- `head`: 起点实体。
- `relation`: 关系类型。
- `tail`: 终点实体。
- `confidence`: 原始 KG 边置信度。
- `evidence_ids`: 支撑该 triple 的 evidence id 列表。
- `source`、`observed_at`、`valid_from`、`valid_to`、`location`: 辅助元数据。

使用位置：

- `GraphStore` 用 `triple_id` 管理真实数据，用 `MultiDiGraph` 建结构索引。
- `CandidateGenerator` 通过路径和邻居生成候选，并用 `has_relation` 排除已有目标关系。
- `EvidenceRetriever` 取 `related_triples` 和 triple 关联证据。

### evidence.jsonl

证据文本文件由 `GraphStore.load_evidence()` 读取。

核心字段：

- `evidence_id`: 证据主键。
- `source`: 来源类型，例如 ticket、document、alert、scan_log。
- `text`: 证据文本。
- `related_entities`: 证据关联实体。
- `reliability`: 证据可靠性。
- `timestamp`、`location`: 辅助元数据。

使用位置：

- `CandidateGenerator` 的 `evidence_overlap` 规则检查 head/tail 是否共同出现在证据中。
- `EvidenceRetriever` 取 `evidence_snippets`。
- `Verifier` 检查 LLM 引用的 evidence id 是否来自当前 context。

### gold_hidden_edges.jsonl

隐藏 gold 边只用于评测，由 `Evaluator` 读取。

核心字段：

- `head`
- `relation`
- `tail`

这些边不在 `triples.jsonl` 中，用来评估 hidden edge recovery。

## 2. 中间与输出文件

### candidate_pairs.jsonl

由 `CandidateGenerator.generate()` 生成。

核心字段：

- `candidate_id`: 候选 ID，排序后重新编号。
- `head`
- `relation`: 来自 `TaskConfig.target_relation`。
- `tail`
- `generation_rules`: 命中的规则名。
- `rule_scores`: 各规则分数。
- `candidate_score`: 规则分数总和。
- `paths`: 从 graph 中找到的路径。
- `common_neighbors`: head/tail 公共邻居。

后续使用：

- `EvidenceRetriever` 用 paths 和 common_neighbors 扩展 query_entities。
- `PipelineRunner` 用 candidate_id 对齐 context 和 prediction。

### evidence_contexts.jsonl

由 `EvidenceRetriever.retrieve()` 生成。

核心字段：

- `candidate_id`
- `candidate`
- `head_profile`
- `tail_profile`
- `graph_paths`
- `common_neighbors`
- `related_triples`
- `evidence_snippets`

后续使用：

- `PromptBuilder` 构造 `structured_context` 和 `prompt_text`。
- `MockReasoner` 读取 structured context。
- `Verifier` 检查 evidence grounding。
- real LLM 通过 prompt_text 读取这些 context。

### verified_predictions.jsonl

由 `PipelineRunner` 在每个 candidate 完成后增量写入，最终也会重写一次完整文件。

核心字段：

- `prediction_id`
- `candidate_id`
- `head`
- `relation`
- `tail`
- `decision`: accept / reject / uncertain。
- `confidence`
- `reason`
- `supporting_evidence_ids`
- `verifier_status`: passed / failed / skipped。
- `verifier_details`: schema、evidence、confidence、conflict 各项结果。
- `source`: mock_llm_inference 或 real_llm_inference。

后续使用：

- `PipelineRunner` 从中筛选 final accepted edges。
- `Evaluator` 统计 accepted/rejected/uncertain、verifier_pass_rate、average_confidence。
- debug 或复盘时分析 Verifier 行为。

### predicted_edges.jsonl

由 `PipelineRunner` 从 verified predictions 过滤得到。

进入条件：

```text
decision == "accept" and verifier_status == "passed"
```

`--disable-verifier` ablation 中允许 `verifier_status == "skipped"`。

后续使用：

- `Evaluator` 用它与 `gold_hidden_edges.jsonl` 计算 precision / recall / F1。

### evaluation_report.json

由 `Evaluator.evaluate()` 生成，并由 `PipelineRunner` 补充 `generated_candidate_count`、`reasoned_candidate_count`、`candidate_offset`。

核心字段：

- `precision`
- `recall`
- `f1`
- `gold_count`
- `predicted_edge_count`
- `hit_count`
- `candidate_count`
- `accepted_count`
- `rejected_count`
- `uncertain_count`
- `verifier_pass_rate`
- `average_confidence`
- `generated_candidate_count`
- `reasoned_candidate_count`
- `candidate_offset`

### timing_report.jsonl

开启 `--debug-timing` 时由 `PipelineRunner` 写出。candidate 级记录会增量 append。

stage 记录字段：

- `event: "stage"`
- `stage`
- `elapsed_sec`
- 可选 `candidate_count`、`context_count`、`llm_elapsed_sec`

candidate 记录字段：

- `event: "candidate"`
- `index`、`total`
- `candidate_id`
- `head`、`relation`、`tail`
- `model`
- `prompt_chars`
- `request_start`
- `response_received`
- `llm_elapsed_sec`
- `parse_elapsed_sec`
- `verify_elapsed_sec`
- `total_elapsed_sec`
- `decision`
- `confidence`
- `verifier_status`
- `error_type`
- `warning`
- `attempt_count`
- `attempts`

## 3. 一个 candidate 的完整流转例子

以 `service_payment_api likely_owned_by team_payment` 为例：

1. `CandidateGenerator` 枚举 service 类型 head 和 team 类型 tail。
2. `TaskConfig.is_allowed_pair("service", "team")` 通过 schema filter。
3. `graph.has_relation(service_payment_api, likely_owned_by, team_payment)` 返回 false，因为隐藏边不在 triples 中。
4. `graph.find_paths(...)` 找到结构路径，例如 service -> app -> team。
5. common neighbor 和 evidence overlap 可能同时触发。
6. 生成 candidate：

```json
{
  "candidate_id": "c_001",
  "head": "service_payment_api",
  "relation": "likely_owned_by",
  "tail": "team_payment",
  "generation_rules": ["two_hop_path", "common_neighbor", "evidence_overlap"],
  "rule_scores": {
    "two_hop_path": 0.4,
    "common_neighbor": 0.3,
    "evidence_overlap": 0.2
  },
  "candidate_score": 0.9
}
```

7. `EvidenceRetriever` 基于 head、tail、paths、common_neighbors 取 related triples 和 evidence snippets。
8. `PromptBuilder` 生成 structured context 和 prompt_text。
9. mock mode 下 `MockReasoner` 依据 context 规则输出 accept；real mode 下 `RealLLMReasoner` 调 provider 并解析 JSON。
10. `Verifier` 检查 evidence id、schema、confidence、conflict。
11. 通过后写入 `verified_predictions.jsonl`。
12. 如果是 accept 且 verifier passed，进入 `predicted_edges.jsonl`。
13. `Evaluator` 发现它在 `gold_hidden_edges.jsonl` 中，则 `hit_count` 增加。
