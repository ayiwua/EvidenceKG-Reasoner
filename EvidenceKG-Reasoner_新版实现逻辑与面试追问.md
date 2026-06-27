# EvidenceKG-Reasoner 新版实现逻辑与面试追问

项目名称：EvidenceKG-Reasoner / 基于 GraphRAG 的企业 IP 与 IT 资产证据推理系统

这份文档面向技术面试准备，不是用户手册。重点是解释当前仓库最新版代码实际做了什么、为什么这样做、有哪些工程取舍、边界在哪里，以及面试中如何回答追问。

## 1. 项目整体 Pipeline

端到端调用链：

```text
scripts/run_pipeline.py
  -> PipelineRunner.run()
  -> load_task_config()
  -> GraphStore.from_dir()
  -> CandidateGenerator.generate()
  -> EvidenceRetriever.retrieve()
  -> PromptBuilder.build()
  -> MockReasoner.predict() / RealLLMReasoner.predict()
  -> OpenAICompatibleClient.complete()   # real mode only
  -> Verifier.verify()
  -> predicted_edges.jsonl
  -> Evaluator.evaluate()
  -> KGWritebackManager / EdgeWriter     # optional writeback
```

### scripts/run_pipeline.py

输入：命令行参数，包括 `--config`、`--data-dir`、`--output-dir`、`--stage`、`--max-candidates`、`--candidate-offset`、`--disable-verifier`、`--debug-timing`、`--enable-writeback`、`--writeback-mode`。

内部逻辑：解析参数，调用 `PipelineRunner().run(...)`。

输出：将 `PipelineRunner.run()` 返回的 report 以 JSON 打印到终端。

下一步：所有核心流程都在 `PipelineRunner.run()` 中执行。

### PipelineRunner.run()

输入：配置路径、数据目录、输出目录、运行阶段、候选窗口参数、LLM 超时/重试覆盖参数、writeback 开关。

内部逻辑：

1. 加载 YAML 配置。
2. 用 `GraphStore.from_dir(data_dir)` 读取 JSONL KG。
3. 用 `CandidateGenerator.generate()` 生成候选关系。
4. 写 `candidate_pairs.jsonl`。
5. 如果 `stage=candidates`，到此返回。
6. 根据 `candidate_offset` 和 `max_candidates` 选择进入推理窗口的候选。
7. 生成 `run_metadata.json`，用于判断是否可 resume。
8. 对每个候选调用 `EvidenceRetriever.retrieve()` 构造 evidence context。
9. 写 `evidence_contexts.jsonl`。
10. 用 `PromptBuilder.build()` 构造结构化上下文和 prompt。
11. 调用 mock 或 real reasoner。
12. 默认走 `Verifier.verify()`；如果 `disable_verifier=True`，走 `_raw_prediction()`。
13. 写 `verified_predictions.jsonl`。
14. 筛出最终 `predicted_edges.jsonl`。
15. 调用 `Evaluator.evaluate()` 计算 hidden edge recovery 指标。
16. 如果启用 writeback，调用 `KGWritebackManager.writeback()`。
17. 写 `evaluation_report.json`，debug 时写 `timing_report.jsonl`。

输出：evaluation report 字典。启用 writeback 时，report 内会多一个 `writeback` 字段。

### GraphStore.from_dir()

输入：数据目录，默认需要：

```text
entities.jsonl
evidence.jsonl
triples.jsonl
```

内部逻辑：依次加载实体、证据、三元组，并建立字典索引与 NetworkX `MultiDiGraph`。

输出：`GraphStore` 实例。

下一步：CandidateGenerator、EvidenceRetriever、Verifier、Evaluator 都会依赖它读取图结构和证据。

### CandidateGenerator.generate()

输入：`TaskConfig` 和 `GraphStore`。

内部逻辑：枚举合法 head/tail 类型组合，排除 self-pair 和已有 target relation 边，基于路径、共同邻居、证据 overlap 计算规则分数。

输出：候选关系列表，每条包含 `candidate_id`、`head`、`relation`、`tail`、`generation_rules`、`rule_scores`、`candidate_score`、`paths`、`common_neighbors`。

下一步：EvidenceRetriever 对这些候选做证据检索。

### EvidenceRetriever.retrieve()

输入：单个 candidate、config、graph。

内部逻辑：构造 graph-aware candidate query；用 bi-encoder 对 query 做 dense retrieval；用 cross-encoder 对召回 evidence 精排；返回上下文结构。

输出：evidence context，包含：

```text
candidate_id
candidate
head_profile
tail_profile
graph_paths
common_neighbors
related_triples
evidence_snippets
```

下一步：PromptBuilder 将该上下文序列化进 prompt。

### PromptBuilder.build()

输入：EvidenceRetriever 返回的 evidence context。

内部逻辑：保留完整 `structured_context`，同时构造一个文本 prompt，要求 LLM 只使用 provided context，不得 invent evidence ids。

输出：

```text
structured_context
prompt_text
```

下一步：Reasoner 使用这两个对象产生 prediction。

### MockReasoner.predict()

输入：structured context 和可选 prompt_text。

内部逻辑：不调用真实 LLM，根据候选分数、是否有 evidence、是否有 path/common neighbor 做规则判断。

输出：模拟的 LLM prediction：

```json
{
  "decision": "accept|reject|uncertain",
  "confidence": 0.0,
  "reason": "...",
  "supporting_evidence_ids": []
}
```

### RealLLMReasoner.predict()

输入：structured context 和 prompt_text。

内部逻辑：调用 OpenAI-compatible client，解析 JSON，归一化字段；调用失败或解析失败时在 reasoner 层降级为 `uncertain`。

输出：同样的 prediction schema。

### OpenAICompatibleClient.complete()

输入：prompt_text、attempt index、candidate_id、debug timing 标志。

内部逻辑：从环境变量或 `.env` 读取 API key、base_url、model；用 OpenAI SDK 调 `/chat/completions` 兼容接口；支持 timeout、temperature、trust_env、debug heartbeat。

输出：模型返回的 message content 字符串。

### Verifier.verify()

输入：candidate、context、prediction、config、graph。

内部逻辑：做 schema、evidence grounding、confidence threshold、conflict 检查。根据检查结果可能改写 decision，并标注 `verifier_status` 和 `verifier_details`。

输出：verified prediction。

