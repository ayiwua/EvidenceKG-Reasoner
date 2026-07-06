# EvidenceKG-Reasoner v2 重构总纲

你现在要帮助我重构 EvidenceKG-Reasoner 项目。

本文件是 EvidenceKG-Reasoner v2 的重构总纲，不是一次性执行提示词。正式执行时必须按 phase 文件逐阶段推进。每一阶段只做该阶段声明范围内的事；阶段完成后新建阶段报告文件，记录完成情况、验收结果、偏离项、是否进入下一阶段。

在正式开始 Phase 0 之前，本总纲可以继续优化。一旦开始 Phase 0，本文件冻结，执行过程中不得回改本总纲。后续新需求、修正建议、阶段偏离统一写入新的 phase 文件、阶段报告或 `progress_log.md`。

## 一、v2 目标

EvidenceKG-Reasoner v2：
面向半结构化企业资产数据的多关系 GraphRAG 证据推理系统。

目标是在当前项目基础上重构出一条更完整、更真实、更能展示工程价值的主流程：

```text
raw CSV 数据
-> DatasetBuilder：解析 CSV、实体归一、关系抽取、证据生成
-> 标准 JSONL：entities.jsonl / triples.jsonl / evidence.jsonl / gold_hidden_edges.jsonl
-> GraphStore：构建 KG、实体索引、证据索引、关系索引、路径查询
-> RelationSchema：定义可补全的关系类型
-> MultiRouteCandidateGenerator：对每种关系类型做多路候选召回
-> Relation-aware Graph Evidence RAG：为每条候选关系检索和组织证据
-> LLMReasoner：通过统一 LLMClient 调用不同 provider
-> HardVerifier：格式、schema、evidence id、confidence、冲突校验
-> SemanticVerifier：校验证据文本是否真正支持候选关系
-> PendingWriteback：输出待审核补边，不直接污染原始图谱
```

## 二、执行原则

1. 不一次性大改整个项目。必须按 phase 文件逐阶段执行。
2. 不追求过度兼容。v2 内部采用统一 schema、统一模块路径、统一输出命名。旧链路如果已经无用，可以在明确记录影响后删除，不为了表面兼容长期保留两套语义。
3. 不做静默 fallback。除 MockLLM 用于本地 smoke run 外，其他降级必须显式记录 `degraded=true`、`fallback_reason` 或 `error_type`。schema 错误、字段缺失、配置错误应 fail fast。
4. 原始 CSV、标准 JSONL、运行时 KG 三层必须解耦：CSV 是原始数据层；JSONL 是标准中间表示层；KG / NetworkX 是运行时索引层。
5. 当前阶段不要引入 Agent，不要上 Neo4j，不要做微调模型。
6. LLM 接口要抽象成多 provider adapter，不要只写死 OpenAI-compatible。
7. 新增功能必须能用 sample data 跑通完整 pipeline。
8. 不追求大规模测试覆盖，但每个阶段必须提供最小 smoke 验证命令和可检查输出。
9. 所有新增代码必须放在现有 Python 包结构下，即 `src/evidencekg/...`，不要新建脱离包结构的 `src/data`、`src/llm`、`src/candidate`。
10. 每次执行前先读当前仓库代码和相关文档，不能只按本总纲臆造实现。

## 三、文件驱动工作流

推荐目录结构：

```text
docs/重构计划/
  codex改进提示词.md
  phase_00_repo_audit.md
  phase_01_dataset_builder.md
  phase_02_graph_store.md
  phase_03_candidate_generation.md
  phase_04_relation_aware_rag.md
  phase_05_llm_adapter.md
  phase_06_reasoner_and_verifier.md
  phase_07_writeback_and_eval.md
  progress_log.md
  reports/
    phase_00_report.md
    phase_01_report.md
```

每个 phase 文件建议包含：

- 阶段目标
- 本阶段范围
- 明确不做什么
- 预计涉及文件
- 输出产物
- 验收标准
- smoke 命令
- 风险与注意事项

每个阶段完成后必须新建报告文件，建议包含：

- 实际新增文件
- 实际修改文件
- 删除的旧链路或废弃接口
- 完成能力
- 验收命令与结果
- 未完成项
- 偏离原计划的地方
- 是否建议进入下一阶段

