from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import evidencekg.data.redocred_adapter as adapter


ROOT = Path(__file__).resolve().parents[1]


def _metadata_row(relation_id: str = "P17") -> dict:
    return {
        "relation_id": relation_id,
        "wikidata_label": "country",
        "wikidata_description": "country of origin",
        "wikidata_aliases": ["state"],
        "relation_name": "country",
        "description": "The tail country is associated with the head entity.",
        "aliases": ["state"],
        "source": "wikidata_property_pages_and_external_rel_info_mapping_reviewed",
        "needs_review": False,
    }


def _write_metadata(path: Path, rows: list[dict] | None = None) -> Path:
    rows = rows or [_metadata_row()]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8", newline="\n")
    return path


def _document(evidence: object = (0,), relation: str = "P17") -> dict:
    label = {"h": 0, "t": 1, "r": relation}
    if evidence != "__missing__":
        label["evidence"] = list(evidence) if isinstance(evidence, tuple) else evidence
    return {
        "title": "Doc",
        "sents": [["Head", "relates", "to", "Tail", "."]],
        "vertexSet": [
            [{"name": "Head", "sent_id": 0, "pos": [0, 1], "type": "ORG"}],
            [{"name": "Tail", "sent_id": 0, "pos": [3, 4], "type": "LOC"}],
        ],
        "labels": [label],
    }


def _write_raw(path: Path, documents: list[object]) -> Path:
    path.write_text(json.dumps(documents, ensure_ascii=False), encoding="utf-8")
    return path


def _load_jsonl(path: Path) -> list[dict]:
    if path.stat().st_size == 0:
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _process(tmp_path: Path, document: dict, *, strict: bool = True, split: str = "dev") -> Path:
    raw = _write_raw(tmp_path / f"{split}.json", [document])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    out = tmp_path / "out"
    adapter.process_split(split, raw, out, metadata, strict=strict)
    return out / split


def test_load_relation_metadata_accepts_exact_schema(tmp_path):
    index = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    assert list(index) == ["P17"]
    assert index["P17"] == _metadata_row()


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("missing", "RELATION_METADATA_MISSING"),
        ("blank", "RELATION_METADATA_JSONL_INVALID"),
        ("json", "RELATION_METADATA_JSONL_INVALID"),
        ("field", "RELATION_METADATA_SCHEMA_INVALID"),
        ("type", "RELATION_METADATA_SCHEMA_INVALID"),
        ("duplicate", "RELATION_METADATA_DUPLICATE_ID"),
        ("review", "RELATION_METADATA_UNREVIEWED"),
    ],
)
def test_relation_metadata_startup_errors(tmp_path, case, code):
    path = tmp_path / "relations.jsonl"
    row = _metadata_row()
    if case == "blank":
        path.write_text(json.dumps(row) + "\n\n" + json.dumps(_metadata_row("P19")) + "\n", encoding="utf-8")
    elif case == "json":
        path.write_text("{bad}\n", encoding="utf-8")
    elif case == "field":
        row.pop("description")
        _write_metadata(path, [row])
    elif case == "type":
        row["aliases"] = "state"
        _write_metadata(path, [row])
    elif case == "duplicate":
        _write_metadata(path, [row, deepcopy(row)])
    elif case == "review":
        row["needs_review"] = True
        _write_metadata(path, [row])
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.load_relation_metadata(path)
    assert exc_info.value.code == code


