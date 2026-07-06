# EvidenceKG-Reasoner 实现逻辑与问答口径

## 1. 项目一句话概括

EvidenceKG-Reasoner 当前实现的是一个面向企业 IP / IT 资产知识图谱的证据驱动关系发现流程：从 JSONL 图谱、证据和配置中生成候选 `likely_owned_by` 关系，再用结构化证据上下文交给 MockReasoner 或真实 OpenAI-compatible LLM 判断，最后经过 Verifier 过滤并与隐藏 gold 边评估。它不是自由生成知识图谱，而是围绕“候选关系 + 图结构 + 证据片段 + 格式化输出 + 规则校验”组织的工程 pipeline。

## 2. 当前代码实现了什么

- JSONL 数据读写：由 `src/evidencekg/io.py` 的 `read_jsonl()`、`write_jsonl()`、`write_json()` 实现。
- 任务配置加载：由 `src/evidencekg/config/task_config.py` 的 `load_task_config()` 和 `TaskConfig` 等 dataclass 实现，配置项包括目标关系、允许实体类型、候选规则、证据检索、LLM、Verifier、Evaluation。
- 图谱加载与内存索引：由 `src/evidencekg/graph/graph_store.py` 的 `GraphStore.from_dir()`、`load_entities()`、`load_triples()`、`load_evidence()` 实现，把 `entities.jsonl`、`triples.jsonl`、`evidence.jsonl` 加载到字典和 `networkx.MultiDiGraph`。
- 结构查询：由 `GraphStore.get_neighbors()`、`find_paths()`、`get_triples_for_entities()`、`get_evidence_for_entities()` 等实现，用于路径、邻居、相关 triples 和相关 evidence 检索。
- 候选关系生成：由 `src/evidencekg/candidate/generator.py` 的 `CandidateGenerator.generate()` 实现，先按 `allowed_head_types` / `allowed_tail_types` 枚举，再用 `two_hop_path`、`common_neighbor`、`evidence_overlap` 打分。
- Schema 类型过滤：由 `TaskConfig.is_allowed_pair()` 和 `CandidateGenerator.generate()` 中的类型检查实现。测试 `tests/test_candidate_generator.py` 明确验证了 type-only pair 不会被生成。
- 候选打分：由 `CandidateGenerator._score_pair()` 实现，`two_hop_path` 最高 0.4，`common_neighbor` 最高 0.3，`evidence_overlap` 为 0.2，`candidate_score` 为规则分数之和。
- 证据上下文构造：由 `src/evidencekg/retrieval/evidence_retriever.py` 的 `EvidenceRetriever.retrieve()` 实现，输出 head/tail profile、graph paths、common neighbors、related triples、evidence snippets。
- Prompt 构造：由 `src/evidencekg/prompting/prompt_builder.py` 的 `PromptBuilder.build()` 实现，同时返回 `structured_context` 和面向真实 LLM 的 `prompt_text`。
- Mock 推理：由 `src/evidencekg/llm/reasoner.py` 的 `MockReasoner.predict()` 实现，是规则化 LLM 替身，读取 structured context，不调用外部模型。
- 真实 LLM 推理：由 `RealLLMReasoner.predict()` 和 `src/evidencekg/llm/openai_compatible_client.py` 的 `OpenAICompatibleClient.complete()` 实现，使用 OpenAI-compatible chat completions 接口。
- LLM JSON 输出解析与降级：由 `RealLLMReasoner._parse_json_output()`、`_normalize()`、`_fallback()` 实现。无 prompt、provider 失败、timeout、无 JSON 或 JSON 不合法时降级为 `decision=uncertain`、`confidence=0.0`。
- 规则校验：由 `src/evidencekg/verify/verifier.py` 的 `Verifier.verify()` 实现，检查 schema consistency、evidence grounding、confidence threshold、conflict check。
- 结果评估：由 `src/evidencekg/eval/evaluator.py` 的 `Evaluator.evaluate()` 实现，计算 precision、recall、F1、hit_count、accepted/rejected/uncertain、verifier_pass_rate、average_confidence。
- Pipeline 串联：由 `src/evidencekg/pipeline/runner.py` 的 `PipelineRunner.run()` 实现，负责加载配置和图、生成候选、检索证据、构造 prompt、调用 reasoner、调用 verifier、写输出、评估。
- 命令行入口：由 `scripts/run_pipeline.py` 和 `scripts/run_evaluation.py` 实现。
- 小窗口推理：`PipelineRunner.run()` 支持 `max_candidates` 和 `candidate_offset`，只限制进入证据检索和推理的候选，不限制完整候选生成。
- Verifier 消融：`scripts/run_pipeline.py` 的 `--disable-verifier` 传入 `PipelineRunner.run(disable_verifier=True)`，输出 raw prediction 并补充风险统计。
- Timing 调试：`PipelineRunner.run(debug_timing=True)` 写出 `timing_report.jsonl`，测试 `tests/test_pipeline_runner.py` 覆盖了 stage 和 candidate 级 timing。
- 样例数据和测试：`data/sample/` 提供实体、已有 triples、证据、隐藏 gold 边；`tests/` 覆盖配置、图存储、候选、证据检索、prompt、mock/real reasoner、verifier、runner、evaluator。

