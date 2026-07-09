# Re-DocRED Relation Metadata Draft Report

## Scope

This report documents a draft relation metadata resource for the Re-DocRED research pipeline. The generated JSONL is a review artifact only and is not connected to the adapter, runtime pipeline, prompt builder, verifier, or evaluator.

## Data Paths

- Preferred path checked: `C:\Users\230\AppData\Local\Temp\redocred_inspect`
- Preferred path exists: `False`
- Local data path used: `D:\Code\EvidenceKG-Reasoner\data\raw\redocred`

The preferred temporary path does not exist because the downloaded files were previously moved into the project-local raw data directory. Relation IDs were extracted from the project-local Re-DocRED files, not guessed.

## Splits Read

- `train_revised.json`: 3053 documents, 85932 labels, 96 unique relation IDs
- `dev_revised.json`: 500 documents, 17284 labels, 95 unique relation IDs
- `test_revised.json`: 500 documents, 17448 labels, 95 unique relation IDs

## Relation Coverage

- Total unique relation IDs across train/dev/test: `96`
- Relation names from mapping: `96`
- Relation names generated without mapping: `0`

## Relation Mapping Source

- Mapping file found: `C:\Users\230\AppData\Local\Temp\redocred_rel_info.json.gz`
- Mapping status: `third_party_external_mapping_hf_bowdbeg_redocred_cached_temp`
- The mapping is not part of the official raw Re-DocRED GitHub data package. It is treated as an external/third-party relation-name mapping and is used only to fill `relation_name`.

## Generated Fields

- `description`: generated draft from relation name; must be manually reviewed.
- `aliases`: generated draft from relation name; must be manually reviewed.
- `head_type_hint`: generated draft hint; not a hard constraint.
- `tail_type_hint`: generated draft hint; not a hard constraint.
- `needs_review`: `true` for every row.

## Anti-Leakage Notes

- Relation IDs were extracted only from `labels[*].r`.
- No relation meaning was inferred from a document-specific gold triple.
- No evidence sentence content or gold evidence IDs were written into metadata.
- The resource is not connected to any runtime module.

## Files Created

- `resources\redocred_relations.draft.jsonl`
- `docs\reports\redocred_relation_metadata_draft_report.md`

## Confirmed Non-Changes

- Did not modify `docs/specs/redocred_adapter.md`.
- Did not modify `docs/architecture.md`.
- Did not modify `docs/redocred_pipeline_design.md`.
- Did not modify `docs/specs/redocred_module_roadmap.md`.
- Did not implement `redocred_adapter`.
- Did not modify the legacy enterprise pipeline.

## Review Priorities

- Verify that every `relation_name` matches the intended Wikidata relation semantics.
- Rewrite generic descriptions into prompt-ready definitions where needed.
- Check aliases for ambiguity, especially broad relations such as `part of`, `has part`, `located in`, and `applies to jurisdiction`.
- Check type hints carefully; they are coarse hints only and should not be used as hard validation rules without review.
