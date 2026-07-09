# Re-DocRED 数据集适配与完整流程改造设计文档

本文档基于当前 `EvidenceKG-Reasoner` 仓库现状，设计一条面向 Re-DocRED 的文档级多关系证据推理流程。Re-DocRED 是后续主研究和主开发方向；旧 enterprise asset hidden edge recovery pipeline 暂时保留为 legacy/reference，只用于理解第一版流程和借鉴少量工具代码，不作为新 pipeline 的长期并行主线或强兼容目标。

目标任务：

给定一篇 Re-DocRED 文档 `D`、head entity `h`、tail entity `t`、candidate relation `r`，系统判断候选三元组 `(h, r, t)` 是否被文档支持，并尽可能返回支持该判断的 evidence sentences。输出结构包括 `decision = accept | reject | uncertain`、`supporting_evidence_ids`、`reason`、`confidence`、`risk` 等字段。

## 一、当前项目现状梳理

### 1.1 当前主流程

当前项目是一个 EvidenceKG-Reasoner 原型，主线流程由 `PipelineRunner` 串联，面向企业资产/IT 资产 KG 的 hidden edge recovery：

1. 从 `data/sample` 或 `data/processed` 加载 `entities.jsonl`、`triples.jsonl`、`evidence.jsonl`。
2. 根据配置中的单个 `target_relation` 和实体类型约束生成候选关系。
3. 为每个候选关系检索图结构上下文和 evidence snippets。
4. 构造结构化 context 和 LLM prompt。
5. 使用 mock reasoner 或真实 LLM 判断候选关系。
6. 使用 verifier 检查 schema、evidence grounding、confidence、conflict。
7. 将通过校验的 accept 结果写成 predicted edges。
8. 对照 `gold_hidden_edges.jsonl` 做 hidden edge recovery evaluation。

主入口在：

- `scripts/run_pipeline.py`
- `src/evidencekg/pipeline/runner.py`

当前输出文件主要包括：

- `candidate_pairs.jsonl`
- `evidence_contexts.jsonl`
- `verified_predictions.jsonl`
- `predicted_edges.jsonl`
- `evaluation_report.json`
- `timing_report.jsonl`

### 1.2 当前核心模块

当前核心模块和文件位置如下。

| 模块 | 主要文件 | 当前职责 |
| --- | --- | --- |
| 数据构建 | `src/evidencekg/data/dataset_builder.py` | 从企业资产 CSV 构造 entities、triples、evidence、gold hidden edges |
| 数据配置 | `configs/dataset_manifest.yaml` | 描述企业资产 CSV 表和字段映射 |
| 图存储 | `src/evidencekg/graph/graph_store.py` | 加载 JSONL，构建 NetworkX `MultiDiGraph`，提供实体、边、路径、邻居、evidence 查询 |
| 任务配置 | `src/evidencekg/config/task_config.py` | 定义单目标关系任务、候选规则、retrieval、LLM、verifier、evaluation 参数 |
| 候选生成 | `src/evidencekg/candidate/generator.py` | 针对一个 `target_relation` 生成候选 `(head, relation, tail)` |
| 多路候选雏形 | `src/evidencekg/candidate/multi_route_generator.py` 等 | 基于 `RelationSpec` 的多关系候选生成雏形 |
| 证据检索 | `src/evidencekg/retrieval/evidence_retriever.py` | 当前版本支持 keyword-only 或 dense rerank 形态，为候选返回 evidence context |
| Prompt | `src/evidencekg/prompting/prompt_builder.py` | 将 evidence context 转成结构化 context 和 JSON-only prompt |
| Reasoner | `src/evidencekg/llm/reasoner.py` | 包含 `MockReasoner`、`RealLLMReasoner`、较新的 `LLMReasoner` |
| LLM client | `src/evidencekg/llm/*.py` | OpenAI-compatible、本地、Anthropic、mock client |
| Verifier | `src/evidencekg/verify/verifier.py` | 校验 schema、evidence grounding、confidence、conflict；另有 `HardVerifier`、`SemanticVerifier` 雏形 |
| 评测 | `src/evidencekg/eval/evaluator.py` | 计算 hidden edge recovery precision、recall、F1、verifier 通过率等 |
| 写回 | `src/evidencekg/writeback.py` | 将 verified accepted edges 写入 pending 或 enriched KG |

### 1.3 当前任务假设

当前项目默认假设是：

1. 输入是一个企业资产 KG，而不是自然语言文档集合。
2. 全局图已经存在，实体、边、evidence 都是独立 JSONL 文件。
3. 任务通常只有一个目标关系，例如 `likely_owned_by`。
4. 候选生成先按实体类型枚举 head/tail，再用路径、共同邻居、evidence overlap 过滤。
5. gold 是被隐藏的 KG 边，存储在 `gold_hidden_edges.jsonl`。
6. evidence 是 ticket、alert、DNS、CMDB 等业务证据片段，不是按句子切分的文档。
7. evaluation 的基本单位是最终补全的边 `(head, relation, tail)`。
8. verifier 只要求 accept 结果引用当前 context 中的 evidence id，并不深判 evidence 是否完整表达关系。

### 1.4 与 Re-DocRED 不兼容的地方

当前项目与 Re-DocRED 的主要不兼容点如下。

| 当前假设 | Re-DocRED 需求 | 不兼容点 |
| --- | --- | --- |
| 单个 `target_relation` | 多关系 label set | 需要支持每个 candidate 拥有自己的 relation |
| 企业资产实体类型 | DocRED/Re-DocRED 实体通常是 `PER`、`ORG`、`LOC`、`TIME`、`NUM`、`MISC` 等 | 现有 schema filter 不适用 |
| evidence 是业务片段 | evidence 应该是 sentence 级文本 | 需要 sentence evidence builder |
| 全局 KG hidden edge recovery | 每篇文档内判断实体对关系 | 需要 document-local KG |
| 候选来自图路径/共同邻居 | 候选来自 gold labels、entity pair、relation label、negative sampling | 现有候选生成规则需要替换 |
| graph path 反映企业拓扑 | graph context 来自文档结构、mention co-occurrence、sentence bridge | 路径含义变化 |
| `gold_hidden_edges.jsonl` | gold labels 在每篇文档内 | 需要文档级 gold triples 和 evidence labels |
| verifier 只查 evidence id 和 related entities | 需要判断 evidence sentence 是否能支持候选关系 | 需要 evidence sufficiency verifier |
| evaluator 只算 relation P/R/F1 | 还应算 evidence P/R/F1、top-k evidence recall、coverage/risk | 评测模块需要扩展 |

## 二、Re-DocRED 任务重新定义

### 2.1 Re-DocRED 字段到当前系统的映射

Re-DocRED 继承 DocRED 的文档级关系抽取数据形态，常见原始字段包括：

- `title`: 文档标题。
- `sents`: 文档句子列表，通常是二维 token list，例如 `List[List[str]]`。
- `vertexSet`: 实体集合，每个实体包含多个 mention，每个 mention 通常有 `name`、`sent_id`、`pos`、`type` 等字段。
- `labels`: 文档内标注关系，每条 label 通常包括 `h`、`t`、`r`、`evidence` 等字段。
- `h` / `t`: head/tail entity 在 `vertexSet` 中的索引。
- `r`: relation label，例如 Wikidata property id 或数据集定义的 relation id。
- `evidence`: 支持该关系的 sentence index 列表。

