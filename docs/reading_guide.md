# 代码阅读指南

这份指南给第一次阅读 EvidenceKG-Reasoner 的同学一个推荐顺序。目标不是背代码，而是逐步建立“数据从哪里来、模块怎么接、结果怎么算”的心智模型。

## 1. 先看 README

为什么先看：README 给出项目一句话定位、运行命令、输入输出文件、Stage 1/2/3 结果。

重点看：

- Run Mock Pipeline
- Run Real LLM Pipeline
- Stage 1 Mock Pipeline Result
- Stage 2 Real LLM Small Run
- Stage 3 Ablation Results
- Real LLM Full Run Result

看完应理解：项目是 GraphRAG 式证据推理系统，不是 Neo4j 系统、不是前端、不是 GNN/TransE/RotatE 训练。

## 2. 看 data/sample 四个 JSONL 文件

为什么看：代码所有行为都围绕这四个文件展开。

重点看：

- `entities.jsonl` 的 `entity_id/type/name`
- `triples.jsonl` 的 `head/relation/tail/evidence_ids`
- `evidence.jsonl` 的 `related_entities/text`
- `gold_hidden_edges.jsonl` 的隐藏目标边

看完应理解：候选关系不是从空中来，而是在已有 KG 结构和证据文本上生成。

## 3. 看 configs/task_owned_by.yaml 和 task_owned_by_real.yaml

为什么看：配置决定 target relation、类型边界、候选规则、证据检索范围和 LLM 模式。

重点看：

- `target_relation`
- `allowed_head_types`
- `allowed_tail_types`
- `candidate_rules`
- `evidence_retrieval`
- `llm.mode`
- `verifier.confidence_threshold`

看完应理解：`likely_owned_by` 是从 config 来的，不应写死在代码里。

## 4. 看 scripts/run_pipeline.py

为什么看：这是命令行入口。

重点看：

- `argparse` 参数
- `PipelineRunner().run(...)`
- `--max-candidates`
- `--candidate-offset`
- `--debug-timing`
- `--llm-timeout-seconds`
- `--llm-max-retries`

看完应理解：CLI 本身不做推理，只负责收参数并调用 Runner。

## 5. 看 PipelineRunner

文件：`src/evidencekg/pipeline/runner.py`

为什么看：它是所有模块的串联点。

重点看：

- `run()`
- `_build_reasoner()`
- `_raw_prediction()`
- `_raw_prediction_risk_stats()`
- `_run_metadata()`
- `_can_resume()`
- `_candidate_timing_event()`

看完应理解：完整 pipeline 的执行顺序、mock/real mode 分支、ablation、resume、timing report 都在这里组织。

## 6. 看 TaskConfig

文件：`src/evidencekg/config/task_config.py`

为什么看：它解释 YAML 如何进入代码。

重点看：

- `TaskConfig`
- `EvidenceRetrievalConfig`
- `LLMConfig`
- `VerifierConfig`
- `load_task_config()`
- `is_allowed_pair()`

看完应理解：配置对象怎样控制后续模块。

## 7. 看 GraphStore

文件：`src/evidencekg/graph/graph_store.py`

为什么看：这是 KG 数据访问层。

重点看：

- `from_dir()`
- `load_entities()`
- `load_triples()`
- `load_evidence()`
- `get_triples_for_entities()`
- `get_evidence_for_entities()`
- `get_neighbors()`
- `find_paths()`

看完应理解：triples 的主数据在 dict，NetworkX MultiDiGraph 是结构索引。

## 8. 看 CandidateGenerator

文件：`src/evidencekg/candidate/generator.py`

为什么看：它决定哪些关系会被拿去推理。

重点看：

- `generate()`
- `_score_pair()`
- `config.is_allowed_pair(...)`
- `graph.has_relation(...)`
- `rule_scores`
- `candidate_score`

看完应理解：type_rule 是 schema filter，候选必须命中结构或证据规则。

## 9. 看 EvidenceRetriever

文件：`src/evidencekg/retrieval/evidence_retriever.py`

为什么看：它把 candidate 转成可供推理的证据上下文。

重点看：

- `retrieve()`
- `query_entities`
- `related_triples`
- `evidence_snippets`
- `include_graph_paths`
- `max_evidence_snippets`

看完应理解：prompt 里的上下文不是全图，而是 candidate 周边的局部证据。

## 10. 看 PromptBuilder

文件：`src/evidencekg/prompting/prompt_builder.py`

为什么看：它连接结构化证据和真实 LLM prompt。

重点看：

- `build()`
- `structured_context`
- `prompt_text`
- JSON 输出 schema

看完应理解：MockReasoner 用 structured context，RealLLMReasoner 用 prompt_text。

## 11. 看 MockReasoner / RealLLMReasoner

文件：`src/evidencekg/llm/reasoner.py`

为什么看：这里是模型推断结果产生的位置。

重点看：

- `MockReasoner.predict()`
- `RealLLMReasoner.predict()`
- `_parse_json_output()`
- `_normalize()`
- `_fallback()`

看完应理解：mock 是可复现规则替身，real mode 是 OpenAI-compatible JSON 推断，并且异常会降级为 uncertain。

## 12. 看 Verifier

文件：`src/evidencekg/verify/verifier.py`

为什么看：它决定哪些预测能进入最终边。

重点看：

- `verify()`
- `_check_evidence_grounding()`
- `schema_consistency`
- `evidence_grounding`
- `confidence_threshold`
- `conflict_check`

看完应理解：`verified_predictions.jsonl` 和 `predicted_edges.jsonl` 的区别。

## 13. 看 Evaluator

文件：`src/evidencekg/eval/evaluator.py`

为什么看：它解释结果指标怎么来的。

重点看：

- `evaluate()`
- `predicted_keys`
- `gold_keys`
- `hits`
- precision / recall / F1

看完应理解：precision / recall / F1 只基于 final accepted edges，不把 rejected / uncertain 算进命中。

## 14. 看 tests

为什么看：测试会告诉你项目最核心的不变量。

重点看：

- `test_candidate_generator.py`: 候选规则和 type filter。
- `test_graph_store.py`: MultiDiGraph 和查询接口。
- `test_pipeline_runner.py`: 输出文件、max_candidates、offset、disable_verifier、timing。
- `test_real_reasoner.py`: real config、JSON 解析、异常降级。
- `test_verifier.py`: evidence grounding、schema、confidence。

看完应理解：哪些行为是已经被固定下来的，不适合随便改。

## 15. 看 stage3_results

文件：`docs/stage3_results.md`

为什么最后看：读完代码后再看结果，才能知道每个数字来自哪个模块。

重点看：

- Mock Ablation Results
- Real LLM Results
- MiMo-v2.5-Pro Full 的解释
- w/o Verifier 的 invalid_evidence_id_count

看完应理解：mock 用于可复现模块消融；Flash 用于低成本真实接入验证；MiMo-v2.5-pro full run 是当前 real baseline，recall=1.0 但 precision 较低，说明真实 LLM 高召回但更激进。