## 四、标准 Schema 约定

v2 标准 JSONL 使用以下字段。除非 phase 文件明确修改，否则后续实现以这里为准。

`entities.jsonl`：

```json
{
  "id": "svc_payment_api",
  "type": "service",
  "name": "payment-api",
  "aliases": ["payment_api"],
  "properties": {
    "app_name": "payment",
    "port": "8080"
  }
}
```

`triples.jsonl`：

```json
{
  "id": "triple_000001",
  "head": "svc_payment_api",
  "relation": "runs_on",
  "tail": "ip_10_2_3_4",
  "source": "services.csv",
  "source_row_id": "row_12",
  "confidence": 0.95,
  "properties": {}
}
```

`evidence.jsonl`：

```json
{
  "id": "ev_ticket_1023",
  "source": "ticket",
  "source_file": "tickets.csv",
  "source_row_id": "INC-1023",
  "text": "工单 INC-1023 记录 payment-api 在 10.2.3.4 出现超时，由支付团队处理。",
  "related_entities": ["ticket_INC_1023", "svc_payment_api", "ip_10_2_3_4", "team_payment"],
  "timestamp": "2025-05-12",
  "reliability": 0.8,
  "metadata": {}
}
```

`gold_hidden_edges.jsonl`：

```json
{
  "head": "svc_payment_api",
  "relation": "owned_by",
  "tail": "team_payment",
  "source": "services.csv",
  "hide_reason": "evaluation_gold"
}
```

注意：

- v2 内部优先使用 `id`，不继续扩散 `entity_id` / `triple_id` / `evidence_id` 三套字段名。
- 如果旧代码仍依赖旧字段，应该在迁移阶段明确删除、改造或写一次性迁移脚本，不长期保留双字段兼容。
- 隐藏边不能进入 `triples.jsonl`。
- 保留 `source_file` 和 `source_row_id`，用于证据溯源。
- 实体 ID 必须稳定规范化，例如 `10.2.3.4 -> ip_10_2_3_4`、`payment-api -> svc_payment_api`。

## 五、数据接入：CSV -> JSONL

新增数据构建模块，支持从半真实企业资产 CSV 构建标准 JSONL。

推荐新增：

```text
data/raw/
data/processed/
configs/dataset_manifest.yaml
scripts/build_dataset_from_csv.py
src/evidencekg/data/dataset_builder.py
src/evidencekg/data/entity_normalizer.py
src/evidencekg/data/evidence_builder.py
```

需要先支持的 raw CSV：

- `teams.csv`：`team_id,team_name,department,oncall_email`
- `assets.csv`：`asset_id,asset_type,ip,hostname,env,region`
- `services.csv`：`service_id,service_name,app_name,owner_team,host_ip,port`
- `dns_records.csv`：`domain,record_type,value,source,timestamp`
- `tickets.csv`：`ticket_id,title,description,related_service,related_ip,assigned_team,timestamp`
- `alerts.csv`：`alert_id,title,description,related_service,related_ip,assigned_team,severity,timestamp`
- `service_dependencies.csv`：`source_service,target_service,evidence_source,timestamp`

`dataset_manifest.yaml` 用来描述 CSV 文件和字段映射，避免字段名完全写死。例如：

```yaml
tables:
  services:
    file: services.csv
    entity_type: service
    id_column: service_id
    name_column: service_name
    fields:
      owner_team: team
      host_ip: ip
      port: port

  tickets:
    file: tickets.csv
    entity_type: ticket
    id_column: ticket_id
    text_columns: [title, description]
    related_entity_columns:
      - related_service
      - related_ip
      - assigned_team
```

如果 raw CSV 不存在，提供一组 sample CSV，使 pipeline 能跑通。

## 六、GraphStore：JSONL -> KG / 索引

GraphStore 只读取标准 JSONL，不直接依赖 CSV。

需要构建：

- `entity_dict`: `id -> entity object`
- `triple_list`: `list of triples`
- `graph`: NetworkX MultiDiGraph，边上保留 `relation/source/confidence/properties`
- `evidence_dict`: `id -> evidence object`
- `entity_to_evidence`: `entity_id -> [evidence_id]`
- `entity_by_type`: `entity_type -> [entity_id]`
- `relation_index`: `relation -> [(head, tail)]`
- `alias / name index`: 用于属性相似召回

