# Phase 6: Reasoner + HardVerifier + SemanticVerifier

## 阶段目标

升级推理与验证链路：通过统一 LLMClient 生成结构化预测，先做硬校验，再做语义证据支持校验。

## 本阶段范围

- 新增 v2 `LLMReasoner`，使用 `BaseLLMClient.chat()`。
- 实现 JSON 解析、Markdown JSON 抽取、字段 normalize、confidence clamp、parse_error fallback uncertain。
- 新增 `HardVerifier`，校验 schema、decision/confidence、evidence id、关系类型、冲突。
- 新增 `SemanticVerifier`，检查 supporting evidence 是否语义支持候选关系。
- 新增 CLI：`scripts/run_reasoning_and_verification.py`。
- 输出 `outputs/llm_predictions.jsonl` 和 `outputs/verified_predictions.jsonl`。

## 明确不做什么

- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不调用真实 LLM；smoke 使用 MockLLM。
- 不写 pending_edges；Phase 7 负责。
- 不生成 evaluation_report；Phase 7 负责。

## 预计涉及文件

新增：

- `scripts/run_reasoning_and_verification.py`
- `docs/重构计划/reports/phase_06_report.md`

修改：

- `src/evidencekg/llm/reasoner.py`
- `src/evidencekg/verify/verifier.py`

## 输出产物

- `outputs/llm_predictions.jsonl`
- `outputs/verified_predictions.jsonl`
- Phase 6 报告。

## 验收标准

- 能读取 `outputs/evidence_contexts.jsonl` 并生成同数量预测。
- MockLLM 输出通过统一 ClientFactory。
- `llm_predictions.jsonl` 包含 v2 prediction schema。
- `verified_predictions.jsonl` 包含 hard 和 semantic verifier 结果。
- accepted + hard passed + semantic supported 的预测可供 Phase 7 writeback。

## Smoke 命令

```powershell
python scripts/run_reasoning_and_verification.py --contexts outputs/evidence_contexts.jsonl --relation-schema configs/relation_schema.yaml --llm-config configs/llm.yaml --out-dir outputs
```

辅助检查：

```powershell
python -c "import json; rows=[json.loads(l) for l in open('outputs/verified_predictions.jsonl', encoding='utf-8') if l.strip()]; print(len(rows)); print(rows[0]['decision'], rows[0]['hard_verifier']['status'], rows[0]['semantic_verifier']['support_status'])"
```

## 风险与注意事项

- SemanticVerifier 是 evidence support checking，不是万能事实裁判。
- MockLLM 只用于 smoke；真实 provider 失败必须显式记录 error_type 或 parse_error。