## 3. 当前代码没有实现什么

- 当前代码未实现知识图谱写回到原始 KG 或外部图数据库；`predicted_edges.jsonl` 只是输出文件，不会写回 `triples.jsonl`、Neo4j 或 RDF store。
- 当前代码未发现 Neo4j、RDF、SPARQL 或图数据库持久化实现；图结构是内存中的 `networkx.MultiDiGraph`。
- 当前代码未发现 embedding、向量数据库、dense retriever、BM25 retriever 或 reranker；证据检索是基于实体 overlap、路径实体和 triple 关联证据的规则检索。
- 当前代码未实现 LLM fine-tuning、LoRA、监督训练或模型更新。
- 当前代码未实现 GNN、TransE、RotatE 等传统 KG completion 训练。
- 当前代码未实现多模型投票、best-of-N 聚合；`LLMConfig.best_of_n` 存在字段，但 README 也说明当前约束不包含 best-of-N，源码中未发现实际使用。
- 当前代码未实现复杂时间推理、空间推理、时空池或事件演化推理。
- 当前代码未实现人工复核 UI；中间文件可人工查看，但没有前端或审核工作台。
- 当前代码未发现专门的证据置信度学习模块；`evidence.jsonl` 有 `reliability` 字段，但候选打分和 Verifier 未学习使用该字段。
- 当前代码未发现对 LLM 输出使用严格 JSON Schema API 或 function calling；当前是 prompt 要求 JSON，再用 `json.loads` / 正则抽取解析。
- 当前代码未发现候选关系由 LLM 从全图自由生成；候选来自规则枚举和过滤。

## 4. 核心流程梳理

```text
配置与输入 JSONL
  ↓
GraphStore 加载实体、证据、triples
  ↓
CandidateGenerator 生成候选关系
  ↓
EvidenceRetriever 构造证据上下文
  ↓
PromptBuilder 构造 structured_context 和 prompt_text
  ↓
MockReasoner 或 RealLLMReasoner 判断 accept / reject / uncertain
  ↓
Verifier 做 schema、证据、置信度、冲突校验
  ↓
写出 verified_predictions / predicted_edges
  ↓
Evaluator 与 gold_hidden_edges 计算指标
```

1. 配置与输入 JSONL  
输入是 `configs/*.yaml` 和 `data/sample/*.jsonl`。配置由 `load_task_config()` 读取，数据包括 `entities.jsonl`、`triples.jsonl`、`evidence.jsonl`、`gold_hidden_edges.jsonl`。输出是 `TaskConfig` 和原始记录列表。关键参数在 YAML 的 `target_relation`、`allowed_head_types`、`allowed_tail_types`、`candidate_rules`、`evidence_retrieval`、`llm`、`verifier`、`evaluation`。

2. 图谱加载 / 解析  
输入是 `entities.jsonl`、`evidence.jsonl`、`triples.jsonl`。输出是 `GraphStore`，内部包含 `entities`、`triples`、`evidence` 三个字典和 `networkx.MultiDiGraph`。由 `GraphStore.from_dir()` 实现。

3. 候选构造  
输入是 `TaskConfig` 和 `GraphStore`。输出是 `candidate_pairs.jsonl` 中的候选，每条包含 `candidate_id`、`head`、`relation`、`tail`、`generation_rules`、`rule_scores`、`candidate_score`、`paths`、`common_neighbors`。由 `CandidateGenerator.generate()` 实现。关键参数是 `allowed_*_types`、`candidate_rules`、`evidence_retrieval.max_hops`、`max_paths`。

4. 证据检索 / 证据聚合  
输入是单个 candidate、配置和 graph。输出是 evidence context，包括 `head_profile`、`tail_profile`、`graph_paths`、`common_neighbors`、`related_triples`、`evidence_snippets`。由 `EvidenceRetriever.retrieve()` 实现。关键参数是 `max_evidence_snippets`、`include_entity_profiles`、`include_graph_paths`、`include_common_neighbors`、`include_related_triples`。