def test_normal_conversion_schema_ids_and_relation_transfer(tmp_path):
    split_dir = _process(tmp_path, _document())
    documents = _load_jsonl(split_dir / "documents.jsonl")
    entities = _load_jsonl(split_dir / "entities.jsonl")
    evidence = _load_jsonl(split_dir / "evidence.jsonl")
    gold = _load_jsonl(split_dir / "gold_triples.jsonl")
    assert documents[0]["doc_id"] == "redocred_dev_000000"
    assert entities[0]["id"] == "ent_redocred_dev_000000_000"
    assert entities[0]["mentions"][0]["mention_id"] == "men_redocred_dev_000000_000_000"
    assert evidence[0]["id"] == "sent_redocred_dev_000000_000"
    assert evidence[0]["related_entities"] == [entities[0]["id"], entities[1]["id"]]
    assert gold[0]["gold_id"] == "gold_redocred_dev_000000_000000"
    assert gold[0]["relation_name"] == "country"
    assert gold[0]["relation_description"] == _metadata_row()["description"]
    assert gold[0]["relation_aliases"] == ["state"]
    assert set(path.name for path in split_dir.iterdir()) == set(adapter.OUTPUT_FILES)
    assert not (split_dir / "relations.jsonl").exists()
    assert not (split_dir / "candidates.jsonl").exists()


def test_alias_first_seen_case_sensitive_and_unknown_type(tmp_path):
    doc = _document()
    doc["vertexSet"][0] = [
        {"name": "Alpha", "sent_id": 0, "pos": [0, 1], "type": ""},
        {"name": "alpha", "sent_id": 0, "pos": [0, 1]},
        {"name": "Alpha", "sent_id": 0, "pos": [0, 1], "type": ""},
    ]
    split_dir = _process(tmp_path, doc)
    entity = _load_jsonl(split_dir / "entities.jsonl")[0]
    stats = json.loads((split_dir / "adapter_stats.json").read_text(encoding="utf-8"))
    assert entity["aliases"] == ["Alpha", "alpha"]
    assert entity["type"] == "UNKNOWN"
    assert stats["warning_counts"] == {"ENTITY_TYPE_UNKNOWN": 1}


@pytest.mark.parametrize("strict", [True, False])
def test_entity_type_conflict_strict_and_non_strict(tmp_path, strict):
    doc = _document()
    doc["vertexSet"][0].append({"name": "Head", "sent_id": 0, "pos": [0, 1], "type": "PERSON"})
    raw = _write_raw(tmp_path / "dev.json", [doc])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    output = tmp_path / ("strict" if strict else "loose")
    adapter.process_split("dev", raw, output, metadata, strict=strict)
    entity = _load_jsonl(output / "dev/entities.jsonl")[0]
    stats = json.loads((output / "dev/adapter_stats.json").read_text(encoding="utf-8"))
    assert entity["type"] == "ORG"
    assert entity["properties"]["type_conflicts"] == ["PERSON"]
    assert stats["warning_counts"] == {"ENTITY_TYPE_CONFLICT": 1}


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("name", "MENTION_NAME_INVALID"),
        ("missing_sent_id", "MENTION_SENT_ID_INVALID"),
        ("sent_id", "MENTION_SENT_ID_INVALID"),
        ("missing_pos", "MENTION_POS_INVALID"),
        ("pos", "MENTION_POS_INVALID"),
        ("span", "MENTION_SPAN_OUT_OF_RANGE"),
    ],
)
def test_malformed_mention_strict_and_non_strict(tmp_path, mutation, code):
    doc = _document()
    bad = {"name": "Bad", "sent_id": 0, "pos": [0, 1], "type": "ORG"}
    if mutation == "name":
        bad.pop("name")
    elif mutation == "missing_sent_id":
        bad.pop("sent_id")
    elif mutation == "sent_id":
        bad["sent_id"] = 5
    elif mutation == "missing_pos":
        bad.pop("pos")
    elif mutation == "pos":
        bad["pos"] = [0]
    else:
        bad["pos"] = [0, 99]
    doc["vertexSet"][0].insert(0, bad)
    raw = _write_raw(tmp_path / "dev.json", [doc])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split("dev", raw, tmp_path / "strict", metadata, strict=True)
    assert exc_info.value.code == code
    adapter.process_split("dev", raw, tmp_path / "loose", metadata, strict=False)
    entity = _load_jsonl(tmp_path / "loose/dev/entities.jsonl")[0]
    assert entity["mentions"][0]["local_mention_index"] == 1


