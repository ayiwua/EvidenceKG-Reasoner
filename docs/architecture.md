# EvidenceKG-Reasoner Architecture

本文档是仓库级架构说明，负责把项目工作模式、Re-DocRED 主研究 pipeline、旧企业资产 pipeline 的 legacy/reference 定位和模块边界放在同一张图里。具体 Re-DocRED 设计细节以 `docs/redocred_pipeline_design.md` 为准；后续每个模块的批准规格应放在 `docs/specs/` 下。

## 1. Architecture Principles

本项目采用 Specification Driven Development。实现应服从已批准的设计文档，而不是反过来由当前代码决定系统方向。

权威顺序如下：

```text
1. 用户最新明确决定
2. docs/specs/ 下已批准的模块规格
3. docs/architecture.md
4. docs/redocred_pipeline_design.md
5. 当前代码行为
```

当前架构原则：

- Re-DocRED 是后续唯一主研究和主开发方向。
- 原企业资产 hidden edge recovery pipeline 降级为 legacy/reference，不再作为长期并行主线。
- 旧 pipeline 暂时保留用于理解第一版流程、借鉴少量工具代码和避免短期内破坏仓库历史功能。
- 新代码不需要强行兼容旧 pipeline，旧代码不能限制 Re-DocRED 模块设计。
- 新模块应围绕 Re-DocRED 独立设计和实现。
- 第一阶段 Re-DocRED 任务是 evidence-aware triple verification。
- 所有 Re-DocRED JSONL 文件使用稳定、可复现 ID。
- 推理链路中禁止 gold label / gold evidence 泄漏。
- Evaluator 是唯一允许将预测结果与 gold labels 对比的模块。
- 每个新增模块应先有设计规格，再实现代码。

## 2. Pipeline Families

仓库当前有两个 pipeline family，但它们的地位不同：Re-DocRED 是 primary research pipeline；enterprise asset pipeline 只是 legacy reference pipeline。

### 2.1 Re-DocRED Primary Research Pipeline

Re-DocRED pipeline 是后续唯一主开发方向，面向文档级、多关系、证据感知的 triple verification。

目标任务：

```text
Given document D, head entity h, relation r, and tail entity t,
decide whether candidate triple (h, r, t) is supported by D,
and return supporting evidence sentence ids when possible.
```

目标流程：

```text
Raw Re-DocRED
  -> RedocredAdapter
  -> Processed JSONL
  -> RedocredCandidateGenerator
  -> RedocredSentenceRetriever
  -> RedocredDocumentGraph / GraphContextRetriever
  -> RedocredPromptBuilder
  -> Reasoner
  -> RedocredVerifier
  -> RedocredEvaluator
```

第一阶段输出：

```text
decision = accept | reject | uncertain
confidence
risk
reason
supporting_evidence_ids
optional conflict_evidence_ids
verifier_details
```

Re-DocRED 模块应独立设计。可以借鉴旧 pipeline 的 JSONL IO、LLM client、JSON parsing、配置加载等工具性代码，但不应把旧 pipeline 的单关系 hidden edge recovery 假设带入新模块。

### 2.2 Enterprise Asset Legacy Reference Pipeline

这是当前已有 pipeline，面向企业资产/IT 资产 KG 的 hidden edge recovery。

```text
entities / triples / evidence
  -> CandidateGenerator
  -> EvidenceRetriever
  -> PromptBuilder
  -> MockReasoner / RealLLMReasoner
  -> Verifier
  -> Evaluator
  -> predicted_edges.jsonl / evaluation_report.json
```

主要文件：

| Layer | Files |
| --- | --- |
| Config | `configs/task_owned_by*.yaml`, `src/evidencekg/config/task_config.py` |
| Data build | `configs/dataset_manifest.yaml`, `scripts/build_dataset_from_csv.py`, `src/evidencekg/data/dataset_builder.py` |
| Graph | `src/evidencekg/graph/graph_store.py` |
| Candidate | `src/evidencekg/candidate/generator.py` |
| Retrieval | `src/evidencekg/retrieval/evidence_retriever.py` |
| Prompt | `src/evidencekg/prompting/prompt_builder.py` |
| Reasoner | `src/evidencekg/llm/reasoner.py`, `src/evidencekg/llm/*_client.py` |
| Verifier | `src/evidencekg/verify/verifier.py` |
| Evaluation | `src/evidencekg/eval/evaluator.py` |
| Runner | `scripts/run_pipeline.py`, `src/evidencekg/pipeline/runner.py` |

