from evidencekg.eval.evaluator import Evaluator
from evidencekg.io import write_jsonl


def test_evaluator_metrics_only_use_predicted_edges(tmp_path):
    predicted = tmp_path / "predicted_edges.jsonl"
    verified = tmp_path / "verified_predictions.jsonl"
    gold = tmp_path / "gold_hidden_edges.jsonl"

    write_jsonl(predicted, [{"head": "h1", "relation": "r", "tail": "t1", "decision": "accept"}])
    write_jsonl(gold, [{"head": "h1", "relation": "r", "tail": "t1"}, {"head": "h2", "relation": "r", "tail": "t2"}])
    write_jsonl(
        verified,
        [
            {"decision": "accept", "verifier_status": "passed", "confidence": 0.8},
            {"decision": "reject", "verifier_status": "failed", "confidence": 0.4},
            {"decision": "uncertain", "verifier_status": "failed", "confidence": 0.6},
        ],
    )

    report = Evaluator().evaluate(predicted, gold, verified)

    assert report["precision"] == 1.0
    assert report["recall"] == 0.5
    assert report["f1"] == 0.6667
    assert report["accepted_count"] == 1
    assert report["rejected_count"] == 1
    assert report["uncertain_count"] == 1

