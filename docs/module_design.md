# 核心模块设计说明

这份文档按模块解释 EvidenceKG-Reasoner 的职责边界和关键实现。项目没有使用 Neo4j、前端、多模型投票、best-of-N、复杂时空推理或 KG embedding 训练。

## 1. config/task_config.py

`TaskConfig` 是整个 pipeline 的控制面。`load_task_config(path)` 读取 YAML 后构造：

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

`target_relation` 不写死在候选生成或评测逻辑里。`CandidateGenerator.generate()` 使用 `config.target_relation` 写入 candidate 的 `relation` 字段，并用 `graph.has_relation(head_id, config.target_relation, tail_id)` 避免生成已有关系。

`llm.mode` 在 `PipelineRunner._build_reasoner()` 中决定使用 `MockReasoner` 还是 `RealLLMReasoner`。`candidate_rules` 决定候选规则集合，比如 `two_hop_path`、`common_neighbor`、`evidence_overlap`。`evidence_retrieval` 控制 `max_hops`、`max_paths`、`max_evidence_snippets` 以及是否包含 graph_paths、common_neighbors、related_triples、entity profiles。`verifier` 控制 schema、evidence grounding、confidence threshold、conflict check。

## 2. graph/graph_store.py

`GraphStore` 负责把 `data/sample/` 下的 JSONL 文件加载为内存结构：

- `entities`: `entity_id -> entity dict`
- `triples`: `triple_id -> triple dict`
- `evidence`: `evidence_id -> evidence dict`
- `graph`: `networkx.MultiDiGraph`

使用 `networkx.MultiDiGraph` 的原因是同一对实体之间可能有多种关系。例如一个 IP 和服务之间可能同时存在扫描、暴露、告警相关的多条边。`MultiDiGraph` 允许同一 `(head, tail)` 上存在多个 key，其中 key 使用 `triple_id`。

但 NetworkX 不是唯一数据源。代码里 triples 仍由 `self.triples[triple_id]` 管理，`MultiDiGraph` 主要承担邻居、路径和结构查询索引。这样可以避免把边属性散落在图结构里。

关键接口：

- `from_dir(data_dir)`: 顺序加载 entities、evidence、triples。
- `get_entity(entity_id)`: 返回实体详情。
- `iter_entities_by_type(entity_types)`: 按类型筛选 candidate head/tail。
- `iter_triples()`: 返回全部 triples。
- `get_triple(triple_id)`: 按主键取 triple。
- `get_triples_between(head, tail)`: 查两个实体之间双向 triples。
- `get_triples_for_entities(entity_ids)`: 查一组实体相关的 triples。
- `get_related_triples(entity_id)`: 查单实体相关 triples。
- `has_relation(head, relation, tail)`: 判断目标关系是否已存在。
- `get_evidence_for_triple(triple_id)`: 根据 triple 的 `evidence_ids` 取证据。
- `get_evidence_for_entities(entity_ids)`: 按 related_entities overlap 排序取证据。
- `get_neighbors(entity_id)`: 用 MultiDiGraph 前驱和后继合并邻居。
- `find_paths(head, tail, max_hops, max_paths)`: 转为无向图后 BFS 找短路径。

## 3. candidate/generator.py

`CandidateGenerator.generate(config, graph)` 生成候选关系。它先用 `graph.iter_entities_by_type(config.allowed_head_types)` 和 `graph.iter_entities_by_type(config.allowed_tail_types)` 枚举可能 head/tail，然后做过滤：

- head 和 tail 不能相同。
- 必须通过 `config.is_allowed_pair(head["type"], tail["type"])`。
- 不能已经存在 `config.target_relation`。
- 必须至少命中一个候选规则。
- 用 `(head, relation, tail)` 去重。

`type_rule` 在这里不是生成规则，而是 schema filter。代码没有“枚举所有合法类型组合就生成候选”，而是在合法类型基础上还要求 `two_hop_path`、`common_neighbor` 或 `evidence_overlap` 至少有一个得分大于 0。

规则触发方式：

- `two_hop_path`: `graph.find_paths(head_id, tail_id, max_hops, max_paths)` 找到路径后触发。最短路径小于等于 2 跳得 `0.4`，否则得 `0.25`。
- `common_neighbor`: head 邻居和 tail 邻居有交集时触发，得分 `min(0.3, 0.15 + 0.05 * len(common_neighbors))`。
- `evidence_overlap`: 任意 evidence 的 `related_entities` 同时包含 head 和 tail 时触发，得 `0.2`。

`rule_scores` 保存每条规则的简单分数，`candidate_score` 是这些分数的和。生成后按 `candidate_score` 降序排序，再重新编号 `candidate_id`。

## 4. retrieval/evidence_retriever.py

`EvidenceRetriever.retrieve(candidate, config, graph)` 为一个 candidate 生成 evidence context。

它先构造 `query_entities`：

- candidate 的 head 和 tail
- candidate 的 common_neighbors
- candidate paths 中出现的所有实体

然后从 GraphStore 取：

- `related_triples`: `graph.get_triples_for_entities(query_entities)`
- `evidence`: `graph.get_evidence_for_entities(query_entities)`
- triple 直接关联的证据：对每个 related triple 调 `graph.get_evidence_for_triple(triple_id)`

输出字段：

- `candidate_id`
- `candidate`
- `head_profile`
- `tail_profile`
- `graph_paths`
- `common_neighbors`
- `related_triples`
- `evidence_snippets`