@pytest.mark.parametrize("bad_sentence", ["text", [], ["ok", 1]])
def test_malformed_sentence_strict_and_non_strict(tmp_path, bad_sentence):
    doc = _document()
    doc["sents"] = [bad_sentence]
    raw = _write_raw(tmp_path / "dev.json", [doc])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split("dev", raw, tmp_path / "strict", metadata, strict=True)
    assert exc_info.value.code == "SENTENCE_INVALID"
    adapter.process_split("dev", raw, tmp_path / "loose", metadata, strict=False)
    assert _load_jsonl(tmp_path / "loose/dev/documents.jsonl") == []


@pytest.mark.parametrize(
    ("case", "code", "split"),
    [
        ("document", "DOCUMENT_NOT_OBJECT", "dev"),
        ("title", "DOCUMENT_TITLE_INVALID", "dev"),
        ("sents", "DOCUMENT_SENTS_INVALID", "dev"),
        ("vertex_set", "VERTEX_SET_INVALID", "dev"),
        ("entity_entry", "ENTITY_ENTRY_INVALID", "dev"),
        ("empty_entity", "ENTITY_NO_VALID_MENTION", "dev"),
        ("train_labels", "LABELS_INVALID", "train"),
        ("test_labels", "TEST_LABELS_INVALID", "test"),
    ],
)
def test_document_level_error_matrix_strict_and_non_strict(tmp_path, case, code, split):
    bad: object = _document()
    if case == "document":
        bad = []
    elif case == "title":
        bad.pop("title")
    elif case == "sents":
        bad["sents"] = "not-a-list"
    elif case == "vertex_set":
        bad["vertexSet"] = "not-a-list"
    elif case == "entity_entry":
        bad["vertexSet"][0] = {}
    elif case == "empty_entity":
        bad["vertexSet"][0] = []
    elif case in ("train_labels", "test_labels"):
        bad["labels"] = "not-a-list"
    raw = _write_raw(tmp_path / f"{split}.json", [bad, _document()])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split(split, raw, tmp_path / "strict", metadata, strict=True)
    assert exc_info.value.code == code
    assert not (tmp_path / "strict" / split).exists()
    adapter.process_split(split, raw, tmp_path / "loose", metadata, strict=False)
    documents = _load_jsonl(tmp_path / "loose" / split / "documents.jsonl")
    stats = json.loads((tmp_path / "loose" / split / "adapter_stats.json").read_text(encoding="utf-8"))
    assert [row["raw_doc_index"] for row in documents] == [1]
    assert stats["document_count_skipped"] == 1
    assert stats["error_counts"][code] == 1


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("missing_h", "LABEL_REQUIRED_FIELD_MISSING"),
        ("missing_t", "LABEL_REQUIRED_FIELD_MISSING"),
        ("missing_r", "LABEL_REQUIRED_FIELD_MISSING"),
        ("non_integer_h", "LABEL_ENTITY_INDEX_INVALID"),
        ("non_integer_t", "LABEL_ENTITY_INDEX_INVALID"),
        ("out_of_range_h", "LABEL_ENTITY_INDEX_INVALID"),
        ("out_of_range_t", "LABEL_ENTITY_INDEX_INVALID"),
    ],
)
def test_label_error_matrix_strict_and_non_strict(tmp_path, case, code):
    doc = _document()
    bad = deepcopy(doc["labels"][0])
    if case.startswith("missing_"):
        bad.pop(case.removeprefix("missing_"))
    elif case == "non_integer_h":
        bad["h"] = "0"
    elif case == "non_integer_t":
        bad["t"] = "1"
    elif case == "out_of_range_h":
        bad["h"] = 9
    else:
        bad["t"] = 9
    doc["labels"] = [bad, doc["labels"][0]]
    raw = _write_raw(tmp_path / "dev.json", [doc])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split("dev", raw, tmp_path / "strict", metadata, strict=True)
    assert exc_info.value.code == code
    adapter.process_split("dev", raw, tmp_path / "loose", metadata, strict=False)
    assert len(_load_jsonl(tmp_path / "loose/dev/gold_triples.jsonl")) == 1
    stats = json.loads((tmp_path / "loose/dev/adapter_stats.json").read_text(encoding="utf-8"))
    assert stats["skipped_label_count"] == 1
    assert stats["error_counts"][code] == 1


