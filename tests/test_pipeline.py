"""Synthetic pipeline mechanics only; these fixtures never prove Skill gain."""
import json
import threading
from pathlib import Path

import pytest

import skill_observatory.pipeline as pipeline_module
from skill_observatory.final_gate import finalize, seal_owner_receipt
from skill_observatory.installations import grant_owner, validate_verdict
from skill_observatory.outcomes import accept_task_result, run_binding, seal_task_receipt
from skill_observatory.pipeline import EvolutionPipeline
from skill_observatory.runtime import register
from skill_observatory.store import Store, canonical, digest


def add_case(tmp_path, store, suffix, decision="CANDIDATE"):
    root = tmp_path / f"owned-{suffix}"
    root.mkdir()
    target = root / "SKILL.md"
    target.write_bytes(b"parent fixture")
    skill = register(store, root, "skill-evolution-loop")
    evidence = store.artifact(
        b"synthetic mechanics authorization; not a real improvement grant"
    )
    grant_owner(
        store,
        target,
        f"authority-{suffix}",
        evidence,
        "2099-01-01T00:00:00+00:00",
    )
    run_id = f"run-{suffix}"
    run = {
        "id": run_id,
        "session_id": f"session-{suffix}",
        "turn_id": f"turn-{suffix}",
        "agent_id": None,
        "origin": "user_run",
        "status": "ready",
        "outcome": "unverified",
        "event_ids": [f"event-{suffix}"],
        "attributions": [
            {
                "skill_id": skill["id"],
                "package_sha256": skill["package_sha256"],
                "attribution": "explicit_loaded",
            }
        ],
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    store.put("runs", run)
    review_id = f"rv_{suffix}"
    review = {
        "id": review_id,
        "schema_version": 1,
        "review_id": review_id,
        "run_id": run_id,
        "skill_id": skill["id"],
        "skill_package_sha256": skill["package_sha256"],
        "attribution": "explicit_loaded",
        "coverage": {"tools": "partial", "outcome": "unverified"},
        "outcome": {"status": "unverified", "source": "runtime_only"},
        "findings": [],
        "decision": decision,
        "missing": [],
        "evidence_manifest_sha256": store.artifact(canonical(run)),
        "reviewer_version": "fixture-reviewer-v1",
        "status": "reviewed",
        "created_at": "2026-01-01T00:00:01+00:00",
    }
    store.put("reviews", review)
    return {"store": store, "skill": skill, "target": target, "review": review}


def fixture_proposer(include_costs=True):
    calls = []

    def proposer(review_bytes, parent_bytes):
        calls.append((json.loads(review_bytes), parent_bytes))
        result = {
            "candidate_bytes": b"candidate fixture",
            "candidate_sha256": digest(b"candidate fixture"),
            "owner_incident_id": "incident-fixture",
            "proposer_method_version_id": "fixture-proposer-v1",
        }
        if include_costs:
            result["cost_attempt_ids"] = ["proposal-fixture-attempt"]
        return result

    return proposer, calls


def final_gate_evaluator(store):
    """Trusted fixture adapter that compiles a deliberately synthetic gate."""

    def evaluator(payload):
        candidate = store.get("candidates", payload["candidate_id"])
        protocol = {
            "id": "protocol-fixture",
            "arm_files": {
                "parent": {"SKILL.md": candidate["parent_sha256"]},
                "candidate": {"SKILL.md": candidate["candidate_sha256"]},
            },
            "oracle_sha256": store.artifact(b"fixture oracle"),
            "activation_oracle_sha256": store.artifact(
                b"fixture activation oracle"
            ),
            "cases": [{"id": "case-fixture", "split": "final"}],
            "min_gain": 0,
            "synthetic": False,
            "final_exposed": False,
            "model": "fixture-model",
            "max_verified_effort": "fixture-effort",
            "cost_limits": {"money": 1, "tokens": 1, "wall_seconds": 2},
        }
        protocol_sha256 = digest(canonical(protocol))
        evaluation = {
            "id": "evaluation-fixture",
            "protocol_id": protocol["id"],
            "protocol_sha256": protocol_sha256,
            "attempt_id": "evaluation-fixture-attempt",
            "missing": [
                "DOMAIN_GUARDRAIL_RECEIPT_REQUIRED",
                "COST_COVERAGE_REQUIRED",
            ],
            "paired_gain_lower_bound": 0.1,
        }
        evaluation_sha256 = store.artifact(canonical(evaluation))
        store.put("protocols", protocol)
        store.put("evaluations", evaluation)
        store.put(
            "evaluation_attempts",
            {
                "id": evaluation["attempt_id"],
                "result_sha256": evaluation_sha256,
            },
        )
        common = {
            "evaluation_sha256": evaluation_sha256,
            "protocol_sha256": protocol_sha256,
            "evidence_sha256": protocol["oracle_sha256"],
        }
        domain = seal_owner_receipt(
            store,
            "domain",
            {
                **common,
                "case_ids": ["case-fixture"],
                "oracle_sha256": protocol["oracle_sha256"],
                "independent_final": True,
                "comparable": True,
                "guardrails_pass": True,
                "regressions_pass": True,
                "regression_case_ids": ["case-fixture"],
                "guardrail_case_ids": ["case-fixture"],
            },
        )
        attempt_ids = [evaluation["attempt_id"], *candidate.get("cost_attempt_ids", [])]
        cost = seal_owner_receipt(
            store,
            "cost",
            {
                **common,
                "all_attempts_covered": True,
                "budget_pass": True,
                "attempt_ids": attempt_ids,
                "money": 0,
                "tokens": 0,
                "wall_seconds": 1,
            },
        )
        return finalize(
            store,
            candidate["id"],
            evaluation["id"],
            domain,
            cost,
        )

    return evaluator


class FakeInstaller:
    calls = []

    def apply(self, store, candidate_id):
        FakeInstaller.calls.append(candidate_id)
        candidate = store.get("candidates", candidate_id)
        validate_verdict(store, store.get("verdicts", candidate["verdict_id"]))
        target = Path(candidate["target"])
        target.write_bytes(store.read_artifact(candidate["candidate_sha256"]))
        installation = {
            "id": "owner_inst_" + candidate_id,
            "owner": "skill-evolution-loop",
            "owner_incident_id": candidate["owner_incident_id"],
            "candidate_id": candidate_id,
            "target": str(target),
            "before_sha256": candidate["parent_sha256"],
            "after_sha256": candidate["candidate_sha256"],
            "status": "activation_pending",
            "activated": False,
            "live_verified": False,
            "created_at": "2026-01-02T00:00:00+00:00",
        }
        return store.put("installations", installation)


def test_deterministic_candidate_queue_processes_first_review(tmp_path):
    store = Store(tmp_path / "state")
    add_case(tmp_path, store, "b")
    add_case(tmp_path, store, "a")
    proposer, calls = fixture_proposer()
    pipeline = EvolutionPipeline(store, proposer=proposer)
    queued = pipeline.tick()
    assert queued["state"] == "experiment_ready" and queued["review_id"] == "rv_a"
    assert len(store.list("experiments")) == 1
    assert pipeline.tick()["state"] == "candidate_ready"
    assert calls[0][0]["id"] == "rv_a"
    assert len(store.list("experiments")) == 1


def test_no_change_does_not_wake_proposer(tmp_path):
    store = Store(tmp_path / "state")
    add_case(tmp_path, store, "case", decision="NO_CHANGE")
    proposer, calls = fixture_proposer()
    assert EvolutionPipeline(store, proposer=proposer).tick() is None
    assert calls == [] and store.list("experiments") == []


def test_paused_operation_retains_state(tmp_path):
    store = Store(tmp_path / "state")
    add_case(tmp_path, store, "case")
    store.settings({"paused": True})
    proposer, calls = fixture_proposer()
    assert EvolutionPipeline(store, proposer=proposer).tick() is None
    assert calls == [] and store.list("experiments") == []


def test_parent_drift_blocks_proposer_and_preserves_user_write(tmp_path):
    case = add_case(tmp_path, Store(tmp_path / "state"), "case")
    store = case["store"]
    proposer, calls = fixture_proposer()
    pipeline = EvolutionPipeline(store, proposer=proposer)
    assert pipeline.tick()["state"] == "experiment_ready"
    case["target"].write_bytes(b"user drift")
    assert pipeline.tick()["state"] == "held"
    assert pipeline.tick() is None
    stage = store.list("experiments")[0]
    assert stage["reason_code"] == "PARENT_PACKAGE_DRIFT"
    assert case["target"].read_bytes() == b"user drift"
    assert calls == []


def test_unsigned_verdict_refusal_does_not_reach_installer(tmp_path, monkeypatch):
    case = add_case(tmp_path, Store(tmp_path / "state"), "case")
    store = case["store"]
    proposer, _ = fixture_proposer()

    def unsigned_evaluator(payload):
        return {
            "id": "verdict-forged",
            "status": "accepted",
            "candidate_id": payload["candidate_id"],
            "parent_sha256": payload["parent_sha256"],
            "candidate_sha256": payload["candidate_sha256"],
            "protocol_id": "protocol-fixture",
            "protocol_sha256": "0" * 64,
            "gates": {gate: True for gate in (
                "authorization_matches",
                "hashes_current",
                "comparable",
                "independent_final",
                "coverage_sufficient",
                "gain_pass",
                "guardrails_pass",
                "regressions_pass",
                "budget_pass",
            )},
        }

    monkeypatch.setattr(pipeline_module, "SkillEvolutionInstaller", FakeInstaller)
    FakeInstaller.calls.clear()
    pipeline = EvolutionPipeline(store, proposer=proposer, evaluator=unsigned_evaluator)
    pipeline.tick()
    pipeline.tick()
    result = pipeline.tick()
    assert result["state"] == "held"
    assert result["reason_code"] == "VERDICT_UNTRUSTED"
    assert FakeInstaller.calls == []
    assert case["target"].read_bytes() == b"parent fixture"


def test_missing_exploration_cost_stays_hold(tmp_path, monkeypatch):
    case = add_case(tmp_path, Store(tmp_path / "state"), "case")
    store = case["store"]
    proposer, _ = fixture_proposer(include_costs=False)
    monkeypatch.setattr(pipeline_module, "SkillEvolutionInstaller", FakeInstaller)
    FakeInstaller.calls.clear()
    pipeline = EvolutionPipeline(
        store,
        proposer=proposer,
        evaluator=final_gate_evaluator(store),
    )
    pipeline.tick()
    pipeline.tick()
    result = pipeline.tick()
    assert result["state"] == "held"
    assert result["reason_code"] == "FINAL_GATE_HOLD"
    candidate = store.list("candidates")[0]
    assert "cost_attempt_ids" not in candidate
    assert FakeInstaller.calls == []
    assert case["target"].read_bytes() == b"parent fixture"


def test_prepared_restart_requires_side_effect_readback(tmp_path):
    case = add_case(tmp_path, Store(tmp_path / "state"), "case")
    store = case["store"]
    proposer, calls = fixture_proposer()
    pipeline = EvolutionPipeline(store, proposer=proposer)
    pipeline.tick()
    stage = store.list("experiments")[0]
    intent = {"operation": "propose"}
    stage.update(
        state="prepared",
        claimed_state="experiment_ready",
        claim_token="owner-now-gone",
        attempts=1,
        prepared_intent=intent,
        prepared_intent_sha256=digest(canonical(intent)),
    )
    store.put("experiments", stage)
    assert EvolutionPipeline(store, proposer=proposer).tick() is None
    recovered = store.get("experiments", stage["id"])
    assert recovered["state"] == "held"
    assert recovered["reason_code"] == "SIDE_EFFECT_READBACK_REQUIRED"
    assert calls == []


def test_concurrent_tick_does_not_invalidate_active_callback(tmp_path):
    case = add_case(tmp_path, Store(tmp_path / "state"), "case")
    store = case["store"]
    pipeline = EvolutionPipeline(store, proposer=fixture_proposer()[0])
    pipeline.tick()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def blocking_proposer(review_bytes, parent_bytes):
        entered.set()
        assert release.wait(timeout=5)
        calls.append(review_bytes)
        return {
            "candidate_bytes": b"candidate fixture",
            "candidate_sha256": digest(b"candidate fixture"),
            "owner_incident_id": "incident-fixture",
            "cost_attempt_ids": ["proposal-fixture-attempt"],
        }

    first = EvolutionPipeline(store, proposer=blocking_proposer)
    second = EvolutionPipeline(store, proposer=blocking_proposer)
    thread = threading.Thread(target=first.tick)
    thread.start()
    assert entered.wait(timeout=5)
    assert second.tick() is None
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    stage = store.list("experiments")[0]
    assert stage["state"] == "candidate_ready"
    assert stage.get("reason_code") is None
    assert len(calls) == 1


def test_full_state_machine_reaches_actual_signed_activation(tmp_path, monkeypatch):
    case = add_case(tmp_path, Store(tmp_path / "state"), "case")
    store = case["store"]
    proposer, _ = fixture_proposer(include_costs=True)
    monkeypatch.setattr(pipeline_module, "SkillEvolutionInstaller", FakeInstaller)
    FakeInstaller.calls.clear()
    pipeline = EvolutionPipeline(
        store,
        proposer=proposer,
        evaluator=final_gate_evaluator(store),
        activation=lambda candidate_id, installation_id: "run-activation-fixture",
    )
    assert pipeline.tick()["state"] == "experiment_ready"
    assert pipeline.tick()["state"] == "candidate_ready"
    assert pipeline.tick()["state"] == "promotion_ready"
    assert pipeline.tick()["state"] == "activation_pending"
    installation = store.list("installations")[0]
    candidate = store.get("candidates", installation["candidate_id"])
    activation_run = {
        "id": "run-activation-fixture",
        "session_id": "activation-session-fixture",
        "origin": "activation_canary",
        "event_ids": ["event-activation-fixture"],
        "attributions": [
            {
                "attribution": "verified_read",
                "file_sha256": candidate["candidate_sha256"],
            }
        ],
        "created_at": "2026-01-03T00:00:00+00:00",
    }
    store.put("runs", activation_run)
    context = store.artifact(
        canonical(
            {
                "context_id": activation_run["session_id"],
                "origin": "trusted_broker",
                "fresh": True,
                "model": "fixture-model",
                "effort": "fixture-effort",
                "created_at": "2026-01-04T00:00:00+00:00",
            }
        )
    )
    protocol = store.get("protocols", "protocol-fixture")
    receipt = {
        "id": "task-receipt-fixture",
        "run_id": activation_run["id"],
        "installation_id": installation["id"],
        "run_binding_sha256": run_binding(activation_run),
        "protocol_sha256": digest(canonical(protocol)),
        "skill_sha256": candidate["candidate_sha256"],
        "status": "accepted",
        "oracle_sha256": protocol["activation_oracle_sha256"],
        "result_artifact_sha256": store.artifact(b"fixture accepted result"),
        "context_receipt_sha256": context,
    }
    accept_task_result(store, seal_task_receipt(store, receipt))
    assert pipeline.tick()["state"] == "activated"
    final_stage = store.list("experiments")[0]
    assert final_stage["activation_run_id"] == "run-activation-fixture"
    assert candidate["cost_attempt_ids"] == ["proposal-fixture-attempt"]
    assert FakeInstaller.calls == [candidate["id"]]
    assert case["target"].read_bytes() == b"candidate fixture"
