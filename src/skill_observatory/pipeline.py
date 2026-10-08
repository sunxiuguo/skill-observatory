"""Durable evolution stage orchestration.

This module owns only stage sequencing and binding checks.  Model work,
independent evaluation, the original owner installer, and fresh activation
evidence remain behind trusted adapters that are supplied by the runtime.
"""
from __future__ import annotations

import fcntl
import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from .installations import activate, authority_expired, validate_verdict
from .owner_installers import SkillEvolutionInstaller
from .store import canonical, digest, now

STATE_EXPERIMENT_READY = "experiment_ready"
STATE_CANDIDATE_READY = "candidate_ready"
STATE_PROMOTION_READY = "promotion_ready"
STATE_ACTIVATION_PENDING = "activation_pending"
STATE_RUNNING = "running"
STATE_PREPARED = "prepared"
STATE_ACTIVATED = "activated"
STATE_REJECTED = "rejected"
STATE_HELD = "held"

STATE_NAMES = (
    STATE_EXPERIMENT_READY,
    STATE_CANDIDATE_READY,
    STATE_PROMOTION_READY,
    STATE_ACTIVATION_PENDING,
    STATE_RUNNING,
    STATE_PREPARED,
    STATE_ACTIVATED,
    STATE_REJECTED,
    STATE_HELD,
)

REASON_CODES = (
    "ACTIVATION_ADAPTER_RETURN_INVALID",
    "ACTIVATION_RUN_ID_INVALID",
    "ADAPTER_ATTEMPT_HOLD",
    "CANDIDATE_ID_COLLISION",
    "CANDIDATE_NO_CHANGE",
    "CLAIM_MISMATCH",
    "EVALUATOR_INPUT_BUDGET_EXCEEDED",
    "FINAL_GATE_HOLD",
    "INDEPENDENT_TRUTH_REQUIRED",
    "INSTALLATION_BINDING_MISMATCH",
    "INSTALLER_RESULT_INVALID",
    "PARENT_INPUT_BUDGET_EXCEEDED",
    "PARENT_PACKAGE_DRIFT",
    "PROPOSAL_OUTPUT_INVALID",
    "PROTOCOL_DRIFT",
    "REVIEW_BINDING_DRIFT",
    "SIDE_EFFECT_READBACK_REQUIRED",
    "TASK_VERIFICATION_REQUIRED",
    "VERDICT_BINDING_MISMATCH",
    "VERDICT_ID_MISSING",
    "VERDICT_UNTRUSTED",
)

VERIFIED_ATTRIBUTIONS = frozenset(
    {"explicit_loaded", "verified_read", "executed_script"}
)
OWNER = "skill-evolution-loop"
SURFACE = "single_text_file"
AUTHORIZED_FILE = "SKILL.md"
INCIDENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MAX_REVIEW_BYTES = 128 * 1024
MAX_PARENT_BYTES = 1024 * 1024
MAX_CANDIDATE_BYTES = 1024 * 1024
MAX_EVALUATOR_BYTES = 2 * 1024 * 1024


