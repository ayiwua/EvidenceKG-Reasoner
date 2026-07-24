from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


SPLITS = ("train", "dev", "test")
DEFAULT_FILES = {split: Path(f"data/raw/redocred/{split}_revised.json") for split in SPLITS}
RELATION_METADATA_PATH = Path("resources/redocred_relations.jsonl")
OUTPUT_FILES = (
    "documents.jsonl",
    "entities.jsonl",
    "evidence.jsonl",
    "gold_triples.jsonl",
    "adapter_stats.json",
    "schema_summary.json",
)
RELATION_FIELDS = (
    "relation_id",
    "wikidata_label",
    "wikidata_description",
    "wikidata_aliases",
    "relation_name",
    "description",
    "aliases",
    "source",
    "needs_review",
)
RECORD_FIELDS = {
    "documents.jsonl": ("doc_id", "split", "title", "raw_doc_index", "sentence_ids", "entity_ids", "label_count", "metadata"),
    "entities.jsonl": ("id", "doc_id", "local_entity_index", "type", "name", "aliases", "mentions", "properties"),
    "evidence.jsonl": (
        "id", "doc_id", "sent_id", "source", "source_file", "source_row_id", "text", "tokens",
        "related_entities", "mention_ids", "timestamp", "reliability", "metadata",
    ),
    "gold_triples.jsonl": (
        "gold_id", "doc_id", "split", "head", "head_index", "head_name", "relation", "relation_name",
        "relation_description", "relation_aliases", "tail", "tail_index", "tail_name", "evidence_ids",
        "evidence_sent_ids", "evidence_annotation_status", "source", "oracle_only", "metadata",
    ),
}
STATS_FIELDS = (
    "split", "raw_file", "strict", "document_count_raw", "document_count_written", "document_count_skipped",
    "sentence_count", "entity_count", "mention_count_raw", "mention_count_written", "label_count_raw",
    "gold_triple_count", "duplicate_label_count", "skipped_label_count", "relations", "unknown_relation_ids",
    "evidence", "warning_counts", "error_counts", "diagnostics",
)
SUMMARY_FIELDS = (
    "split", "raw_file", "top_level_type", "top_level_fields", "sentence_shape", "mention_fields",
    "label_fields", "labels_available", "evidence_field_available", "relation_metadata_path",
    "relation_metadata_record_count", "warnings",
)


class _AdapterContractError(Exception):
    def __init__(self, code: str, message: str, affected_unit: str = "split") -> None:
        super().__init__(message)
        self.code = code
        self.affected_unit = affected_unit