GraphStore 基础方法：

```text
get_entity(entity_id)
get_entities_by_type(type_name)
get_neighbors(entity_id, relation=None, direction="both")
get_shortest_path(head, tail, max_depth=3)
get_common_neighbors(head, tail)
get_evidence(evidence_id)
get_evidence_by_entity(entity_id)
has_edge(head, relation, tail)
```

旧 GraphStore 接口如果阻碍 v2 schema，可以在对应 phase 中删除或迁移，不要求长期兼容。

## 七、多关系 Schema：relation_schema.yaml

新增 `configs/relation_schema.yaml`。

先支持三类核心补全关系：

- `owned_by / managed_by`：IP、Host、Service、Application 可能由某个 Team 负责。
- `runs_on / deployed_on`：Service / Application 运行在某个 IP / Host / Container 上。
- `depends_on / calls`：Service / Application 依赖或调用另一个 Service / Application。

每种关系要包含：

- relation name
- description
- head_types
- tail_types
- preferred_sources
- recall_routes
- prompt_guidance
- semantic_verification_criteria
- max_candidates

## 八、多路候选召回：MultiRouteCandidateGenerator

重构 CandidateGenerator 为 schema-driven multi-route candidate generation。

推荐新增：

```text
src/evidencekg/candidate/base.py
src/evidencekg/candidate/schema_recall.py
src/evidencekg/candidate/path_recall.py
src/evidencekg/candidate/common_neighbor_recall.py
src/evidencekg/candidate/evidence_cooccurrence_recall.py
src/evidencekg/candidate/attribute_similarity_recall.py
src/evidencekg/candidate/source_specific_recall.py
src/evidencekg/candidate/multi_route_generator.py
```

核心思想：

对每种 relation type，根据 `relation_schema.yaml` 中的 `head_types/tail_types/recall_routes` 生成候选。不同召回通道生成的相同候选按 key 合并：

```text
key = (head, relation, tail)
```

候选对象 schema：

```json
{
  "candidate_id": "cand_000001",
  "head": "svc_payment_api",
  "relation": "owned_by",
  "tail": "team_payment",
  "candidate_score": 2.35,
  "recall_sources": ["schema_type", "path_rule", "evidence_cooccurrence"],
  "debug": {
    "shared_evidence_count": 3,
    "shortest_path_len": 2,
    "common_neighbor_count": 2,
    "attribute_similarity": 0.42,
    "source_hits": ["ticket", "service_registry"]
  }
}
```

召回通道：

- `schema_type`：只生成类型合法的实体对，分数低。
- `path_rule`：head 和 tail 在 KG 中存在短路径时召回。
- `common_neighbor`：head 和 tail 有公共邻居时召回。
- `evidence_cooccurrence`：head 和 tail 出现在同一条 evidence.related_entities 中时召回。
- `attribute_similarity`：基于 name / aliases / domain / service token 的弱相似信号。
- `source_specific_rule`：针对 ticket、service_registry、dns、service_dependencies 的强规则。

要求：

- 已经存在于 `triples.jsonl` 的同类型边不要作为待补全候选，除非配置 `allow_existing=true`。
- 对每个 relation_type 限制 `max_candidates`。
- 保留 `recall_sources` 和 `debug`。
- 候选生成阶段要能单独运行。
- 最终输出 `candidate_edges.jsonl`。

## 九、RAG 增强：Relation-aware Graph Evidence RAG

在 EvidenceRetriever 基础上增强为 relation-aware retrieval，不要只做普通 `query -> topK`。

需要支持：

- Relation-aware Query Builder：根据 relation type 构造不同 query。
- Metadata Filtering：优先使用包含 head/tail、preferred_sources、可靠性更高的 evidence。
- Hybrid Retrieval：关键词检索 + dense embedding 检索。若 embedding/reranker 不可用，不应静默降级；必须显式记录 degraded 状态。是否允许 keyword-only 模式由配置控制。
- Cross-encoder rerank：如果启用 cross-encoder 但模型不可用，应明确失败或显式 degraded。
- Evidence Expansion：根据 evidence.related_entities 找邻居实体，再拉取相关 evidence。
- Supporting evidence + conflict evidence：区分 `supporting_evidence_candidates` 和 `conflict_evidence_candidates`。
- Context Packing：输出结构化 context，而不是简单拼接 topK。