建议映射如下。

| Re-DocRED 概念 | 当前系统内部概念 | 建议 ID |
| --- | --- | --- |
| document | Document node / document record | `doc_{split}_{doc_index}` 或稳定 title hash |
| sentence | evidence record + Sentence node | `sent_{doc_id}_{sent_id}` |
| entity | entity record + Entity node | `ent_{doc_id}_{entity_index}` |
| mention | Mention node / entity metadata | `men_{doc_id}_{entity_index}_{mention_index}` |
| relation label | candidate relation / gold relation | 原始 `r`，另附 `relation_name`、`description` |
| evidence sentence | `supporting_evidence_ids` 的候选集合 | sentence evidence id |
| label `(h,r,t)` | gold triple / positive candidate | `gold_{doc_id}_{label_index}` |

### 2.2 新任务性质

Re-DocRED 可以被拆成三个相关但不同的任务：

1. **Triple verification**  
   输入文档、一个实体对和一个候选关系，判断 `(h, r, t)` 是否被文档支持。

2. **Document-level relation extraction**  
   输入整篇文档，输出所有被文档支持的实体对关系集合。

3. **Evidence-aware relation reasoning**  
   在 triple verification 或 relation extraction 基础上，额外要求给出支持判断的 evidence sentences，并对证据充分性进行约束。

本项目第一阶段建议采用：

**evidence-aware triple verification**。

原因：

1. 它与当前 pipeline 的 candidate-by-candidate 结构最接近，可以复用 `candidate -> evidence_context -> prompt -> reasoner -> verifier -> evaluator` 的骨架。
2. 它避免一开始要求 LLM 直接从全文中抽取所有关系，降低 prompt 长度、输出解析和召回评测复杂度。
3. 它能突出当前项目的核心卖点：对每个候选三元组做 evidence retrieval、graph context construction、LLM judgment 和 verifier risk control。
4. 它可以自然扩展到 document-level relation extraction：先生成候选，再对每个候选做 verification，最终聚合 accept 结果。

因此，第一版任务定义为：

```text
Input:
  document D
  head entity h
  tail entity t
  candidate relation r
  retrieved evidence sentences E_k
  local graph context G_k

Output:
  decision: accept | reject | uncertain
  confidence: float in [0, 1]
  risk: low | medium | high
  reason: short evidence-grounded explanation
  supporting_evidence_ids: sentence evidence ids selected from E_k
  conflict_evidence_ids: optional sentence evidence ids selected from E_k
```

## 三、数据适配设计

### 3.1 Re-DocRED 原始字段预期

适配器应先兼容 DocRED/Re-DocRED 常见 JSON 格式：

```json
{
  "title": "Document title",
  "sents": [
    ["Token", "Token"],
    ["Another", "sentence"]
  ],
  "vertexSet": [
    [
      {
        "name": "Entity name",
        "sent_id": 0,
        "pos": [0, 2],
        "type": "ORG"
      }
    ]
  ],
  "labels": [
    {
      "h": 0,
      "t": 1,
      "r": "P17",
      "evidence": [0, 2]
    }
  ]
}
```

需要注意：

- 不同发布版本可能存在字段差异，应在 Stage 1 先用数据字段检查脚本输出 schema summary。
- `sents` 可能是 token list，需要 join 成 sentence text。
- `evidence` 可能缺失、为空或不完整，不能把 absence 直接当作没有证据。
- relation id 需要配套 relation metadata，包括自然语言名称、描述、head/tail 类型约束或 prompt guidance。

### 3.2 内部统一格式

建议新增一套 Re-DocRED processed 数据目录，例如：

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

`test` split 如果官方不提供 labels，则只做推理输出，不反复用于调参。

### 3.3 `documents.jsonl`

每行一篇文档：

```json
{
  "doc_id": "redocred_dev_000001",
  "title": "Document title",
  "split": "dev",
  "sentence_ids": [
    "sent_redocred_dev_000001_000",
    "sent_redocred_dev_000001_001"
  ],
  "entity_ids": [
    "ent_redocred_dev_000001_000",
    "ent_redocred_dev_000001_001"
  ],
  "raw_doc_index": 1,
  "metadata": {
    "source": "Re-DocRED",
    "sentence_count": 12,
    "entity_count": 8
  }
}
```

用途：

- 作为每篇文档 local KG 的根节点。
- 作为按文档运行 pipeline 的基本索引。
- 便于后续统计文档长度、实体数、候选数。

### 3.4 `entities.jsonl`

每行一个文档内实体：

```json
{
  "id": "ent_redocred_dev_000001_000",
  "doc_id": "redocred_dev_000001",
  "local_entity_index": 0,
  "type": "ORG",
  "name": "Entity canonical name",
  "aliases": ["Alias A", "Alias B"],
  "mentions": [
    {
      "mention_id": "men_redocred_dev_000001_000_000",
      "name": "Entity canonical name",
      "sent_id": 0,
      "sentence_id": "sent_redocred_dev_000001_000",
      "pos": [0, 2],
      "type": "ORG"
    }
  ],
  "properties": {
    "source": "vertexSet",
    "mention_count": 1
  }
}
```

与当前 `GraphStore.load_entities()` 兼容时，要保留当前要求字段：

- `id`
- `type`
- `name`
- `aliases`
- `properties`

Re-DocRED 专用字段如 `doc_id`、`local_entity_index`、`mentions` 可以作为额外字段保留。

### 3.5 `evidence.jsonl`

第一版证据单元采用 sentence，每行一个 sentence：

```json
{
  "id": "sent_redocred_dev_000001_000",
  "doc_id": "redocred_dev_000001",
  "sent_id": 0,
  "source": "redocred_sentence",
  "source_file": "dev_revised.json",
  "source_row_id": "redocred_dev_000001:0",
  "text": "Sentence text after joining tokens.",
  "tokens": ["Sentence", "text"],
  "related_entities": [
    "ent_redocred_dev_000001_000",
    "ent_redocred_dev_000001_002"
  ],
  "mention_ids": [
    "men_redocred_dev_000001_000_000"
  ],
  "timestamp": "",
  "reliability": 1.0,
  "metadata": {
    "title": "Document title",
    "sentence_index": 0
  }
}
```

与当前 `GraphStore.load_evidence()` 兼容时，要保留当前要求字段：

- `id`
- `source`
- `source_file`
- `source_row_id`
- `text`
- `related_entities`
- `timestamp`
- `reliability`
- `metadata`

### 3.6 `gold_triples.jsonl`

每行一个正样本关系：

```json
{
  "gold_id": "gold_redocred_dev_000001_000",
  "doc_id": "redocred_dev_000001",
  "head": "ent_redocred_dev_000001_000",
  "head_index": 0,
  "relation": "P17",
  "relation_name": "country",
  "tail": "ent_redocred_dev_000001_001",
  "tail_index": 1,
  "evidence_ids": [
    "sent_redocred_dev_000001_000",
    "sent_redocred_dev_000001_002"
  ],
  "source": "redocred_label",
  "metadata": {
    "raw_label_index": 0
  }
}
```