5. LLM 或规则推理  
输入是 `PromptBuilder.build()` 返回的 `structured_context` 和 `prompt_text`。mock 模式由 `MockReasoner.predict()` 根据结构化上下文规则判断；real 模式由 `RealLLMReasoner.predict()` 调用 OpenAI-compatible provider。输出是 `decision`、`confidence`、`reason`、`supporting_evidence_ids`。关键参数是 `llm.mode`、`provider`、`model`、`base_url`、`temperature`、`timeout_seconds`、`max_retries`。

6. Verifier 校验  
输入是 candidate、context、prediction、config、graph。输出是 verified prediction，加入 `verifier_status` 和 `verifier_details`。由 `Verifier.verify()` 实现。关键参数是 `confidence_threshold`、`require_supporting_evidence`、`check_schema_consistency`、`check_evidence_grounding`、`check_conflict`。

7. 结果输出与评估  
输出包括 `candidate_pairs.jsonl`、`evidence_contexts.jsonl`、`verified_predictions.jsonl`、`predicted_edges.jsonl`、`evaluation_report.json`、`run_metadata.json`，开启 debug 时还有 `timing_report.jsonl`。评估由 `Evaluator.evaluate()` 实现，gold 文件由 `evaluation.gold_file` 指定。

## 5. 关键模块说明

### 5.1 数据加载模块

数据读取使用 `src/evidencekg/io.py` 的 JSONL 工具。`GraphStore.from_dir(data_dir)` 固定读取：

- `entities.jsonl`：实体节点，字段包括 `entity_id`、`name`、`type`、`description`、`attributes`。
- `triples.jsonl`：已有 KG 边，字段包括 `triple_id`、`head`、`relation`、`tail`、`evidence_ids`、`confidence`、`source`、`observed_at`、`valid_from`、`valid_to`、`location`。
- `evidence.jsonl`：证据记录，字段包括 `evidence_id`、`source`、`text`、`timestamp`、`related_entities`、`location`、`reliability`。
- `gold_hidden_edges.jsonl`：评估用隐藏边，字段包括 `head`、`relation`、`tail`、`evidence_ids`，由 `Evaluator` 读取。

当前数据目录文件名在 `GraphStore.from_dir()` 中写死为上述三个输入文件；gold 文件名通过 YAML 的 `evaluation.gold_file` 配置。

### 5.2 KG / Graph 模块

KG 使用 JSONL 作为输入格式，运行时由 `GraphStore` 保存为自定义字典结构和 NetworkX 图：

- 实体、triples、evidence 分别保存在 `self.entities`、`self.triples`、`self.evidence`。
- 结构索引用 `networkx.MultiDiGraph`，边 key 是 `triple_id`，边属性包含 `triple_id` 和 `relation`。
- 路径查询 `find_paths()` 会把有向多重图转换为无向 `nx.Graph()` 后 BFS 搜索，受 `max_hops` 和 `max_paths` 限制。
- 代码中未发现 Neo4j、RDF、SPARQL 或图数据库连接。

### 5.3 Evidence 模块

证据是 `evidence.jsonl` 中的记录，通过 `evidence_id` 标识，并用 `related_entities` 关联实体。检索逻辑在 `EvidenceRetriever.retrieve()`：

- 先把 candidate 的 head、tail、common neighbors、paths 中实体合并成 `query_entities`。
- 调 `graph.get_triples_for_entities(query_entities)` 获取相关 triples。
- 调 `graph.get_evidence_for_entities(query_entities)` 获取与查询实体有 overlap 的证据，overlap 多的排前。
- 对每个 related triple 再调 `graph.get_evidence_for_triple()` 补充 triple 直接引用的证据。
- 用 `evidence_id` 去重，再截断到 `max_evidence_snippets`。

当前没有 embedding 检索、语义相似度检索或 reranker；`reliability` 字段存在于证据记录，但未发现专门的学习式证据评分逻辑。

### 5.4 Reasoner 模块

推理有两种模式，由 `llm.mode` 控制：

- `mock`：`MockReasoner` 是规则化替身。它根据 evidence、graph paths、common neighbors、candidate_score 生成 `accept`、`reject` 或 `uncertain`，不调用外部 LLM。
- `real`：`RealLLMReasoner` 使用 `prompt_text` 调 OpenAI-compatible chat completions 接口。模型输出 JSON 后经 `_parse_json_output()` 和 `_normalize()` 转成统一字段。

当前推理不是路径算法单独决定，也不是 KG embedding completion；路径、邻居、证据负责构造上下文，最终由 mock 规则或 real LLM 产出判断，再由 Verifier 做硬校验。