class EvolutionPipeline:
    """Process at most one durable evolution stage per ``tick``.

    ``proposer`` receives ``(review_bytes, parent_bytes)`` and returns
    ``{"candidate_bytes": bytes, "candidate_sha256": str,
    "owner_incident_id": str}``.  ``evaluator`` receives a bounded dict with
    parent/candidate bytes and experiment metadata, never the proposer result
    or the Store.  ``activation`` receives ``(candidate_id, installation_id)``
    and returns an actual observed activation run ID whose run already has
    the signed outcome receipt installed by ``accept_task_result``.
    """

    def __init__(
        self,
        store,
        proposer: Callable[..., Any] | None = None,
        evaluator: Callable[..., Any] | None = None,
        activation: Callable[..., Any] | None = None,
    ):
        self.store = store
        self.proposer = proposer
        self.evaluator = evaluator
        self.activation = activation
        # A new object represents a new execution attempt.  A stage left behind
        # by another token cannot be safely replayed after a process restart.
        self.claim_token = uuid.uuid4().hex
        self._tick_mutex = threading.Lock()

    @classmethod
    def state_names(cls):
        return STATE_NAMES

    @classmethod
    def reason_codes(cls):
        return REASON_CODES

    def tick(self):
        # Serialize the entire callback-bearing tick across processes.  A busy
        # tick is live progress and must not recover or replay its stage.
        if not self._tick_mutex.acquire(blocking=False):
            return None
        try:
            lock_path = self.store.root / "pipeline.lock"
            with lock_path.open("a") as lock_file:
                try:
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return None
                try:
                    return self._tick_locked()
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
        finally:
            self._tick_mutex.release()

    def _tick_locked(self):
        if self.store.settings().get("paused"):
            return None
        claim = self._claim_next()
        if claim is None:
            return None
        stage, was_claimed = claim
        if not was_claimed:
            return stage
        try:
            claimed_state = stage["claimed_state"]
            if claimed_state == STATE_EXPERIMENT_READY:
                return self._run_proposer(stage)
            if claimed_state == STATE_CANDIDATE_READY:
                return self._run_evaluator(stage)
            if claimed_state == STATE_PROMOTION_READY:
                return self._run_installer(stage)
            if claimed_state == STATE_ACTIVATION_PENDING:
                return self._run_activation(stage)
            return self._hold(stage, "CLAIM_MISMATCH")
        except BaseException as exc:
            held = self._hold(stage, self._reason_from_exception(exc))
            if isinstance(exc, Exception):
                return held
            raise

    def _claim_next(self):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._recover_interrupted(db)
            stages = self._rows(db, "experiments")
            ready = self._ready_states()
            blocked_by_missing_adapter = any(
                stage.get("state") in ready and not self._adapter_for(stage)
                for stage in stages
            )
            candidates = [
                stage for stage in stages if stage.get("state") in ready
            ]
            if candidates:
                stage = sorted(
                    candidates,
                    key=lambda item: (item.get("created_at") or "", item["id"]),
                )[0]
                stage.update(
                    state=STATE_RUNNING,
                    claimed_state=stage["state"],
                    claim_token=self.claim_token,
                    attempts=int(stage.get("attempts", 0)) + 1,
                    updated_at=now(),
                )
                self.store.put("experiments", stage, db=db)
                return stage, True
            if blocked_by_missing_adapter:
                return None

            reviews = sorted(
                self._rows(db, "reviews"),
                key=lambda item: (item.get("created_at") or "", item["id"]),
            )
            existing = {stage.get("review_id") for stage in stages}
            for review in reviews:
                if review.get("id") in existing:
                    continue
                eligible = self._eligible_review(db, review)
                if eligible is None:
                    continue
                experiment = self._create_experiment(db, *eligible)
                if experiment is not None:
                    return experiment, False
            return None

    def _ready_states(self):
        states = {STATE_PROMOTION_READY}
        if self.proposer is not None:
            states.add(STATE_EXPERIMENT_READY)
        if self.evaluator is not None:
            states.add(STATE_CANDIDATE_READY)
        if self.activation is not None:
            states.add(STATE_ACTIVATION_PENDING)
        return states

    def _adapter_for(self, stage):
        state = stage.get("state")
        if state == STATE_EXPERIMENT_READY:
            return self.proposer is not None
        if state == STATE_CANDIDATE_READY:
            return self.evaluator is not None
        if state == STATE_ACTIVATION_PENDING:
            return self.activation is not None
        return True

    def _recover_interrupted(self, db):
        # This runs only while the exclusive tick lock is held.  Therefore any
        # running/prepared row is a prior attempt whose callback is no longer
        # active; it requires side-effect readback instead of replay.
        for stage in self._rows(db, "experiments"):
            if stage.get("state") not in {STATE_RUNNING, STATE_PREPARED}:
                continue
            stage.update(
                state=STATE_HELD,
                reason_code="SIDE_EFFECT_READBACK_REQUIRED",
                updated_at=now(),
            )
            self.store.put("experiments", stage, db=db)

    def _eligible_review(self, db, review):
        if review.get("status") != "reviewed" or review.get("decision") != "CANDIDATE":
            return None
        if review.get("attribution") not in VERIFIED_ATTRIBUTIONS:
            return None
        if not review.get("skill_id") or not review.get("skill_package_sha256"):
            return None
        skill = self.store.get("skills", review["skill_id"], db=db)
        if not skill or skill.get("package_sha256") != review["skill_package_sha256"]:
            return None
        run = self.store.get("runs", review.get("run_id"), db=db)
        if not run or not any(
            attribution.get("skill_id") == review["skill_id"]
            and attribution.get("package_sha256") == review["skill_package_sha256"]
            and attribution.get("attribution") == review["attribution"]
            for attribution in run.get("attributions", [])
        ):
            return None
        try:
            from .runtime import package_manifest

            manifest = package_manifest(skill["path"])
            target = Path(skill["path"]) / AUTHORIZED_FILE
            if manifest != skill.get("manifest") or not target.is_file():
                return None
            parent = target.read_bytes()
            if (
                len(parent) > MAX_PARENT_BYTES
                or manifest.get("files", {}).get(AUTHORIZED_FILE) != digest(parent)
            ):
                return None
        except (OSError, ValueError, KeyError):
            return None
        authority = self._matching_authority(db, review, skill, target)
        if authority is None:
            return None
        return review, skill, authority, parent

    def _matching_authority(self, db, review, skill, target):
        matches = []
        expected_target = str(target.resolve())
        for authority in self._rows(db, "authority_grants"):
            if (
                authority.get("status") != "authorized"
                or authority.get("owner") != OWNER
                or authority.get("surface") != SURFACE
                or authority.get("target") != expected_target
            ):
                continue
            if authority.get("skill_id") not in (None, review["skill_id"]):
                continue
            if authority.get("package_sha256") not in (None, skill["package_sha256"]):
                continue
            allowed = authority.get("allowed_files")
            if allowed is not None and set(allowed) != {AUTHORIZED_FILE}:
                continue
            try:
                if authority_expired(authority.get("expires_at")):
                    continue
            except ValueError:
                continue
            try:
                self.store.read_artifact(authority["evidence_sha256"])
            except (KeyError, ValueError, OSError):
                continue
            matches.append(authority)
        if len(matches) != 1:
            return None
        return matches[0]

    def _create_experiment(self, db, review, skill, authority, parent):
        review_sha256 = digest(canonical(review))
        binding = {
            "review_sha256": review_sha256,
            "review_id": review["id"],
            "run_id": review.get("run_id"),
            "skill_id": review["skill_id"],
            "skill_package_sha256": review["skill_package_sha256"],
            "attribution": review["attribution"],
            "decision": review["decision"],
            "authority_id": authority["id"],
            "target": str((Path(skill["path"]) / AUTHORIZED_FILE).resolve()),
            "parent_sha256": digest(parent),
        }
        binding_sha256 = digest(canonical(binding))
        experiment_id = "exp_" + digest(
            canonical(
                {
                    "review_id": review["id"],
                    "review_binding_sha256": binding_sha256,
                }
            )
        )[:32]
        experiment = {
            "id": experiment_id,
            "state": STATE_EXPERIMENT_READY,
            "review_id": review["id"],
            "run_id": review.get("run_id"),
            "review_sha256": review_sha256,
            "review_binding_sha256": binding_sha256,
            "review_artifact_sha256": self.store.artifact(canonical(review)),
            "skill_id": skill["id"],
            "skill_package_sha256": skill["package_sha256"],
            "target": binding["target"],
            "parent_sha256": binding["parent_sha256"],
            "parent_artifact_sha256": self.store.artifact(parent),
            "authority_id": authority["id"],
            "attempts": 0,
            "created_at": now(),
            "updated_at": now(),
        }
        self.store.put("experiments", experiment, db=db)
        return experiment

    def _run_proposer(self, stage):
        parent, _skill = self._current_parent(stage)
        review = self.store.get("reviews", stage["review_id"])
        if not review or digest(canonical(review)) != stage["review_sha256"]:
            return self._hold(stage, "REVIEW_BINDING_DRIFT")
        review_bytes = canonical(review)
        if len(review_bytes) > MAX_REVIEW_BYTES:
            return self._hold(stage, "PARENT_INPUT_BUDGET_EXCEEDED")
        intent = {
            "operation": "propose",
            "review_sha256": stage["review_sha256"],
            "parent_sha256": stage["parent_sha256"],
            "authority_id": stage["authority_id"],
        }
        stage = self._prepare_intent(stage, intent)
        result = self.proposer(review_bytes, parent)
        candidate_bytes = self._proposal_bytes(stage, result, parent)
        cost_attempt_ids = result.get("cost_attempt_ids")
        parent, _skill = self._current_parent(stage)
        candidate_sha256 = digest(candidate_bytes)
        result_record = {
            "candidate_sha256": candidate_sha256,
            "owner_incident_id": result["owner_incident_id"],
            "proposer_method_version_id": result.get("proposer_method_version_id"),
            "cost_attempt_ids": result.get("cost_attempt_ids"),
        }
        result_sha256 = self.store.artifact(canonical(result_record))
        candidate_id = "cand_" + digest(
            canonical(
                {
                    "experiment_id": stage["id"],
                    "candidate_sha256": candidate_sha256,
                }
            )
        )[:32]
        candidate = {
            "id": candidate_id,
            "experiment_id": stage["id"],
            "review_id": stage["review_id"],
            "review_binding_sha256": stage["review_binding_sha256"],
            "skill_id": stage["skill_id"],
            "target": stage["target"],
            "parent_sha256": stage["parent_sha256"],
            "candidate_sha256": candidate_sha256,
            "parent_artifact_sha256": stage["parent_artifact_sha256"],
            "candidate_artifact_sha256": self.store.artifact(candidate_bytes),
            "authority_id": stage["authority_id"],
            "owner_incident_id": result["owner_incident_id"],
            **(
                {"cost_attempt_ids": cost_attempt_ids}
                if cost_attempt_ids is not None
                else {}
            ),
            "verdict_id": None,
            "status": STATE_CANDIDATE_READY,
            "created_at": now(),
        }
        return self._finish(
            stage,
            {
                "state": STATE_CANDIDATE_READY,
                "candidate_id": candidate_id,
                "candidate_sha256": candidate_sha256,
                "result_sha256": result_sha256,
            },
            [("candidates", candidate)],
        )

    def _proposal_bytes(self, stage, result, parent):
        if not isinstance(result, dict):
            self._hold(stage, "PROPOSAL_OUTPUT_INVALID")
            raise ValueError("PROPOSAL_OUTPUT_INVALID")
        candidate_bytes = result.get("candidate_bytes")
        candidate_sha256 = result.get("candidate_sha256")
        incident = result.get("owner_incident_id")
        if (
            not isinstance(candidate_bytes, bytes)
            or not isinstance(candidate_sha256, str)
            or not isinstance(incident, str)
            or not INCIDENT_ID.fullmatch(incident)
        ):
            self._hold(stage, "PROPOSAL_OUTPUT_INVALID")
            raise ValueError("PROPOSAL_OUTPUT_INVALID")
        try:
            candidate_bytes.decode("utf-8")
        except UnicodeDecodeError:
            self._hold(stage, "PROPOSAL_OUTPUT_INVALID")
            raise
        if (
            len(candidate_bytes) > MAX_CANDIDATE_BYTES
            or digest(candidate_bytes) != candidate_sha256
        ):
            self._hold(stage, "PROPOSAL_OUTPUT_INVALID")
            raise ValueError("PROPOSAL_OUTPUT_INVALID")
        cost_attempt_ids = result.get("cost_attempt_ids")
        if cost_attempt_ids is not None and (
            not isinstance(cost_attempt_ids, list)
            or not cost_attempt_ids
            or any(
                not isinstance(item, str)
                or not item
                or len(item) > 256
                for item in cost_attempt_ids
            )
            or len(set(cost_attempt_ids)) != len(cost_attempt_ids)
        ):
            self._hold(stage, "PROPOSAL_OUTPUT_INVALID")
            raise ValueError("PROPOSAL_OUTPUT_INVALID")
        if candidate_sha256 == stage["parent_sha256"]:
            self._hold(stage, "CANDIDATE_NO_CHANGE")
            raise ValueError("CANDIDATE_NO_CHANGE")
        return candidate_bytes

    def _run_evaluator(self, stage):
        candidate = self._candidate(stage)
        parent, _skill = self._current_parent(stage)
        candidate_bytes = self.store.read_artifact(
            candidate["candidate_artifact_sha256"]
        )
        if len(parent) + len(candidate_bytes) > MAX_EVALUATOR_BYTES:
            return self._hold(stage, "EVALUATOR_INPUT_BUDGET_EXCEEDED")
        payload = {
            "experiment_id": stage["id"],
            "review_binding_sha256": stage["review_binding_sha256"],
            "skill_id": stage["skill_id"],
            "skill_package_sha256": stage["skill_package_sha256"],
            "target": AUTHORIZED_FILE,
            "parent_sha256": candidate["parent_sha256"],
            "candidate_id": candidate["id"],
            "candidate_sha256": candidate["candidate_sha256"],
            "cost_attempt_ids": candidate.get("cost_attempt_ids"),
            "parent_bytes": parent,
            "candidate_bytes": candidate_bytes,
            "protocol_metadata": {
                "experiment_id": stage["id"],
                "review_binding_sha256": stage["review_binding_sha256"],
                "skill_id": stage["skill_id"],
            },
        }
        intent = {
            "operation": "evaluate",
            "candidate_id": candidate["id"],
            "parent_sha256": candidate["parent_sha256"],
            "candidate_sha256": candidate["candidate_sha256"],
        }
        stage = self._prepare_intent(stage, intent)
        verdict = self.evaluator(payload)
        if not isinstance(verdict, dict) or not verdict.get("id"):
            return self._hold(stage, "VERDICT_ID_MISSING")
        raw_verdict = canonical(verdict)
        if len(raw_verdict)>MAX_REVIEW_BYTES:
            return self._hold(stage,"EVALUATOR_OUTPUT_BUDGET_EXCEEDED")
        verdict_artifact = self.store.artifact(raw_verdict)
        if (
            verdict.get("candidate_id") != candidate["id"]
            or (
                "experiment_id" in verdict
                and verdict.get("experiment_id") != stage["id"]
            )
            or (
                "review_binding_sha256" in verdict
                and verdict.get("review_binding_sha256")
                != stage["review_binding_sha256"]
            )
        ):
            return self._hold(stage, "VERDICT_BINDING_MISMATCH")
        if verdict.get("status") == "hold":
            missing=verdict.get('missing',[])
            if not isinstance(missing,list) or any(not isinstance(x,str) for x in missing):missing=[]
            return self._hold(stage, "FINAL_GATE_HOLD",{'result_sha256':verdict_artifact,'missing':missing})
        validate_verdict(self.store, verdict)
        if (
            verdict["parent_sha256"] != candidate["parent_sha256"]
            or verdict["candidate_sha256"] != candidate["candidate_sha256"]
        ):
            return self._hold(stage, "VERDICT_BINDING_MISMATCH")
        promoted_candidate = {
            **candidate,
            "verdict_id": verdict["id"],
            "status": STATE_PROMOTION_READY,
        }
        result_record = {
            "verdict_id": verdict["id"],
            "verdict_sha256": digest(canonical(verdict)),
        }
        return self._finish(
            stage,
            {
                "state": STATE_PROMOTION_READY,
                "result_sha256": self.store.artifact(canonical(result_record)),
            },
            [
                ("verdicts", verdict),
                ("candidates", promoted_candidate),
            ],
        )

    def _run_installer(self, stage):
        candidate = self._candidate(stage)
        verdict = self.store.get("verdicts", candidate.get("verdict_id"))
        if not verdict:
            return self._hold(stage, "VERDICT_BINDING_MISMATCH")
        validate_verdict(self.store, verdict)
        if (
            verdict.get("candidate_id") != candidate["id"]
            or (
                "experiment_id" in verdict
                and verdict.get("experiment_id") != stage["id"]
            )
            or (
                "review_binding_sha256" in verdict
                and verdict.get("review_binding_sha256")
                != stage["review_binding_sha256"]
            )
            or verdict.get("parent_sha256") != candidate["parent_sha256"]
            or verdict.get("candidate_sha256") != candidate["candidate_sha256"]
        ):
            return self._hold(stage, "VERDICT_BINDING_MISMATCH")
        self._current_parent(stage)
        intent = {
            "operation": "install",
            "candidate_id": candidate["id"],
            "verdict_id": verdict["id"],
            "parent_sha256": candidate["parent_sha256"],
            "candidate_sha256": candidate["candidate_sha256"],
        }
        stage = self._prepare_intent(stage, intent)
        installation = SkillEvolutionInstaller().apply(
            self.store, candidate["id"]
        )
        expected_id = "owner_inst_" + candidate["id"]
        if (
            not isinstance(installation, dict)
            or installation.get("id") != expected_id
            or installation.get("candidate_id") != candidate["id"]
            or installation.get("target") != candidate["target"]
            or installation.get("before_sha256") != candidate["parent_sha256"]
            or installation.get("after_sha256") != candidate["candidate_sha256"]
            or installation.get("status") != STATE_ACTIVATION_PENDING
        ):
            return self._hold(stage, "INSTALLER_RESULT_INVALID")
        try:
            target = Path(candidate["target"])
            if target.is_symlink() or digest(target.read_bytes()) != candidate["candidate_sha256"]:
                return self._hold(stage, "INSTALLATION_BINDING_MISMATCH")
        except OSError:
            return self._hold(stage, "INSTALLATION_BINDING_MISMATCH")
        return self._finish(
            stage,
            {
                "state": STATE_ACTIVATION_PENDING,
                "installation_id": expected_id,
                "result_sha256": self.store.artifact(canonical(installation)),
            },
        )

    def _run_activation(self, stage):
        candidate = self._candidate(stage)
        installation = self.store.get(
            "installations", stage.get("installation_id")
        )
        if (
            not installation
            or installation.get("candidate_id") != candidate["id"]
            or installation.get("status") != STATE_ACTIVATION_PENDING
            or installation.get("after_sha256") != candidate["candidate_sha256"]
        ):
            return self._hold(stage, "INSTALLATION_BINDING_MISMATCH")
        intent = {
            "operation": "activate",
            "candidate_id": candidate["id"],
            "installation_id": installation["id"],
            "candidate_sha256": candidate["candidate_sha256"],
        }
        stage = self._prepare_intent(stage, intent)
        returned = self.activation(candidate["id"], installation["id"])
        if isinstance(returned, dict):
            run_id = returned.get("run_id")
        else:
            run_id = returned
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            return self._hold(stage, "ACTIVATION_ADAPTER_RETURN_INVALID")
        try:
            activated = activate(self.store, installation["id"], run_id)
        except ValueError:
            return self._hold(stage, "ACTIVATION_RUN_ID_INVALID")
        if activated.get("status") != STATE_ACTIVATED or activated.get(
            "activation_run_id"
        ) != run_id:
            return self._hold(stage, "INSTALLATION_BINDING_MISMATCH")
        return self._finish(
            stage,
            {
                "state": STATE_ACTIVATED,
                "activation_run_id": run_id,
                "result_sha256": self.store.artifact(canonical(activated)),
            },
        )

    def _candidate(self, stage):
        candidate = self.store.get("candidates", stage.get("candidate_id"))
        if (
            not candidate
            or candidate.get("experiment_id") != stage["id"]
            or candidate.get("review_id") != stage["review_id"]
            or candidate.get("review_binding_sha256")
            != stage["review_binding_sha256"]
            or candidate.get("target") != stage["target"]
            or candidate.get("parent_sha256") != stage["parent_sha256"]
        ):
            self._hold(stage, "INSTALLATION_BINDING_MISMATCH")
            raise ValueError("INSTALLATION_BINDING_MISMATCH")
        return candidate

    def _current_parent(self, stage):
        skill = self.store.get("skills", stage["skill_id"])
        if not skill:
            self._hold(stage, "PARENT_PACKAGE_DRIFT")
            raise ValueError("PARENT_PACKAGE_DRIFT")
        try:
            from .runtime import package_manifest

            manifest = package_manifest(skill["path"])
            target = Path(stage["target"])
            if (
                manifest != skill.get("manifest")
                or target.name != AUTHORIZED_FILE
                or target.is_symlink()
                or not target.is_file()
            ):
                raise ValueError("PARENT_PACKAGE_DRIFT")
            parent = target.read_bytes()
            if (
                len(parent) > MAX_PARENT_BYTES
                or digest(parent) != stage["parent_sha256"]
                or manifest.get("files", {}).get(AUTHORIZED_FILE) != stage["parent_sha256"]
            ):
                raise ValueError("PARENT_PACKAGE_DRIFT")
            return parent, skill
        except (OSError, ValueError, KeyError):
            self._hold(stage, "PARENT_PACKAGE_DRIFT")
            raise

    def _prepare_intent(self, stage, intent):
        intent_sha256 = digest(canonical(intent))
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.store.get("experiments", stage["id"], db=db)
            if not self._claim_is_current(current, stage):
                raise ValueError("CLAIM_MISMATCH")
            current.update(
                prepared_intent=intent,
                prepared_intent_sha256=intent_sha256,
                updated_at=now(),
            )
            self.store.put("experiments", current, db=db)
            return current

    def _finish(self, stage, updates, entities=()):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.store.get("experiments", stage["id"], db=db)
            if not self._claim_is_current(current, stage):
                return current
            for kind, value in entities:
                existing = self.store.get(kind, value["id"], db=db)
                if existing and not self._entity_update_allowed(
                    kind, existing, value
                ):
                    raise ValueError("CANDIDATE_ID_COLLISION")
                self.store.put(kind, value, db=db)
            current.update(**updates)
            current["updated_at"] = now()
            self.store.put("experiments", current, db=db)
            return current

    @staticmethod
    def _entity_update_allowed(kind, existing, value):
        if digest(canonical(existing)) == digest(canonical(value)):
            return True
        if kind != "candidates":
            return False
        mutable = {"verdict_id", "status"}
        immutable = [key for key in existing if key not in mutable]
        return (
            all(existing.get(key) == value.get(key) for key in immutable)
            and existing.get("verdict_id") in {None, value.get("verdict_id")}
            and existing.get("status") in {STATE_CANDIDATE_READY, value.get("status")}
        )

    def _hold(self, stage, reason_code,details=None):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.store.get("experiments", stage["id"], db=db)
            if not current:
                return None
            if not self._claim_is_current(
                current, stage, require_prepared=False
            ):
                return current
            current.update(
                state=STATE_HELD,
                reason_code=reason_code,
                updated_at=now(),
            )
            if details:current.update(details)
            self.store.put("experiments", current, db=db)
            return current

    def _claim_is_current(self, current, stage, require_prepared=True):
        matched = bool(
            current
            and current.get("state") == STATE_RUNNING
            and current.get("claim_token") == stage.get("claim_token")
            and current.get("claimed_state") == stage.get("claimed_state")
            and current.get("attempts") == stage.get("attempts")
        )
        if not require_prepared:
            return matched
        return bool(
            matched
            and current.get("prepared_intent_sha256")
            == stage.get("prepared_intent_sha256")
        )

    @staticmethod
    def _rows(db, kind):
        rows = db.execute(
            "SELECT data FROM entities WHERE kind=? ORDER BY rowid", (kind,)
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    @staticmethod
    def _reason_from_exception(exc):
        message = str(exc)
        for reason in REASON_CODES:
            if message.startswith(reason):
                return reason
        return "ADAPTER_ATTEMPT_HOLD"