下一步：只有 `decision=accept` 且 `verifier_status=passed` 的记录进入 `predicted_edges.jsonl` 和 writeback。

### Evaluator.evaluate()

输入：`predicted_edges.jsonl`、`gold_hidden_edges.jsonl`、可选 `verified_predictions.jsonl`。

内部逻辑：按 `(head, relation, tail)` 集合比较 predicted 和 gold，计算 precision、recall、F1、hit_count，并统计 accept/reject/uncertain、verifier pass rate、平均置信度。

输出：evaluation report。

### KGWritebackManager / EdgeWriter

输入：verified predictions、graph、output_dir、writeback mode。

内部逻辑：只处理 `decision=accept` 且 `verifier_status=passed` 的 prediction；做 duplicate/conflict 检查；写 pending 或 enriched KG 文件。

输出：

```text
pending_edges.jsonl       # pending mode
triples.enriched.jsonl    # approved mode
writeback_report.json
```

## 2. 数据格式与配置

### entities.jsonl

每条 entity 是一个 JSON object，主要字段：

```json
{
  "entity_id": "ip_001",
  "name": "10.12.3.21",
  "type": "ip",
  "description": "Office observed IP for payment API access.",
  "attributes": {
    "subnet": "10.12.3.0/24",
    "asset_zone": "office_network"
  }
}
```

字段说明：

- `entity_id`：实体唯一 id，必需。
- `name`：展示名或业务名。
- `type`：实体类型，例如 `ip`、`host`、`service`、`api`、`database`、`application`、`team`、`department`、`person`。
- `description`：文本描述。
- `attributes`：可选属性字典，检索时会拼进 query/evidence text。

### triples.jsonl

每条 triple 是已有 KG 边：

```json
{
  "triple_id": "t_001",
  "head": "ip_001",
  "relation": "belongs_to_subnet",
  "tail": "subnet_office_a",
  "evidence_ids": ["ev_023"],
  "confidence": 0.93,
  "source": "scan_log",
  "observed_at": "2026-05-12",
  "valid_from": "2026-05-12",
  "valid_to": null,
  "location": "building_A"
}
```

必需核心字段是 `triple_id/head/relation/tail`。`evidence_ids`、`confidence`、`source`、时间和 location 字段在当前代码中是可选使用，GraphStore 会把 `evidence_ids` 用于从 triple 找 evidence。

### evidence.jsonl

每条 evidence 是证据片段：

```json
{
  "evidence_id": "ev_001",
  "source": "ticket",
  "text": "Payment team reported intermittent timeout...",
  "timestamp": "2026-05-12",
  "related_entities": ["ip_001", "service_payment_api", "team_payment"],
  "location": "building_A",
  "reliability": 0.9
}
```

字段说明：

- `evidence_id`：证据唯一 id。
- `source`：来源，例如 ticket、document、alert、scan_log。
- `text`：证据正文。
- `timestamp`：证据时间。
- `related_entities`：关联实体 id 列表。
- `location`：可选。
- `reliability`：证据可靠度，当前 retrieval 会拼进 evidence text，但没有做学习型校准。

### gold_hidden_edges.jsonl

hidden edge recovery 评估用 gold 边，核心字段：

```json
{
  "head": "ip_001",
  "relation": "likely_owned_by",
  "tail": "team_payment"
}
```

Evaluator 只用 `(head, relation, tail)` 做集合比较。

### configs/*.yaml

核心配置包括：

- `task_name`
- `target_relation`
- `allowed_head_types`
- `allowed_tail_types`
- `candidate_rules`
- `schema_filter`
- `evidence_retrieval`
- `llm`
- `verifier`
- `evaluation`

当前 `evidence_retrieval` 新版字段：

```yaml
evidence_retrieval:
  max_hops: 3
  max_paths: 5
  max_evidence_snippets: 8
  top_k_before_rerank: 30
  top_k_after_rerank: 8
  bi_encoder_model: sentence-transformers/all-MiniLM-L6-v2
  cross_encoder_model: cross-encoder/ms-marco-MiniLM-L-6-v2
  include_entity_profiles: true
  include_graph_paths: true
  include_common_neighbors: true
  include_related_triples: true
```

注意：writeback 不是 YAML 配置字段，而是 CLI 参数：

```text
--enable-writeback
--writeback-mode pending|approved
```

## 3. GraphStore 实现逻辑

`GraphStore` 同时维护字典和 NetworkX `MultiDiGraph`。

字典的作用：

- `entities: dict[str, dict]`：按 entity_id 快速取实体。
- `triples: dict[str, dict]`：按 triple_id 快速取边。
- `evidence: dict[str, dict]`：按 evidence_id 快速取证据。
- `_triples_by_pair`：按 `(head, tail)` 找边。
- `_triples_by_entity`：按实体找相关 triple。
- `_evidence_by_entity`：加载 evidence 时建立，但当前 `get_evidence_for_entities()` 实际是遍历全部 evidence 计算 overlap。

NetworkX `MultiDiGraph` 的作用：

- 节点是 entity_id。
- 边是 triple。
- 边 key 使用 `triple_id`。
- 边属性包括 `triple_id` 和 `relation`。

为什么是 MultiDiGraph：同一对实体之间可能存在多种关系或多条边，用 MultiDiGraph 可以用不同 key 存储。

关键函数：

- `get_entity(entity_id)`：从实体字典取实体。
- `iter_entities_by_type(entity_types)`：按类型枚举实体，用于 candidate head/tail 枚举。
- `iter_triples()`：返回全部 triple。
- `get_triple(triple_id)`：按 id 取 triple。
- `get_triples_between(head, tail)`：查 head->tail 和 tail->head 两个方向的边。
- `get_triples_for_entities(entity_ids)`：返回这些实体相关的 triple。
- `get_related_triples(entity_id)`：返回单个实体相关 triple。
- `has_relation(head, relation, tail)`：判断已有 KG 中是否已有目标边。
- `get_evidence(evidence_id)`：按 id 取 evidence。
- `get_evidence_for_triple(triple_id)`：根据 triple.evidence_ids 找 evidence。
- `get_evidence_for_entities(entity_ids)`：计算 evidence.related_entities 与 query entities 的 overlap，按 overlap 降序返回。
- `get_neighbors(entity_id)`：返回前驱和后继的并集。
- `find_paths(head, tail, max_hops, max_paths)`：把有向图转成无向 `nx.Graph` 后做 BFS，找最多 max_paths 条短路径。

