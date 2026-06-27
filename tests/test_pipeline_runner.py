from pathlib import Path

from evidencekg.io import read_jsonl
from evidencekg.pipeline.runner import PipelineRunner


def test_pipeline_runner_writes_expected_outputs(tmp_path):
    report = PipelineRunner().run("configs/task_owned_by.yaml", "data/sample", str(tmp_path))

    expected = [
        "candidate_pairs.jsonl",
        "evidence_contexts.jsonl",
        "verified_predictions.jsonl",
        "predicted_edges.jsonl",
        "evaluation_report.json",
    ]
    for name in expected:
        assert (tmp_path / name).exists()

    predicted = read_jsonl(tmp_path / "predicted_edges.jsonl")
    verified = read_jsonl(tmp_path / "verified_predictions.jsonl")
    assert predicted
    assert all(item["decision"] == "accept" and item["verifier_status"] == "passed" for item in predicted)
    assert any(item["decision"] == "reject" for item in verified)
    assert report["candidate_count"] == len(verified)


def test_pipeline_runner_limits_reasoning_without_limiting_generation(tmp_path):
    report = PipelineRunner().run(
        "configs/task_owned_by.yaml",
        "data/sample",
        str(tmp_path),
        max_candidates=5,
    )

    candidates = read_jsonl(tmp_path / "candidate_pairs.jsonl")
    contexts = read_jsonl(tmp_path / "evidence_contexts.jsonl")
    verified = read_jsonl(tmp_path / "verified_predictions.jsonl")

    assert len(candidates) == 102
    assert len(contexts) == 5
    assert len(verified) == 5
    assert report["generated_candidate_count"] == 102
    assert report["reasoned_candidate_count"] == 5
    assert report["candidate_offset"] == 0


def test_pipeline_runner_offsets_reasoning_window(tmp_path):
    report = PipelineRunner().run(
        "configs/task_owned_by.yaml",
        "data/sample",
        str(tmp_path),
        max_candidates=3,
        candidate_offset=40,
    )

    candidates = read_jsonl(tmp_path / "candidate_pairs.jsonl")
    contexts = read_jsonl(tmp_path / "evidence_contexts.jsonl")
    verified = read_jsonl(tmp_path / "verified_predictions.jsonl")

    assert len(candidates) == 102
    assert len(contexts) == 3
    assert len(verified) == 3
    assert contexts[0]["candidate_id"] == candidates[40]["candidate_id"]
    assert report["generated_candidate_count"] == 102
    assert report["reasoned_candidate_count"] == 3
    assert report["candidate_offset"] == 40


def test_pipeline_runner_disable_verifier_reports_raw_risks(tmp_path):
    report = PipelineRunner().run(
        "configs/task_owned_by.yaml",
        "data/sample",
        str(tmp_path),
        disable_verifier=True,
    )

    verified = read_jsonl(tmp_path / "verified_predictions.jsonl")

    assert verified
    assert all(item["verifier_status"] == "skipped" for item in verified)
    assert "invalid_evidence_id_count" in report
    assert report["invalid_evidence_id_count"] > 0


def test_pipeline_runner_debug_timing_writes_timing_report(tmp_path):
    PipelineRunner().run(
        "configs/task_owned_by.yaml",
        "data/sample",
        str(tmp_path),
        max_candidates=2,
        debug_timing=True,
    )

    timing = read_jsonl(tmp_path / "timing_report.jsonl")

    assert any(item.get("stage") == "load config" for item in timing)
    assert any(item.get("stage") == "load graph" for item in timing)
    assert any(item.get("stage") == "generate candidates" for item in timing)
    assert any(item.get("stage") == "retrieve evidence contexts" for item in timing)
    assert any(item.get("stage") == "reasoning" for item in timing)
    assert any(item.get("stage") == "verifier" for item in timing)
    assert any(item.get("stage") == "write outputs" for item in timing)
    assert any(item.get("stage") == "evaluation" for item in timing)
    assert sum(1 for item in timing if item.get("event") == "candidate") == 2


def test_pipeline_runner_writeback_writes_pending_report(tmp_path):
    report = PipelineRunner().run(
        "configs/task_owned_by.yaml",
        "data/sample",
        str(tmp_path),
        max_candidates=5,
        enable_writeback=True,
        writeback_mode="pending",
    )

    pending_path = tmp_path / "pending_edges.jsonl"
    writeback_report_path = tmp_path / "writeback_report.json"

    assert pending_path.exists()
    assert writeback_report_path.exists()
    assert "writeback" in report
    assert report["writeback"]["written_count"] == len(read_jsonl(pending_path))