@pytest.mark.parametrize(
    ("raw_evidence", "code", "valid_indices"),
    [
        ("not-a-list", "EVIDENCE_VALUE_INVALID", []),
        ([0, "bad"], "EVIDENCE_INDEX_INVALID", [0]),
        ([0, 9], "EVIDENCE_INDEX_INVALID", [0]),
    ],
)
def test_invalid_evidence_error_matrix_strict_and_non_strict(tmp_path, raw_evidence, code, valid_indices):
    doc = _document()
    doc["labels"][0]["evidence"] = raw_evidence
    raw = _write_raw(tmp_path / "dev.json", [doc])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split("dev", raw, tmp_path / "strict", metadata, strict=True)
    assert exc_info.value.code == code
    adapter.process_split("dev", raw, tmp_path / "loose", metadata, strict=False)
    gold = _load_jsonl(tmp_path / "loose/dev/gold_triples.jsonl")
    assert gold[0]["evidence_annotation_status"] == "invalid"
    assert gold[0]["evidence_sent_ids"] == valid_indices
    stats = json.loads((tmp_path / "loose/dev/adapter_stats.json").read_text(encoding="utf-8"))
    assert stats["error_counts"][code] == 1


@pytest.mark.parametrize(
    ("evidence", "strict", "status"),
    [
        ((0,), True, "present"),
        ((), True, "empty"),
        ("__missing__", True, "missing"),
        (None, True, "missing"),
        ("invalid", False, "invalid"),
        ([0, 8], False, "invalid"),
    ],
)
def test_evidence_annotation_states(tmp_path, evidence, strict, status):
    split_dir = _process(tmp_path, _document(evidence), strict=strict)
    gold = _load_jsonl(split_dir / "gold_triples.jsonl")
    assert gold[0]["evidence_annotation_status"] == status
    assert gold[0]["evidence_sent_ids"] == ([0] if evidence in ((0,), [0, 8]) else [])


def test_duplicate_merge_order_evidence_union_and_status_precedence(tmp_path):
    doc = _document(())
    doc["labels"] = [
        {"h": 0, "t": 1, "r": "P17"},
        {"h": 0, "t": 1, "r": "P17", "evidence": []},
        {"h": 0, "t": 1, "r": "P17", "evidence": [0]},
        {"h": 0, "t": 1, "r": "P17", "evidence": [0, 9]},
    ]
    split_dir = _process(tmp_path, doc, strict=False)
    gold = _load_jsonl(split_dir / "gold_triples.jsonl")
    stats = json.loads((split_dir / "adapter_stats.json").read_text(encoding="utf-8"))
    assert len(gold) == 1
    assert gold[0]["metadata"]["raw_label_indices"] == [0, 1, 2, 3]
    assert gold[0]["evidence_sent_ids"] == [0]
    assert gold[0]["evidence_annotation_status"] == "invalid"
    assert stats["duplicate_label_count"] == 3


def test_unknown_relation_strict_and_non_strict(tmp_path):
    doc = _document(relation="P999999")
    raw = _write_raw(tmp_path / "dev.json", [doc])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split("dev", raw, tmp_path / "strict", metadata, strict=True)
    assert exc_info.value.code == "UNKNOWN_RELATION_ID"
    adapter.process_split("dev", raw, tmp_path / "loose", metadata, strict=False)
    assert _load_jsonl(tmp_path / "loose/dev/gold_triples.jsonl") == []
    stats = json.loads((tmp_path / "loose/dev/adapter_stats.json").read_text(encoding="utf-8"))
    assert stats["unknown_relation_ids"] == [{"relation_id": "P999999", "count": 1, "split": "dev"}]