### 5.5 LLM / Prompt 模块

真实 LLM 接口在 `OpenAICompatibleClient`：

- API 形式：OpenAI SDK 的 `client.chat.completions.create()`。
- 配置来源：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 或 YAML 默认值。
- system message：要求只返回 evidence-grounded KG relation judgments 的 JSON。
- user prompt：来自 `PromptBuilder.build()` 的 `prompt_text`。

Prompt 包含：

- candidate 三元组：`head relation tail`。
- head/tail profile。
- graph paths。
- common neighbors。
- related triples。
- evidence snippets。
- 输出格式要求：`decision`、`confidence`、`reason`、`supporting_evidence_ids`。

输出解析：

- 先 `json.loads(content)`。
- 如果失败，用正则抽取第一个 JSON object 再解析。
- `decision` 不在 `accept/reject/uncertain` 时归一化为 `uncertain`。
- `confidence` 截断到 `[0.0, 1.0]`。
- `supporting_evidence_ids` 非 list 时置空。

当前没有使用 OpenAI JSON schema / function calling 的强约束；格式正确性依靠 prompt、解析、归一化、失败降级和 Verifier。

### 5.6 输出与评估模块

主要输出：

- `candidate_pairs.jsonl`：所有生成候选。
- `evidence_contexts.jsonl`：进入推理窗口的候选上下文。
- `verified_predictions.jsonl`：所有已推理候选的最终审查记录。
- `predicted_edges.jsonl`：只保留 `decision=accept` 且 verifier 通过的边。
- `evaluation_report.json`：precision、recall、F1、gold_count、hit_count、accepted/rejected/uncertain、verifier_pass_rate、average_confidence 等。
- `run_metadata.json`：本次运行配置摘要，用于 resume 判断。
- `timing_report.jsonl`：开启 `--debug-timing` 时写出。

评估只把 `predicted_edges.jsonl` 与 `gold_hidden_edges.jsonl` 的 `(head, relation, tail)` 集合比较；reject 和 uncertain 不参与 precision / recall / F1。

## 6. 关键配置与运行方式

安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

运行默认 mock pipeline：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs
```

只生成候选：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs --stage candidates
```

运行真实 LLM pipeline：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real
```

真实 LLM 小样本：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real_10 --max-candidates 10
```

带 offset 的候选窗口：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_real_offset40 --candidate-offset 40 --max-candidates 10
```

评估入口：

```powershell
python scripts/run_evaluation.py --predicted outputs/predicted_edges.jsonl --verified outputs/verified_predictions.jsonl --gold data/sample/gold_hidden_edges.jsonl --output outputs/evaluation_report.json
```

运行测试：

```powershell
python -m pytest
```

真实 LLM 需要 `.env` 或环境变量：

```text
LLM_API_KEY=your_provider_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

## 7. 代码级问答口径

**Q1：这个项目的输入是什么？**  
A：主要输入是 `data/sample/entities.jsonl`、`triples.jsonl`、`evidence.jsonl` 和配置文件 `configs/*.yaml`。评估时还读取 `gold_hidden_edges.jsonl`。加载逻辑在 `GraphStore.from_dir()` 和 `load_task_config()`。

**Q2：证据在代码里怎么表示？**  
A：证据是 dict 记录，主键是 `evidence_id`，核心字段包括 `source`、`text`、`timestamp`、`related_entities`、`location`、`reliability`。运行时保存在 `GraphStore.evidence`，检索由 `EvidenceRetriever.retrieve()` 完成。

**Q3：知识图谱在代码里怎么表示？**  
A：输入是 JSONL triples，运行时同时保存在 `GraphStore.triples` 字典和 `networkx.MultiDiGraph` 中。NetworkX 主要用于邻居和路径查询，真实 triple 数据仍以 dict 管理。

**Q4：候选关系是怎么来的？**  
A：`CandidateGenerator.generate()` 枚举允许类型的 head/tail，排除相同实体和已有目标关系，再要求至少命中 `two_hop_path`、`common_neighbor`、`evidence_overlap` 中的一个规则，最后按 `candidate_score` 排序。

**Q5：推理到底是 LLM 做的，还是规则做的？**  
A：取决于配置。`llm.mode=mock` 时是 `MockReasoner` 的规则判断；`llm.mode=real` 时调用 OpenAI-compatible LLM。无论哪种模式，最终都经过 `Verifier` 的规则校验。