输出 `evidence_contexts.jsonl`。

## 十、多 Provider LLM 接口

重构 LLM 调用层，设计统一 LLMClient 接口，通过 adapter 支持多个 provider。

推荐新增：

```text
src/evidencekg/llm/base_client.py
src/evidencekg/llm/openai_compatible_client.py
src/evidencekg/llm/anthropic_client.py
src/evidencekg/llm/local_client.py
src/evidencekg/llm/mock_client.py
src/evidencekg/llm/client_factory.py
```

统一接口：

```python
class BaseLLMClient:
    def chat(self, messages, **kwargs) -> LLMResponse:
        raise NotImplementedError
```

统一 `LLMResponse`：

```json
{
  "provider": "openai_compatible",
  "model": "gpt-4o-mini",
  "content": "...",
  "latency_ms": 1234,
  "usage": {
    "input_tokens": 1000,
    "output_tokens": 300
  },
  "raw": {}
}
```

需要实现：

- `OpenAICompatibleClient`：支持 `base_url`、`model`、`api_key_env`。
- `AnthropicClient`：支持 Anthropic 原生 messages API，依赖缺失或 API key 不存在时不影响其他 provider。
- `MockLLMClient`：用于本地 smoke run，返回固定 JSON。
- `ClientFactory`：根据 config 选择 provider。

注意：

- 不宣称兼容所有模型，只通过 adapter 扩展不同 provider。
- Reasoner 上层不关心 provider 差异。
- 保留 `timeout`、`max_retries`、`retry_interval`、`temperature`、`max_tokens`。
- 失败后可以生成 uncertain，但必须记录 `error_type`、`fallback_reason`、`raw_response` 或 provider metadata。

## 十一、LLMReasoner 输出结构升级

LLM 不应只输出 `accept/reject/uncertain`。升级结构化输出 schema：

```json
{
  "decision": "accept | reject | uncertain",
  "confidence": 0.82,
  "relation": "owned_by",
  "reason": "...",
  "supporting_evidence_ids": ["ev_001", "ev_002"],
  "conflict_evidence_ids": [],
  "evidence_analysis": [
    {
      "evidence_id": "ev_001",
      "support_label": "strong_support | weak_support | irrelevant | conflict",
      "explanation": "..."
    }
  ]
}
```

解析策略：

- `json.loads` 优先；
- 如果返回 Markdown 包裹 JSON，尝试抽取 JSON object；
- 字段 normalize；
- decision 非法则 uncertain；
- confidence clamp 到 `[0,1]`；
- evidence ids 必须是 `list[str]`；
- 解析失败 fallback uncertain，并记录 `parse_error`。

## 十二、SemanticVerifier

在 HardVerifier 后新增 SemanticVerifier。

目的：解决 evidence_id 合法，但 evidence 语义不支持 candidate relation 的问题。

流程：

```text
LLMReasoner 输出 accept
-> HardVerifier 通过
-> SemanticVerifier 对 supporting evidence 做语义支持性判断
-> 只有证据真正支持关系，才进入 pending_edges
```

输出 schema：

```json
{
  "support_status": "supported | partially_supported | not_supported | conflicted",
  "supported_evidence_ids": ["ev_001"],
  "weak_evidence_ids": ["ev_002"],
  "irrelevant_evidence_ids": ["ev_003"],
  "conflict_evidence_ids": [],
  "reason": "..."
}
```

定位：

- SemanticVerifier 是 evidence support checking，不是万能事实裁判。
- 不要写成简单 evidence_id 校验。
- 如果使用 LLM，必须通过统一 LLMClient 调用。

## 十三、Pending Writeback

新增或增强 writeback 模块：

```text
outputs/pending_edges.jsonl
outputs/review_decisions.jsonl
outputs/triples.enriched.jsonl
```

流程：

```text
accept + verifier passed -> pending_edges.jsonl
人工在 review_decisions.jsonl 中标记 approved/rejected
scripts/apply_review.py 根据 review_decisions.jsonl 生成 triples.enriched.jsonl
不覆盖原始 triples.jsonl
```

`pending_edges.jsonl`：