def test_test_without_labels_writes_empty_gold(tmp_path):
    doc = _document()
    doc.pop("labels")
    split_dir = _process(tmp_path, doc, split="test")
    assert (split_dir / "gold_triples.jsonl").read_bytes() == b""
    summary = json.loads((split_dir / "schema_summary.json").read_text(encoding="utf-8"))
    assert summary["labels_available"] is False


def test_deterministic_bytes_and_lf(tmp_path):
    raw = _write_raw(tmp_path / "dev.json", [_document()])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    adapter.process_split("dev", raw, tmp_path / "one", metadata)
    adapter.process_split("dev", raw, tmp_path / "two", metadata)
    for name in adapter.OUTPUT_FILES:
        first = (tmp_path / "one/dev" / name).read_bytes()
        second = (tmp_path / "two/dev" / name).read_bytes()
        assert first == second
        assert not first.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in first
        assert first.endswith(b"\n")


def test_nonempty_target_is_not_overwritten(tmp_path):
    raw = _write_raw(tmp_path / "train.json", [_document()])
    dev_raw = _write_raw(tmp_path / "dev.json", [_document()])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))
    target = tmp_path / "out/train"
    target.mkdir(parents=True)
    old = target / "old.txt"
    old.write_bytes(b"keep")
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split("train", raw, tmp_path / "out", metadata)
    assert exc_info.value.code == "OUTPUT_TARGET_NONEMPTY"
    assert old.read_bytes() == b"keep"
    result = adapter.run_adapter(
        output_dir=tmp_path / "out", train_file=raw, dev_file=dev_raw, strict=False,
        relation_metadata_path=tmp_path / "relations.jsonl",
    )
    assert result["failed_splits"][0]["code"] == "OUTPUT_TARGET_NONEMPTY"
    assert result["successful_splits"][0]["split"] == "dev"
    assert (tmp_path / "out/dev/documents.jsonl").exists()


def test_write_failure_removes_temporary_output(tmp_path, monkeypatch):
    raw = _write_raw(tmp_path / "dev.json", [_document()])
    metadata = adapter.load_relation_metadata(_write_metadata(tmp_path / "relations.jsonl"))

    def fail_replace(source, target):
        raise OSError("injected")

    monkeypatch.setattr(adapter.os, "replace", fail_replace)
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.process_split("dev", raw, tmp_path / "out", metadata)
    assert exc_info.value.code == "OUTPUT_WRITE_OR_VALIDATION_FAILED"
    assert not (tmp_path / "out/dev").exists()
    assert list((tmp_path / "out").glob(".dev.tmp-*")) == []


def test_non_strict_write_failure_continues(tmp_path, monkeypatch):
    train = _write_raw(tmp_path / "train.json", [_document()])
    dev = _write_raw(tmp_path / "dev.json", [_document()])
    metadata_path = _write_metadata(tmp_path / "relations.jsonl")
    real_replace = adapter.os.replace
    calls = 0

    def fail_first_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected")
        return real_replace(source, target)

    monkeypatch.setattr(adapter.os, "replace", fail_first_replace)
    result = adapter.run_adapter(
        output_dir=tmp_path / "out", train_file=train, dev_file=dev, strict=False,
        relation_metadata_path=metadata_path,
    )
    assert result["failed_splits"][0]["code"] == "OUTPUT_WRITE_OR_VALIDATION_FAILED"
    assert result["successful_splits"][0]["split"] == "dev"
    assert not (tmp_path / "out/train").exists()
    assert (tmp_path / "out/dev/documents.jsonl").exists()