这条 pipeline 的历史输入数据合同是：

```text
entities.jsonl
triples.jsonl
evidence.jsonl
gold_hidden_edges.jsonl
```

旧 pipeline 的当前定位：

- 用于理解第一版 EvidenceKG 流程。
- 用于借鉴少量工具代码。
- 用于短期内保留仓库历史功能。
- 不再要求长期维护。
- 不再作为 Re-DocRED 的强复用基础。
- 不应限制 Re-DocRED 的数据格式、模块边界、runner、evaluator 或实验设计。

当 Re-DocRED small pipeline 跑通后，可以考虑把旧 enterprise pipeline 移入 `legacy/`，后续甚至删除。

## 3. Re-DocRED Data Architecture

Re-DocRED processed data should be split-aware and document-local.

Recommended layout:

```text
data/redocred_processed/
  train/
    documents.jsonl
    entities.jsonl
    evidence.jsonl
    gold_triples.jsonl
    candidates.jsonl
  dev/
    documents.jsonl
    entities.jsonl
    evidence.jsonl
    gold_triples.jsonl
    candidates.jsonl
  test/
    documents.jsonl
    entities.jsonl
    evidence.jsonl
    candidates.jsonl
```

Required stable IDs:

| ID | Meaning |
| --- | --- |
| `doc_id` | deterministic document id from split and document index |
| `sentence_id` | deterministic sentence id from `doc_id` and sentence index |
| `entity_id` | deterministic entity id from `doc_id` and `vertexSet` index |
| `mention_id` | deterministic mention id from `entity_id` and mention index |
| `candidate_id` | deterministic candidate id from split/doc/candidate index |
| `gold_id` | deterministic gold triple id |
| `prediction_id` | deterministic or sequential prediction id within a run |

Core processed files:

| File | Producer | Main Consumers | Gold Access |
| --- | --- | --- | --- |
| `documents.jsonl` | Adapter | Candidate, Retriever, Graph | no gold required |
| `entities.jsonl` | Adapter | Candidate, Retriever, Graph, Verifier | no gold required |
| `evidence.jsonl` | Adapter | Retriever, Prompt, Verifier | no gold required |
| `gold_triples.jsonl` | Adapter | Candidate builder, Evaluator | gold file |
| `candidates.jsonl` | Candidate Generator | Retriever, Runner, Evaluator | may contain labels for dataset/debug; inference modules must not use labels as oracle |

Runtime outputs:

| File | Producer | Purpose |
| --- | --- | --- |
| `evidence_contexts.jsonl` | Sentence Retriever + Graph Context | Context for prompt/reasoner/verifier |
| `verified_predictions.jsonl` | Verifier / Runner | Full decision log |
| `predicted_triples.jsonl` | Runner | Accepted and verifier-passed triples |
| `evaluation_report.json` | Evaluator | Relation, evidence, risk-control metrics |
| `timing_report.jsonl` | Runner | Optional timing and resume diagnostics |

## 4. Re-DocRED Module Boundaries

### 4.1 Adapter

Responsibility:

- Read raw Re-DocRED files and relation metadata.
- Convert `title`, `sents`, `vertexSet`, `labels`, and `evidence` into deterministic JSONL.
- Produce documents, entities, sentence evidence, gold triples, and optionally positive candidates.

Allowed gold access:

- May read raw labels.
- May construct `gold_triples.jsonl`.
- May attach `gold_evidence_ids` for evaluation fields.

Forbidden:

- No retrieval.
- No prompt construction.
- No LLM reasoning.
- No verifier decisions.

Expected future files:

```text
src/evidencekg/data/redocred_adapter.py
scripts/build_redocred_dataset.py
configs/redocred_dataset.yaml
```

### 4.2 Candidate Generator

Responsibility:

- Create positive, negative, and hard negative candidate triples.
- Record `generation_rules`, `negative_type`, and `candidate_score`.
- Control candidate count per document.

Allowed gold access:

- May use gold triples during dataset construction to create positives and controlled negatives.

Forbidden:

- Must not perform evidence retrieval.
- Must not inject gold evidence into inference context.

Expected future files:

```text
src/evidencekg/candidate/redocred_candidate_generator.py
scripts/generate_redocred_candidates.py
```

### 4.3 Sentence Evidence Retriever

Responsibility:

- Retrieve top-k sentence evidence for each candidate.
- Use mention overlap, relation metadata, text similarity, sentence distance, and graph context features.
- Produce `evidence_contexts.jsonl`.

Allowed inputs:

- documents
- entities and mentions
- sentence evidence
- candidates
- relation metadata

Forbidden:

- Must not use `gold_evidence_ids` as retrieval input.
- Must not read `gold_triples.jsonl` during formal inference.

Expected future files:

```text
src/evidencekg/retrieval/redocred_sentence_retriever.py
scripts/retrieve_redocred_evidence_contexts.py
```

### 4.4 Document Graph / Graph Context Retriever

Responsibility:

- Build a document-local graph per Re-DocRED document.
- Model Document, Sentence, Entity, Mention, and CandidateTriple nodes.
- Extract head/tail mention sentences, common sentences, bridge entities, and co-occurrence paths.

Forbidden:

- Must not inject the current candidate's gold relation into prompt context.
- Should not require Neo4j or GNN in the first stage.

Expected future files:

```text
src/evidencekg/graph/redocred_document_graph.py
src/evidencekg/retrieval/redocred_graph_context.py
```

### 4.5 Prompt Builder

Responsibility:

- Build a strict JSON-only prompt for candidate triple verification.
- Include candidate, relation definition, allowed evidence ids, retrieved evidence sentences, and graph context.
- Explicitly instruct the model to use only provided document evidence.

Forbidden:

- Must not read gold labels.
- Must not read gold evidence.
- Must not expose oracle fields such as `label`, `gold`, or `gold_evidence_ids`.

Expected future file:

```text
src/evidencekg/prompting/redocred_prompt_builder.py
```

### 4.6 Reasoner

Responsibility:

- Call mock or real LLM.
- Return parseable structured output.
- Normalize invalid outputs to `uncertain` where appropriate.

Output schema:

```json
{
  "decision": "accept | reject | uncertain",
  "confidence": 0.0,
  "risk": "low | medium | high",
  "relation": "P17",
  "reason": "short evidence-grounded explanation",
  "supporting_evidence_ids": [],
  "conflict_evidence_ids": [],
  "evidence_analysis": []
}
```

Forbidden:

- Must not access evaluator files.
- Must not access gold labels or gold evidence.

Likely reusable code:

- `src/evidencekg/llm/reasoner.py`
- `src/evidencekg/llm/openai_compatible_client.py`
- `src/evidencekg/llm/local_client.py`
- `src/evidencekg/llm/anthropic_client.py`

### 4.7 Verifier

Responsibility:

- Check schema validity.
- Check evidence grounding.
- Check evidence sufficiency.
- Check conflicts and duplicate accepts.
- Apply uncertainty / abstention rules.

Forbidden:

- Must not use gold labels to decide correctness.
- Must not turn an incorrect prediction into correct by consulting evaluation gold.

Expected future file:

```text
src/evidencekg/verify/redocred_verifier.py
```

### 4.8 Evaluator

Responsibility:

- Compare predictions to gold labels.
- Compute relation precision, recall, F1.
- Compute evidence precision, recall, F1 when gold evidence is available.
- Compute risk-control metrics such as wrong accept rate, uncertain rate, coverage, and precision under coverage.

Allowed gold access:

- Evaluator is the only formal inference-stage module allowed to compare predictions to gold.

Expected future files:

```text
src/evidencekg/eval/redocred_evaluator.py
scripts/evaluate_redocred.py
```

## 5. Anti-Leakage Architecture

Gold information must be isolated by stage.

Allowed:

- Adapter may read raw labels to build gold files.
- Candidate generator may use gold labels to create positive candidates and controlled negatives.
- Evaluator may compare predictions to gold triples and gold evidence.

Forbidden:

- Retriever must not use `gold_evidence_ids` to rank or select evidence.
- Prompt builder must not expose gold labels or gold evidence fields.
- Reasoner must not read gold labels.
- Verifier must not use gold labels to decide whether a prediction is correct.

Practical rule:

Any field named `gold`, `label`, `gold_evidence_ids`, `gold_triples`, or equivalent must be removed from the object passed to prompt/reasoner/verifier unless that module specification explicitly allows it for non-oracle metadata.

## 6. First-Stage Non-Goals

The first Re-DocRED implementation must not include the following unless explicitly approved:

- full entity-pair x all-relation brute-force expansion;
- LLM full-document extraction that directly outputs all relations;
- Neo4j integration;
- GNN models;
- cross-encoder training;
- multi-agent debate;
- best-of-N LLM voting;
- complex temporal/spatial reasoning;
- premature large-scale refactor of the enterprise legacy pipeline before Re-DocRED small pipeline runs;
- deleting or moving the enterprise legacy pipeline before an approved migration/removal decision;
- test-set prompt or threshold tuning.

## 7. Suggested Implementation Stages

The implementation should follow the stages from `docs/redocred_pipeline_design.md`:

| Stage | Goal | Main Output |
| --- | --- | --- |
| 1 | Inspect Re-DocRED fields | schema summary |
| 2 | Build adapter | processed JSONL |
| 3 | Generate candidates | `candidates.jsonl` |
| 4 | Retrieve sentence evidence | `evidence_contexts.jsonl` |
| 5 | Build document graph context | graph context in evidence contexts |
| 6 | Build Re-DocRED prompt | structured context + prompt text |
| 7 | Verify predictions | `verified_predictions.jsonl` |
| 8 | Evaluate | `evaluation_report.json` |
| 9 | Smoke debug | small runnable pipeline |
| 10 | Formal dev/test experiments | reproducible experiment outputs |

Before coding each stage, Codex must produce the implementation plan required by `AGENTS.md` and wait for approval.

## 8. Documentation Layout

Recommended documentation structure:

```text
AGENTS.md
docs/
  architecture.md
  redocred_pipeline_design.md
  specs/
    redocred_adapter.md
    redocred_candidate_generator.md
    redocred_sentence_retriever.md
    redocred_document_graph.md
    redocred_prompt_builder.md
    redocred_verifier.md
    redocred_evaluator.md
```

The Re-DocRED design documents are worth committing to GitHub because they define the research direction and implementation contract. At minimum, commit:

- `AGENTS.md`
- `docs/architecture.md`
- `docs/redocred_pipeline_design.md`
- future `docs/specs/*.md` module specifications

## 9. Validation Expectations

Every implementation step should have a smoke check or test command. Examples:

```text
python scripts/inspect_redocred.py --input ...
python scripts/build_redocred_dataset.py --max-docs 5 ...
python scripts/generate_redocred_candidates.py --max-docs 5 ...
python scripts/run_redocred_pipeline.py --max-docs 3 --mock
python scripts/evaluate_redocred.py --input ...
```

If a full validation is impossible, the implementation report must say why and provide the strongest available dry-run or static validation.

## 10. Current Architecture Decision

The current approved direction is:

```text
Make Re-DocRED the primary and only active research/development pipeline.
Treat the original enterprise EvidenceKG pipeline as legacy/reference only.
Design new Re-DocRED modules independently.
Use old code only as optional reference or utility source, not as a required compatibility target.
Use documents and module specifications as the source of truth.
```

This architecture keeps the project direction clean: Re-DocRED becomes the research-grade path for document-level relation reasoning experiments, while the old enterprise pipeline stays only as temporary historical reference until it can be moved to `legacy/` or removed by approval.
