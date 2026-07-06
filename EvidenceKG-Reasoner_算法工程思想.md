# EvidenceKG-Reasoner 算法工程思想

## 1. 项目背后的核心思想

EvidenceKG-Reasoner 的核心思想是把“关系发现”拆成一组可控制、可验证、可复盘的工程步骤，而不是让 LLM 直接从文本或全图中自由生成三元组。当前代码已经实现了 JSONL KG 加载、候选关系生成、证据上下文聚合、Mock/Real reasoner 判断、Verifier 校验和 hidden edge recovery 评估。它的完成程度更接近一个可运行的研究 demo / 小型框架：主流程完整，模块边界清楚，有测试和样例数据，但证据打分、语义检索、写回保护、人工复核和更强的真实 LLM 校准还没有完善。

## 2. 算法抽象

```text
Algorithm: EvidenceKG-Reasoner

Input:
- Entity records: entities.jsonl
- Existing KG triples: triples.jsonl
- Evidence records: evidence.jsonl
- Task config: target relation, allowed types, candidate rules, retrieval options, LLM mode, verifier rules
- Optional gold hidden edges: gold_hidden_edges.jsonl

Output:
- candidate_pairs.jsonl
- evidence_contexts.jsonl
- verified_predictions.jsonl
- predicted_edges.jsonl
- evaluation_report.json

Implemented Steps:
1. Load task config from YAML.
2. Load entities, triples, and evidence into GraphStore.
3. Build an in-memory NetworkX MultiDiGraph structural index.
4. Enumerate allowed head/tail entity pairs.
5. Remove self-pairs and already existing target-relation edges.
6. Score candidates with configured rules:
   - two_hop_path
   - common_neighbor
   - evidence_overlap
7. Keep only candidates with at least one nonzero rule score.
8. Retrieve evidence context for each reasoning candidate:
   - entity profiles
   - graph paths
   - common neighbors
   - related triples
   - evidence snippets
9. Build structured_context and prompt_text.
10. Run MockReasoner or RealLLMReasoner.
11. Normalize prediction into decision, confidence, reason, supporting_evidence_ids.
12. Verify schema consistency, evidence grounding, confidence threshold, and conflict.
13. Save all verified predictions and final accepted predicted edges.
14. Compare predicted edges with gold hidden edges and compute metrics.

Reserved / Not Implemented:
- Write accepted edges back to the KG.
- Embedding retriever or reranker.
- Learned evidence confidence model.
- Strict JSON Schema / function calling.
- Human review interface.
```

## 3. 工程设计思想

### 3.1 证据优先，而不是自由生成

当前代码先通过 `EvidenceRetriever.retrieve()` 组织证据，再让 reasoner 判断候选关系。这样做的价值是把模型判断限制在已有图结构和证据片段上，而不是让 LLM 凭常识补边。`PromptBuilder` 明确写了 “Use only the provided context. Do not invent evidence ids.”，`Verifier` 又要求 accept 结果必须引用当前 context 中存在的 evidence id。这个设计让关系判断可以追溯到具体证据，虽然当前证据检索仍是规则 overlap，不是语义检索。

### 3.2 候选生成和关系判断分离

`CandidateGenerator` 负责生成“可能值得判断”的候选，`MockReasoner` / `RealLLMReasoner` 负责判断候选是否成立。分离这两步的好处是：候选空间由类型约束、路径、公共邻居和证据 overlap 控制，LLM 不需要从全图中自由枚举所有关系。这减少了输出空间，也方便调试每个候选为什么出现。测试 `test_type_only_pair_is_not_generated()` 也说明，类型合法本身不足以生成候选，必须有结构或证据规则支持。

### 3.3 结构化输入和结构化输出

项目把输入上下文整理成结构化字段：candidate、head_profile、tail_profile、graph_paths、common_neighbors、related_triples、evidence_snippets。真实 LLM 的 prompt 是自然语言指令加 Context JSON，输出被要求为固定 JSON 字段。这样的结构化设计提高了可控性：

- reasoner 输出统一为 `decision`、`confidence`、`reason`、`supporting_evidence_ids`。
- Verifier 可以读取 evidence id 做 grounding 检查。
- Evaluator 可以基于 `(head, relation, tail)` 集合计算指标。
- 中间文件 `candidate_pairs.jsonl`、`evidence_contexts.jsonl`、`verified_predictions.jsonl` 方便复盘。

不足是当前没有使用 provider 级 JSON schema 或 function calling，仍可能依赖正则兜底解析。

### 3.4 规则约束和 LLM 判断结合

当前代码已经有多层规则约束：

- 候选阶段：`allowed_head_types` / `allowed_tail_types`、排除已有目标关系、候选规则打分。
- 推理阶段：mock 模式是可复现规则替身；real 模式是 LLM 判断。
- 校验阶段：`Verifier.verify()` 检查 schema、evidence grounding、confidence threshold、conflict。

