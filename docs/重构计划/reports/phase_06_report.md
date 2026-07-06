# Phase 6 报告：Reasoner + HardVerifier + SemanticVerifier

## 实际新增文件

- `docs/重构计划/phase_06_reasoner_and_verifier.md`
- `docs/重构计划/reports/phase_06_report.md`
- `scripts/run_reasoning_and_verification.py`
- `outputs/llm_predictions.jsonl`
- `outputs/verified_predictions.jsonl`

## 实际修改文件

- `src/evidencekg/llm/reasoner.py`
- `src/evidencekg/verify/verifier.py`
- `src/evidencekg/verify/__init__.py`

## 删除的旧链路或废弃接口

- v2 主链路使用 `LLMReasoner + ClientFactory`，不再直接调用 OpenAI-compatible `complete()`。
- v2 验证拆分为 `HardVerifier` 和 `SemanticVerifier`。
- 旧 `Verifier` 类暂未删除，避免本阶段误伤仍未迁移的旧脚本；后续 v2 pipeline 不使用它。

## 完成能力

- LLM 输出结构化解析。
- Markdown JSON object 抽取。
- decision normalize。
- confidence clamp。
- evidence id list normalize。
- provider/parse failure 显式 uncertain。
- HardVerifier 校验 schema、decision、confidence、evidence ids、accept evidence、冲突。
- SemanticVerifier 检查 evidence related_entities 和 relation-specific 文本信号。

## 验收命令与结果

执行：

```powershell
python scripts/run_reasoning_and_verification.py --contexts outputs/evidence_contexts.jsonl --relation-schema configs/relation_schema.yaml --llm-config configs/llm.yaml --out-dir outputs
```

结果：

```json
{
  "accept_count": 14,
  "hard_pass_count": 60,
  "prediction_count": 60,
  "reject_count": 31,
  "semantic_supported_count": 14,
  "uncertain_count": 15
}
```

结构检查：

```powershell
python -c "import json; rows=[json.loads(l) for l in open('outputs/verified_predictions.jsonl', encoding='utf-8') if l.strip()]; print(len(rows)); print(rows[0]['decision'], rows[0]['hard_verifier']['status'], rows[0]['semantic_verifier']['support_status']); print({'decision','confidence','relation','reason','supporting_evidence_ids','conflict_evidence_ids','evidence_analysis'} <= set(rows[0]))"
```

结果：

```text
60
accept passed supported
True
```

accepted gold 覆盖：

```powershell
python -c "import json; gold={(r['head'],r['relation'],r['tail']) for r in map(json.loads, open('data/processed/gold_hidden_edges.jsonl', encoding='utf-8'))}; rows=[json.loads(l) for l in open('outputs/verified_predictions.jsonl', encoding='utf-8') if l.strip()]; accepted={(r['head'],r['relation'],r['tail']) for r in rows if r['decision']=='accept'}; print(len(accepted), len(accepted & gold), sorted(accepted & gold))"
```

结果：`14 7`，sample gold 全部在 accepted 中。

## 未完成项

- pending writeback、review apply、evaluation_report 尚未实现。
- 完整 sample pipeline CLI 尚未串联。

## 偏离原计划的地方

- 写 `outputs/llm_predictions.jsonl` 和 `outputs/verified_predictions.jsonl` 时受限环境拒绝仓库内输出写入，已使用提升权限重跑同一命令。

## 是否建议进入下一阶段

建议进入 Phase 7：Pending Writeback + Eval + Pipeline。