def load_relation_metadata(path: str | Path = RELATION_METADATA_PATH) -> dict[str, dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        raise _AdapterContractError("RELATION_METADATA_MISSING", f"relation metadata not found: {target}", "invocation")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise _AdapterContractError("RELATION_METADATA_JSONL_INVALID", f"metadata is not UTF-8: {target}", "invocation") from exc
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line:
            raise _AdapterContractError("RELATION_METADATA_JSONL_INVALID", f"blank metadata line: {line_no}", "invocation")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _AdapterContractError("RELATION_METADATA_JSONL_INVALID", f"invalid metadata JSON at line {line_no}", "invocation") from exc
        if not isinstance(row, dict) or set(row) != set(RELATION_FIELDS):
            raise _AdapterContractError("RELATION_METADATA_SCHEMA_INVALID", f"invalid metadata fields at line {line_no}", "invocation")
        string_fields = ("relation_id", "wikidata_label", "wikidata_description", "relation_name", "description", "source")
        if any(not isinstance(row[field], str) for field in string_fields) or not row["relation_id"]:
            raise _AdapterContractError("RELATION_METADATA_SCHEMA_INVALID", f"invalid metadata string field at line {line_no}", "invocation")
        if any(not isinstance(row[field], list) or any(not isinstance(v, str) for v in row[field]) for field in ("wikidata_aliases", "aliases")):
            raise _AdapterContractError("RELATION_METADATA_SCHEMA_INVALID", f"invalid metadata aliases at line {line_no}", "invocation")
        if row["needs_review"] is not False:
            raise _AdapterContractError("RELATION_METADATA_UNREVIEWED", f"unreviewed metadata at line {line_no}", "invocation")
        rows.append(row)
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        relation_id = row["relation_id"]
        if relation_id in index:
            raise _AdapterContractError("RELATION_METADATA_DUPLICATE_ID", f"duplicate relation_id: {relation_id}", "invocation")
        index[relation_id] = row
    return index


def select_splits(
    train_file: str | Path | None = None,
    dev_file: str | Path | None = None,
    test_file: str | Path | None = None,
    split: str | None = None,
) -> list[tuple[str, Path]]:
    explicit = {"train": train_file, "dev": dev_file, "test": test_file}
    if split is not None and split not in SPLITS:
        raise _AdapterContractError("INVALID_SPLIT", f"invalid split: {split}", "invocation")
    if split is not None:
        names = [split]
    elif any(value is not None for value in explicit.values()):
        names = [name for name in SPLITS if explicit[name] is not None]
    else:
        names = [name for name in SPLITS if DEFAULT_FILES[name].exists()]
    selected = [(name, Path(explicit[name]) if explicit[name] is not None else DEFAULT_FILES[name]) for name in names]
    if not selected or not any(path.exists() for _, path in selected):
        raise _AdapterContractError("NO_SELECTED_SPLIT", "no selected split resolves to an existing file", "invocation")
    return selected


def _diagnostic(
    state: dict[str, Any],
    code: str,
    severity: str,
    affected_unit: str,
    message: str,
    doc: int | None = None,
    entity: int | None = None,
    mention: int | None = None,
    label: int | None = None,
) -> None:
    state["diagnostics"].append({
        "code": code, "severity": severity, "split": state["split"], "raw_doc_index": doc,
        "raw_entity_index": entity, "raw_mention_index": mention, "raw_label_index": label,
        "affected_unit": affected_unit, "message": message,
    })
    counts = state["warning_counts"] if severity == "warning" else state["error_counts"]
    counts[code] = counts.get(code, 0) + 1
    if severity == "warning" and code not in state["warning_order"]:
        state["warning_order"].append(code)


def _raise(code: str, message: str, unit: str) -> None:
    raise _AdapterContractError(code, message, unit)


def _observe_keys(target: list[str], seen: set[str], value: Any) -> None:
    if isinstance(value, dict):
        for key in value:
            if key not in seen:
                seen.add(key)
                target.append(key)


def _load_raw_split(path: Path) -> list[Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _AdapterContractError("RAW_JSON_INVALID", f"invalid raw JSON: {path}") from exc
    except UnicodeDecodeError as exc:
        raise _AdapterContractError("RAW_JSON_INVALID", f"raw file is not UTF-8: {path}") from exc
    if not isinstance(payload, list):
        _raise("RAW_TOP_LEVEL_INVALID", f"raw top-level value is not a list: {path}", "split")
    return payload


def _document_error(state: dict[str, Any], strict: bool, code: str, message: str, doc: int) -> None:
    if strict:
        _raise(code, message, "document")
    _diagnostic(state, code, "error", "document", message, doc)
    state["document_count_skipped"] += 1


def _mention_error(
    state: dict[str, Any], strict: bool, code: str, message: str, doc: int, entity: int, mention: int
) -> bool:
    if strict:
        _raise(code, message, "mention")
    _diagnostic(state, code, "error", "mention", message, doc, entity, mention)
    return False


def _parse_evidence(
    label_obj: dict[str, Any], sentence_count: int, state: dict[str, Any], strict: bool, doc: int, label: int
) -> tuple[str, list[int], Any]:
    if "evidence" not in label_obj or label_obj["evidence"] is None:
        return "missing", [], None
    raw = label_obj["evidence"]
    if not isinstance(raw, list):
        if strict:
            _raise("EVIDENCE_VALUE_INVALID", f"label {label} evidence is not a list", "label")
        _diagnostic(state, "EVIDENCE_VALUE_INVALID", "error", "label", "evidence is not a list", doc, label=label)
        return "invalid", [], raw
    if not raw:
        return "empty", [], raw
    valid: list[int] = []
    invalid = False
    for value in raw:
        if type(value) is not int or not 0 <= value < sentence_count:
            invalid = True
            if strict:
                _raise("EVIDENCE_INDEX_INVALID", f"label {label} has invalid evidence index", "label")
            _diagnostic(state, "EVIDENCE_INDEX_INVALID", "error", "label", f"invalid evidence index: {value!r}", doc, label=label)
        elif value not in valid:
            valid.append(value)
    return ("invalid" if invalid else "present"), sorted(valid), raw


def _convert_document(
    raw: Any,
    raw_doc_index: int,
    split: str,
    raw_file: str,
    source_name: str,
    metadata: dict[str, dict[str, Any]],
    state: dict[str, Any],
    strict: bool,
) -> dict[str, list[dict[str, Any]]] | None:
    if not isinstance(raw, dict):
        _document_error(state, strict, "DOCUMENT_NOT_OBJECT", "document is not an object", raw_doc_index)
        return None
    _observe_keys(state["top_level_fields"], state["top_level_seen"], raw)
    title = raw.get("title")
    if not isinstance(title, str) or not title:
        _document_error(state, strict, "DOCUMENT_TITLE_INVALID", "title is missing, empty, or non-string", raw_doc_index)
        return None
    sents = raw.get("sents")
    if not isinstance(sents, list):
        _document_error(state, strict, "DOCUMENT_SENTS_INVALID", "sents is missing or non-list", raw_doc_index)
        return None
    sentence_valid = True
    for sentence in sents:
        if not isinstance(sentence, list):
            state["sentence_shape"]["non_list"] += 1
            sentence_valid = False
        elif not sentence:
            state["sentence_shape"]["empty_token_list"] += 1
            sentence_valid = False
        elif any(not isinstance(token, str) for token in sentence):
            state["sentence_shape"]["list_with_non_string_token"] += 1
            sentence_valid = False
        else:
            state["sentence_shape"]["list_of_string_tokens"] += 1
    if not sentence_valid:
        _document_error(state, strict, "SENTENCE_INVALID", "sentence is not a non-empty token list of strings", raw_doc_index)
        return None
    vertex_set = raw.get("vertexSet")
    if not isinstance(vertex_set, list):
        _document_error(state, strict, "VERTEX_SET_INVALID", "vertexSet is missing or non-list", raw_doc_index)
        return None
    labels_available = "labels" in raw
    labels = raw.get("labels")
    if split in ("train", "dev") and not isinstance(labels, list):
        _document_error(state, strict, "LABELS_INVALID", f"{split} labels are missing or non-list", raw_doc_index)
        return None
    if split == "test" and labels_available and not isinstance(labels, list):
        _document_error(state, strict, "TEST_LABELS_INVALID", "present test labels are non-list", raw_doc_index)
        return None
    if split == "test" and not labels_available:
        labels = []
    assert isinstance(labels, list)

    doc_id = f"redocred_{split}_{raw_doc_index:06d}"
    evidence = [{
        "id": f"sent_{doc_id}_{sent_id:03d}", "doc_id": doc_id, "sent_id": sent_id,
        "source": "redocred_sentence", "source_file": raw_file,
        "source_row_id": f"{doc_id}:sent:{sent_id:03d}", "text": " ".join(tokens), "tokens": list(tokens),
        "related_entities": [], "mention_ids": [], "timestamp": "", "reliability": 1.0,
        "metadata": {"title": title, "split": split, "sentence_index": sent_id, "source": source_name},
    } for sent_id, tokens in enumerate(sents)]

    entities: list[dict[str, Any]] = []
    local_mention_written = 0
    for entity_index, raw_entity in enumerate(vertex_set):
        if not isinstance(raw_entity, list):
            _document_error(state, strict, "ENTITY_ENTRY_INVALID", "entity entry is not a list", raw_doc_index)
            return None
        state["mention_count_raw"] += len(raw_entity)
        valid_mentions: list[dict[str, Any]] = []
        aliases: list[str] = []
        alias_seen: set[str] = set()
        selected_type: str | None = None
        type_conflicts: list[str] = []
        entity_id = f"ent_{doc_id}_{entity_index:03d}"
        for mention_index, raw_mention in enumerate(raw_entity):
            _observe_keys(state["mention_fields"], state["mention_seen"], raw_mention)
            if not isinstance(raw_mention, dict):
                _mention_error(state, strict, "MENTION_NAME_INVALID", "mention is not an object", raw_doc_index, entity_index, mention_index)
                continue
            name = raw_mention.get("name")
            if not isinstance(name, str) or not name:
                _mention_error(state, strict, "MENTION_NAME_INVALID", "mention name is missing, empty, or non-string", raw_doc_index, entity_index, mention_index)
                continue
            sent_id = raw_mention.get("sent_id")
            if type(sent_id) is not int or not 0 <= sent_id < len(sents):
                _mention_error(state, strict, "MENTION_SENT_ID_INVALID", "mention sent_id is invalid", raw_doc_index, entity_index, mention_index)
                continue
            pos = raw_mention.get("pos")
            if not isinstance(pos, list) or len(pos) != 2 or any(type(v) is not int for v in pos):
                _mention_error(state, strict, "MENTION_POS_INVALID", "mention pos is malformed", raw_doc_index, entity_index, mention_index)
                continue
            if not 0 <= pos[0] < pos[1] <= len(sents[sent_id]):
                _mention_error(state, strict, "MENTION_SPAN_OUT_OF_RANGE", "mention span is outside sentence tokens", raw_doc_index, entity_index, mention_index)
                continue
            raw_type = raw_mention.get("type")
            mention_type = raw_type if isinstance(raw_type, str) and raw_type else "UNKNOWN"
            if mention_type != "UNKNOWN":
                if selected_type is None:
                    selected_type = mention_type
                elif mention_type != selected_type:
                    type_conflicts.append(mention_type)
                    _diagnostic(state, "ENTITY_TYPE_CONFLICT", "warning", "entity", f"conflicting type: {mention_type}", raw_doc_index, entity_index, mention_index)
            if name not in alias_seen:
                alias_seen.add(name)
                aliases.append(name)
            mention_id = f"men_{doc_id}_{entity_index:03d}_{mention_index:03d}"
            valid_mentions.append({
                "mention_id": mention_id, "local_mention_index": mention_index, "name": name, "sent_id": sent_id,
                "sentence_id": evidence[sent_id]["id"], "pos": list(pos), "type": mention_type,
            })
            evidence[sent_id]["mention_ids"].append(mention_id)
        if not valid_mentions:
            _document_error(state, strict, "ENTITY_NO_VALID_MENTION", "entity has no valid mention", raw_doc_index)
            return None
        if selected_type is None:
            selected_type = "UNKNOWN"
            _diagnostic(state, "ENTITY_TYPE_UNKNOWN", "warning", "entity", "entity has no valid mention type", raw_doc_index, entity_index)
        mentioned_sentences: set[int] = set()
        for mention in valid_mentions:
            sent_id = mention["sent_id"]
            if sent_id not in mentioned_sentences:
                mentioned_sentences.add(sent_id)
                evidence[sent_id]["related_entities"].append(entity_id)
        local_mention_written += len(valid_mentions)
        entities.append({
            "id": entity_id, "doc_id": doc_id, "local_entity_index": entity_index, "type": selected_type,
            "name": valid_mentions[0]["name"], "aliases": aliases, "mentions": valid_mentions,
            "properties": {
                "source": "vertexSet", "mention_count": len(raw_entity), "valid_mention_count": len(valid_mentions),
                "raw_entity_index": entity_index, "type_conflicts": type_conflicts,
            },
        })

    state["label_count_raw"] += len(labels)
    merged: list[dict[str, Any]] = []
    positions: dict[tuple[int, str, int], int] = {}
    for label_index, label_obj in enumerate(labels):
        _observe_keys(state["label_fields"], state["label_seen"], label_obj)
        if isinstance(label_obj, dict):
            state["raw_label_objects"] += 1
            if "evidence" not in label_obj:
                state["all_evidence_fields"] = False
        if not isinstance(label_obj, dict) or any(field not in label_obj for field in ("h", "t", "r")):
            if strict:
                _raise("LABEL_REQUIRED_FIELD_MISSING", f"label {label_index} lacks h/t/r", "label")
            _diagnostic(state, "LABEL_REQUIRED_FIELD_MISSING", "error", "label", "label lacks h/t/r", raw_doc_index, label=label_index)
            state["skipped_label_count"] += 1
            continue
        h, t, relation = label_obj["h"], label_obj["t"], label_obj["r"]
        if type(h) is not int or type(t) is not int or not 0 <= h < len(entities) or not 0 <= t < len(entities):
            if strict:
                _raise("LABEL_ENTITY_INDEX_INVALID", f"label {label_index} has invalid h/t", "label")
            _diagnostic(state, "LABEL_ENTITY_INDEX_INVALID", "error", "label", "label h/t is invalid", raw_doc_index, label=label_index)
            state["skipped_label_count"] += 1
            continue
        if not isinstance(relation, str) or not relation:
            if strict:
                _raise("LABEL_REQUIRED_FIELD_MISSING", f"label {label_index} has invalid r", "label")
            _diagnostic(state, "LABEL_REQUIRED_FIELD_MISSING", "error", "label", "label r is invalid", raw_doc_index, label=label_index)
            state["skipped_label_count"] += 1
            continue
        if relation not in metadata:
            if strict:
                _raise("UNKNOWN_RELATION_ID", f"unknown relation_id: {relation}", "label")
            _diagnostic(state, "UNKNOWN_RELATION_ID", "error", "label", f"unknown relation_id: {relation}", raw_doc_index, label=label_index)
            state["skipped_label_count"] += 1
            if relation not in state["unknown_counts"]:
                state["unknown_order"].append(relation)
                state["unknown_counts"][relation] = 0
            state["unknown_counts"][relation] += 1
            continue
        status, valid_evidence, raw_evidence = _parse_evidence(label_obj, len(sents), state, strict, raw_doc_index, label_index)
        key = (h, relation, t)
        if key not in positions:
            positions[key] = len(merged)
            merged.append({
                "h": h, "t": t, "relation": relation, "statuses": [status], "evidence": list(valid_evidence),
                "raw_label_indices": [label_index], "raw_evidence_by_label": [raw_evidence],
            })
        else:
            state["duplicate_label_count"] += 1
            _diagnostic(state, "DUPLICATE_LABEL_MERGED", "warning", "label", "duplicate label merged", raw_doc_index, label=label_index)
            item = merged[positions[key]]
            item["statuses"].append(status)
            item["raw_label_indices"].append(label_index)
            item["raw_evidence_by_label"].append(raw_evidence)
            item["evidence"] = sorted(set(item["evidence"]) | set(valid_evidence))

    gold: list[dict[str, Any]] = []
    precedence = {"missing": 0, "empty": 1, "present": 2, "invalid": 3}
    for gold_index, item in enumerate(merged):
        status = max(item["statuses"], key=precedence.__getitem__)
        relation_row = metadata[item["relation"]]
        evidence_sent_ids = sorted(item["evidence"])
        gold.append({
            "gold_id": f"gold_{doc_id}_{gold_index:06d}", "doc_id": doc_id, "split": split,
            "head": entities[item["h"]]["id"], "head_index": item["h"], "head_name": entities[item["h"]]["name"],
            "relation": item["relation"], "relation_name": relation_row["relation_name"],
            "relation_description": relation_row["description"], "relation_aliases": list(relation_row["aliases"]),
            "tail": entities[item["t"]]["id"], "tail_index": item["t"], "tail_name": entities[item["t"]]["name"],
            "evidence_ids": [evidence[index]["id"] for index in evidence_sent_ids],
            "evidence_sent_ids": evidence_sent_ids, "evidence_annotation_status": status,
            "source": "redocred_label", "oracle_only": True,
            "metadata": {
                "raw_label_indices": item["raw_label_indices"], "raw_relation": item["relation"],
                "raw_evidence_by_label": item["raw_evidence_by_label"],
            },
        })
    document = {
        "doc_id": doc_id, "split": split, "title": title, "raw_doc_index": raw_doc_index,
        "sentence_ids": [row["id"] for row in evidence], "entity_ids": [row["id"] for row in entities],
        "label_count": len(gold),
        "metadata": {
            "source": source_name, "raw_file": raw_file, "sentence_count": len(evidence),
            "entity_count": len(entities), "raw_label_count": len(labels), "labels_available": labels_available,
        },
    }
    state["mention_count_written"] += local_mention_written
    return {"documents": [document], "entities": entities, "evidence": evidence, "gold": gold}


def _new_state(split: str, raw_file: str, strict: bool, raw_count: int) -> dict[str, Any]:
    return {
        "split": split, "raw_file": raw_file, "strict": strict, "document_count_raw": raw_count,
        "document_count_skipped": 0, "mention_count_raw": 0, "mention_count_written": 0,
        "label_count_raw": 0, "duplicate_label_count": 0, "skipped_label_count": 0,
        "diagnostics": [], "warning_counts": {}, "error_counts": {}, "warning_order": [],
        "unknown_counts": {}, "unknown_order": [], "top_level_fields": [], "top_level_seen": set(),
        "mention_fields": [], "mention_seen": set(), "label_fields": [], "label_seen": set(),
        "sentence_shape": {
            "list_of_string_tokens": 0, "empty_token_list": 0, "non_list": 0,
            "list_with_non_string_token": 0,
        },
        "raw_label_objects": 0, "all_evidence_fields": True,
    }


def _build_stats(
    state: dict[str, Any], documents: list[dict[str, Any]], entities: list[dict[str, Any]],
    evidence: list[dict[str, Any]], gold: list[dict[str, Any]],
) -> dict[str, Any]:
    relation_counts: dict[str, int] = {}
    status_counts = {"present": 0, "empty": 0, "missing": 0, "invalid": 0}
    for row in gold:
        relation_counts[row["relation"]] = relation_counts.get(row["relation"], 0) + 1
        status_counts[row["evidence_annotation_status"]] += 1
    return {
        "split": state["split"], "raw_file": state["raw_file"], "strict": state["strict"],
        "document_count_raw": state["document_count_raw"], "document_count_written": len(documents),
        "document_count_skipped": state["document_count_skipped"], "sentence_count": len(evidence),
        "entity_count": len(entities), "mention_count_raw": state["mention_count_raw"],
        "mention_count_written": state["mention_count_written"], "label_count_raw": state["label_count_raw"],
        "gold_triple_count": len(gold), "duplicate_label_count": state["duplicate_label_count"],
        "skipped_label_count": state["skipped_label_count"],
        "relations": {key: relation_counts[key] for key in sorted(relation_counts)},
        "unknown_relation_ids": [
            {"relation_id": key, "count": state["unknown_counts"][key], "split": state["split"]}
            for key in state["unknown_order"]
        ],
        "evidence": status_counts,
        "warning_counts": {key: state["warning_counts"][key] for key in sorted(state["warning_counts"])},
        "error_counts": {key: state["error_counts"][key] for key in sorted(state["error_counts"])},
        "diagnostics": state["diagnostics"],
    }


def _build_summary(
    state: dict[str, Any], documents: list[dict[str, Any]], metadata_count: int
) -> dict[str, Any]:
    labels_available = bool(documents) and all(row["metadata"]["labels_available"] for row in documents)
    evidence_available = state["raw_label_objects"] > 0 and state["all_evidence_fields"]
    return {
        "split": state["split"], "raw_file": state["raw_file"], "top_level_type": "list",
        "top_level_fields": state["top_level_fields"], "sentence_shape": state["sentence_shape"],
        "mention_fields": state["mention_fields"], "label_fields": state["label_fields"],
        "labels_available": labels_available, "evidence_field_available": evidence_available,
        "relation_metadata_path": "resources/redocred_relations.jsonl",
        "relation_metadata_record_count": metadata_count, "warnings": state["warning_order"],
    }


def _validate_schemas(records: dict[str, list[dict[str, Any]]], stats: dict[str, Any], summary: dict[str, Any]) -> None:
    for file_name, expected in RECORD_FIELDS.items():
        key = {"documents.jsonl": "documents", "entities.jsonl": "entities", "evidence.jsonl": "evidence", "gold_triples.jsonl": "gold"}[file_name]
        for row in records[key]:
            if tuple(row) != expected:
                _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", f"schema field order mismatch: {file_name}", "split")
    for row in records["documents"]:
        if tuple(row["metadata"]) != ("source", "raw_file", "sentence_count", "entity_count", "raw_label_count", "labels_available"):
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "document metadata schema mismatch", "split")
    for row in records["entities"]:
        if tuple(row["properties"]) != ("source", "mention_count", "valid_mention_count", "raw_entity_index", "type_conflicts"):
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "entity properties schema mismatch", "split")
        if any(tuple(mention) != ("mention_id", "local_mention_index", "name", "sent_id", "sentence_id", "pos", "type") for mention in row["mentions"]):
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "mention schema mismatch", "split")
    for row in records["evidence"]:
        if tuple(row["metadata"]) != ("title", "split", "sentence_index", "source"):
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "evidence metadata schema mismatch", "split")
    for row in records["gold"]:
        if tuple(row["metadata"]) != ("raw_label_indices", "raw_relation", "raw_evidence_by_label"):
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "gold metadata schema mismatch", "split")
    if tuple(stats) != STATS_FIELDS or tuple(summary) != SUMMARY_FIELDS:
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "diagnostic schema field order mismatch", "split")
    warning_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    for diagnostic in stats["diagnostics"]:
        target = warning_counts if diagnostic["severity"] == "warning" else error_counts
        target[diagnostic["code"]] = target.get(diagnostic["code"], 0) + 1
    if stats["warning_counts"] != {key: warning_counts[key] for key in sorted(warning_counts)}:
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "warning diagnostic counts mismatch", "split")
    if stats["error_counts"] != {key: error_counts[key] for key in sorted(error_counts)}:
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "error diagnostic counts mismatch", "split")
    if stats["document_count_raw"] != stats["document_count_written"] + stats["document_count_skipped"]:
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "document counts mismatch", "split")
    if stats["mention_count_written"] != sum(len(entity["mentions"]) for entity in records["entities"]):
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "mention counts mismatch", "split")
    if stats["label_count_raw"] != stats["gold_triple_count"] + stats["duplicate_label_count"] + stats["skipped_label_count"]:
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "label counts mismatch", "split")
    if sum(stats["relations"].values()) != stats["gold_triple_count"] or sum(stats["evidence"].values()) != stats["gold_triple_count"]:
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "gold diagnostic counts mismatch", "split")