这个文件替代当前 hidden edge recovery 中的 `gold_hidden_edges.jsonl`，但为了复用 evaluator，也可以在 Re-DocRED runner 中接受一个 `gold_file` 配置。

### 3.7 `candidates.jsonl`

每行一个候选 triple verification 样本：

```json
{
  "candidate_id": "cand_redocred_dev_000001_000001",
  "doc_id": "redocred_dev_000001",
  "head": "ent_redocred_dev_000001_000",
  "head_index": 0,
  "relation": "P17",
  "relation_name": "country",
  "tail": "ent_redocred_dev_000001_001",
  "tail_index": 1,
  "label": "positive",
  "gold": true,
  "gold_evidence_ids": [
    "sent_redocred_dev_000001_000"
  ],
  "negative_type": "",
  "generation_rules": [
    "gold_label"
  ],
  "candidate_score": 1.0,
  "metadata": {
    "head_name": "Head name",
    "tail_name": "Tail name"
  }
}
```

负样本示例：

```json
{
  "candidate_id": "cand_redocred_dev_000001_000123",
  "doc_id": "redocred_dev_000001",
  "head": "ent_redocred_dev_000001_000",
  "relation": "P17",
  "tail": "ent_redocred_dev_000001_003",
  "label": "negative",
  "gold": false,
  "gold_evidence_ids": [],
  "negative_type": "same_head_relation_wrong_tail",
  "generation_rules": [
    "hard_negative_same_head_relation"
  ],
  "candidate_score": 0.4
}
```

### 3.8 正样本、负样本和 hard negative

正样本：

- 直接来自 `labels`。
- 每条 label 生成一个 positive candidate。
- `gold_evidence_ids` 来自 `label.evidence` 对应的 sentence ids。

普通负样本：

- 同一文档内随机实体对 `(h, t)`，选择某个 relation `r`，只要 `(h, r, t)` 不在 gold labels 中。
- 控制负样本比例，例如每个正样本采样 `1-3` 个负样本。

Hard negative：

1. **same entity pair, wrong relation**  
   `(h, r_wrong, t)`，实体对正确但关系错误。

2. **same head and relation, wrong tail**  
   `(h, r, t_wrong)`，head 和 relation 正确但 tail 错。

3. **same tail and relation, wrong head**  
   `(h_wrong, r, t)`，tail 和 relation 正确但 head 错。

4. **co-mentioned but unlabeled pair**  
   head 和 tail 在同一句或相邻句出现，但没有 gold relation。

5. **same type compatible negative**  
   根据 relation schema，head/tail 类型看似合法，但文档不支持。

负样本处理原则：

- 不要把未标注的所有 entity pair 都当负样本，因为即使 Re-DocRED 修复了大量漏标，也不能保证完全没有缺漏。
- dev/test 评测时应明确负样本构造策略，否则 relation precision/recall 的含义会受候选集影响。
- 第一版以 “gold positives + controlled negatives” 做 triple verification，后续再扩展到 full candidate generation。

### 3.9 evidence 字段不完整时的降级

如果某条 gold label 缺少 `evidence` 或 evidence 为空：

1. `gold_evidence_ids` 置为空列表。
2. `evidence_annotation_status` 设为 `missing` 或 `empty`。
3. 关系 P/R/F1 仍可计算。
4. evidence P/R/F1 不纳入该样本，或单独统计为 `evidence_gold_missing_count`。
5. 训练/调试 retrieval 时，可以把包含 head/tail mention 的句子作为 silver evidence，但必须标记为：

```json
{
  "evidence_source": "silver_mention_overlap",
  "is_gold_evidence": false
}
```

降级优先级：

1. gold evidence sentences。
2. 同时包含 head 和 tail mention 的 sentences。
3. 包含 head 或 tail mention 且与 relation description 相似的 sentences。
4. 文档 title 和全文摘要作为弱上下文，只用于 reasoner，不作为 gold evidence。

## 四、文档级局部 KG 构建设计

### 4.1 每篇文档构造成一个 local KG

Re-DocRED 不应先合并成一个跨文档全局 KG。第一版建议每篇文档独立构造 local KG：

```text
Document
  -> Sentence
  -> Entity
  -> Mention
  -> CandidateTriple
```

这样做的好处：

- 与任务定义一致：关系是否成立只由当前文档支持。
- 避免 LLM 使用跨文档或常识信息污染判断。
- 可以将 path、neighbor、co-occurrence 等 graph context 限制在文档内。
- 每篇文档图较小，NetworkX 足够，不需要 Neo4j 或 GNN。

### 4.2 节点类型

建议节点类型：

| 节点类型 | ID 示例 | 字段 |
| --- | --- | --- |
| Document | `doc_redocred_dev_000001` | title、split、sentence_count、entity_count |
| Sentence | `sent_redocred_dev_000001_000` | text、sent_id、tokens、related_entities |
| Entity | `ent_redocred_dev_000001_000` | name、type、aliases、mentions |
| Mention | `men_redocred_dev_000001_000_000` | name、sent_id、pos、entity_id |
| CandidateTriple | `cand_redocred_dev_000001_000001` | head、relation、tail、label、score |

### 4.3 边类型

建议边类型：

| 边类型 | 方向 | 含义 |
| --- | --- | --- |
| `contains_sentence` | Document -> Sentence | 文档包含句子 |
| `contains_entity` | Document -> Entity | 文档包含实体 |
| `has_mention` | Entity -> Mention | 实体包含 mention |
| `mentioned_in` | Mention -> Sentence | mention 出现在句子中 |
| `entity_mentioned_in` | Entity -> Sentence | 实体在句子中出现 |
| `cooccur_with` | Entity -> Entity | 两实体在同一句或相邻句共现 |
| `candidate_head` | CandidateTriple -> Entity | candidate 的 head |
| `candidate_tail` | CandidateTriple -> Entity | candidate 的 tail |
| `candidate_relation` | CandidateTriple -> relation literal | candidate 的 relation |
| `gold_relation` | Entity -> Entity | gold label 对应的真实关系 |
| `supports_candidate` | Sentence -> CandidateTriple | gold 或检索认为句子支持 candidate |
| `conflicts_candidate` | Sentence -> CandidateTriple | 可选，句子包含否定或冲突信号 |

### 4.4 local KG 如何服务 graph retriever

Graph retriever 可从 local KG 提取：

- head mention sentences。
- tail mention sentences。
- 同时包含 head 和 tail 的 common sentences。
- head/tail 相邻句中的 bridge entities。
- head -> sentence -> tail 的共现路径。
- head -> sentence -> bridge entity -> sentence -> tail 的桥接路径。
- 已知 gold relations 或已接受 relations 的局部关系上下文，仅限 train/dev 分析时使用；正式推理时不能泄露当前 candidate 的 gold label。

### 4.5 local KG 如何服务 verifier

Verifier 可利用 local KG 做以下检查：

