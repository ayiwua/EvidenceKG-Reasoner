# Phase 5: LLMClient Adapter

## 阶段目标

实现统一多 provider LLMClient 接口，使 Reasoner 上层不直接依赖 OpenAI-compatible 调用细节。

## 本阶段范围

- 新增 `BaseLLMClient` 和 `LLMResponse`。
- 实现 `MockLLMClient`，用于本地 smoke run。
- 实现 `OpenAICompatibleClient.chat()`。
- 实现 `AnthropicClient.chat()`，依赖缺失或 key 缺失时只影响 Anthropic provider。
- 实现 `LocalClient.chat()`，用于本地 HTTP chat endpoint。
- 实现 `ClientFactory`，从配置选择 provider。
- 新增 `configs/llm.yaml`。

## 明确不做什么

- 不修改 `docs/重构计划/codex改进提示词.md`。
- 不调用真实外部 LLM。
- 不在 Reasoner 中解析 LLM 输出；Phase 6 负责。
- 不做 verifier、writeback、eval。
- 不把 Anthropic 写成 OpenAI-compatible。

## 预计涉及文件

新增：

- `configs/llm.yaml`
- `src/evidencekg/llm/base_client.py`
- `src/evidencekg/llm/anthropic_client.py`
- `src/evidencekg/llm/local_client.py`
- `src/evidencekg/llm/mock_client.py`
- `src/evidencekg/llm/client_factory.py`

修改：

- `src/evidencekg/llm/openai_compatible_client.py`
- `src/evidencekg/llm/__init__.py`

## 输出产物

- 统一 LLM adapter 层。
- Phase 5 报告。

## 验收标准

- `ClientFactory` 能创建 mock client。
- mock `chat()` 返回 `LLMResponse`。
- response 包含 `provider`、`model`、`content`、`latency_ms`、`usage`、`raw`。
- 未配置真实 provider key 时不会影响 mock。

## Smoke 命令

```powershell
python -B -c "import sys, yaml, json; sys.path.insert(0, 'src'); from pathlib import Path; from evidencekg.llm.client_factory import ClientFactory; cfg=yaml.safe_load(Path('configs/llm.yaml').read_text(encoding='utf-8')); client=ClientFactory.from_config(cfg); resp=client.chat([{'role':'user','content':'smoke'}], context={'supporting_evidence_candidates':[{'id':'ev_1'}], 'candidate': {'relation':'owned_by'}}); print(resp.provider, resp.model, json.loads(resp.content)['decision'], resp.usage)"
```

## 风险与注意事项

- Provider-specific failures must be explicit; missing key is an error for that provider, not a fallback to mock.
- MockLLM is the only intended local smoke fallback.
