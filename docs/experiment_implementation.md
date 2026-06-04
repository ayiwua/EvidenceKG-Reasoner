# Stage 3 实验实现说明

Stage 3 的目标是解释模块贡献和真实 LLM 接入质量，不扩大项目范围。所有实验都复用同一条 pipeline，只通过 config 或 runner 参数改变局部行为。

## 1. Mock Full Pipeline

命令：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs_stage3/mock_full
```

实现方式：

- `llm.mode: mock`
- candidate rules 使用 `two_hop_path`、`common_neighbor`、`evidence_overlap`
- evidence context 保留 entity profiles、graph paths、common neighbors、related triples、evidence snippets
- Verifier 正常启用

当前结果：

- precision: 0.5455
- recall: 0.8000
- F1: 0.6486
- accepted: 22
- rejected: 9
- uncertain: 71

Mock Full 是可复现模块分析基线，不代表最终真实 LLM 能力。

## 2. w/o Verifier ablation

命令：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by.yaml --data-dir data/sample --output-dir outputs_stage3/mock_no_verifier --disable-verifier
```

实现方式：

- `PipelineRunner.run(disable_verifier=True)` 不调用 `Verifier.verify(...)`
- 走 `_raw_prediction(...)`
- `verifier_status` 写为 `skipped`
- 额外统计 `_raw_prediction_risk_stats(...)`

当前结果：

- precision: 0.3871
- recall: 0.8000
- F1: 0.5217
- invalid_evidence_id_count: 9

解释：跳过 Verifier 后 accepted 从 22 增到 31，但 precision 下降，并出现不存在 evidence id，说明 Verifier 对可靠性是必要的。

## 3. Entity-text-only evidence ablation

命令：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_entity_text_only.yaml --data-dir data/sample --output-dir outputs_stage3/mock_entity_text_only
```

实现方式：

- candidate generation 不变
- `evidence_retrieval.include_graph_paths: false`
- `include_common_neighbors: false`
- `include_related_triples: false`
- 保留 `head_profile`、`tail_profile`、`evidence_snippets`

当前结果：

- precision: 0.0000
- recall: 0.0000
- F1: 0.0000
- uncertain: 102

解释：当前 MockReasoner 的 accept 条件依赖 graph paths，因此去掉图结构后全部变成 uncertain。这是对 mock 规则敏感性的消融，不说明真实 LLM 只能依赖结构。

## 4. Evidence-only candidate rules

命令：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_evidence_only.yaml --data-dir data/sample --output-dir outputs_stage3/mock_evidence_only
```

实现方式：

- `candidate_rules` 只保留 `evidence_overlap`
- `type_rule` 仍只是 schema filter
- 不允许 type_rule 单独生成候选

当前结果：

- candidate_count: 63
- precision: 0.0000
- recall: 0.0000
- F1: 0.0000

解释：只靠 evidence overlap 能生成候选，但在当前 mock 规则下缺少结构路径支撑，因此没有最终 accepted edges。

## 5. Structure-only candidate rules

命令：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_structure_only.yaml --data-dir data/sample --output-dir outputs_stage3/mock_structure_only
```

实现方式：

- `candidate_rules` 使用 `two_hop_path` 和 `common_neighbor`
- 去掉 `evidence_overlap` 候选规则
- type_rule 仍只做 schema filter

当前结果：

- candidate_count: 87
- precision: 0.7059
- recall: 0.8000
- F1: 0.7500

解释：在当前样例 KG 和 mock 规则中，隐藏 ownership 边被两跳路径和共同邻居强表示，所以 structure-only 表现更好。这是样例和 mock 规则共同作用的结果，不应夸大为所有真实场景结论。

## 6. Flash Top-10 / Offset-10

Top-10 命令：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_stage3/real_flash_top10 --max-candidates 10
```

Offset-10 命令：

```powershell
python scripts/run_pipeline.py --config configs/task_owned_by_real.yaml --data-dir data/sample --output-dir outputs_stage3/real_flash_offset10 --max-candidates 10 --candidate-offset 40
```

实现方式：

- `llm.mode: real`
- provider 通过 `.env` 中的 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 控制
- Top-10 观察高分候选
- Offset-10 观察弱证据候选

当前结果：

- Flash Top-10: precision 0.7000, recall 0.4667, F1 0.5600
- Flash Offset-10: precision 0.0000, recall 0.0000, F1 0.0000

解释：Flash small run 用于低成本验证 real LLM 接入、JSON 输出、evidence grounding、Verifier 兼容性。因为使用 `--max-candidates`，recall 不能和 full run 直接比较。

## 7. MiMo-v2.5-pro full real run

推荐命令：

```powershell
$env:LLM_MODEL='mimo-v2.5-pro'
python scripts/run_pipeline.py `
  --config configs/task_owned_by_real.yaml `
  --data-dir data/sample `
  --output-dir outputs_stage3/real_mimo_v25_pro_full `
  --debug-timing `
  --llm-timeout-seconds 120 `
  --llm-max-retries 0
```

实现方式：

- 使用有效模型 ID `mimo-v2.5-pro`
- 102 个 generated candidates 全量进入 reasoning
- 每个 candidate 完成后增量写 `verified_predictions.jsonl`
- debug timing 下增量写 `timing_report.jsonl`
- 输出仍必须经过 Verifier

当前结果：

- precision: 0.2586
- recall: 1.0000
- F1: 0.4110
- accepted: 58
- rejected: 21
- uncertain: 23
- verifier_pass_rate: 0.9412

解释：MiMo-v2.5-pro 找回了全部 15 条 hidden gold edges，recall=1.0。但它接受了 58 条最终边，precision 较低，说明真实 LLM 更倾向高召回和积极接受。后续应重点做 reranking、Verifier 阈值校准或更严格的接受策略。

## 8. 实验输出目录

| 实验 | 输出目录 |
| --- | --- |
| Mock Full | `outputs_stage3/mock_full` |
| w/o Verifier | `outputs_stage3/mock_no_verifier` |
| Entity-text-only | `outputs_stage3/mock_entity_text_only` |
| Evidence-only | `outputs_stage3/mock_evidence_only` |
| Structure-only | `outputs_stage3/mock_structure_only` |
| Flash Top-10 | `outputs_stage3/real_flash_top10` |
| Flash Offset-10 | `outputs_stage3/real_flash_offset10` |
| MiMo Full | `outputs_stage3/real_mimo_v25_pro_full` |

每组标准输出包括：

- `candidate_pairs.jsonl`
- `evidence_contexts.jsonl`
- `verified_predictions.jsonl`
- `predicted_edges.jsonl`
- `evaluation_report.json`
- `timing_report.jsonl`，仅 debug timing 开启时

## 9. 指标解释

Mock ablation 用来分析模块贡献。w/o Verifier 显示可靠性过滤的重要性。Entity-text-only 和 Evidence-only 显示当前 mock 规则对图结构依赖明显。Structure-only 在当前样例上表现更好，是因为隐藏 ownership 边有强结构信号。

Real LLM small run 用来验证真实模型接入，不是最终 full evaluation。MiMo-v2.5-pro full run 是当前 full real baseline：召回强，但 precision 低，后续工作应聚焦误报控制。