- 引用的 evidence id 是否属于当前 `doc_id`。
- evidence sentence 是否在当前 candidate 的 retrieved context 中。
- evidence sentence 是否包含 head 或 tail mention。
- accept 时是否至少有一个 evidence sentence 同时包含 head 和 tail，或存在可解释的 bridge path。
- quoted evidence 是否和 candidate relation 的 direction 一致。
- 同一实体对是否出现互斥关系或方向冲突。

## 五、候选关系生成设计

### 5.1 正样本来源

正样本直接来自 Re-DocRED `labels`：

```text
label.h -> vertexSet[h] -> head entity
label.t -> vertexSet[t] -> tail entity
label.r -> relation
label.evidence -> gold evidence sentence ids
```

每条 label 生成一个 candidate：

- `label = positive`
- `gold = true`
- `generation_rules = ["gold_label"]`
- `candidate_score = 1.0`

### 5.2 负样本采样

第一版不建议对所有 `entity pair × relation` 全展开。推荐控制负样本数量：

```text
for each document:
  positives = gold labels
  negatives = sample(
    same_pair_wrong_relation,
    same_head_relation_wrong_tail,
    same_tail_relation_wrong_head,
    co_mentioned_unlabeled_pair,
    random_type_compatible_pair
  )
  keep negative_count <= positive_count * negative_ratio
```

建议初始参数：

- train/debug: `negative_ratio = 1` 或 `2`
- dev small: 每篇文档最多 `20-50` 个 candidate
- dev full: 每篇文档最多 `100-200` 个 candidate

### 5.3 hard negative 构造

Hard negative 是本任务的重点，因为 LLM 很容易根据实体名或常识过度 accept。

构造策略：

1. 对每个 positive `(h, r, t)`，在同一文档内采样一个 `t_wrong`，生成 `(h, r, t_wrong)`。
2. 对每个 positive `(h, r, t)`，采样一个 relation `r_wrong`，生成 `(h, r_wrong, t)`。
3. 对共现实体对 `(e_i, e_j)`，如果没有 gold relation，则采样若干高频 relation 作为 hard negative。
4. 对同类型实体 pair 采样容易混淆的 relation，例如地点类关系、组织隶属关系、人物出生/死亡/国籍等。

每个 hard negative 应记录：

- `negative_type`
- `generation_rules`
- `source_positive_candidate_id`，如果由某个 positive 派生
- `hardness_score`

### 5.4 是否全展开

第一阶段不建议全展开 `all entity pairs × all relation labels`。

原因：

- 候选数量会随文档实体数和关系数急剧膨胀。
- 大量 trivially negative 会让 relation precision 看似高，但不利于检验 evidence reasoning。
- LLM 成本不可控。
- Re-DocRED 仍可能有少量未标注关系，把所有 unlabeled 当负会引入噪声。

可以在后续阶段做 full extraction setting：

1. 使用规则/模型先召回 top-N candidates。
2. 对 top-N 做 triple verification。
3. 最终聚合 accept triples。

### 5.5 第一阶段候选数量控制

建议策略：

- 每篇文档保留全部 positives。
- 每个 positive 生成 `1-2` 个 hard negatives。
- 每篇文档额外采样少量 co-mention negatives。
- 设置文档级上限，例如 `max_candidates_per_doc = 64`。
- 设置 relation 级上限，避免高频关系垄断。
- 输出 candidate 统计报告：positive_count、negative_count、hard_negative_count、avg_candidates_per_doc。

### 5.6 candidate 字段

候选字段建议：

```json
{
  "candidate_id": "cand_redocred_dev_000001_000001",
  "doc_id": "redocred_dev_000001",
  "head": "ent_redocred_dev_000001_000",
  "head_index": 0,
  "head_name": "Head name",
  "head_type": "ORG",
  "relation": "P17",
  "relation_name": "country",
  "relation_description": "country associated with this entity",
  "tail": "ent_redocred_dev_000001_001",
  "tail_index": 1,
  "tail_name": "Tail name",
  "tail_type": "LOC",
  "label": "positive",
  "gold": true,
  "gold_evidence_ids": ["sent_redocred_dev_000001_000"],
  "generation_rules": ["gold_label"],
  "negative_type": "",
  "candidate_score": 1.0,
  "metadata": {
    "split": "dev",
    "title": "Document title"
  }
}
```

## 六、Evidence Retrieval 设计

### 6.1 证据单元

第一版证据单元采用 sentence。

原因：

- Re-DocRED 的 evidence annotation 通常就是 sentence index。
- sentence 粒度利于 verifier 做 grounding。
- prompt 更可控，不需要传整篇长文。
- evidence precision/recall 可以直接对齐 gold sentence ids。

每个 sentence evidence 必须有稳定 ID：

```text
sent_{doc_id}_{sent_id:03d}
```

### 6.2 每个 candidate 的检索目标

对 candidate `(h, r, t)`，检索 top-k evidence sentences：

1. 优先找同时包含 head mention 和 tail mention 的句子。
2. 其次找包含 head 或 tail mention，且 relation description/token 相似的句子。
3. 再找相邻句或 bridge entity 连接的句子。
4. 对可能冲突的句子单独标记。

输出：

- `evidence_snippets`: top-k 证据候选。
- `supporting_evidence_candidates`: 倾向支持的句子。
- `conflict_evidence_candidates`: 倾向冲突或否定的句子。
- `retrieval_metadata`: 检索模式、top-k、分数、降级原因。

### 6.3 第一版简单有效特征

第一版建议不用复杂模型，先实现可解释检索：

1. **mention overlap**
   - sentence 包含 head mention: `+1.0`
   - sentence 包含 tail mention: `+1.0`
   - 同时包含 head 和 tail: 额外 `+1.0`

2. **relation description similarity**
   - relation name、description、aliases 与 sentence token overlap。
   - 可用 TF-IDF cosine 或简单 token Jaccard。

3. **sentence distance**
   - head mention sentence 和 tail mention sentence 相同: 高分。
   - 相邻句: 中等分。
   - 距离越远分数越低。

4. **bridge entity**
   - head sentence 和 tail sentence 共享其他 entity。
   - 或存在 `head -> sentence -> bridge -> sentence -> tail`。

5. **BM25/TF-IDF**
   - query = head name + relation description + tail name。
   - corpus = 当前文档 sentences。
   - 作为文本相关性分。

6. **gold leakage guard**
   - dev/test 正式推理时 retrieval 不能直接读取 `gold_evidence_ids`。
   - 只能在 evaluation 时对比 gold evidence。

### 6.4 后续升级为 bi-encoder + cross-encoder

当前 `EvidenceRetriever` 已有 bi-encoder 和 cross-encoder 相关雏形，但 Re-DocRED 应改成 document-local corpus：

1. bi-encoder recall：
   - query: `head name [HEAD_TYPE], relation name/description, tail name [TAIL_TYPE]`
   - corpus: 当前文档所有 sentence text，附带 mention entity names。
   - top-k before rerank: `20-30`

2. cross-encoder rerank：
   - pair: `(candidate query, sentence text)`
   - top-k after rerank: `5-8`

3. rerank 特征融合：
   - dense score
   - cross-encoder score
   - mention overlap score
   - sentence distance score

