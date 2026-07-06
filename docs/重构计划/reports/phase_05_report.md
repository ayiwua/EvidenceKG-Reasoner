# Phase 5 报告：LLMClient Adapter

## 实际新增文件

- `docs/重构计划/phase_05_llm_adapter.md`
- `docs/重构计划/reports/phase_05_report.md`
- `configs/llm.yaml`
- `src/evidencekg/llm/base_client.py`
- `src/evidencekg/llm/mock_client.py`
- `src/evidencekg/llm/client_factory.py`
- `src/evidencekg/llm/local_client.py`
- `src/evidencekg/llm/anthropic_client.py`

## 实际修改文件

- `src/evidencekg/llm/openai_compatible_client.py`
- `src/evidencekg/llm/__init__.py`

## 删除的旧链路或废弃接口

- 本阶段未删除旧 `RealLLMReasoner`，Phase 6 迁移 Reasoner。
- v2 adapter 主接口为 `chat(messages, **kwargs) -> LLMResponse`，不再要求上层直接调用 OpenAI-compatible `complete()`。

## 完成能力

- 统一 `LLMResponse`。
- Mock provider 可本地 smoke。
- OpenAI-compatible provider 支持 dict config 和 `chat()`。
- Anthropic provider 使用原生 Anthropic messages API，不伪装成 OpenAI-compatible。
- Local provider 支持本地 HTTP endpoint。
- ClientFactory 可按配置选择 provider。

## 验收命令与结果

执行：

```powershell
python -B -c "import sys, yaml, json; sys.path.insert(0, 'src'); from pathlib import Path; from evidencekg.llm.client_factory import ClientFactory; cfg=yaml.safe_load(Path('configs/llm.yaml').read_text(encoding='utf-8')); client=ClientFactory.from_config(cfg); resp=client.chat([{'role':'user','content':'smoke'}], context={'supporting_evidence_candidates':[{'id':'ev_1'}], 'candidate': {'relation':'owned_by'}}); print(resp.provider, resp.model, json.loads(resp.content)['decision'], resp.usage)"
```

结果：

```text
mock mock-evidencekg-v2 accept {'input_tokens': 5, 'output_tokens': 400}
```

## 未完成项

- Reasoner 尚未迁移到统一 client；Phase 6 处理。
- HardVerifier 和 SemanticVerifier 尚未迁移。
- 未执行真实 provider 调用，因为本阶段 smoke 不需要外部 key。

## 偏离原计划的地方

- 无。

## 是否建议进入下一阶段

建议进入 Phase 6：Reasoner + HardVerifier + SemanticVerifier。