def _validate_invariants(records: dict[str, list[dict[str, Any]]], metadata: dict[str, dict[str, Any]]) -> None:
    documents = {row["doc_id"]: row for row in records["documents"]}
    entities = {row["id"]: row for row in records["entities"]}
    evidence = {row["id"]: row for row in records["evidence"]}
    mentions = {m["mention_id"]: (entity, m) for entity in records["entities"] for m in entity["mentions"]}
    if any(len(index) != len(records[key]) for index, key in ((documents, "documents"), (entities, "entities"), (evidence, "evidence"))):
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "duplicate stable ID", "split")
    for entity in records["entities"]:
        if entity["doc_id"] not in documents or entity["id"] != f"ent_{entity['doc_id']}_{entity['local_entity_index']:03d}":
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "invalid entity foreign key or index", "split")
        for mention in entity["mentions"]:
            sentence = evidence.get(mention["sentence_id"])
            if sentence is None or sentence["doc_id"] != entity["doc_id"] or sentence["sent_id"] != mention["sent_id"]:
                _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "invalid mention sentence foreign key", "split")
            expected = f"men_{entity['doc_id']}_{entity['local_entity_index']:03d}_{mention['local_mention_index']:03d}"
            if mention["mention_id"] != expected:
                _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "invalid mention local index", "split")
    for document in records["documents"]:
        doc_evidence = [row["id"] for row in records["evidence"] if row["doc_id"] == document["doc_id"]]
        doc_entities = [row["id"] for row in records["entities"] if row["doc_id"] == document["doc_id"]]
        if document["sentence_ids"] != doc_evidence or document["entity_ids"] != doc_entities:
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "document ID lists do not close", "split")
    for sentence in records["evidence"]:
        if sentence["doc_id"] not in documents:
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "dangling evidence document", "split")
        for mention_id in sentence["mention_ids"]:
            pair = mentions.get(mention_id)
            if pair is None or pair[0]["doc_id"] != sentence["doc_id"] or pair[1]["sentence_id"] != sentence["id"]:
                _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "dangling evidence mention", "split")
        for entity_id in sentence["related_entities"]:
            entity = entities.get(entity_id)
            if entity is None or entity["doc_id"] != sentence["doc_id"] or not any(m["sentence_id"] == sentence["id"] for m in entity["mentions"]):
                _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "dangling related entity", "split")
    for row in records["gold"]:
        head, tail = entities.get(row["head"]), entities.get(row["tail"])
        if row["doc_id"] not in documents or head is None or tail is None or head["doc_id"] != row["doc_id"] or tail["doc_id"] != row["doc_id"]:
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "invalid gold entity foreign key", "split")
        if head["local_entity_index"] != row["head_index"] or tail["local_entity_index"] != row["tail_index"]:
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "invalid gold entity index", "split")
        if row["relation"] not in metadata:
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "unknown relation in gold output", "split")
        for sentence_id, sent_id in zip(row["evidence_ids"], row["evidence_sent_ids"]):
            sentence = evidence.get(sentence_id)
            if sentence is None or sentence["doc_id"] != row["doc_id"] or sentence["sent_id"] != sent_id:
                _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "invalid gold evidence foreign key", "split")


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    return "".join(json.dumps(row, ensure_ascii=False, separators=(", ", ": ")) + "\n" for row in rows).encode("utf-8")


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", f"BOM found: {path}", "split")
    if not raw:
        return []
    text = raw.decode("utf-8")
    if not text.endswith("\n") or "\r" in text:
        _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", f"invalid newline format: {path}", "split")
    rows = []
    for line in text.splitlines():
        if not line:
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", f"blank JSONL line: {path}", "split")
        value = json.loads(line)
        if not isinstance(value, dict):
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", f"non-object JSONL row: {path}", "split")
        rows.append(value)
    return rows