4. 训练后续版本：
   - 如果有 gold evidence，可构造 sentence-level support classifier。
   - 但第一版先不训练模型，避免扩大工程范围。

### 6.5 `evidence_contexts.jsonl` 输出格式

建议格式：

```json
{
  "candidate_id": "cand_redocred_dev_000001_000001",
  "doc_id": "redocred_dev_000001",
  "candidate": {
    "head": "ent_redocred_dev_000001_000",
    "head_name": "Head name",
    "relation": "P17",
    "relation_name": "country",
    "tail": "ent_redocred_dev_000001_001",
    "tail_name": "Tail name",
    "candidate_score": 1.0
  },
  "document": {
    "title": "Document title",
    "sentence_count": 12
  },
  "relation_query": "Head name country Tail name ...",
  "retrieval_metadata": {
    "mode": "mention_tfidf",
    "top_k": 8,
    "degraded": false,
    "gold_evidence_used": false
  },
  "evidence_snippets": [
    {
      "evidence_id": "sent_redocred_dev_000001_000",
      "sent_id": 0,
      "text": "Sentence text.",
      "related_entities": [
        "ent_redocred_dev_000001_000",
        "ent_redocred_dev_000001_001"
      ],
      "contains_head": true,
      "contains_tail": true,
      "retrieval_score": 3.4,
      "retrieval_reasons": [
        "contains_head",
        "contains_tail",
        "relation_token_overlap"
      ]
    }
  ],
  "supporting_evidence_candidates": [],
  "conflict_evidence_candidates": []
}
```

## 七、Graph Context Retrieval 设计

### 7.1 每个 candidate 提取的 graph context

对 `(h, r, t)` 提取以下图上下文：

1. **head profile**
   - name、type、aliases、mentions、mention sentence ids。

2. **tail profile**
   - name、type、aliases、mentions、mention sentence ids。

3. **head mention sentences**
   - 包含 head mention 的句子列表。

4. **tail mention sentences**
   - 包含 tail mention 的句子列表。

5. **common sentences**
   - 同时包含 head 和 tail 的句子。

6. **neighbor sentences**
   - head/tail mention 所在句子的前后窗口，例如 `window = 1`。

7. **bridge entities**
   - 在 head/tail 相关句子之间反复出现的实体。
   - 与 head 或 tail 同句共现且连接另一端的实体。

8. **co-occurrence paths**
   - `head -> sentence -> tail`
   - `head -> sentence -> bridge_entity -> sentence -> tail`

9. **known local relations**
   - 当前文档中已接受或已知的其他关系，用于后续多轮推理。
   - 第一版正式评测时不要把 gold labels 注入 context，避免泄露。

### 7.2 graph context 和 evidence sentences 的组合

Prompt 中建议分开呈现：

```json
{
  "candidate": {},
  "relation_definition": {},
  "retrieved_evidence_sentences": [],
  "graph_context": {
    "head_profile": {},
    "tail_profile": {},
    "head_mention_sentences": [],
    "tail_mention_sentences": [],
    "common_sentences": [],
    "bridge_entities": [],
    "cooccurrence_paths": []
  }
}
```

规则：

- `retrieved_evidence_sentences` 是 LLM 可引用的 evidence id 池。
- `graph_context` 帮助 LLM 理解文档内实体分布，但 accept 时仍必须引用 evidence sentence。
- 如果 graph context 包含 sentence text，应使用同一 evidence id，避免 LLM 引用不可验证文本。

### 7.3 graph context 输出格式

建议在 `evidence_contexts.jsonl` 中增加：

```json
{
  "graph_context": {
    "head_profile": {
      "entity_id": "ent_x_0",
      "name": "Head",
      "type": "ORG",
      "mention_sentence_ids": ["sent_x_0", "sent_x_3"]
    },
    "tail_profile": {
      "entity_id": "ent_x_1",
      "name": "Tail",
      "type": "LOC",
      "mention_sentence_ids": ["sent_x_0"]
    },
    "common_sentence_ids": ["sent_x_0"],
    "bridge_entities": [
      {
        "entity_id": "ent_x_4",
        "name": "Bridge",
        "type": "PER",
        "path": ["ent_x_0", "sent_x_2", "ent_x_4", "sent_x_5", "ent_x_1"]
      }
    ],
    "cooccurrence_paths": [
      {
        "path_type": "same_sentence",
        "nodes": ["ent_x_0", "sent_x_0", "ent_x_1"]
      }
    ]
  }
}
```

## 八、Prompt / Reasoner 改造设计

### 8.1 当前 prompt/reasoner 与新任务差异

当前 `PromptBuilder` 的 prompt 是：

- 面向企业资产 KG。
- 默认判断一个候选 enterprise asset relation。
- relation 语义来自 `candidate['relation']` 和 context，不包含完整 relation definition。
- evidence snippets 是业务证据片段，不是 sentence id。
- 输出 schema 只有 `decision`、`confidence`、`reason`、`supporting_evidence_ids`。

Re-DocRED prompt 需要：

- 面向文档级关系判断。
- 支持多 relation。
- 包含 relation label 的自然语言定义和方向说明。
- 明确禁止基于常识、Wikipedia 背景知识或实体名猜测。
- 强制 evidence ids 必须来自当前文档的 retrieved sentence ids。
- 输出 evidence analysis，便于 verifier 检查证据充分性。

### 8.2 Re-DocRED prompt 组成

建议 prompt 包含以下部分：

1. **System instruction**
   - 严格 JSON-only。
   - 只基于给定文档证据判断。
   - 不允许使用外部知识。
   - accept 必须引用至少一个 evidence sentence id。

2. **Task definition**
   - 判断 candidate triple 是否被当前 document 支持。
   - relation 是有方向的：`head -> relation -> tail`。

3. **Candidate**
   - head id/name/type/aliases。
   - relation id/name/description。
   - tail id/name/type/aliases。

4. **Allowed evidence ids**
   - 明确列出 LLM 可以引用的 evidence sentence ids。

5. **Retrieved evidence sentences**
   - sentence id、sent_id、text、contains_head、contains_tail、retrieval_reasons。

6. **Graph context**
   - common sentences。
   - mention sentence ids。
   - bridge entities。
   - co-occurrence paths。

7. **Output schema**
   - 严格 JSON schema。

### 8.3 LLM 输出 JSON schema

建议 schema：

```json
{
  "decision": "accept | reject | uncertain",
  "confidence": 0.0,
  "risk": "low | medium | high",
  "relation": "P17",
  "reason": "short evidence-grounded explanation",
  "supporting_evidence_ids": [],
  "conflict_evidence_ids": [],
  "evidence_analysis": [
    {
      "evidence_id": "sent_redocred_dev_000001_000",
      "support_label": "strong_support | weak_support | irrelevant | conflict",
      "mentions_head": true,
      "mentions_tail": true,
      "explanation": "why this sentence supports or does not support the candidate"
    }
  ]
}
```

规范化规则：

- 非法 `decision` 归一成 `uncertain`。
- `confidence` clamp 到 `[0, 1]`。
- `risk` 缺失时根据 confidence 和 verifier 结果推断。
- `supporting_evidence_ids` 非 list 时置空。
- 未出现在 allowed evidence ids 中的 evidence id 直接删除或由 verifier fail。