这说明系统不是把 LLM 当唯一裁判，而是把 LLM 放在受约束的位置上。后续可以继续扩展更细的规则，例如关系互斥、方向性约束、时间有效期、来源可靠性阈值。

### 3.5 可追溯性

可追溯性来自几个字段：

- `candidate_id`：串联候选、上下文、预测和 timing。
- `evidence_id`：让模型引用具体证据。
- `related_entities`：把证据和实体联系起来。
- `triple_id`、`evidence_ids`：把已有 KG 边和支撑证据联系起来。
- `reason`：保留 reasoner 的简短解释。
- `verifier_details`：记录 schema、evidence、confidence、conflict 各项是否通过。

这些字段让结果不是只给一个分数，而是能回答“为什么生成这个候选”“用了哪些证据”“为什么被 verifier 拒绝”。

### 3.6 工程可调试性

项目的可调试性体现在：

- 模块拆分明确：config、graph、candidate、retrieval、prompting、llm、verify、eval、pipeline。
- 中间结果落盘：候选、证据上下文、全部预测、最终预测边、评估报告。
- 支持小样本窗口：`--max-candidates`、`--candidate-offset`。
- 支持 verifier 消融：`--disable-verifier`。
- 支持 timing：`--debug-timing` 写 `timing_report.jsonl`。
- 测试覆盖关键模块：`tests/test_pipeline_runner.py`、`tests/test_verifier.py`、`tests/test_real_reasoner.py` 等。

不足是日志主要通过 print / tqdm 输出，没有统一 logging 配置；真实 LLM 运行的错误分类较基础，缺少更细粒度的 provider 诊断和重试策略分析。

## 4. 和普通方法的区别

### 4.1 和普通 RAG 的区别

普通 RAG 常见流程是“检索文档片段 -> 生成自然语言回答”。当前项目虽然也有 retrieval 和 prompt，但目标不是问答，而是判断结构化候选关系是否成立。它检索的不只是文本证据，还包括图路径、公共邻居、实体 profile 和相关 triples；输出也不是自由文本答案，而是 `accept/reject/uncertain`、置信度、原因和 evidence id。需要注意，当前检索不是 embedding RAG，而是基于 KG 结构和实体 overlap 的规则检索。

### 4.2 和普通 KG completion 的区别

普通 KG completion 往往用 embedding、GNN 或打分模型预测缺失边，输出通常是候选边分数。当前代码没有训练 KG completion 模型，而是通过可解释的结构规则生成候选，再绑定证据让 reasoner 判断。它更强调 evidence grounding、schema 校验、输出文件可复盘和隐藏边评估。代价是自动化泛化能力可能不如训练式模型，证据召回也受规则检索限制。

### 4.3 和单纯 LLM 抽取的区别

单纯 LLM 抽取通常把文本交给模型，让模型直接抽实体关系；风险是自由生成、关系类型不受控、证据引用不稳定。当前项目把 LLM 放在候选判断环节：候选来自代码规则，输入上下文来自图和证据，输出格式固定，最终还要过 Verifier。因此它更像“LLM 参与的受控关系判别系统”，而不是“LLM 一步抽取系统”。不过真实 LLM 的语义误判仍可能发生，当前主要靠 Verifier 做基础拦截。

## 5. 可以迁移到我自己项目的部分

面向“对象关联知识图谱 / 网络侧-物理侧对象关联 / LLM 隐含关系挖掘”，可以借鉴以下设计：

- 候选关系生成：当前代码已有。可迁移为先按对象类型、拓扑邻接、业务链路、共同告警、共同日志等规则生成候选，而不是让 LLM 从零找所有关系。
- 证据聚合：当前代码已有基础形态。可迁移为把网络侧日志、配置、告警、CMDB、工单、物理侧台账等证据按对象 ID 聚合成上下文。
- LLM 判断：当前代码已有 real LLM 模式。可迁移为让 LLM 只判断某个候选关联是否成立，并输出原因和证据 id。
- 关系校验：当前代码已有基础 verifier。可迁移为校验类型是否合法、方向是否合法、证据是否覆盖两端对象、置信度是否过阈值、是否和已有关系冲突。
- 结果写回：当前代码未实现。可扩展为写入图数据库前先进入 pending 状态，带来源、证据、时间戳和审核状态。
- 可追溯解释：当前代码已有 candidate_id、evidence_id、reason、verifier_details。可迁移为每条网络侧-物理侧关联都保留证据链和判断原因。
- 人工复核接口或中间结果保存：当前代码已有中间 JSONL 文件，但未实现 UI。可扩展为生成待复核表格或审核页面，让人确认高风险边。

迁移时最关键的不是照搬 `likely_owned_by`，而是照搬“候选先行、证据绑定、模型判别、规则校验、可追溯输出”的流程。