`max_paths` 控制 `graph_paths` 数量，`max_evidence_snippets` 控制 `evidence_snippets` 数量。`include_graph_paths`、`include_common_neighbors`、`include_related_triples`、`include_entity_profiles` 支持 Stage 3 ablation。

## 5. prompting/prompt_builder.py

`PromptBuilder.build(evidence_context)` 同时输出两类内容：

- `structured_context`: evidence_context 的直接 dict 拷贝，给 `MockReasoner` 和 Verifier 使用。
- `prompt_text`: 给真实 LLM 的自然语言指令和 JSON context。

MockReasoner 不解析自然语言 prompt，因为第一阶段 mock 的目标是可复现、规则化地模拟推断。真实 LLM 使用 `prompt_text`，其中明确要求：

```json
{"decision":"accept|reject|uncertain","confidence":0.0,"reason":"short explanation","supporting_evidence_ids":[]}
```

Prompt 还写明 “Use only the provided context. Do not invent evidence ids.”，用于减少 evidence hallucination。

## 6. llm/reasoner.py

`MockReasoner` 是规则化 LLM 替身。它只读 structured context：

- 有 evidence、paths，并且有 common_neighbors 或 candidate_score 足够高，且 confidence 大于等于 0.7 时 accept。
- 有 evidence 或 paths 但不够强时 uncertain。
- 没有足够结构和证据时 reject。

Mock 中还故意对 tail 类型为 `department/person` 的间接 owner candidate 引入 `ev_missing_mock`，让 Verifier 能展示 evidence grounding 失败的作用。

`RealLLMReasoner` 使用 `OpenAICompatibleClient.complete(prompt_text, ...)` 调真实 provider。它负责：

- 多 attempt 调用，attempt 数为 `max_retries + 1`。
- `_parse_json_output()` 先尝试 `json.loads`，失败后用正则抽取 JSON object。
- `_normalize()` 规范化 decision、confidence、supporting_evidence_ids。
- provider error、timeout、parse failure 都通过 `_fallback()` 降级为 `uncertain`。

`last_metadata` 记录 elapsed、attempts、parse_elapsed、client_attempts、error_type，供 `PipelineRunner` 写入 `timing_report.jsonl`。

## 7. llm/openai_compatible_client.py

OpenAI-compatible 指 provider 暴露 OpenAI style chat completions 接口。代码使用 `openai.OpenAI` SDK，但 `base_url`、`api_key`、`model` 都来自环境变量或 config：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

因此它可以连接 OpenAI、DeepSeek、MiMo、LM Studio 等兼容 provider。

`complete()` 会读取 `.env`，构造 `OpenAI(api_key=..., base_url=..., http_client=httpx.Client(...))`，调用 `client.chat.completions.create(...)`。`timeout_seconds <= 0` 时不设置 HTTP timeout。`debug_timing` 开启时用 heartbeat 线程每 10 秒打印：

```text
[llm] candidate=c_001 still waiting... elapsed=10s
```

异常被分类为 `timeout` 或 `provider_error`，并写入 `last_metadata`。

## 8. verify/verifier.py

Verifier 是必要的，因为 mock 或 real LLM 都可能过度接受、引用不存在证据、置信度不足或产生重复冲突。

`Verifier.verify(...)` 检查：

- schema consistency：`config.is_allowed_pair(head_type, tail_type)`。
- evidence grounding：accept 必须有 supporting evidence；每个 evidence id 必须在当前 context 中，且 evidence 本身存在；证据 related_entities 至少包含 head 或 tail。
- confidence threshold：accept 的 confidence 不能低于 `config.verifier.confidence_threshold`。
- conflict check：同一 `(head, relation, tail)` 不能重复接受。

`verified_predictions.jsonl` 保存所有候选的最终审查记录，包括 accept、reject、uncertain。`predicted_edges.jsonl` 只保存 `decision=accept` 且 `verifier_status=passed` 的边。

## 9. eval/evaluator.py

`Evaluator.evaluate(predicted_edges_path, gold_edges_path, verified_predictions_path)` 做 hidden edge recovery 评测。

它把 `predicted_edges.jsonl` 和 `gold_hidden_edges.jsonl` 都转成 `(head, relation, tail)` 集合，命中为二者交集。

- precision = hit_count / predicted_edge_count
- recall = hit_count / gold_count
- F1 = 2PR / (P+R)
- accepted_count / rejected_count / uncertain_count 来自 `verified_predictions.jsonl`
- verifier_pass_rate = verifier_status passed 的比例
- average_confidence = verified 记录平均 confidence

rejected 和 uncertain 不参与 precision / recall / F1 命中计算，因为它们不是最终补全边，只用于分析模型和 Verifier 行为。`--max-candidates` 下只评测被 reasoned 的候选窗口，因此 recall 不能和 full run 直接比较。

## 10. pipeline/runner.py

`PipelineRunner` 串联所有模块。它处理：

- mock / real mode 的 reasoner 选择。
- `--max-candidates` 和 `--candidate-offset` 的 reasoning window。
- `--disable-verifier` ablation。
- 输出文件写入。
- `run_metadata.json` 和 resume。
- `debug_timing` 与 `timing_report.jsonl`。

对于增量运行，Runner 会在每个 candidate 完成后 append `verified_predictions.jsonl`，debug timing 开启时也 append `timing_report.jsonl`。如果下一次运行的 `run_metadata.json` 完全匹配，会读取已有 verified predictions，跳过已完成 candidate。