### 8.4 强制只基于文档证据判断

Prompt 约束：

```text
Use only the provided document sentences and graph context.
Do not use world knowledge, entity popularity, Wikidata facts, or assumptions from entity names.
If the evidence does not explicitly or strongly imply the relation, choose uncertain or reject.
Accept requires at least one supporting_evidence_id selected from allowed evidence ids.
```

Verifier 约束：

- accept 无 evidence id，降为 reject 或 uncertain。
- evidence id 不在当前 context，fail。
- evidence id 不属于当前 doc，fail。
- evidence sentence 不包含 head/tail，也没有 bridge path，降为 uncertain。
- reason 中如果出现 “generally known”、“according to common knowledge” 等措辞，可标记高风险。

### 8.5 accept / reject / uncertain 处理

建议定义：

- `accept`: 当前文档证据明确或强烈支持 `(h, r, t)`，且至少一个 evidence sentence 可引用。
- `reject`: 当前文档证据明确不支持该关系，或存在明显冲突，或候选与文档表达相反。
- `uncertain`: 证据不足、只出现实体共现、relation 语义不明确、检索上下文缺失、LLM 输出不稳定。

工程上：

- `accept` 且 verifier passed 才写入 `predicted_triples.jsonl`。
- `reject` 和 `uncertain` 都保留在 `verified_predictions.jsonl`，用于分析风险和 coverage。
- 在开放抽取场景中，`uncertain` 不计入预测边。

## 九、Verifier 改造设计

### 9.1 当前 verifier 可复用逻辑

当前 `Verifier` 可复用的思想：

- 统一接收 candidate、context、prediction、config、graph。
- 只允许 LLM 引用当前 context 中的 evidence id。
- accept 必须满足 confidence threshold。
- 输出 `verifier_status` 和 `verifier_details`。
- 维护 accepted key，避免重复 accept。

当前 `HardVerifier` 和 `SemanticVerifier` 的雏形也可借鉴：

- `HardVerifier` 更接近 schema、decision、confidence、evidence id 检查。
- `SemanticVerifier` 已有 evidence support status 的接口思想，但其 relation words 是企业资产关系硬编码，Re-DocRED 需要 relation metadata 驱动。

### 9.2 新 verifier 子模块

建议新增 Re-DocRED 专用 verifier，由多个子检查组成。

#### 9.2.1 Schema verifier

输入：

- candidate
- relation metadata
- entity metadata

检查：

- `prediction.relation` 是否等于 `candidate.relation`。
- `decision` 是否在合法集合中。
- head/tail 是否属于当前 doc。
- head/tail 是否不同。
- 如果 relation metadata 有 allowed type pairs，检查 head/tail type 是否兼容。

输出：

```json
{
  "schema": {
    "passed": true,
    "relation_match": true,
    "entity_in_doc": true,
    "type_compatible": true,
    "message": ""
  }
}
```

第一版可以规则实现。

#### 9.2.2 Evidence grounding verifier

输入：

- context allowed evidence ids
- prediction supporting/conflict evidence ids
- document id

检查：

- accept 是否至少有一个 supporting evidence id。
- 所有 cited evidence ids 是否出现在当前 retrieved context。
- 所有 cited evidence ids 是否属于当前 doc。
- cited evidence ids 是否去重。

输出：

```json
{
  "evidence_grounding": {
    "passed": true,
    "invalid_evidence_ids": [],
    "out_of_doc_evidence_ids": [],
    "accept_has_evidence": true
  }
}
```

第一版必须规则实现。

#### 9.2.3 Evidence sufficiency verifier

输入：

- candidate
- cited evidence sentences
- entity mentions
- graph context
- relation metadata
- optional LLM evidence_analysis

检查：

- 至少一个 cited sentence 是否包含 head 或 tail。
- 更严格地，至少一个 cited sentence 同时包含 head 和 tail，或多句证据通过 bridge entity/path 连接。
- cited sentence 是否包含与 relation description 相关的触发词或语义线索。
- LLM 的 `evidence_analysis` 是否把 cited evidence 标为 `strong_support` 或 `weak_support`。

输出：

```json
{
  "evidence_sufficiency": {
    "status": "sufficient | weak | insufficient",
    "passed": true,
    "strong_evidence_ids": [],
    "weak_evidence_ids": [],
    "message": ""
  }
}
```

第一版实现：

- 规则版：mention overlap + relation token overlap + bridge path。
- 后续优化：sentence-level NLI / cross-encoder support classifier。

#### 9.2.4 Conflict verifier

输入：

- candidate
- conflict evidence ids
- accepted predictions in same document
- relation metadata

检查：

- 同一 `(doc_id, head, relation, tail)` 是否重复 accept。
- 是否同时 accept 互斥关系。
- 是否 accept 了明显反方向关系，取决于 relation metadata。
- conflict evidence 是否被 LLM 忽略。

输出：

```json
{
  "conflict": {
    "passed": true,
    "duplicate_accept": false,
    "mutual_exclusion_violation": false,
    "reverse_direction_conflict": false,
    "message": ""
  }
}
```

第一版实现重复检查和基础方向检查即可。

#### 9.2.5 Uncertainty / abstention rule

输入：

- LLM decision
- confidence
- risk
- verifier sub-results

规则：

- accept + confidence < threshold -> uncertain。
- accept + evidence sufficiency weak -> uncertain。
- accept + evidence grounding fail -> reject 或 uncertain，建议 `uncertain` 用于缺证据，`reject` 用于非法引用。
- reasoner parse failure -> uncertain。
- retrieval empty -> uncertain。
- conflict high risk -> uncertain 或 reject。

输出：

```json
{
  "final_decision": "accept | reject | uncertain",
  "risk": "low | medium | high",
  "abstention_reason": ""
}
```

### 9.3 Re-DocRED verifier 总输出

建议 `verified_predictions.jsonl` 每行：

```json
{
  "prediction_id": "pred_000001",
  "candidate_id": "cand_redocred_dev_000001_000001",
  "doc_id": "redocred_dev_000001",
  "head": "ent_redocred_dev_000001_000",
  "relation": "P17",
  "tail": "ent_redocred_dev_000001_001",
  "decision": "accept",
  "raw_decision": "accept",
  "confidence": 0.86,
  "risk": "low",
  "reason": "The cited sentence states ...",
  "supporting_evidence_ids": ["sent_redocred_dev_000001_000"],
  "conflict_evidence_ids": [],
  "verifier_status": "passed",
  "verifier_details": {
    "schema": {},
    "evidence_grounding": {},
    "evidence_sufficiency": {},
    "conflict": {},
    "abstention": {}
  },
  "source": "real_llm_inference"
}
```

## 十、Evaluation 设计

### 10.1 主指标：relation precision / recall / F1

对最终 accepted 且 verifier passed 的 triples 计算：

```text
predicted_key = (doc_id, head, relation, tail)
gold_key = (doc_id, head, relation, tail)
```

指标：

- relation precision = hits / predicted_count
- relation recall = hits / gold_count
- relation F1 = 2PR / (P + R)