当前没有 Neo4j、RDF、SPARQL 或图数据库持久化。数据源是 JSONL，图索引是进程内 NetworkX。

面试口径：为什么 JSONL 读进来还要建 NetworkX？

可以答：JSONL 适合作为轻量可复现的数据交换格式，但它不适合做邻居查询、路径查询和结构规则计算。NetworkX 是运行时结构索引，帮助快速做 common neighbor、path search、关系存在性检查。两者分工不同：JSONL 负责存储和复现实验，NetworkX 负责图算法。

## 4. CandidateGenerator 实现逻辑

`CandidateGenerator.generate(config, graph)` 流程：

1. 用 `graph.iter_entities_by_type(config.allowed_head_types)` 枚举 head。
2. 用 `graph.iter_entities_by_type(config.allowed_tail_types)` 枚举 tail。
3. 跳过 `head_id == tail_id` 的 self-pair。
4. 用 `config.is_allowed_pair(head["type"], tail["type"])` 再做 schema 检查。
5. 用 `graph.has_relation(head_id, target_relation, tail_id)` 排除已有目标关系边。
6. 调 `_score_pair()` 计算规则分数、paths、common_neighbors。
7. 如果没有任何规则分数大于 0，则不生成候选。
8. 用 `(head, relation, tail)` 去重。
9. 计算 `candidate_score = sum(rule_scores.values())`。
10. 按 `candidate_score` 降序排序，并重新编号 `candidate_id`。

type-only pair 不会生成，因为仅类型合法不够。必须命中至少一个结构或证据规则。

规则：

- `two_hop_path`：如果存在 path，最短路径小于等于 2 跳给 0.4，否则给 0.25。
- `common_neighbor`：head/tail 邻居交集非空，分数 `min(0.3, 0.15 + 0.05 * count)`。
- `evidence_overlap`：如果存在 evidence 同时关联 head 和 tail，给 0.2。

`candidate_score` 不是训练出来的，是规则分数求和，用于排序和 mock reasoner 的启发式判断。

`candidate_pairs.jsonl` 字段：

```text
candidate_id
head
relation
tail
generation_rules
rule_scores
candidate_score
paths
common_neighbors
```

面试追问：

为什么不让 LLM 直接生成候选关系？

好回答：候选生成阶段用 schema 和图结构约束搜索空间，避免 LLM 在全图上自由生成导致不可控、不可复现、难验证。LLM 更适合作为 evidence-grounded judge，而不是开放式 KG completion 生成器。

为什么先候选生成再 LLM 判断？

好回答：这是 coarse-to-fine 设计。规则候选保证召回和可解释性，LLM 负责判断候选是否被证据支持，Verifier 再做硬约束校验。

如果候选召回漏了正确边怎么办？

好回答：后续要优化 candidate generator，例如增加更多结构规则、文本召回候选、schema 扩展、弱监督学习排序；当前 LLM 不会生成未进入 candidate set 的边，所以候选召回是上限。

## 5. 新版 EvidenceRetriever：Graph-aware Evidence RAG

当前最新版不是旧规则 overlap evidence retrieval，也不是 BM25/hybrid 多模式。它是固定两阶段：

```text
graph-aware candidate query
  -> bi-encoder dense recall
  -> cross-encoder rerank
  -> top evidence snippets
```

生产代码没有 fallback。如果 `sentence-transformers` 或模型不可用，会直接暴露错误。

### 5.1 输入输出

输入：

- `candidate: dict`
- `config: TaskConfig`
- `graph: GraphStore`

输出仍包含：

```text
candidate_id
candidate
head_profile
tail_profile
graph_paths
common_neighbors
related_triples
evidence_snippets
```

`evidence_snippets` 中新增：

- `embedding_score`
- `rerank_score`
- `retrieval_query`
- `retrieval_rank`

### 5.2 evidence corpus 怎么构造

入口是 `_get_or_build_corpus(config, graph)`。

流程：

```python
for evidence in graph.evidence.values():
    evidence_ids.append(evidence["evidence_id"])
    evidence_texts.append(self._build_evidence_text(evidence, graph))

bi_encoder = self._get_bi_encoder(config.bi_encoder_model)
evidence_embeddings = self._as_vectors(bi_encoder.encode(evidence_texts))
```

`_build_evidence_text()` 拼入：

- evidence 原文 `text`
- `source`
- `related_entities` id
- related entity 的 `id/name/type/description/attributes`
- `timestamp`
- `reliability`

corpus 缓存结构：

```python
{
    "evidence_ids": [...],
    "evidence_texts": [...],
    "evidence_embeddings": [...]
}
```

缓存变量：

```python
self._corpus_cache: dict[tuple[int, str], dict[str, Any]]
```

cache key：

```python
(id(graph), config.bi_encoder_model)
```

当前没有向量数据库，没有 FAISS/Milvus/Chroma，只是进程内 embedding cache。

### 5.3 embedding 怎么计算

bi-encoder 加载：

```python
from sentence_transformers import SentenceTransformer
encoder = SentenceTransformer(model_name)
```

默认模型：

```text
sentence-transformers/all-MiniLM-L6-v2
```

evidence embeddings：首次构建 corpus 时计算并缓存，不是每个 candidate 重算。

query embedding：每个 candidate 都会重新构造 query，并调用：

```python
query_embedding = self._first_vector(bi_encoder.encode([retrieval_query]))
```

cosine similarity：

```python
dot / (left_norm * right_norm)
```

`top_k_before_rerank` 从 `config.evidence_retrieval.top_k_before_rerank` 读取。

### 5.4 candidate_query 怎么构造

函数：`_build_candidate_query(candidate, related_triples, graph)`。

包含：

- 固定意图文本：`Find evidence supporting this candidate relation.`
- target relation
- head entity profile：id/name/type/description/attributes
- tail entity profile：id/name/type/description/attributes
- common neighbors：id/name/type/description/attributes
- graph paths：路径中实体和相邻实体间关系摘要
- related triples：head entity text + relation + tail entity text + source

为什么叫 graph-aware query？

因为它不是只拿 `head relation tail` 做普通文本查询，而是把候选周围的图结构证据也编码进 query，包括路径、共同邻居、相关三元组和实体属性。这样 dense retriever 能检索到与候选结构上下文相关的 evidence。

### 5.5 粗排 dense recall

输入：