**Q6：LLM 的输入 prompt 包含哪些信息？**  
A：`PromptBuilder` 把 candidate、head/tail profile、graph paths、common neighbors、related triples、evidence snippets 序列化进 Context JSON，并要求模型只返回指定 JSON。

**Q7：LLM 输出怎么保证格式正确？**  
A：当前不是严格 JSON Schema API。代码先要求 prompt 返回 JSON，再由 `RealLLMReasoner` 解析、正则兜底抽取、字段归一化；失败时降级为 `uncertain`。之后 Verifier 还会校验证据和置信度。

**Q8：有没有证据打分？**  
A：有简单规则层面的证据 overlap 分数：候选生成的 `evidence_overlap` 命中给 0.2。证据检索按 related_entities overlap 排序。但没有发现学习式证据打分或使用 `reliability` 的复杂评分模块。

**Q9：有没有置信度？**  
A：有。Reasoner 输出 `confidence`，Verifier 用 `config.verifier.confidence_threshold` 检查 accept 是否低于阈值；Evaluator 统计 `average_confidence`。但置信度不是校准模型学习出来的。

**Q10：有没有写回 KG？**  
A：当前代码没有实现写回原始 KG 或外部图数据库。最终接受的边写到 `predicted_edges.jsonl`，并不会修改 `triples.jsonl`。

**Q11：这个项目和普通 RAG 有什么区别？**  
A：普通 RAG 通常检索文档来回答自然语言问题；这个项目检索图结构和证据片段来判断结构化候选关系，并输出三元组级结果和 evidence id。

**Q12：这个项目和普通 KG completion 有什么区别？**  
A：普通 KG completion 常用 embedding 或模型分数预测缺失边；当前代码没有 KG embedding 训练，而是用类型约束、路径、公共邻居、证据 overlap 生成候选，再用 reasoner 和 verifier 判断。

**Q13：这个项目和单纯 LLM 抽取有什么区别？**  
A：它不让 LLM 从文本中自由抽全部关系，而是先生成候选并绑定 evidence context。LLM 只在限定 candidate 上判断 accept/reject/uncertain。

**Q14：如果 LLM 判断错了怎么办？**  
A：代码层面主要靠 Verifier 兜底：schema 不合法、accept 无证据、引用不存在 evidence id、置信度过低、重复冲突都会被拦截或降为 uncertain/reject。但对“证据存在但语义误判”的错误，当前没有更强的自动纠错机制。

**Q15：如何保证关系不会乱补？**  
A：候选生成阶段限制 head/tail 类型和至少一个结构/证据规则；推理阶段要求 evidence context；Verifier 阶段要求 evidence grounding 和 confidence threshold；最终只写 verifier passed 的 accept 到 `predicted_edges.jsonl`。

**Q16：当前代码最大不足是什么？**  
A：从工程实现看，证据检索和打分仍偏规则化，LLM 输出没有严格 schema API，最终结果没有写回保护或人工复核接口，真实 LLM 的 precision 还需要校准、reranking 或更严格接受策略。

**Q17：如果继续改进，优先改哪里？**  
A：优先补强 evidence scoring / reranking、使用严格 JSON schema 或 tool/function calling、增加人工复核输出字段、设计安全写回流程，并把 `reliability`、时间、来源等证据元数据纳入判断。

## 8. 适合汇报时说的版本

这个项目当前实现了一个面向企业资产知识图谱的证据驱动关系发现流程，目标不是让大模型自由补图，而是先把输入 KG、证据记录和任务配置组织成可控的工程 pipeline。系统从 `entities.jsonl`、`triples.jsonl`、`evidence.jsonl` 加载实体、已有边和证据，用 NetworkX 建立内存图索引，然后根据配置中的目标关系和实体类型约束生成候选，例如资产到团队、部门或人员的 `likely_owned_by` 关系。候选不是只靠类型枚举，而是必须命中路径、公共邻居或证据重叠等规则，并保留规则分数和候选分数。随后，系统为每个候选聚合图路径、相关 triples、实体 profile 和证据片段，构造成结构化上下文。推理阶段既支持本地可复现的 MockReasoner，也支持 OpenAI-compatible 的真实 LLM；两种模式都会输出判断、置信度、原因和引用证据。最后 Verifier 会检查类型一致性、证据 grounding、置信度阈值和冲突，只有通过校验的 accept 才写入 `predicted_edges.jsonl`，并用隐藏 gold 边计算 precision、recall 和 F1。整体上，它体现的是“候选约束、证据绑定、可解释输出、可追溯评估”的工程化思路；同时当前代码还没有实现图数据库写回、embedding 检索、模型训练和人工复核 UI，这些是后续可扩展方向。