def _write_and_commit(
    output_dir: Path,
    split: str,
    records: dict[str, list[dict[str, Any]]],
    stats: dict[str, Any],
    summary: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
) -> None:
    target = output_dir / split
    temp_path: Path | None = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_path = Path(tempfile.mkdtemp(prefix=f".{split}.tmp-", dir=output_dir))
        payloads = {
            "documents.jsonl": _jsonl_bytes(records["documents"]),
            "entities.jsonl": _jsonl_bytes(records["entities"]),
            "evidence.jsonl": _jsonl_bytes(records["evidence"]),
            "gold_triples.jsonl": _jsonl_bytes(records["gold"]),
            "adapter_stats.json": _json_bytes(stats),
            "schema_summary.json": _json_bytes(summary),
        }
        for name in OUTPUT_FILES:
            (temp_path / name).write_bytes(payloads[name])
        parsed = {
            "documents": _parse_jsonl(temp_path / "documents.jsonl"),
            "entities": _parse_jsonl(temp_path / "entities.jsonl"),
            "evidence": _parse_jsonl(temp_path / "evidence.jsonl"),
            "gold": _parse_jsonl(temp_path / "gold_triples.jsonl"),
        }
        parsed_stats = json.loads((temp_path / "adapter_stats.json").read_text(encoding="utf-8"))
        parsed_summary = json.loads((temp_path / "schema_summary.json").read_text(encoding="utf-8"))
        _validate_schemas(parsed, parsed_stats, parsed_summary)
        _validate_invariants(parsed, metadata)
        if [len(parsed[key]) for key in ("documents", "entities", "evidence", "gold")] != [
            stats["document_count_written"], stats["entity_count"], stats["sentence_count"], stats["gold_triple_count"]
        ]:
            _raise("OUTPUT_WRITE_OR_VALIDATION_FAILED", "parse-back record counts mismatch", "split")
        if target.exists():
            target.rmdir()
        os.replace(temp_path, target)
        temp_path = None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _AdapterContractError("OUTPUT_WRITE_OR_VALIDATION_FAILED", f"output write or parse-back failed: {exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            shutil.rmtree(temp_path)


def process_split(
    split: str,
    raw_path: str | Path,
    output_dir: str | Path,
    metadata: dict[str, dict[str, Any]],
    strict: bool = True,
    max_docs: int | None = None,
    source_name: str = "Re-DocRED",
) -> dict[str, Any]:
    path = Path(raw_path)
    target = Path(output_dir) / split
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        _raise("OUTPUT_TARGET_NONEMPTY", f"output split directory is non-empty: {target}", "split")
    raw_documents = _load_raw_split(path)
    selected = raw_documents[:max_docs] if max_docs is not None else raw_documents
    state = _new_state(split, path.name, strict, len(selected))
    records: dict[str, list[dict[str, Any]]] = {"documents": [], "entities": [], "evidence": [], "gold": []}
    for raw_doc_index, raw in enumerate(selected):
        converted = _convert_document(raw, raw_doc_index, split, path.name, source_name, metadata, state, strict)
        if converted is None:
            continue
        for key in records:
            records[key].extend(converted[key])
    stats = _build_stats(state, records["documents"], records["entities"], records["evidence"], records["gold"])
    summary = _build_summary(state, records["documents"], len(metadata))
    _validate_schemas(records, stats, summary)
    _validate_invariants(records, metadata)
    _write_and_commit(Path(output_dir), split, records, stats, summary, metadata)
    return {"split": split, "output_dir": str(Path(output_dir) / split), "stats": stats}


def run_adapter(
    output_dir: str | Path = "data/redocred_processed",
    train_file: str | Path | None = None,
    dev_file: str | Path | None = None,
    test_file: str | Path | None = None,
    split: str | None = None,
    max_docs: int | None = None,
    source_name: str = "Re-DocRED",
    strict: bool = True,
    relation_metadata_path: str | Path = RELATION_METADATA_PATH,
) -> dict[str, Any]:
    metadata = load_relation_metadata(relation_metadata_path)
    selected = select_splits(train_file, dev_file, test_file, split)
    successful: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for split_name, path in selected:
        if not path.exists():
            error = _AdapterContractError("EXPLICIT_SPLIT_MISSING", f"explicit split file not found: {path}")
            if strict:
                raise error
            failed.append({"split": split_name, "code": error.code, "message": str(error)})
            continue
        try:
            successful.append(process_split(split_name, path, output_dir, metadata, strict, max_docs, source_name))
        except _AdapterContractError as exc:
            if strict:
                raise
            failed.append({"split": split_name, "code": exc.code, "message": str(exc)})
    return {"successful_splits": successful, "failed_splits": failed}


__all__ = ["load_relation_metadata", "process_split", "run_adapter", "select_splits"]
