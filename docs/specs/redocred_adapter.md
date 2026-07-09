# Re-DocRED Adapter Specification

## 1. Module Goal

`redocred_adapter` converts raw Re-DocRED files into split-aware processed JSONL files for the Re-DocRED pipeline.

It is the data-contract source for later modules:

- `redocred_candidate_generator`
- `redocred_sentence_retriever`
- `redocred_document_graph` / `redocred_graph_context`
- `redocred_prompt_builder`
- `redocred_verifier`
- `redocred_evaluator`

The adapter must produce deterministic IDs and stable schemas. It may read raw labels and gold evidence because it constructs gold files, but it must clearly mark oracle-only fields and must not perform candidate generation beyond gold-file construction, evidence retrieval, prompt construction, LLM reasoning, verification, or evaluation.

## 2. Current

### Existing Data-Building Logic

The current repository has an enterprise asset CSV builder:

- `scripts/build_dataset_from_csv.py`
- `src/evidencekg/data/dataset_builder.py`
- `src/evidencekg/data/evidence_builder.py`
- `src/evidencekg/data/entity_normalizer.py`
- `src/evidencekg/io.py`

Current output style:

- JSONL files are written with `write_jsonl(...)`.
- JSON files are written with `write_json(...)`.
- Records use deterministic string IDs.
- `entities.jsonl` records include `id`, `type`, `name`, `aliases`, `properties`.
- `evidence.jsonl` records include `id`, `source`, `source_file`, `source_row_id`, `text`, `related_entities`, `timestamp`, `reliability`, `metadata`.
- old gold records are written to `gold_hidden_edges.jsonl`.

`GraphStore` currently validates:

- entity required fields: `id`, `type`, `name`, `aliases`, `properties`;
- evidence required fields: `id`, `source`, `source_file`, `source_row_id`, `text`, `related_entities`, `timestamp`, `reliability`, `metadata`;
- triples required fields: `id`, `head`, `relation`, `tail`, `source`, `source_row_id`, `confidence`, `properties`.

### Reference-Only Logic

These old components are useful as reference, but must not be directly imposed on Re-DocRED:

- enterprise CSV manifest logic;
- asset/service/team/IP entity types;
- hidden edge recovery assumptions;
- single `target_relation` task shape;
- `gold_hidden_edges.jsonl` naming and semantics;
- enterprise evidence sources such as tickets, alerts, DNS, CMDB-like rows;
- old global KG loading assumptions that require `triples.jsonl`.

The Re-DocRED adapter should reuse only generic patterns where helpful:

- deterministic IDs;
- explicit JSONL schemas;
- UTF-8 JSON read/write style;
- strict validation and summary stats;
- stable sorted output where practical.

### Missing Re-DocRED Capabilities

The current repository does not yet have:

- raw Re-DocRED JSON inspection;
- support for `title`, `sents`, `vertexSet`, `labels`;
- sentence-level evidence records;
- document-local entity and mention records;
- Re-DocRED relation metadata handling;
- `documents.jsonl`;
- `gold_triples.jsonl`;
- `schema_summary.json` or `adapter_stats.json`;
- evidence annotation status reporting;
- oracle-field tagging for downstream anti-leakage.

## 3. Target

The adapter must support raw Re-DocRED-style fields:

- `title`
- `sents`
- `vertexSet`
- `labels`
- label-level `h`
- label-level `t`
- label-level `r`
- label-level `evidence`

It must support relation metadata that maps relation IDs to human-readable names, descriptions, aliases, and optional type information.

It must produce split-aware processed files under a caller-provided output directory, typically:

```text
data/redocred_processed/
  train/
    documents.jsonl
    entities.jsonl
    evidence.jsonl
    gold_triples.jsonl
    schema_summary.json
    adapter_stats.json
  dev/
    documents.jsonl
    entities.jsonl
    evidence.jsonl
    gold_triples.jsonl
    schema_summary.json
    adapter_stats.json
  test/
    documents.jsonl
    entities.jsonl
    evidence.jsonl
    gold_triples.jsonl   # only if labels are available
    schema_summary.json
    adapter_stats.json
```

If relation metadata is normalized during adaptation, the adapter may additionally produce:

```text
data/redocred_processed/relations.jsonl
```

or a repository config file:

```text
configs/redocred_relations.yaml
```

The first implementation should prefer writing `relations.jsonl` under the processed output directory unless the user explicitly approves a config-file workflow.

## 4. Input Contract

### Required Inputs

The adapter should accept explicit split paths:

```text
--train-file path/to/train.json
--dev-file path/to/dev.json
--test-file path/to/test.json
--relation-metadata path/to/relations.json-or-yaml
--output-dir data/redocred_processed
```