- `retrieval_query`
- 全量已缓存 `evidence_embeddings`

输出：

- 粗排 topK evidence index 和 `embedding_score`

逻辑：

1. 编码 query。
2. 对全量 evidence embeddings 计算 cosine similarity。
3. 按 `embedding_score` 降序排序。
4. 取 `top_k_before_rerank`。

`embedding_score` 是 query embedding 和 evidence embedding 的余弦相似度，不是最终关系置信度。

`retrieval_rank` 是精排之后生成的，不是粗排 rank。

复杂度：当前是每个 query 对全量 evidence 做线性扫描，约 `O(N * d)`，N 是 evidence 数量，d 是 embedding 维度。样例数据很小，所以可接受。

### 5.6 cross-encoder rerank

cross-encoder 加载：

```python
from sentence_transformers import CrossEncoder
encoder = CrossEncoder(model_name)
```

默认模型：

```text
cross-encoder/ms-marco-MiniLM-L-6-v2
```

输入 pair：

```python
[(retrieval_query, evidence_text), ...]
```

调用：

```python
rerank_scores = cross_encoder.predict(pairs)
```

`rerank_score` 是 query/evidence pair 的相关性分数，不等于候选关系为真的业务 confidence。

`top_k_after_rerank` 从 `config.evidence_retrieval.top_k_after_rerank` 读取。最终还会受 `max_evidence_snippets` 上限约束：

```python
min(top_k_after_rerank, max_evidence_snippets, len(ranked))
```

为什么只 rerank 粗排 topK？

cross-encoder 比 bi-encoder 慢得多，因为它要联合编码每个 query-evidence pair。先用 bi-encoder 快速缩小候选证据，再对 topK 精排，是典型效率/质量折中。

### 5.7 和 Verifier grounding 的关系

EvidenceRetriever 只负责选择进入 context 的 evidence snippets。

LLM 输出：

```json
{
  "supporting_evidence_ids": ["ev_001"]
}
```

Verifier 检查：

1. prediction 如果不是 accept，grounding 直接通过。
2. accept 必须有 supporting evidence ids。
3. 每个 id 必须来自当前 context 的 `evidence_snippets`。
4. 该 evidence 必须存在于 graph.evidence。
5. evidence.related_entities 至少包含 candidate head 或 tail。

如果 LLM 引用不存在或未提供的 evidence id，默认会被改成 `reject` 且 `verifier_status=failed`。不会进入 `predicted_edges.jsonl`，也不会进入 writeback。

面试口径：

为什么不用向量数据库？

当前 evidence 只有几十条，内存向量扫描简单、可复现、依赖少。规模变大后可以把 `_get_or_build_corpus` 的内存 cache 替换为 FAISS/Milvus/Chroma 索引。

为什么 bi-encoder + cross-encoder？

bi-encoder 快，可以缓存 evidence embedding 做粗召回；cross-encoder 慢但更准，只对 topK 做精排，提高证据质量。

为什么 embedding_score/rerank_score 不能当最终 confidence？

它们只是 query-evidence 相关性分数，不判断候选关系是否真实成立。最终关系判断还需要 LLM 基于上下文推理，并由 Verifier 做硬约束检查。

没有训练自己的 retriever/reranker 怎么解释？

当前是工程原型和小数据验证阶段，使用 sentence-transformers 预训练权重做零样本语义检索。后续如果有标注 query-evidence 或 relation-evidence 数据，可以微调 bi-encoder/cross-encoder。

如果 evidence 数量变大怎么扩展？

把全量 cosine 扫描替换成 ANN 向量索引；保留 cross-encoder topK rerank；增量更新 evidence embedding；增加 embedding cache 持久化和版本管理。

## 6. PromptBuilder 实现逻辑

`PromptBuilder.build(evidence_context)` 输入 EvidenceRetriever 的 context。

输出：

```python
{
    "structured_context": structured_context,
    "prompt_text": prompt_text
}
```

`structured_context` 是原始结构化上下文，供 MockReasoner、Verifier 或调试使用。

`prompt_text` 是给真实 LLM 的文本，其中包含 compact context JSON：

- candidate
- head_profile
- tail_profile
- graph_paths
- common_neighbors
- related_triples
- evidence_snippets

prompt 明确要求：

- Use only the provided context.
- Do not invent evidence ids.
- Return only valid JSON.

要求输出 schema：

```json
{
  "decision": "accept|reject|uncertain",
  "confidence": 0.0,
  "reason": "short explanation",
  "supporting_evidence_ids": []
}
```

面试口径：

为什么需要 structured_context？

因为后续 Verifier 和 MockReasoner 需要机器可读结构，不应该再从 prompt 文本里反解析。

为什么不直接把 evidence 拼成一段文本？

结构化上下文保留了实体、路径、三元组、证据 id、检索分数等字段，便于 grounding、审计和验证。

Prompt 能不能完全防幻觉？

不能。Prompt 是软约束，Verifier 是硬约束。LLM 仍可能输出不存在 evidence id，因此必须有 Verifier。

## 7. Reasoner 与 LLM 接入

### 7.1 MockReasoner

输入：context 和可选 prompt_text。

输出：标准 prediction dict。

规则：

- 取 `candidate_score`。
- 如果有 evidence、有 graph paths，且有 common_neighbors 或 score >= 0.6，并且 confidence >= 0.7，则 accept。
- 如果 tail 类型是 `department` 或 `person`，mock 会故意引用 bad evidence id，用来测试 Verifier。
- 如果 evidence 或 paths 存在但不够强，则 uncertain。
- 否则 reject。

为什么需要 mock？

mock 让 pipeline 本地可跑、可测、可复现，不依赖 API key 和外部 LLM。它不能代表真实 LLM 效果，只是工程闭环和 verifier 测试替身。

### 7.2 RealLLMReasoner

输入：context 和 prompt_text。

内部逻辑：

1. 检查 prompt_text。
2. 根据 `max_retries` 控制尝试次数。
3. 调 `OpenAICompatibleClient.complete()`。
4. 解析 JSON。
5. normalize 输出。
6. 如果所有尝试失败，调用 `_fallback()` 降级为 uncertain。

provider-agnostic 的实现：

- YAML 配置 `base_url`、`model`、env var 名称。
- 环境变量可覆盖：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。
- OpenAI SDK 指向不同兼容服务，如 OpenAI、DeepSeek、LM Studio。

