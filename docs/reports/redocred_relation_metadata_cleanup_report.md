# Re-DocRED Relation Metadata Cleanup Report

## Scope

This cleanup updates only LLM-facing semantic fields in `resources/redocred_relations.draft.jsonl`. No adapter specification, architecture document, runtime module, or legacy component was modified or connected.

## Changes

- `relation_name` modified: **11** records.
- `description` rewritten: **96** records.
- `aliases` cleaned: **13** records.
- `source` modified: **0** records.
- `needs_review` modified: **0** records; all 96 records remain `true`.

### relation_name Changes

P118, P1344, P140, P179, P190, P355, P364, P449, P607, P706, P749

Prompt-friendly names `founded by` (P112) and `lyrics by` (P676) were retained because they express the documented head-to-tail reading without expanding the Wikidata property meaning.

## Direction or Boundary Review Items

- Inverse or sequence pairs: P1344/P710, P1365/P1366, and P155/P156.
- Part-whole and organization pairs: P150, P355, P361, P527, and P749.
- Location distinctions: P131 (administrative), P276 (general), P206 (body of water), and P706 (physical feature).
- Temporal properties P580, P582, and P585 intentionally allow entities, events, roles, or statements as heads.
- P190 is often used symmetrically, but its definition remains restricted to administrative bodies.

## Recommended Manual Focus

P1001, P118, P1344, P150, P190, P205, P276, P355, P403, P527, P607, P706, P710, and P749 have broad boundaries, close neighboring properties, or direction-sensitive semantics.

## Automated Validation

- All **96** lines parse independently with `json.loads`.
- The `relation_id` sequence and set exactly match the pre-clean snapshot; no duplicate IDs exist.
- `relation_id`, `wikidata_label`, `wikidata_description`, and `wikidata_aliases` are identical record by record before and after cleanup.
- Every record has the required nine fields.
- Every retained alias is a case-insensitive member of that record's `wikidata_aliases`, and aliases are de-duplicated case-insensitively.
- No architecture or spec file was modified, and no runtime was connected.
- No `.bak` file is part of this cleanup change.

## Second-Pass Semantic Rewrite

The descriptions produced in the preceding cleanup pass were rejected because they repeated a fixed two-sentence frame (`must stand in` / `This property covers`) and merely appended the Wikidata description. This pass replaced that templated output with relation-specific definitions that state the concrete roles of the head and tail and the direction in which the property holds.

### Changes in This Pass

- `description` rewritten: **96 of 96** records.
- `P576.relation_name` corrected from `dissolved, abolished or demolished` to `dissolved, abolished or demolished date`.
- All other `relation_name` values remained unchanged from the input to this pass.
- `relation_id`, all `wikidata_*` fields, `aliases`, `source`, and `needs_review` remained unchanged record by record.
- Six descriptions (P35, P172, P175, P264, P30, and P400) received an additional boundary-tightening review after the first semantic rewrite.

### Direction and Boundary Checks

- **P1344 / P710:** P1344 places the participant in the head and the event in the tail; P710 places the event or process in the head and the participant in the tail.
- **P1365 / P1366:** P1365 says the head replaces the tail predecessor; P1366 says the tail successor replaces the head.
- **P155 / P156:** P155 places the head immediately after the tail; P156 places the tail immediately after the head.
- **P150 / P361 / P527:** P150 is administrative containment from head territory to tail subdivision; P361 maps a head component to a larger tail whole; P527 maps a head whole to a tail component.
- **P355 / P749:** P355 maps a head parent organization to a tail child or subsidiary; P749 maps a head child organization to its tail parent.
- **P131 / P206 / P276 / P706:** The definitions distinguish administrative containment, adjacency to a body of water, a non-administrative physical location or event venue, and location on a physical geographic feature that is not merely administrative, a mountain range, or a body of water.
- **P580 / P582 / P585:** The tail respectively specifies when the head began to apply, ceased to apply, or specifically occurred, existed, or was true.
- **P403:** The head is the watercourse and the tail is the body of water into which it drains.
- **P190:** The definition requires a twinning, sister-city, or comparable cooperative partnership between local administrative bodies, while allowing either legal or informal governmental acknowledgement.
- **P1001:** The head item applies to, belongs to, or has authority over the tail territorial jurisdiction.
- **P118:** The tail is the league or competition in which the head team/player participates or the head event occurs.
- **P205:** The head body of water drains through, receives drainage from, or borders the tail country.
- **P607:** The head participant took part in the military conflict represented by the tail.

### Automated Acceptance Results

- All **96** lines were independently parsed with `json.loads`; record count and unique relation ID count are both 96.
- The relation ID order and set are unchanged.
- Protected fields (`relation_id`, `wikidata_label`, `wikidata_description`, `wikidata_aliases`, `aliases`, `source`, and `needs_review`) are identical before and after this pass.
- Except for P576, every `relation_name` is identical before and after this pass.
- Every `needs_review` value remains `true`.
- The forbidden phrases `must stand in`, `This property covers:`, and `Indicates that the head entity has the relation` are absent.
- All 96 final descriptions are distinct, contain both head and tail roles, and contain no more than two sentences.
- The most common identical four-word opening occurs only five times; no large-scale relation-name substitution template remains.
- A deterministic random sample of 15 before/after pairs and all required focus descriptions were printed during validation.

### Remaining Manual Review Priorities

P1001, P118, P172, P190, P205, P276, P355, P400, P576, P706, and P749 remain useful human-review priorities because their Wikidata definitions are broad, carry qualification-sensitive boundaries, or have closely related inverse or neighboring properties. All records intentionally retain `needs_review: true`.

## Targeted Boundary Corrections

A subsequent review corrected eight definitions whose previous wording narrowed, broadened, or incompletely represented the Wikidata boundary:

- P190 now permits legally or informally acknowledged governmental twinning partnerships.
- P205 now covers drainage to or from, and borders with, the tail country.
- P403 now identifies the tail specifically as a body of water.
- P19 and P20 now include people, animals, and fictional characters and require the most specific known location.
- P364 now covers films and performance works without adding release language.
- P449 is restricted to radio or television programs and their original network or service.
- P585 now requires the time when the event occurred, entity existed, or statement was true, rather than an arbitrary temporal association.

P276 and P706 were also refined to distinguish a non-administrative physical location or event venue from a physical geographic feature. P706 explicitly excludes purely administrative locations, mountain ranges, and bodies of water in accordance with its Wikidata description.

Automated comparison confirmed that these ten `description` values were the only fields changed in this targeted pass. All 96 records remained valid JSONL, all protected fields were identical record by record, and every `needs_review` value remained `true`.

## Final Acceptance and Consolidation

This final acceptance state supersedes the pass-specific `needs_review: true` statements recorded in earlier sections.

- All 96 relation metadata records have completed format, direction, and semantic-boundary review.
- Every record has formally passed review; `needs_review` is now `false` for all records.
- The reviewed provenance is recorded uniformly as `wikidata_property_pages_and_external_rel_info_mapping_reviewed`.
- The draft resource has been consolidated as `resources/redocred_relations.jsonl`; the old draft path is no longer used.
- The finalized metadata has not been connected to runtime code.
- No architecture, specification, adapter, runtime, or legacy file was modified as part of consolidation.