## 6. 当前代码的工程不足

- 输入文件名部分写死：`GraphStore.from_dir()` 固定读取 `entities.jsonl`、`evidence.jsonl`、`triples.jsonl`，不够通用。
- 证据检索偏规则：当前没有 embedding、BM25、reranker 或语义相似度，主要依赖 `related_entities` overlap 和 triple 关联。
- 证据可靠性未充分使用：`evidence.jsonl` 有 `reliability` 字段，但候选打分和 Verifier 没有系统使用它。
- 候选规则权重写在代码里：`two_hop_path`、`common_neighbor`、`evidence_overlap` 的分数是硬编码，不在 YAML 中配置。
- LLM 输出约束不够强：当前依靠 prompt、JSON 解析和正则兜底，没有严格 JSON Schema / function calling。
- 真实 LLM precision 校准不足：README 记录的 full real baseline recall 高但 precision 低，说明接受策略还需要 reranking 或阈值校准。
- 没有 KG 写回保护：`predicted_edges.jsonl` 是最终文件输出，但没有 pending / approved / rejected 写回流程。
- 没有人工复核界面：可以看中间 JSONL，但没有面向审核人员的交互入口。
- 日志系统不统一：有 tqdm、print、stderr warning 和 timing 文件，但没有统一 logging 配置。
- 缺少复杂约束：当前未发现时间有效性推理、空间约束、关系互斥、唯一 owner 等更强业务规则。
- 没有学习式模块：未发现 fine-tuning、KG embedding、GNN、证据置信度学习或阈值自动校准。

## 7. 后续改进路线

### 7.1 最小可用改进

- 把候选规则权重移到 YAML 配置中，避免改代码调参。
- 在 `verified_predictions.jsonl` 中增加更明确的 `failure_reason`，例如 `invalid_evidence_id`、`low_confidence`、`schema_violation`。
- 在证据上下文中保留 evidence overlap 分数和来源可靠性摘要。
- 给 `.env`、真实 LLM provider 错误、空数据文件增加更明确的报错说明。
- 增加一个导出 CSV / Markdown 审核表的脚本，便于人工复核。

### 7.2 中等规模改进

- 增加 evidence reranker，把 `text`、`source`、`reliability`、时间、实体覆盖度综合排序。
- 引入严格 JSON Schema / function calling，减少 LLM 输出解析失败。
- 设计关系写回模块：先写 pending edges，审核通过后再写入 KG。
- 增加更多 verifier 规则，例如关系唯一性、时间有效期、反向冲突、来源黑白名单。
- 增加配置化数据 schema，让项目可适配不叫 `entities.jsonl` / `triples.jsonl` 的数据集。
- 做更系统的 ablation，比较结构、证据、LLM、Verifier、reranker 的贡献。

### 7.3 论文 / 项目级改进

- 构建证据感知的关系判别框架，把候选生成、证据检索、LLM 判别、规则校验统一建模。
- 引入 learned retriever / reranker，用人工标注或 gold hidden edges 学习证据排序和接受阈值。
- 研究 LLM 与规则 verifier 的协同校准，降低高 recall 模式下的 false positives。
- 做可解释 KG completion：不仅预测边，还输出证据链、路径、冲突检查和人类可读解释。
- 扩展到对象关联知识图谱，把网络侧、业务侧、物理侧对象统一为多源证据驱动的关联发现任务。
- 加入人机协同闭环：模型产生候选，Verifier 拦截风险，人工审核高价值边，审核结果反哺阈值和 reranker。

## 8. 适合对外讲的算法工程总结

EvidenceKG-Reasoner 的工程价值在于，它把知识图谱补边问题拆成可控的证据驱动流程，而不是直接把任务交给大模型自由生成。当前实现从 JSONL 资产图谱、已有关系和证据记录出发，先用实体类型、图路径、公共邻居和证据重叠生成候选关系，再为每个候选聚合实体 profile、相关 triples、路径和证据片段，形成可追溯的判断上下文。推理阶段既可以使用本地规则化 MockReasoner 保证复现，也可以切换到 OpenAI-compatible 的真实 LLM；模型输出被规范为判断、置信度、原因和支撑证据 id。之后 Verifier 会继续检查 schema、证据 grounding、置信度阈值和冲突，只有通过校验的 accept 才进入最终预测边，并通过隐藏 gold 边计算 precision、recall 和 F1。这个设计的重点不是某个单点模型，而是候选约束、证据绑定、结构化输出、规则校验和中间结果落盘形成的工程闭环。它目前仍是一个研究 demo / 小型框架，尚未实现 embedding 检索、图数据库写回、人工审核和学习式校准，但已经提供了一个可以迁移到对象关联、网络侧-物理侧映射和隐含关系挖掘任务中的清晰范式。