```json
{
  "candidate_id": "...",
  "head": "...",
  "relation": "...",
  "tail": "...",
  "confidence": 0.82,
  "supporting_evidence_ids": [],
  "semantic_status": "supported",
  "reason": "...",
  "recall_sources": [],
  "created_at": "..."
}
```

## 十四、输出报告

每次完整运行后，输出：

```text
outputs/candidate_edges.jsonl
outputs/evidence_contexts.jsonl
outputs/llm_predictions.jsonl
outputs/verified_predictions.jsonl
outputs/pending_edges.jsonl
outputs/evaluation_report.json
```

`evaluation_report.json` 至少包含：

```yaml
candidate:
  candidate_count
  candidate_count_by_relation
  candidate_recall_if_gold_available

retrieval:
  avg_evidence_count
  empty_context_rate
  evidence_recall_at_k_if_gold_available

llm:
  accept_count
  reject_count
  uncertain_count
  parse_error_count
  fallback_count

verifier:
  hard_pass_count
  hard_fail_count
  semantic_supported_count
  semantic_not_supported_count
  semantic_conflicted_count

final:
  precision
  recall
  f1
  hit_count
```

## 十五、CLI 入口

尽量提供清晰 CLI 或脚本入口：

```bash
python scripts/build_dataset_from_csv.py \
  --manifest configs/dataset_manifest.yaml \
  --raw-dir data/raw \
  --out-dir data/processed
```

```bash
python scripts/generate_candidates.py \
  --data-dir data/processed \
  --relation-schema configs/relation_schema.yaml \
  --out outputs/candidate_edges.jsonl
```

```bash
python scripts/run_pipeline.py \
  --data-dir data/processed \
  --relation-schema configs/relation_schema.yaml \
  --llm-config configs/llm.yaml \
  --out-dir outputs
```

```bash
python scripts/apply_review.py \
  --triples data/processed/triples.jsonl \
  --pending outputs/pending_edges.jsonl \
  --review outputs/review_decisions.jsonl \
  --out outputs/triples.enriched.jsonl
```

## 十六、建议阶段顺序

### Phase 0：仓库审查与重构边界确认

- 阅读当前仓库结构、核心代码、已有文档。
- 输出当前模块理解、v1 可删除/可迁移链路、v2 需要新增/修改文件列表。
- 不改代码。

### Phase 1：CSV -> JSONL DatasetBuilder

- 实现 DatasetBuilder、EntityNormalizer、EvidenceBuilder。
- 提供 sample raw CSV。
- 生成标准 JSONL。

### Phase 2：GraphStore v2

- 按标准 JSONL 构图和建索引。
- 清理或迁移旧 GraphStore schema。

### Phase 3：RelationSchema + MultiRouteCandidateGenerator

- 实现 `relation_schema.yaml`。
- 实现多路候选召回。
- 输出 `candidate_edges.jsonl`。

### Phase 4：Relation-aware RAG

- 增强 EvidenceRetriever。
- 输出 `evidence_contexts.jsonl`。

### Phase 5：LLMClient Adapter

- 实现 BaseLLMClient、OpenAICompatibleClient、AnthropicClient、MockLLMClient、ClientFactory。

### Phase 6：Reasoner + HardVerifier + SemanticVerifier

- 升级 LLMReasoner 输出 schema。
- 实现 HardVerifier 和 SemanticVerifier 的 v2 流程。

### Phase 7：Pending Writeback + Eval + Pipeline

- 实现 pending_edges、apply_review、evaluation_report。
- 跑通 sample pipeline。

## 十七、不要做的事

1. 不要把项目改成 Agent。
2. 不要引入 Neo4j 作为强依赖。
3. 不要强制依赖真实 LLM 才能跑通；必须有 MockLLM。
4. 不要把 Claude / Anthropic 调用写成 OpenAI-compatible。
5. 不要直接覆盖原始 `triples.jsonl`。
6. 不要让 LLM 自由生成关系类型；关系类型必须来自 `relation_schema.yaml`。
7. 不要把 SemanticVerifier 写成简单 evidence_id 校验。
8. 不要为了兼容旧链路保留长期无用代码。
9. 不要为了测试写大量无关代码；每阶段保留必要 smoke 验证即可。