### 7.3 JSON 输出解析

`_parse_json_output()`：

1. 先 `json.loads(content)`。
2. 如果失败，用正则 `\{.*\}` 从内容中抽取 JSON object 再解析。
3. 如果仍失败，抛异常。

`_normalize()`：

- decision 只允许 `accept/reject/uncertain`，否则变 `uncertain`。
- confidence 转 float，并 clamp 到 `[0, 1]`。
- supporting_evidence_ids 必须是 list，否则置空，并转字符串。

`_fallback()`：

触发场景：

- 没有 prompt_text。
- provider 请求失败。
- timeout。
- 无内容。
- JSON 解析失败。
- 多次 retry 仍失败。

降级结果：

```json
{
  "decision": "uncertain",
  "confidence": 0.0,
  "reason": "...",
  "supporting_evidence_ids": []
}
```

注意：retrieval 模型加载没有 fallback；这里的 fallback 是 LLM 调用层的安全降级。

面试口径：

如何保证结构化输出？

当前通过 prompt 强约束、JSON parse、normalize、Verifier 组合保证。尚未使用 strict JSON Schema 或 function calling。

如果 LLM 输出格式错了怎么办？

先尝试直接 parse，再正则抽取 JSON；失败后降级 uncertain，不写入最终边。

provider-agnostic 好处和局限？

好处是能切 OpenAI-compatible provider；局限是不同 provider 的模型行为、错误码和 JSON 稳定性不同，仍要靠日志和 verifier 兜底。

## 8. Verifier 实现逻辑

`Verifier.verify(candidate, context, prediction, config, graph)` 做四类检查。

### schema consistency

输入：candidate head/tail 和 graph entity type。

检查：`config.is_allowed_pair(head_type, tail_type)`。

失败：`decision=reject`，`verifier_status=failed`。

### evidence grounding

输入：context evidence snippets 和 prediction.supporting_evidence_ids。

检查：

- accept 必须有 evidence ids。
- evidence id 必须在当前 context。
- evidence id 必须在 graph.evidence。
- evidence.related_entities 至少包含 head 或 tail。

失败：默认 `require_supporting_evidence=true` 时 `decision=reject`，`verifier_status=failed`。如果配置成 false，则会变 `uncertain`。

### confidence threshold

输入：prediction confidence 和 `config.verifier.confidence_threshold`。

检查：accept 的 confidence 是否低于阈值。

失败：`decision=uncertain`，`verifier_status=failed`。所以它既降级为 uncertain，也标记 verifier failed。

### conflict check

输入：当前 verifier 实例内已接受的 `(head, relation, tail)`。

检查：是否重复接受同一个 key。

失败：`decision=reject`，`verifier_status=failed`。

注意：Verifier 的 conflict 不是查已有 KG，也不是查 writeback 中同一 `(head, relation)` 的不同 tail。已有 KG duplicate/conflict 主要由 CandidateGenerator 和 Writeback 处理。

### predicted_edges / writeback

进入 `predicted_edges.jsonl` 的条件：

```text
decision=accept and verifier_status=passed
```

writeback 同样只处理这些 prediction。

面试口径：

Verifier 能挡住什么？

能挡 schema 不合法、证据 id 不在 context、无 supporting evidence、低置信度 accept、重复接受同一边。

挡不住什么？

如果 evidence id 合法但 LLM 对证据语义理解错了，当前 verifier 无法做深层自然语言蕴含校验。后续可加入 NLI verifier、规则校验或人工审核。

confidence 是否校准？

没有严格校准，更多是 LLM 自报置信度加阈值过滤。后续可基于验证集做 calibration。

## 9. Evaluator：hidden edge recovery

`Evaluator.evaluate(predicted_edges_path, gold_edges_path, verified_predictions_path=None)`。

输入：

- `predicted_edges.jsonl`
- `gold_hidden_edges.jsonl`
- 可选 `verified_predictions.jsonl`

内部逻辑：

```python
predicted_keys = {(head, relation, tail) for item in predicted}
gold_keys = {(head, relation, tail) for item in gold}
hits = predicted_keys & gold_keys
```

指标：

- precision = hits / predicted
- recall = hits / gold
- F1 = harmonic mean
- hit_count = 命中 gold 的预测边数
- accepted/rejected/uncertain count 来自 verified predictions
- verifier_pass_rate = verifier_status passed 的比例
- average_confidence = verified predictions 平均 confidence

rejected/uncertain 不参与 precision/recall，只参与统计。

面试口径：

hidden edge recovery 是什么？

把一部分真实关系从 KG 中隐藏，系统从现有结构和证据中恢复它们，用恢复结果和 gold hidden edges 比较。

recall 高 precision 低怎么优化？

提升 verifier 严格度、调 LLM prompt、调 topK、加入 reranker 微调、增加关系冲突约束、做 confidence calibration。

局限是什么？

gold 只是样例隐藏边，规模小，不能代表真实生产分布；precision/recall 只看 triple key，不评价 explanation 质量。

## 10. KG writeback / staging

### 10.1 新增文件和类

文件：`src/evidencekg/writeback.py`

类：

- `EdgeWriter`
- `KGWritebackManager`

PipelineRunner 新参数：

- `enable_writeback: bool`
- `writeback_mode: str = "pending"`

CLI：

```text
--enable-writeback
--writeback-mode pending|approved
```

### 10.2 writeback 输入

处理对象：verified predictions。

只处理：

```text
decision=accept
verifier_status=passed
```

保留字段：

- `candidate_id`
- `prediction_id`
- `supporting_evidence_ids` -> 写为 `evidence_ids`
- `confidence`
- `reason`
- `verifier_details`
- `head/relation/tail`

### 10.3 pending 模式

输出：

```text
pending_edges.jsonl
writeback_report.json
```

不会修改原始 `triples.jsonl`。

适合场景：人工审核、审批流、离线检查。可以说它是人工可控的 staging，不是自动污染 KG。

pending edge 字段：

```text
triple_id
head
relation
tail
evidence_ids
confidence
reason
candidate_id
prediction_id
verifier_details
source
```

### 10.4 approved 模式

输出：

```text
triples.enriched.jsonl
writeback_report.json
```

生成方式：

```python
enriched_triples = original triples + approved prediction edges
```

不覆盖原始 `triples.jsonl`。

pending 和 approved 区别：

