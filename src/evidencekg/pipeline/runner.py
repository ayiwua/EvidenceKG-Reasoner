from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from evidencekg.candidate.generator import CandidateGenerator
from evidencekg.config.task_config import load_task_config
from evidencekg.eval.evaluator import Evaluator
from evidencekg.graph.graph_store import GraphStore
from evidencekg.io import read_jsonl, write_json, write_jsonl
from evidencekg.llm.reasoner import MockReasoner, RealLLMReasoner
from evidencekg.prompting.prompt_builder import PromptBuilder
from evidencekg.retrieval.evidence_retriever import EvidenceRetriever
from evidencekg.verify.verifier import Verifier
from tqdm import tqdm


class PipelineRunner:
    def run(
        self,
        config_path: str,
        data_dir: str,
        output_dir: str,
        stage: str = "all",
        max_candidates: int | None = None,
        candidate_offset: int = 0,
        disable_verifier: bool = False,
        debug_timing: bool = False,
        llm_timeout_seconds: float | None = None,
        llm_max_retries: int | None = None,
    ) -> dict[str, Any]:
        timing_events: list[dict[str, Any]] = []
        output_root = Path(output_dir)
        write_elapsed_total = 0.0

        stage_start = time.perf_counter()
        config = load_task_config(config_path)
        if llm_timeout_seconds is not None or llm_max_retries is not None:
            config = replace(
                config,
                llm=replace(
                    config.llm,
                    timeout_seconds=(
                        llm_timeout_seconds
                        if llm_timeout_seconds is not None
                        else config.llm.timeout_seconds
                    ),
                    max_retries=llm_max_retries if llm_max_retries is not None else config.llm.max_retries,
                ),
            )
        self._record_stage(timing_events, "load config", stage_start, debug_timing)

        stage_start = time.perf_counter()
        graph = GraphStore.from_dir(data_dir)
        self._record_stage(timing_events, "load graph", stage_start, debug_timing)

        stage_start = time.perf_counter()
        candidates = CandidateGenerator().generate(config, graph)
        self._record_stage(
            timing_events,
            "generate candidates",
            stage_start,
            debug_timing,
            {"candidate_count": len(candidates)},
        )
        write_start = time.perf_counter()
        write_jsonl(output_root / "candidate_pairs.jsonl", candidates)
        write_elapsed_total += time.perf_counter() - write_start
        if stage == "candidates":
            self._record_write_outputs(timing_events, write_elapsed_total, debug_timing)
            if debug_timing:
                write_jsonl(output_root / "timing_report.jsonl", timing_events)
            return {"candidate_count": len(candidates)}

        if candidate_offset < 0:
            raise ValueError("candidate_offset must be non-negative")
        candidate_window = candidates[candidate_offset:]
        reasoning_candidates = candidate_window[:max_candidates] if max_candidates is not None else candidate_window
        run_metadata = self._run_metadata(
            config_path=config_path,
            data_dir=data_dir,
            config=config,
            max_candidates=max_candidates,
            candidate_offset=candidate_offset,
            disable_verifier=disable_verifier,
            reasoning_candidate_ids=[item["candidate_id"] for item in reasoning_candidates],
        )
        resume_run = self._can_resume(output_root, run_metadata)
        if resume_run and debug_timing:
            print("[timing] resume=true matched run_metadata.json", flush=True)
            timing_path = output_root / "timing_report.jsonl"
            if timing_path.exists():
                timing_events.extend(read_jsonl(timing_path))
        if not resume_run:
            self._reset_incremental_outputs(output_root, debug_timing)
        write_json(output_root / "run_metadata.json", run_metadata)

        retriever = EvidenceRetriever()
        stage_start = time.perf_counter()
        contexts = [retriever.retrieve(candidate, config, graph) for candidate in reasoning_candidates]
        self._record_stage(
            timing_events,
            "retrieve evidence contexts",
            stage_start,
            debug_timing,
            {"context_count": len(contexts)},
        )
        write_start = time.perf_counter()
        write_jsonl(output_root / "evidence_contexts.jsonl", contexts)
        write_elapsed_total += time.perf_counter() - write_start

        prompt_builder = PromptBuilder()
        reasoner = self._build_reasoner(config, debug_timing=debug_timing)
        verifier = Verifier()
        context_by_id = {context["candidate_id"]: context for context in contexts}
        verified_predictions = (
            read_jsonl(output_root / "verified_predictions.jsonl")
            if resume_run and (output_root / "verified_predictions.jsonl").exists()
            else []
        )
        completed_candidate_ids = {item["candidate_id"] for item in verified_predictions}
        if resume_run and debug_timing:
            print(f"[timing] resume_completed_candidates={len(completed_candidate_ids)}", flush=True)
        reasoning_elapsed_total = 0.0
        verifier_elapsed_total = 0.0
        stage_reasoning_start = time.perf_counter()
        progress = tqdm(
            reasoning_candidates,
            desc=f"{config.llm.mode} reasoning",
            unit="candidate",
            dynamic_ncols=True,
            leave=False,
            disable=config.llm.mode != "real",
        )
        total = len(reasoning_candidates)
        for index, candidate in enumerate(progress, start=1):
            if candidate["candidate_id"] in completed_candidate_ids:
                if config.llm.mode == "real" and debug_timing:
                    tqdm.write(
                        "[timing] "
                        f"candidate={candidate['candidate_id']} index={index}/{total} resume_skip=true"
                    )
                continue
            candidate_total_start = time.perf_counter()
            if config.llm.mode == "real":
                model = os.environ.get(config.llm.model_env, config.llm.model)
                progress.set_description(f"real reasoning {candidate['candidate_id']}")
                progress.set_postfix_str(f"{candidate['head']} -> {candidate['tail']} | requesting", refresh=True)
                tqdm.write(
                    "[reasoning] "
                    f"candidate={candidate['candidate_id']} index={index}/{total} "
                    f"model={model} {candidate['head']} -> {candidate['tail']} | calling_llm"
                )
            built = prompt_builder.build(context_by_id[candidate["candidate_id"]])
            prompt_chars = len(built.get("prompt_text") or "")
            started_at = time.perf_counter()
            prediction = reasoner.predict(built["structured_context"], built["prompt_text"])
            reasoning_elapsed = time.perf_counter() - started_at
            reasoning_elapsed_total += reasoning_elapsed
            verify_start = time.perf_counter()
            if disable_verifier:
                verified = self._raw_prediction(candidate, prediction)
            else:
                verified = verifier.verify(candidate, built["structured_context"], prediction, config, graph)
            verify_elapsed = time.perf_counter() - verify_start
            verifier_elapsed_total += verify_elapsed
            verified["prediction_id"] = f"p_{len(verified_predictions) + 1:03d}"
            verified["source"] = "real_llm_inference" if config.llm.mode == "real" else "mock_llm_inference"
            verified_predictions.append(verified)
            self._append_jsonl(output_root / "verified_predictions.jsonl", verified)
            total_elapsed = time.perf_counter() - candidate_total_start
            metadata = getattr(reasoner, "last_metadata", {})
            candidate_timing = self._candidate_timing_event(
                index=index,
                total=total,
                candidate=candidate,
                model=os.environ.get(config.llm.model_env, config.llm.model),
                prompt_chars=prompt_chars,
                reasoning_elapsed=reasoning_elapsed,
                parse_elapsed=float(metadata.get("parse_elapsed_seconds", 0.0) or 0.0),
                verify_elapsed=verify_elapsed,
                total_elapsed=total_elapsed,
                prediction=verified,
                metadata=metadata,
            )
            timing_events.append(candidate_timing)
            if debug_timing:
                self._append_jsonl(output_root / "timing_report.jsonl", candidate_timing)
            if config.llm.mode == "real":
                elapsed = getattr(reasoner, "last_metadata", {}).get("elapsed_seconds")
                if elapsed is None:
                    elapsed = round(time.perf_counter() - started_at, 3)
                progress.set_postfix_str(
                    f"{candidate['head']} -> {candidate['tail']} | {verified['decision']}/{verified['verifier_status']}",
                    refresh=True,
                )
                warning = getattr(reasoner, "last_metadata", {}).get("warning", "")
                tqdm.write(
                    "[reasoning] "
                    f"candidate={candidate['candidate_id']} index={index}/{total} "
                    f"elapsed={float(elapsed):.2f}s decision={verified['decision']} "
                    f"confidence={verified['confidence']} verifier={verified['verifier_status']}"
                )
                if debug_timing:
                    tqdm.write(
                        "[timing] "
                        f"candidate={candidate['candidate_id']} index={index}/{total} "
                        f"triple={candidate['head']} {candidate['relation']} {candidate['tail']} "
                        f"model={model} prompt_chars={prompt_chars} "
                        f"request_start={candidate_timing['request_start']} "
                        f"response_received={candidate_timing['response_received']} "
                        f"llm_elapsed_sec={candidate_timing['llm_elapsed_sec']} "
                        f"parse_elapsed_sec={candidate_timing['parse_elapsed_sec']} "
                        f"verify_elapsed_sec={candidate_timing['verify_elapsed_sec']} "
                        f"total_elapsed_sec={candidate_timing['total_elapsed_sec']} "
                        f"decision={verified['decision']} confidence={verified['confidence']} "
                        f"verifier_status={verified['verifier_status']}"
                    )
                if warning:
                    tqdm.write(f"[reasoning][warning] candidate={candidate['candidate_id']} {warning}")

        self._record_stage(
            timing_events,
            "reasoning",
            stage_reasoning_start,
            debug_timing,
            {"candidate_count": len(reasoning_candidates), "llm_elapsed_sec": round(reasoning_elapsed_total, 3)},
        )
        timing_events.append(
            {
                "event": "stage",
                "stage": "verifier",
                "elapsed_sec": round(verifier_elapsed_total, 3),
                "candidate_count": len(reasoning_candidates),
            }
        )
        if debug_timing:
            print(f"[timing] stage=verifier elapsed_sec={verifier_elapsed_total:.3f}", flush=True)

        write_start = time.perf_counter()
        write_jsonl(output_root / "verified_predictions.jsonl", verified_predictions)
        predicted_edges = [
            item
            for item in verified_predictions
            if item["decision"] == "accept"
            and (item["verifier_status"] == "passed" or disable_verifier)
        ]
        write_jsonl(output_root / "predicted_edges.jsonl", predicted_edges)
        write_elapsed_total += time.perf_counter() - write_start

        stage_start = time.perf_counter()
        report = Evaluator().evaluate(
            output_root / "predicted_edges.jsonl",
            Path(data_dir) / config.evaluation.gold_file,
            output_root / "verified_predictions.jsonl",
        )
        self._record_stage(timing_events, "evaluation", stage_start, debug_timing)
        report["generated_candidate_count"] = len(candidates)
        report["reasoned_candidate_count"] = len(reasoning_candidates)
        report["candidate_offset"] = candidate_offset
        if disable_verifier:
            report.update(self._raw_prediction_risk_stats(verified_predictions, config, graph))
        self._record_write_outputs(timing_events, write_elapsed_total, debug_timing)
        write_json(output_root / "evaluation_report.json", report)
        if debug_timing:
            write_jsonl(output_root / "timing_report.jsonl", timing_events)
        return report

    def _build_reasoner(self, config: Any, debug_timing: bool = False) -> Any:
        if config.llm.mode == "mock":
            return MockReasoner()
        if config.llm.mode == "real":
            return RealLLMReasoner(config.llm, debug_timing=debug_timing)
        raise ValueError(f"unsupported llm.mode: {config.llm.mode}")

    def _record_stage(
        self,
        events: list[dict[str, Any]],
        stage: str,
        start: float,
        debug_timing: bool,
        extra: dict[str, Any] | None = None,
    ) -> None:
        elapsed = time.perf_counter() - start
        event = {"event": "stage", "stage": stage, "elapsed_sec": round(elapsed, 3)}
        if extra:
            event.update(extra)
        events.append(event)
        if debug_timing:
            details = " ".join(f"{key}={value}" for key, value in (extra or {}).items())
            print(f"[timing] stage={stage} elapsed_sec={elapsed:.3f} {details}".rstrip(), flush=True)

    def _record_write_outputs(
        self,
        events: list[dict[str, Any]],
        elapsed_total: float,
        debug_timing: bool,
    ) -> None:
        events.append({"event": "stage", "stage": "write outputs", "elapsed_sec": round(elapsed_total, 3)})
        if debug_timing:
            print(f"[timing] stage=write outputs elapsed_sec={elapsed_total:.3f}", flush=True)

    def _candidate_timing_event(
        self,
        index: int,
        total: int,
        candidate: dict[str, Any],
        model: str,
        prompt_chars: int,
        reasoning_elapsed: float,
        parse_elapsed: float,
        verify_elapsed: float,
        total_elapsed: float,
        prediction: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        attempts = metadata.get("client_attempts") or []
        first_attempt = attempts[0] if attempts else {}
        last_attempt = attempts[-1] if attempts else {}
        return {
            "event": "candidate",
            "index": index,
            "total": total,
            "candidate_id": candidate["candidate_id"],
            "head": candidate["head"],
            "relation": candidate["relation"],
            "tail": candidate["tail"],
            "model": model,
            "prompt_chars": prompt_chars,
            "request_start": first_attempt.get("request_start"),
            "response_received": last_attempt.get("response_received"),
            "llm_elapsed_sec": round(reasoning_elapsed, 3),
            "parse_elapsed_sec": round(parse_elapsed, 3),
            "verify_elapsed_sec": round(verify_elapsed, 3),
            "total_elapsed_sec": round(total_elapsed, 3),
            "decision": prediction["decision"],
            "confidence": prediction["confidence"],
            "verifier_status": prediction["verifier_status"],
            "error_type": metadata.get("error_type", ""),
            "warning": metadata.get("warning", ""),
            "attempt_count": metadata.get("attempts", 0),
            "attempts": attempts,
        }

    def _run_metadata(
        self,
        config_path: str,
        data_dir: str,
        config: Any,
        max_candidates: int | None,
        candidate_offset: int,
        disable_verifier: bool,
        reasoning_candidate_ids: list[str],
    ) -> dict[str, Any]:
        return {
            "config_path": str(config_path),
            "data_dir": str(data_dir),
            "llm_mode": config.llm.mode,
            "llm_provider": config.llm.provider,
            "llm_model": os.environ.get(config.llm.model_env, config.llm.model),
            "llm_timeout_seconds": config.llm.timeout_seconds,
            "llm_max_retries": config.llm.max_retries,
            "candidate_offset": candidate_offset,
            "max_candidates": max_candidates,
            "disable_verifier": disable_verifier,
            "reasoning_candidate_ids": reasoning_candidate_ids,
        }

    def _can_resume(self, output_root: Path, run_metadata: dict[str, Any]) -> bool:
        metadata_path = output_root / "run_metadata.json"
        verified_path = output_root / "verified_predictions.jsonl"
        if not metadata_path.exists() or not verified_path.exists():
            return False
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        return existing == run_metadata

    def _reset_incremental_outputs(self, output_root: Path, debug_timing: bool) -> None:
        output_root.mkdir(parents=True, exist_ok=True)
        for name in ["verified_predictions.jsonl", "predicted_edges.jsonl"]:
            (output_root / name).write_text("", encoding="utf-8")
        if debug_timing:
            (output_root / "timing_report.jsonl").write_text("", encoding="utf-8")

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _raw_prediction(self, candidate: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
        return {
            "prediction_id": "",
            "candidate_id": candidate["candidate_id"],
            "head": candidate["head"],
            "relation": candidate["relation"],
            "tail": candidate["tail"],
            "decision": prediction["decision"],
            "confidence": prediction["confidence"],
            "reason": prediction["reason"],
            "supporting_evidence_ids": prediction.get("supporting_evidence_ids", []),
            "verifier_status": "skipped",
            "verifier_details": {
                "schema_consistency": None,
                "evidence_grounding": None,
                "confidence_threshold": None,
                "conflict_check": None,
            },
            "source": "",
        }

    def _raw_prediction_risk_stats(
        self, predictions: list[dict[str, Any]], config: Any, graph: GraphStore
    ) -> dict[str, int]:
        evidence_ids = set(graph.evidence)
        accepted = [item for item in predictions if item.get("decision") == "accept"]
        seen: set[tuple[str, str, str]] = set()
        conflict_count = 0
        schema_violation_count = 0
        invalid_evidence_id_count = 0
        low_confidence_accept_count = 0
        for item in accepted:
            key = (item["head"], item["relation"], item["tail"])
            if key in seen:
                conflict_count += 1
            seen.add(key)
            head = graph.get_entity(item["head"]) or {}
            tail = graph.get_entity(item["tail"]) or {}
            if not config.is_allowed_pair(head.get("type", ""), tail.get("type", "")):
                schema_violation_count += 1
            if item.get("confidence", 0.0) < config.verifier.confidence_threshold:
                low_confidence_accept_count += 1
            for evidence_id in item.get("supporting_evidence_ids", []):
                if evidence_id not in evidence_ids:
                    invalid_evidence_id_count += 1
        return {
            "invalid_evidence_id_count": invalid_evidence_id_count,
            "low_confidence_accept_count": low_confidence_accept_count,
            "conflict_count": conflict_count,
            "schema_violation_count": schema_violation_count,
        }