注意：

- 如果评测是在 controlled candidate set 上进行，recall 是 “在该候选集合上的 verification recall”。
- 如果要报告 document-level relation extraction recall，需要候选生成覆盖所有 gold triples，并统计 candidate recall。

### 10.2 证据指标

如果 gold evidence 可用：

- evidence precision:

```text
|predicted_supporting_evidence_ids ∩ gold_evidence_ids| / |predicted_supporting_evidence_ids|
```

- evidence recall:

```text
|predicted_supporting_evidence_ids ∩ gold_evidence_ids| / |gold_evidence_ids|
```

- evidence F1。
- top-k evidence recall:

```text
gold evidence 是否出现在 retrieved top-k evidence snippets 中
```

建议分别统计：

- retrieval evidence recall@k。
- final cited evidence precision/recall/F1。
- only-on-correct-relation evidence F1。
- all-accepted evidence F1。

如果 gold evidence 缺失：

- 不计算该样本 evidence P/R/F1。
- 记录 `evidence_gold_missing_count`。
- 可报告 silver evidence 命中率，但不能与 gold evidence metric 混用。

### 10.3 风险控制指标

建议新增：

| 指标 | 含义 |
| --- | --- |
| wrong accept rate | accepted 但不在 gold 中的比例 |
| uncertain rate | uncertain_count / candidate_count |
| coverage | accept_count / candidate_count，或非 uncertain 比例 |
| precision under coverage | 在不同 confidence threshold 下的 precision |
| verifier rejection rate | verifier 将 raw accept 降级的比例 |
| invalid evidence citation rate | LLM 引用非法 evidence id 的比例 |
| empty retrieval rate | evidence retriever 没有返回句子的比例 |
| evidence grounding fail rate | accept 时 grounding 失败比例 |

这些指标能体现 verifier/calibration 的价值，尤其适合论文或答辩中解释风险控制。

### 10.4 消融实验设计

建议消融：

1. **LLM-only**
   - 只给 candidate 和 relation definition，不给 evidence sentences。
   - 用来衡量常识/实体名猜测倾向。

2. **LLM + full document**
   - 给全文所有 sentences。
   - 检查长上下文和无检索的效果。

3. **LLM + retrieved evidence**
   - 只给 top-k evidence sentences。
   - 检查 evidence retrieval 的贡献。

4. **LLM + graph context**
   - 给 mention/co-occurrence/bridge context，但不强调 verifier。

5. **current EvidenceKG-style pipeline**
   - 使用当前 candidate -> evidence -> prompt -> verifier 骨架的直接迁移版本。

6. **ours with verifier/calibration**
   - 完整 Re-DocRED pipeline，包括 evidence sufficiency、conflict、uncertainty rules。

7. **w/o evidence sufficiency verifier**
   - 验证 evidence sufficiency 的贡献。

8. **w/o graph context**
   - 只用 evidence sentences，不用 local KG context。

9. **mention-only retrieval vs dense rerank**
   - 比较简单检索和 bi-encoder/cross-encoder。

### 10.5 baseline 设计

必备 baseline：

1. LLM-only。
2. LLM + full document。
3. LLM + retrieved evidence。
4. LLM + graph context。
5. current EvidenceKG-style pipeline。
6. Ours with verifier/calibration。

建议报告表：

| Method | Relation P | Relation R | Relation F1 | Evidence F1 | Wrong Accept | Uncertain | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LLM-only | | | | | | | |
| LLM + full document | | | | | | | |
| LLM + retrieved evidence | | | | | | | |
| LLM + graph context | | | | | | | |
| EvidenceKG-style | | | | | | | |
| Ours | | | | | | | |

## 十一、建议的代码改造路径

原则：

- 不一次性重构全部。
- 保留现有企业资产 KG pipeline。
- 新增 Re-DocRED 专用 adapter、runner、retriever、prompt、verifier、evaluator。
- 尽量复用通用工具，例如 JSONL IO、LLM client、reasoner JSON parsing、GraphStore 部分能力。

### Stage 1：检查 Re-DocRED 数据字段

目标：

- 确认实际下载版本的字段结构。
- 输出 schema summary。
- 确认是否有 `evidence` 字段、relation metadata 文件、train/dev/test split。

建议新增：

- `scripts/inspect_redocred.py`
- 可选输出 `outputs/redocred_schema_summary.json`

输入：

- raw Re-DocRED JSON files。

输出：

- 文档数、句子数、实体数、label 数。
- `labels` 字段样例。
- evidence 覆盖率。
- relation label 频次。

验收标准：

- 能打印并保存 schema summary。
- 明确 evidence 字段是否完整。
- 明确 relation id 到 name/description 的来源。

### Stage 2：实现 `redocred_adapter`

目标：

- 将 raw Re-DocRED 转换为内部 processed JSONL。

建议新增：

- `src/evidencekg/data/redocred_adapter.py`
- `scripts/build_redocred_dataset.py`
- `configs/redocred_dataset.yaml`

输入：

- raw train/dev/test JSON。
- relation metadata。

输出：

- `documents.jsonl`
- `entities.jsonl`
- `evidence.jsonl`
- `gold_triples.jsonl`

验收标准：

- JSONL 字段稳定。
- sentence evidence id 可由 `doc_id + sent_id` 复现。
- entity id 可由 `doc_id + vertexSet index` 复现。
- 所有 evidence `related_entities` 都能在 `entities.jsonl` 中找到。

### Stage 3：生成 candidates

目标：

- 从 gold labels 和负采样策略生成 controlled candidate set。

建议新增：

- `src/evidencekg/candidate/redocred_candidate_generator.py`
- `scripts/generate_redocred_candidates.py`
- `configs/redocred_task.yaml`

输入：

- `documents.jsonl`
- `entities.jsonl`
- `gold_triples.jsonl`
- relation metadata。

输出：

- `candidates.jsonl`
- `candidate_stats.json`

验收标准：

- 全部 gold triples 都出现在 candidates 中。
- 负样本不与 gold triples 重叠。
- 每篇文档 candidate 数受上限控制。
- hard negative 类型统计可见。

### Stage 4：实现 sentence evidence retriever

目标：

- 为每个 candidate 检索 top-k sentence evidence。

建议新增：

- `src/evidencekg/retrieval/redocred_sentence_retriever.py`
- 可选 `scripts/retrieve_redocred_evidence_contexts.py`

输入：

- `documents.jsonl`
- `entities.jsonl`
- `evidence.jsonl`
- `candidates.jsonl`

输出：

- `evidence_contexts.jsonl`
- retrieval stats。

验收标准：

- 每个 candidate 有 evidence context。
- dev 上可计算 retrieval evidence recall@k。
- 检索过程不读取 gold evidence，除 evaluation 对比外。

### Stage 5：实现 document graph builder

目标：

- 为每篇文档构建 local KG，并提供 graph context retrieval。

建议新增：

- `src/evidencekg/graph/redocred_document_graph.py`
- `src/evidencekg/retrieval/redocred_graph_context.py`

输入：

- `documents.jsonl`
- `entities.jsonl`
- `evidence.jsonl`
- `candidates.jsonl`

输出：