- pending：只写待审核新增边。
- approved：生成一个包含原始 KG + 新边的新 KG 文件。

### 10.5 duplicate / conflict 检查

exact duplicate 定义：

```text
(head, relation, tail) 完全相同
```

如果已在原始 KG 或当前 writeback batch 中出现，跳过并计入 `skipped_duplicate`。

conflict 定义：

```text
同一个 (head, relation) 指向不同 tail
```

既检查原始 KG，也检查本次 batch 已写入边。冲突跳过并计入 `skipped_conflict`。

`writeback_report.json` 字段：

```text
pending
skipped_duplicate
skipped_conflict
approved
written_count
```

面试口径：

writeback 是不是自动污染 KG？

不是。默认 pending 是待审核文件；approved 也只是生成 `triples.enriched.jsonl`，不覆盖源 KG。

为什么不直接覆盖 triples.jsonl？

为了可审计、可回滚、避免 LLM 错误写入污染原始知识图谱。

和生产图数据库写回差什么？

当前是 JSONL 文件级 staging，没有事务、权限、审计 UI、并发控制、图数据库约束。接 Neo4j 时可把 `EdgeWriter` 替换成 graph DB writer，保留过滤和 report 逻辑。

## 11. PipelineRunner 端到端串联

执行顺序：

1. load config
2. load graph
3. generate candidates
4. write candidate_pairs
5. 如果 `stage=candidates`，返回
6. 根据 offset/max_candidates 选推理窗口
7. 写 run_metadata
8. retrieve evidence contexts
9. write evidence_contexts
10. build prompts
11. reason
12. verify
13. write verified_predictions incrementally and finally
14. write predicted_edges
15. evaluate
16. optional writeback
17. write reports/timing

`stage=candidates` 只生成候选。

`max_candidates` 和 `candidate_offset` 不限制候选生成，只限制进入 evidence retrieval、reasoning、verifier、evaluation 的窗口。

`disable_verifier=True` 会用 raw prediction，`verifier_status=skipped`，并在 report 中加入 raw risk stats。

`debug_timing=True` 会打印阶段耗时，并写 `timing_report.jsonl`。

`run_metadata.json` 用于 resume 判断，包含配置路径、数据目录、LLM 设置、candidate window、writeback 设置等。匹配时可以跳过已完成 prediction。

60 秒面试版：

这个 pipeline 先从 JSONL 加载实体、三元组和证据，构建 NetworkX 图索引用于路径和邻居查询。CandidateGenerator 先按 schema 和图规则生成候选关系，而不是让 LLM 自由生成。EvidenceRetriever 对每个候选构造 graph-aware query，用 bi-encoder 召回证据，再用 cross-encoder 精排，形成 evidence context。PromptBuilder 把结构上下文和证据交给 mock 或 real LLM 判断，LLM 只输出 JSON。Verifier 再检查 schema、evidence grounding、置信度和冲突，只有 accept 且 passed 的结果进入 predicted_edges。Evaluator 用 hidden gold edges 算 precision/recall/F1。最后可选 writeback 只把 verified accepted edges 写到 pending 或 enriched 文件，不覆盖原始 KG。

## 12. 输出文件解释

### candidate_pairs.jsonl

生成模块：CandidateGenerator / PipelineRunner。

内容：候选关系及规则分数、路径、共同邻居。

面试解释：候选空间，不是最终预测。

### evidence_contexts.jsonl

生成模块：EvidenceRetriever。

内容：每个 candidate 的实体 profile、路径、共同邻居、相关三元组、rerank 后 evidence snippets。

面试解释：LLM 判断所能看到的 evidence-grounded context。

### verified_predictions.jsonl

生成模块：Reasoner + Verifier。

内容：每个候选的 decision、confidence、reason、supporting_evidence_ids、verifier_status/details。

面试解释：完整推理结果，包括 accept/reject/uncertain。

### predicted_edges.jsonl

生成模块：PipelineRunner。

内容：只包含 `decision=accept` 且 `verifier_status=passed` 的边。

面试解释：最终预测边。

### pending_edges.jsonl

生成模块：EdgeWriter pending mode。

内容：待人工审核写回边。

面试解释：writeback staging，不改原始 KG。

### triples.enriched.jsonl

生成模块：EdgeWriter approved mode。

内容：原始 triples + approved prediction edges。

面试解释：生成新版 KG 文件，不覆盖原始 KG。

### writeback_report.json

生成模块：EdgeWriter。

内容：pending、approved、skipped_duplicate、skipped_conflict、written_count。

### evaluation_report.json

生成模块：Evaluator / PipelineRunner。

内容：precision、recall、F1、hit_count、candidate_count、accepted/rejected/uncertain 等。

### run_metadata.json

生成模块：PipelineRunner。

内容：本次运行配置摘要，用于 resume 判断。

### timing_report.jsonl

生成模块：PipelineRunner debug timing。

内容：阶段耗时和每个 candidate 的 LLM/parse/verify 耗时。

## 13. 测试与运行

当前测试覆盖：

- `tests/test_candidate_generator.py`：候选生成、限制生成规则。
- `tests/test_evidence_retriever.py`：topN evidence、embedding/rerank 字段、模型/语料缓存、PromptBuilder、Verifier grounding。
- `tests/test_pipeline_runner.py`：输出文件、max_candidates、candidate_offset、disable_verifier、debug_timing、writeback。
- `tests/test_verifier.py`：bad evidence id、合法 grounding、schema 非法。
- `tests/test_real_reasoner.py`：real reasoner 解析、fallback、错误处理。
- `tests/test_writeback.py`：failed 不写回、pending 写入、duplicate、conflict、enriched、不覆盖原始 triples。
- 其他测试覆盖 graph store、prompt builder、mock reasoner、evaluator、task config。

当前 `python -m pytest` 全部通过：32 passed。Windows pytest cache warning 不影响功能。

测试里的 fake sentence_transformers：

`tests/conftest.py` 用 autouse fixture 注入 fake `sentence_transformers` 模块，避免测试时下载真实模型。生产代码没有 retrieval fallback，导入或模型加载失败会暴露错误。

运行 sample pipeline：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs
```

运行 pending writeback：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs --enable-writeback --writeback-mode pending
```

运行 approved enriched KG：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs --enable-writeback --writeback-mode approved
```

运行 real LLM：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real --max-candidates 10
```

需要设置 `LLM_API_KEY`，可选设置 `LLM_BASE_URL` 和 `LLM_MODEL`。