@pytest.mark.parametrize(
    ("bad_text", "code"),
    [
        ("{bad}", "RAW_JSON_INVALID"),
        ("{}", "RAW_TOP_LEVEL_INVALID"),
    ],
)
def test_raw_split_failure_strict_stops_and_non_strict_continues(tmp_path, bad_text, code):
    bad = tmp_path / "train.json"
    bad.write_text(bad_text, encoding="utf-8")
    good = _write_raw(tmp_path / "dev.json", [_document()])
    metadata_path = _write_metadata(tmp_path / "relations.jsonl")
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.run_adapter(
            output_dir=tmp_path / "strict", train_file=bad, dev_file=good, strict=True,
            relation_metadata_path=metadata_path,
        )
    assert exc_info.value.code == code
    assert not (tmp_path / "strict/dev").exists()
    result = adapter.run_adapter(
        output_dir=tmp_path / "out", train_file=bad, dev_file=good, strict=False,
        relation_metadata_path=metadata_path,
    )
    assert result["failed_splits"][0]["code"] == code
    assert result["successful_splits"][0]["split"] == "dev"
    assert (tmp_path / "out/dev/documents.jsonl").exists()


def test_explicit_missing_split_strict_stops_and_non_strict_continues(tmp_path):
    missing = tmp_path / "missing-train.json"
    dev = _write_raw(tmp_path / "dev.json", [_document()])
    metadata_path = _write_metadata(tmp_path / "relations.jsonl")
    with pytest.raises(adapter._AdapterContractError) as exc_info:
        adapter.run_adapter(
            output_dir=tmp_path / "strict", train_file=missing, dev_file=dev, strict=True,
            relation_metadata_path=metadata_path,
        )
    assert exc_info.value.code == "EXPLICIT_SPLIT_MISSING"
    assert not (tmp_path / "strict/dev").exists()
    result = adapter.run_adapter(
        output_dir=tmp_path / "loose", train_file=missing, dev_file=dev, strict=False,
        relation_metadata_path=metadata_path,
    )
    assert result["failed_splits"][0]["code"] == "EXPLICIT_SPLIT_MISSING"
    assert result["successful_splits"][0]["split"] == "dev"


def test_cli_smoke(tmp_path):
    raw = _write_raw(tmp_path / "dev.json", [_document()])
    output = tmp_path / "out"
    completed = subprocess.run(
        [
            sys.executable, "scripts/build_redocred_dataset.py", "--dev-file", str(raw),
            "--output-dir", str(output), "--strict", "true",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert set(path.name for path in (output / "dev").iterdir()) == set(adapter.OUTPUT_FILES)


@pytest.mark.parametrize("split", ["train", "dev", "test"])
def test_official_split_smoke_contract(tmp_path, split):
    raw = ROOT / f"data/raw/redocred/{split}_revised.json"
    if not raw.exists():
        pytest.skip(f"official {split} split is unavailable")
    metadata = adapter.load_relation_metadata(ROOT / "resources/redocred_relations.jsonl")
    adapter.process_split(split, raw, tmp_path, metadata, strict=True, max_docs=5)
    assert set(path.name for path in (tmp_path / split).iterdir()) == set(adapter.OUTPUT_FILES)


@pytest.mark.parametrize("split", ["train", "dev", "test"])
def test_official_split_full_contract_non_strict(tmp_path, split):
    raw = ROOT / f"data/raw/redocred/{split}_revised.json"
    if not raw.exists():
        pytest.skip(f"official {split} split is unavailable")
    metadata = adapter.load_relation_metadata(ROOT / "resources/redocred_relations.jsonl")
    result = adapter.process_split(split, raw, tmp_path, metadata, strict=False)
    assert result["stats"]["document_count_written"] > 0
    assert result["stats"]["document_count_skipped"] == 0
    assert result["stats"]["error_counts"] == {}
    assert set(path.name for path in (tmp_path / split).iterdir()) == set(adapter.OUTPUT_FILES)
