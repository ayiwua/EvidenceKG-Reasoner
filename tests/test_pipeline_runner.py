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