## 14. 当前已经实现 vs 没有实现

### 已实现

- JSONL KG 加载。
- NetworkX MultiDiGraph 图索引。
- 基于 schema、路径、共同邻居、证据 overlap 的 candidate generation。
- Graph-aware candidate query construction。
- in-memory evidence embedding cache。
- bi-encoder dense recall。
- cross-encoder rerank。
- PromptBuilder。
- MockReasoner。
- RealLLMReasoner。
- OpenAI-compatible client。
- JSON parse / normalize / LLM 调用 fallback。
- Verifier：schema、grounding、confidence、conflict。
- Evaluator：hidden edge recovery。
- pending / approved writeback。
- duplicate / conflict writeback 检查。
- timing report。
- pytest 覆盖。

### 没有实现

- 没有向量数据库。
- 没有 FAISS / Milvus / Chroma 持久索引。
- 没有训练自己的 bi-encoder / cross-encoder。
- 没有 LLM fine-tuning / LoRA。
- 没有 KG embedding / GNN completion。
- 没有 Neo4j / RDF / SPARQL 写回。
- 没有人工审核 UI。
- 没有 strict JSON Schema / function calling。
- 没有复杂时间推理 / 空间推理。
- 没有 learned evidence reliability calibration。
- 没有生产级权限、审计、事务和并发写回。

## 15. 面试追问清单

### 基础理解

1. 问：为什么这个项目叫 GraphRAG？
   好回答：候选生成和 query 构造都使用 KG 图结构，证据检索再用 RAG 思路召回证据给 LLM 判断。
   踩坑：说成只是普通向量 RAG。
   兜底：可以说当前是 graph-aware evidence retrieval，不是完整图数据库级 GraphRAG。

2. 问：和普通 RAG 区别？
   好回答：普通 RAG 多是用户 query 到文档；这里 query 来自候选关系和图上下文，包括路径、邻居、三元组。
   踩坑：只说用了 embedding。
   兜底：强调图结构用于约束候选和构造 query。

3. 问：和 KG completion 区别？
   好回答：不是训练 TransE/GNN 预测边，而是候选生成 + evidence-grounded LLM 判断。
   踩坑：说模型自动补全 KG。
   兜底：当前是规则候选和证据推理，不是 learned KG completion。

4. 问：为什么需要 CandidateGenerator？
   好回答：控制搜索空间，保证 schema 合法和可解释。
   踩坑：让 LLM 全图自由生成。
   兜底：候选召回决定上限，后续可扩展候选规则。

5. 问：为什么 type-only pair 不生成？
   好回答：仅类型合法太宽，会产生大量弱候选，必须命中结构或证据规则。
   踩坑：说 type rule 就是候选规则。
   兜底：type 是 schema filter，不是生成依据。

6. 问：GraphStore 为什么既有 dict 又有 NetworkX？
   好回答：dict 做 O(1) 取数，NetworkX 做路径和邻居算法。
   踩坑：说重复存储没有意义。
   兜底：这是轻量运行时索引。

### 关键实现

7. 问：graph-aware query 包含什么？
   好回答：target relation、head/tail profile、common neighbors、paths、related triples。
   踩坑：只说 head relation tail。
   兜底：图上下文被拼进 query。

8. 问：evidence_text 怎么构造？
   好回答：evidence text、source、related_entities、timestamp、reliability、related entity profile。
   踩坑：只说 evidence 原文。
   兜底：为了让 embedding 覆盖实体语义。

9. 问：in-memory embedding cache 是什么？
   好回答：缓存 evidence_ids/texts/embeddings，key 是 graph id 和 bi-encoder model。
   踩坑：说用了向量库。
   兜底：当前只是内存列表，数据小够用。

10. 问：bi-encoder 输入输出？
    好回答：query 和 evidence 分别编码，输出向量，cosine 召回 topK。
    踩坑：说它直接判断关系真假。
    兜底：它只做语义相关性召回。

11. 问：cross-encoder 输入输出？
    好回答：输入 `(query, evidence_text)` pairs，输出 rerank_score，取 topN。
    踩坑：对全量 evidence 做 cross-encoder。
    兜底：只 rerank topK 是效率折中。

12. 问：embedding_score / rerank_score / confidence 区别？
    好回答：前两者是检索相关性，confidence 是 LLM 对关系判断的置信度。
    踩坑：把 rerank_score 当最终关系置信度。
    兜底：最终还要 Reasoner + Verifier。

13. 问：production code 有没有 retrieval fallback？
    好回答：没有。sentence-transformers 或模型不可用会暴露错误。
    踩坑：说有哈希 fallback。
    兜底：测试里 fake 模块只是隔离模型下载。

14. 问：PromptBuilder 为什么要 JSON context？
    好回答：让 LLM 看到结构化上下文，同时保留 evidence id 供 grounding。
    踩坑：只拼纯文本。
    兜底：结构化更便于 verifier。

15. 问：OpenAI-compatible client 怎么实现 provider-agnostic？
    好回答：base_url/model/api_key_env 可配置，使用 OpenAI SDK 指向兼容接口。
    踩坑：只支持 OpenAI 官方。
    兜底：兼容但不同 provider 行为仍需测试。

### 工程取舍

16. 问：为什么不用向量库？
    好回答：样例数据小，内存扫描简单；大规模时再引入 FAISS/Milvus/Chroma。
    踩坑：说永远不需要。
    兜底：当前是可替换实现。

17. 问：为什么不用 LLM 直接写 KG？
    好回答：要先经过 Verifier 和 writeback staging，避免污染 KG。
    踩坑：把 accept 直接当事实。
    兜底：pending 模式人工可控。

18. 问：为什么不覆盖 triples.jsonl？
    好回答：保留可审计、可回滚和原始数据不变。
    踩坑：直接修改源文件。
    兜底：approved 也只是 enriched 新文件。

19. 问：Verifier 和 Writeback duplicate/conflict 有什么不同？
    好回答：Verifier 检查当前推理接受状态；writeback 检查原始 KG 和本 batch 的 duplicate/conflict。
    踩坑：混为一谈。
    兜底：两层不同生命周期的保护。

20. 问：max_candidates 限制什么？
    好回答：不限制候选生成，只限制进入 retrieval/reasoning 的窗口。
    踩坑：说生成候选变少。
    兜底：candidate_pairs 仍是全量。