- 可内存构建，不一定落盘。
- graph context 合并进入 `evidence_contexts.jsonl`。

验收标准：

- 能返回 head/tail mention sentences。
- 能返回 common sentences。
- 能返回 bridge entities 和 co-occurrence paths。
- 不泄露当前 candidate 的 gold label。

### Stage 6：实现 Re-DocRED prompt builder

目标：

- 构造文档级 relation verification prompt。

建议新增：

- `src/evidencekg/prompting/redocred_prompt_builder.py`

输入：

- evidence context。
- relation metadata。

输出：

- `structured_context`
- `prompt_text`

验收标准：

- prompt 明确 JSON schema。
- prompt 明确 allowed evidence ids。
- prompt 明确禁止外部知识。
- 能被 mock/real reasoner 调用。

### Stage 7：实现 Re-DocRED verifier

目标：

- 对 LLM 输出做 schema、grounding、sufficiency、conflict 和 abstention 校验。

建议新增：

- `src/evidencekg/verify/redocred_verifier.py`

输入：

- candidate。
- evidence context。
- prediction。
- relation metadata。
- local graph context。

输出：

- verified prediction record。

验收标准：

- 非法 evidence id 被拦截。
- accept 无 evidence 被降级。
- confidence threshold 生效。
- weak evidence accept 可降为 uncertain。
- verifier details 可解释。

### Stage 8：实现 evaluator

目标：

- 计算 relation、evidence 和 risk control 指标。

建议新增：

- `src/evidencekg/eval/redocred_evaluator.py`
- `scripts/evaluate_redocred.py`

输入：

- `verified_predictions.jsonl`
- `predicted_triples.jsonl`
- `gold_triples.jsonl`
- `evidence_contexts.jsonl`

输出：

- `evaluation_report.json`
- 可选 per-relation metrics。

验收标准：

- relation P/R/F1 正确。
- evidence P/R/F1 在 gold evidence 可用时正确。
- coverage、uncertain rate、wrong accept rate 可计算。
- 能区分 controlled candidate setting 和 full extraction setting。

### Stage 9：小样本调试

目标：

- 在少量文档上跑通全流程。

建议新增或使用参数：

- `--max-docs`
- `--max-candidates`
- `--candidate-offset`
- `--debug-timing`

输入：

- processed dev small split。

输出：

- `outputs_redocred_smoke/`

验收标准：

- 不调用真实 LLM 时可用 mock 或 deterministic rule 跑通。
- 调真实 LLM 时 JSON parse 稳定。
- evidence id 不 hallucinate。
- verifier 能产生有效降级。

### Stage 10：dev/test 正式实验

目标：

- 在 dev 上完成调参与消融。
- 在 test 或 held-out split 上跑最终结果。

建议新增：

- `scripts/run_redocred_pipeline.py`
- `configs/redocred_task_real.yaml`
- `configs/redocred_task_mock.yaml`

输入：

- full processed dev/test。

输出：

- `outputs_redocred/dev/...`
- `outputs_redocred/test/...`

验收标准：

- 结果可复现。
- 消融输出目录和配置保存完整。
- test 不反复调参。
- 保留 run metadata、timing 和 model 信息。

## 十二、风险与注意事项

### 12.1 先确认 evidence 字段完整性

Re-DocRED 改善了 DocRED 的漏标问题，但仍应先确认当前使用版本：

- label 是否都有 `evidence`。
- evidence 是否为空。
- evidence sentence index 是否越界。
- relation metadata 是否完整。

如果 evidence 不完整，relation metrics 仍可做，evidence metrics 要单独过滤或标注。

### 12.2 第一版不要让 LLM 直接全关系抽取

不要让 LLM 输入全文后直接输出所有关系。原因：

- 输出长度和格式不可控。
- 很难做逐候选 verifier。
- 容易混入常识推断。
- 不利于复用当前 pipeline。

第一版应做 triple verification：

```text
one document + one candidate triple + retrieved evidence + graph context -> one JSON judgment
```

### 12.3 不要一开始暴力展开所有实体对和关系

`entity_pair × relation` 全展开会导致候选数量、负样本噪声和 LLM 成本失控。先使用：

- gold positives。
- controlled negatives。
- hard negatives。
- max candidates per doc。

后续再做 full extraction setting。

### 12.4 不要一开始引入过复杂组件

第一版不建议直接做：

- cross-encoder 训练。
- GNN。
- Neo4j。
- 多跳神经检索。
- 多 agent 反复辩论。

推荐优先做：

- deterministic adapter。
- sentence-level evidence retrieval。
- document-local graph context。
- strict JSON prompt。
- rule-based verifier。
- 可复现 evaluator。

### 12.5 test set 不要反复调参

实验纪律：

- train/debug 用于开发。
- dev 用于参数、prompt、verifier threshold 和消融。
- test 只跑最终配置。
- 每次正式实验保存 config、commit hash、model name、run metadata。

### 12.6 保留原项目任务

不要直接破坏当前企业资产 KG pipeline。建议采用并行目录和类名：

- `redocred_adapter.py`
- `redocred_candidate_generator.py`
- `redocred_sentence_retriever.py`
- `redocred_document_graph.py`
- `redocred_prompt_builder.py`
- `redocred_verifier.py`
- `redocred_evaluator.py`
- `run_redocred_pipeline.py`

现有 `PipelineRunner` 可以作为参考，但不要强行把所有 Re-DocRED 逻辑塞进旧 runner。更稳妥的做法是新增 `RedocredPipelineRunner`，等接口稳定后再抽象公共基类。

### 12.7 论文实验口径

建议论文或报告中这样描述：

1. 当前系统从企业资产 hidden edge recovery 扩展到文档级 evidence-aware relation reasoning。
2. Re-DocRED 用作通用文档级关系推理 benchmark。
3. 第一阶段采用 controlled triple verification，用于检验 LLM 是否能在检索证据和局部图上下文约束下做可靠判断。
4. 系统重点不是替代传统 DocRE 模型，而是验证 EvidenceKG-style graph/evidence context、LLM reasoning 和 verifier/calibration 的组合能降低错误 accept、提高 evidence grounding。

## 附录：建议目录结构

建议后续实现后形成：

```text
configs/
  redocred_dataset.yaml
  redocred_task_mock.yaml
  redocred_task_real.yaml
  redocred_relations.yaml

scripts/
  inspect_redocred.py
  build_redocred_dataset.py
  generate_redocred_candidates.py
  retrieve_redocred_evidence_contexts.py
  run_redocred_pipeline.py
  evaluate_redocred.py

src/evidencekg/data/
  redocred_adapter.py

src/evidencekg/candidate/
  redocred_candidate_generator.py

src/evidencekg/graph/
  redocred_document_graph.py

src/evidencekg/retrieval/
  redocred_sentence_retriever.py
  redocred_graph_context.py

src/evidencekg/prompting/
  redocred_prompt_builder.py

src/evidencekg/verify/
  redocred_verifier.py

src/evidencekg/eval/
  redocred_evaluator.py
```

这条路径能最大限度保留当前项目，同时让 Re-DocRED pipeline 成为一个可评测、可消融、可写论文实验的独立系统。