At least one split file must be provided.

### Optional Inputs

Supported optional arguments:

```text
--split train|dev|test
--max-docs 5
--source-name Re-DocRED
--strict true|false
```

Expected behavior:

- `--split` limits processing to one split when multiple paths are configured.
- `--max-docs` processes only the first N documents per selected split.
- `--source-name` is stored in metadata.
- `--strict true` should fail on schema violations that would corrupt references.
- `--strict false` may skip malformed labels/mentions while recording errors in stats.

### Raw Field Compatibility Strategy

Raw Re-DocRED files may vary slightly. The adapter must inspect and normalize:

- `sents` as `list[list[str]]`, `list[str]`, or mixed token/string sentences.
- `vertexSet` as a list of entity mention lists.
- mention fields such as `name`, `sent_id`, `pos`, `type`.
- label fields such as `h`, `t`, `r`, `evidence`.
- missing `labels` on test files.

Normalization rules:

- If a sentence is `list[str]`, join tokens with spaces.
- If a sentence is already `str`, trim it and preserve it.
- If a sentence is empty after normalization, keep the sentence record but set `text` to `""` only if explicitly allowed by `strict=false`; otherwise fail.
- If `labels` is missing, write no gold triples and record `labels_available=false`.
- If `evidence` is missing or invalid, keep the gold triple if `h/t/r` are valid and record evidence status.

## 5. Output Contract

All output files must be UTF-8. JSONL records must be one JSON object per line, sorted deterministically where possible.

### `documents.jsonl`

One row per document.

Required fields:

```json
{
  "doc_id": "redocred_dev_000001",
  "split": "dev",
  "title": "Document title",
  "raw_doc_index": 1,
  "sentence_ids": ["sent_redocred_dev_000001_000"],
  "entity_ids": ["ent_redocred_dev_000001_000"],
  "label_count": 3,
  "metadata": {
    "source": "Re-DocRED",
    "raw_file": "dev_revised.json",
    "sentence_count": 12,
    "entity_count": 8,
    "labels_available": true
  }
}
```

Field rules:

- `doc_id` must be deterministic.
- `sentence_ids` must contain every sentence record produced for the document.
- `entity_ids` must contain every entity record produced for the document.
- `label_count` is the count of raw valid labels converted into gold triples, not necessarily the raw label list length if malformed labels are skipped.

### `entities.jsonl`

One row per document-local entity, corresponding to one `vertexSet` entry.

Required fields:

```json
{
  "id": "ent_redocred_dev_000001_000",
  "doc_id": "redocred_dev_000001",
  "local_entity_index": 0,
  "type": "ORG",
  "name": "Canonical entity name",
  "aliases": ["Alias A", "Alias B"],
  "mentions": [
    {
      "mention_id": "men_redocred_dev_000001_000_000",
      "name": "Canonical entity name",
      "sent_id": 0,
      "sentence_id": "sent_redocred_dev_000001_000",
      "pos": [0, 2],
      "type": "ORG",
      "valid": true,
      "error": ""
    }
  ],
  "properties": {
    "source": "vertexSet",
    "mention_count": 1,
    "valid_mention_count": 1,
    "raw_entity_index": 0
  }
}
```

Compatibility fields:

- Keep `id`, `type`, `name`, `aliases`, `properties` to remain friendly to existing JSONL conventions.
- Re-DocRED-specific fields such as `doc_id`, `local_entity_index`, and `mentions` are required for the new pipeline.

Field rules:

- `name` should be the first valid mention name if available; otherwise a deterministic fallback such as `entity_000`.
- `aliases` must be de-duplicated and sorted or preserved in deterministic first-seen order.
- Entity `type` should be the majority or first valid mention type. If missing, use `"UNKNOWN"`.
- Mentions with invalid `sent_id` should be recorded as invalid in `mentions` only in non-strict mode; strict mode should fail.

### `evidence.jsonl`

One row per sentence. The evidence unit for the first-stage pipeline is a sentence.

Required fields:

```json
{
  "id": "sent_redocred_dev_000001_000",
  "doc_id": "redocred_dev_000001",
  "sent_id": 0,
  "source": "redocred_sentence",
  "source_file": "dev_revised.json",
  "source_row_id": "redocred_dev_000001:sent:000",
  "text": "Sentence text after token join.",
  "tokens": ["Sentence", "text"],
  "related_entities": ["ent_redocred_dev_000001_000"],
  "mention_ids": ["men_redocred_dev_000001_000_000"],
  "timestamp": "",
  "reliability": 1.0,
  "metadata": {
    "title": "Document title",
    "split": "dev",
    "sentence_index": 0,
    "source": "Re-DocRED"
  }
}
```