### 局限与改进

21. 问：当前最大不足是什么？
    好回答：数据小、无训练检索器、无向量索引、Verifier 不能做深层语义蕴含。
    踩坑：说已经生产可用。
    兜底：这是可解释原型。

22. 问：如果 recall 高 precision 低怎么办？
    好回答：增强 verifier、调 topK、微调 reranker、校准 confidence、加入冲突/类型约束。
    踩坑：只调 prompt。
    兜底：需要多层优化。

23. 问：如果候选漏召怎么办？
    好回答：增加 candidate rules、文本候选召回、弱监督排序。
    踩坑：指望 LLM 补。
    兜底：当前候选集决定召回上限。

24. 问：如何扩展到生产系统？
    好回答：接向量库/图数据库、增量 embedding、审核 UI、权限审计、监控和数据版本。
    踩坑：只说换大模型。
    兜底：工程化比模型更重要。

25. 问：如何处理 evidence 语义误判？
    好回答：加入 NLI verifier、人工审核、更多负例、reranker 微调。
    踩坑：说 Verifier 已完全解决。
    兜底：当前 verifier 主要是结构和 id grounding。

26. 问：confidence 校准了吗？
    好回答：没有严格校准，是 LLM 自报值加阈值。
    踩坑：说 confidence 等于概率。
    兜底：后续可做验证集 calibration。

### 压力追问

27. 问：这是不是只是规则系统套了 LLM？
    好回答：候选生成是规则约束，但证据选择是 dense retrieval + rerank，关系判断由 LLM 和 verifier 完成。
    踩坑：否认规则存在。
    兜底：规则是可解释搜索空间控制。

28. 问：没有训练模型，创新点在哪里？
    好回答：工程重点是把 KG 结构、Evidence RAG、LLM judge、Verifier、writeback staging 串成可审计闭环。
    踩坑：夸大模型创新。
    兜底：这是系统设计和工程落地项目。

29. 问：LLM 调用失败怎么办？
    好回答：RealLLMReasoner 降级为 uncertain，不写最终边。
    踩坑：说 pipeline 崩溃。
    兜底：retrieval 模型失败会暴露，LLM provider 失败会安全降级。

30. 问：如何证明写回安全？
    好回答：只处理 accept+passed；pending 默认；不覆盖原始 triples；duplicate/conflict 检查；report 可审计。
    踩坑：说自动写入生产 KG。
    兜底：当前是 staging 文件，不是生产事务写回。

## 16. 面试用 30 秒 / 60 秒 / 2 分钟介绍

### 30 秒版本

EvidenceKG-Reasoner 是一个面向企业 IP 和 IT 资产 KG 的证据推理系统。它先用 schema 和图规则生成候选关系，再基于 graph-aware query 做 bi-encoder 证据召回和 cross-encoder 精排，把证据上下文交给 LLM 判断。最后 Verifier 校验证据 id、schema、置信度和冲突，只有 accept 且 passed 的结果才进入预测边。写回也不是直接污染 KG，而是默认生成 pending 文件，支持人工审核。

### 60 秒版本

这个项目的核心不是让 LLM 自由补全 KG，而是做一个可控的 Graph-aware Evidence RAG pipeline。数据从 JSONL 加载成 GraphStore，并建立 NetworkX 图索引。CandidateGenerator 根据 allowed types、路径、共同邻居和 evidence overlap 生成候选关系。EvidenceRetriever 为每个候选构造包含实体 profile、图路径、共同邻居和相关三元组的 query，用 sentence-transformers bi-encoder 从 evidence corpus 召回 topK，再用 cross-encoder 精排 topN。PromptBuilder 把结构化上下文交给 mock 或 real LLM 输出 JSON。Verifier 再做 schema、evidence grounding、confidence 和 conflict 检查。最后 Evaluator 做 hidden edge recovery，writeback 模块只把 verified accepted edges 写入 pending 或 enriched 文件，不覆盖原始 KG。

### 2 分钟版本

EvidenceKG-Reasoner 是我实现的一个企业资产知识图谱证据推理系统，目标是从已有 IP、服务、应用、团队、工单、文档等数据中恢复隐藏的 ownership-like 关系。整体设计是 candidate generation、evidence retrieval、LLM judgment、verifier、writeback staging 的闭环。

首先，GraphStore 从 JSONL 加载 entities、triples、evidence，同时维护字典索引和 NetworkX MultiDiGraph。字典用于快速取实体、边和证据，图用于邻居查询和路径搜索。CandidateGenerator 不让 LLM 自由生成关系，而是基于 allowed head/tail types、已有 target relation 排除、two-hop path、common neighbor、evidence overlap 生成候选，这样候选空间可控、可解释。

新版 EvidenceRetriever 是重点：它不再是简单 related_entities overlap，而是 graph-aware Evidence RAG。对每个 candidate，先把 head/tail profile、target relation、common neighbors、graph paths、related triples 拼成 retrieval query。证据侧把 evidence text、source、timestamp、reliability、related entities 以及 related entity 的 name/type/description/attributes 拼成 evidence_text。所有 evidence_text 用 `all-MiniLM-L6-v2` bi-encoder 编码并缓存在内存中。每个 query 来时编码 query，和全量 evidence embeddings 算 cosine，召回 topK；再用 `ms-marco-MiniLM-L-6-v2` cross-encoder 对 query-evidence pair 精排，取 topN 进入 LLM context。当前没有向量数据库，因为数据量小；生产代码也没有 retrieval fallback，模型不可用就暴露错误。

LLM 部分支持 mock 和 real 两种模式。real 模式用 OpenAI-compatible client，可通过 base_url/model/env var 切 provider。LLM 必须输出 JSON，包括 decision、confidence、reason、supporting_evidence_ids。Prompt 只是软约束，所以后面有 Verifier 做硬约束：schema 不合法、evidence id 不在当前 context、证据不存在或不关联 head/tail、冲突、低置信度等都会被处理。最终只有 accept 且 verifier passed 的边进入 predicted_edges。

最后我实现了 writeback staging：默认 pending 模式生成 pending_edges.jsonl，approved 模式生成 triples.enriched.jsonl，但永远不覆盖原始 triples.jsonl。写回前还会做 duplicate 和 conflict 检查，并输出 writeback_report。这个设计强调可审计、可回滚、人工可控，适合作为真实生产 KG 写回前的安全层。