Compatibility fields:

- Keep `id`, `source`, `source_file`, `source_row_id`, `text`, `related_entities`, `timestamp`, `reliability`, `metadata`.
- Add `doc_id`, `sent_id`, `tokens`, and `mention_ids`.

Field rules:

- `related_entities` contains entity IDs that have valid mentions in this sentence.
- `mention_ids` contains valid mention IDs in this sentence.
- `tokens` should preserve the raw token list when available; if raw sentence is string-only, tokenization may be omitted or set to a simple whitespace split, but this must be reported in stats.
- `reliability` is `1.0` for Re-DocRED sentence records unless a future spec defines another score.

### `gold_triples.jsonl`

One row per valid raw label with valid `h`, `t`, and `r`.

Required fields:

```json
{
  "gold_id": "gold_redocred_dev_000001_000000",
  "doc_id": "redocred_dev_000001",
  "split": "dev",
  "head": "ent_redocred_dev_000001_000",
  "head_index": 0,
  "head_name": "Head name",
  "relation": "P17",
  "relation_name": "country",
  "relation_description": "Relation description.",
  "relation_aliases": ["country"],
  "tail": "ent_redocred_dev_000001_001",
  "tail_index": 1,
  "tail_name": "Tail name",
  "evidence_ids": ["sent_redocred_dev_000001_000"],
  "evidence_sent_ids": [0],
  "evidence_annotation_status": "gold",
  "source": "redocred_label",
  "oracle_only": true,
  "metadata": {
    "raw_label_index": 0,
    "raw_relation": "P17",
    "raw_evidence": [0]
  }
}
```

Field rules:

- `oracle_only` must always be `true`.
- `evidence_ids` are sentence evidence IDs mapped from valid `label.evidence` indices.
- `evidence_sent_ids` are the corresponding integer sentence indices.
- If evidence is missing, empty, or partially invalid, follow the evidence handling rules below.
- Duplicate labels should be de-duplicated by `(doc_id, head_index, relation, tail_index)` unless strict mode is configured to preserve duplicates for audit. Deduplication decisions must be counted in stats.

### `adapter_stats.json`

One JSON file per split.

Required top-level fields:

```json
{
  "split": "dev",
  "raw_file": "dev_revised.json",
  "document_count": 5,
  "sentence_count": 80,
  "entity_count": 40,
  "mention_count": 120,
  "valid_mention_count": 118,
  "label_count_raw": 30,
  "gold_triple_count": 28,
  "duplicate_label_count": 2,
  "skipped_label_count": 0,
  "evidence": {
    "label_with_gold_evidence_count": 24,
    "label_with_empty_evidence_count": 2,
    "label_with_missing_evidence_count": 1,
    "label_with_out_of_range_evidence_count": 1,
    "evidence_coverage": 0.8571
  },
  "relations": {
    "P17": 10
  },
  "errors": []
}
```

### `schema_summary.json`

One JSON file per split, focused on raw-field inspection.

Required fields:

```json
{
  "split": "dev",
  "raw_file": "dev_revised.json",
  "top_level_fields": ["title", "sents", "vertexSet", "labels"],
  "sentence_shapes": {
    "list_of_tokens": 5,
    "string_sentence": 0,
    "empty_sentence": 0
  },
  "mention_fields": ["name", "sent_id", "pos", "type"],
  "label_fields": ["h", "t", "r", "evidence"],
  "labels_available": true,
  "evidence_available": true,
  "relation_metadata_available": true,
  "warnings": []
}
```

`adapter_stats.json` and `schema_summary.json` may be combined only if the combined file preserves both statistics and raw schema inspection sections.

## 6. ID Rules

All IDs must be stable and reproducible from split, document index, and local indices.

### `doc_id`

Format:

```text
redocred_{split}_{doc_index:06d}
```

Example:

```text
redocred_dev_000001
```

Rules:

- `doc_index` is zero-based or one-based only if consistently documented. The first implementation should use zero-based indices.
- Title should not be used as the primary ID because titles can be missing, duplicated, or changed.

### `sentence_id`

Format:

```text
sent_{doc_id}_{sent_id:03d}
```

Example:

```text
sent_redocred_dev_000001_000
```

### `entity_id`

Format:

```text
ent_{doc_id}_{entity_index:03d}
```

Example:

```text
ent_redocred_dev_000001_000
```

### `mention_id`

Format:

```text
men_{doc_id}_{entity_index:03d}_{mention_index:03d}
```

Example:

```text
men_redocred_dev_000001_000_000
```

### `gold_id`

Format:

```text
gold_{doc_id}_{gold_index:06d}
```

Example:

```text
gold_redocred_dev_000001_000000
```

Rules:

- `gold_index` is assigned after validating labels and de-duplicating if deduplication is enabled.
- If preserving duplicates for audit in non-strict mode, duplicate rows must still receive unique `gold_id`s.

## 7. Evidence Handling

### Valid `label.evidence`

When `label.evidence` exists and contains valid sentence indices:

- map each sentence index `i` to `sent_{doc_id}_{i:03d}`;
- write those IDs to `gold_triples.evidence_ids`;
- write integer indices to `gold_triples.evidence_sent_ids`;
- set `evidence_annotation_status = "gold"`;
- count the label as evidence-covered.

### Missing Evidence

When `evidence` key is missing:

- keep the gold triple if `h`, `t`, and `r` are valid;
- set `evidence_ids = []`;
- set `evidence_sent_ids = []`;
- set `evidence_annotation_status = "missing"`;
- record count in `adapter_stats.evidence.label_with_missing_evidence_count`.

### Empty Evidence

When `evidence` exists but is empty:

- keep the gold triple if `h`, `t`, and `r` are valid;
- set `evidence_ids = []`;
- set `evidence_sent_ids = []`;
- set `evidence_annotation_status = "empty"`;
- record count in `adapter_stats.evidence.label_with_empty_evidence_count`.

### Out-of-Range Evidence

When some evidence indices are out of range:

- keep valid evidence indices;
- drop invalid evidence indices;
- set `evidence_annotation_status = "partial_invalid"` if at least one valid evidence remains;
- set `evidence_annotation_status = "out_of_range"` if no valid evidence remains;
- record invalid indices in `metadata.invalid_evidence_sent_ids`;
- record count in `adapter_stats.evidence.label_with_out_of_range_evidence_count`.

In strict mode, any out-of-range evidence index may fail the build instead of producing partial output.

### Oracle Boundary

Gold evidence is oracle information. It may be written only to:

- `gold_triples.jsonl`;
- `adapter_stats.json`;
- `schema_summary.json`;
- later evaluator inputs.

It must not be used by:

- sentence retrieval;
- graph context construction;
- prompt building;
- reasoner;
- verifier correctness decisions.

Downstream modules must consume a sanitized candidate/context view that excludes `gold_evidence_ids`, `evidence_ids` from gold triples, and any `oracle_only` fields.

## 8. Relation Metadata Handling

The adapter must support relation metadata mapping from raw relation IDs to:

- `relation`
- `relation_name`
- `description`
- `aliases`
- optional `head_types`
- optional `tail_types`
- optional `direction`
- optional `source`

Recommended normalized relation record:

```json
{
  "relation": "P17",
  "relation_name": "country",
  "description": "Country associated with the entity.",
  "aliases": ["country"],
  "head_types": [],
  "tail_types": [],
  "direction": "head_to_tail",
  "metadata": {
    "source": "relation_metadata"
  }
}
```

### Missing Metadata

If metadata is missing for a relation ID:

- keep the raw relation ID in `relation`;
- set `relation_name` to the raw ID;
- set `description` to `""`;
- set `aliases` to `[]`;
- add warning to `schema_summary.warnings`;
- increment `adapter_stats.missing_relation_metadata_count`.

Missing metadata must not block adapter output unless `strict=true`.

### Output Location

The first implementation may output:

```text
data/redocred_processed/relations.jsonl
```

If the project later standardizes relation configuration, it may instead write or consume:

```text
configs/redocred_relations.yaml
```

This spec does not require generating both.

## 9. Anti-Leakage Rules

The adapter may:

- read raw labels;
- read raw evidence annotations;
- generate `gold_triples.jsonl`;
- include oracle-only evidence fields in `gold_triples.jsonl`;
- compute evidence coverage stats.

The adapter must:

- mark `gold_triples.jsonl` rows with `oracle_only: true`;
- document oracle-only fields in output stats;
- keep gold fields out of sentence evidence records;
- avoid adding candidate-ready `gold_evidence_ids` to non-gold files;
- make it easy for later modules to construct sanitized inference records.

Oracle-only fields include:

- `gold_id`;
- `evidence_ids` in `gold_triples.jsonl`;
- `evidence_sent_ids`;
- `evidence_annotation_status`;
- `oracle_only`;
- raw label metadata.

Downstream inference modules must not use these fields as retrieval or reasoning input.

## 10. Edge Cases

The adapter spec must handle these cases:

### Empty Document

If a document has no sentences:

- strict mode: fail the split build;
- non-strict mode: skip the document and record an error.

### Empty `vertexSet`

If `vertexSet` is empty:

- write the document and sentence evidence;
- write no entities;
- skip labels that reference entities;
- record `empty_vertexset_count`.

### Label Missing Fields

If a label lacks `h`, `t`, or `r`:

- strict mode: fail;
- non-strict mode: skip the label and record missing fields.

### Evidence Index Out of Range

Handled according to Section 7.

### Mention `sent_id` Out of Range

If a mention references an invalid sentence:

- strict mode: fail;
- non-strict mode: mark mention `valid=false`, set `error`, exclude it from sentence `related_entities`, and record count.

### Token List Join

If sentence is a token list:

- join tokens with a single space;
- preserve original tokens in `tokens`.

If sentence is a string:

- trim whitespace;
- set `tokens` to a whitespace split or `[]`, but record this in `schema_summary.sentence_shapes`.

### Entity Alias De-Duplication

Aliases should be derived from mention names:

- remove empty aliases;
- de-duplicate exact strings;
- keep deterministic order;
- do not lowercase aliases unless a separate normalized alias field is added later.

### Duplicate Labels

Duplicates are labels with same:

```text
(doc_id, h, r, t)
```

Default behavior:

- merge evidence indices;
- produce one `gold_triples.jsonl` row;
- increment `duplicate_label_count`.

### `h` / `t` Entity Index Out of Range

If label `h` or `t` is outside `vertexSet`:

- strict mode: fail;
- non-strict mode: skip the label and record the invalid index.

## 11. Acceptance Criteria

The adapter module is acceptable only when:

- raw Re-DocRED fields can be inspected and summarized;
- `max_docs=5` can generate processed JSONL for at least one split;
- `documents.jsonl`, `entities.jsonl`, `evidence.jsonl`, and `gold_triples.jsonl` are produced when labels are available;
- all entity IDs referenced by evidence exist in `entities.jsonl`;
- all sentence IDs referenced by documents and gold evidence exist in `evidence.jsonl`;
- all `head` and `tail` IDs in `gold_triples.jsonl` exist in `entities.jsonl`;
- `schema_summary.json` reports top-level fields, mention fields, label fields, labels availability, and evidence availability;
- `adapter_stats.json` reports document count, sentence count, entity count, mention count, label count, evidence coverage, and relation frequency;
- relation metadata is normalized or missing metadata is explicitly reported;
- no LLM is called;
- no retrieval is performed;
- no prompt is built;
- no evaluator metric is computed;
- no legacy enterprise pipeline files are modified.

## 12. Suggested Files

Future implementation should add or use:

```text
src/evidencekg/data/redocred_adapter.py
scripts/inspect_redocred.py
scripts/build_redocred_dataset.py
configs/redocred_dataset.yaml
data/redocred_processed/relations.jsonl
```

`data/redocred_processed/relations.jsonl` is optional and should be generated only if relation metadata normalization is part of the implementation plan.

## 13. Smoke Tests / Validation Commands

Future implementation should support commands like:

```powershell
python scripts/inspect_redocred.py `
  --input data/raw/redocred/dev_revised.json `
  --relation-metadata data/raw/redocred/relations.json `
  --max-docs 5
```

```powershell
python scripts/build_redocred_dataset.py `
  --dev-file data/raw/redocred/dev_revised.json `
  --relation-metadata data/raw/redocred/relations.json `
  --output-dir data/redocred_processed `
  --max-docs 5
```

```powershell
python scripts/build_redocred_dataset.py `
  --train-file data/raw/redocred/train_revised.json `
  --dev-file data/raw/redocred/dev_revised.json `
  --test-file data/raw/redocred/test_revised.json `
  --relation-metadata data/raw/redocred/relations.json `
  --output-dir data/redocred_processed
```

Post-run validation examples:

```powershell
python -m pytest tests/test_redocred_adapter.py
```

```powershell
python scripts/inspect_redocred.py `
  --processed-dir data/redocred_processed/dev
```

The exact commands may change in the implementation plan, but they must validate:

- schema summary generation;
- processed JSONL creation;
- ID reference integrity;
- evidence coverage reporting;
- relation frequency reporting;
- no oracle leakage into non-gold files.

## 14. Non-Goals

The adapter must not:

- generate candidates;
- perform retrieval;
- build graph context;
- build prompts;
- call mock or real LLMs;
- run verifier logic;
- compute evaluator metrics;
- train models;
- move or modify the legacy enterprise pipeline;
- implement full document-level extraction;
- implement full entity-pair x all-relation expansion.
