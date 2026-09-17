"""Bounded M09 data-only recording for one authoritative Catch the Fly session."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from typing import Any
import zipfile

import numpy as np

from flybench.game import (
    GameInputError,
    GameSession,
    ResolvedLiveProfile,
    build_live_session,
    load_live_profile,
    sha256_file,
)


FLYRUN_FORMAT_ID = "flybench.flyrun.v0.2"
FLYRUN_SCHEMA_VERSION = 2
FLYRUN_MEMBERS = ("manifest.json", "events.jsonl", "summary.json")
STATE_DIGEST_INTERVALS = 100
EVENT_ORDER_ID = "flybench.flyrun-event-order.v0.2"
ARCHITECTURE_SHA256 = (
    "bae80837d5d6d769ae5b728af3b80c1caa21b7f08efdd7f3eb458f7bb2eab9d1"
)
M08_DEFER_DECISION_ID = "D-M08-HUMAN-GATE-DEFER-01"
M08_DEFER_DECISION_PATH = "decisions/D-M08-HUMAN-GATE-DEFER-01.json"
M08_DEFER_DECISION_SHA256 = (
    "79d9a7e68e4d2d865411c2bb00fa62295fec503c976f38c4d579f8d077212a89"
)
MAX_ROUND_DURATION_MS = 20_000
MAX_ATTACKS = 6
MAX_ESSENTIAL_RECORDS = 8_192
MAX_OPTIONAL_RECORDS = 2_048
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
MAX_EXPANDED_BYTES = 4 * 1024 * 1024
MAX_EVENT_LINE_BYTES = 64 * 1024
MAX_ARCHIVE_MEMBERS = len(FLYRUN_MEMBERS)


class FlyRunError(ValueError):
    """Base error for bounded recorder or archive validation failures."""


class FlyRunLimitError(FlyRunError):
    """A declared recorder/archive resource limit was exceeded."""


class FlyRunSafetyError(FlyRunError):
    """An archive is malformed, unsafe, or outside the supported data-only format."""


def _canonical_json(value: object) -> bytes:
    try:
        payload = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise FlyRunError(f"record is not canonical JSON data: {exc}") from exc
    return payload.encode("utf-8") + b"\n"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise FlyRunSafetyError(f"non-finite JSON constant is forbidden: {value}")


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode or len(value) != 40:
        raise FlyRunError("unable to resolve the recorder code Git identity")
    return value


def canonical_applied_input_records(
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Project only server-applied scientific/game inputs in logical order."""

    records: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("type")
        if event_type == "accepted_aim":
            records.append(
                {
                    "type": "accepted_aim",
                    "control_tick": event["control_tick"],
                    "sequence": event["sequence"],
                    "aim": event["aim"],
                }
            )
        elif event_type == "attack_commit":
            records.append(
                {
                    "type": "attack_commit",
                    "control_tick": event["control_tick"],
                    "sequence": event["sequence"],
                    "attack_id": event["attack_id"],
                    "locked_target": event["locked_target"],
                    "impact_tick": event["impact_tick"],
                }
            )
    return tuple(records)


def canonical_applied_input_sha256(
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> str:
    """Hash authoritative applied values, excluding recorder/presentation metadata."""

    return _sha256(
        b"".join(
            _canonical_json(record)
            for record in canonical_applied_input_records(events)
        )
    )


def _update_array(digest: Any, name: str, value: np.ndarray) -> None:
    array = np.ascontiguousarray(value)
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "bytes": int(array.nbytes),
    }
    digest.update(_canonical_json(metadata))
    digest.update(array.tobytes(order="C"))


def _hash_json_context(label: str, value: object) -> str:
    digest = hashlib.sha256(f"FlyBench M09 {label} v0.2\0".encode("ascii"))
    digest.update(_canonical_json(value))
    return digest.hexdigest()


def scientific_state_digest(
    runner: Any,
    *,
    game_session: GameSession | None = None,
    bench_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hash complete mutable authoritative state without serializing full arrays."""

    neural = runner.neural
    neural_digest = hashlib.sha256(b"FlyBench M09 neural state v0.2\0")
    neural_digest.update(
        _canonical_json(
            {
                "tick": int(neural.tick),
                "seed": int(neural.seed),
                "rng_state": neural.rng.bit_generator.state,
            }
        )
    )
    for name in (
        "voltage",
        "synaptic_current",
        "refractory_until_tick",
        "pending_spikes",
        "pending_inputs",
    ):
        _update_array(neural_digest, name, getattr(neural, name))
    neural_sha = neural_digest.hexdigest()

    environment = runner.environment
    environment_snapshot = environment.snapshot()
    environment_value = {
        "x": environment_snapshot["x"],
        "y": environment_snapshot["y"],
        "heading_rad": environment_snapshot["heading_rad"],
        "control_tick": environment_snapshot["control_tick"],
        "takeoff_ticks_remaining": environment_snapshot["takeoff_ticks_remaining"],
        "takeoff_heading_rad": environment_snapshot["takeoff_heading_rad"],
        "takeoff_active_last_interval": environment_snapshot[
            "takeoff_active_last_interval"
        ],
        "scheduled_impact_ticks": list(
            environment_snapshot["scheduled_impact_ticks"]
        ),
        "impacts": [asdict(item) for item in environment_snapshot["impacts"]],
        "rng_state": environment_snapshot["rng_state"],
        "seed": environment_snapshot["seed"],
    }
    environment_sha = _hash_json_context("environment state", environment_value)

    if game_session is not None:
        strike = game_session.active_strike
        game_value: dict[str, Any] = {
            "kind": "game-session",
            "control_tick": game_session.control_tick,
            "latest_aim": (
                None
                if game_session.latest_aim is None
                else list(game_session.latest_aim)
            ),
            "pending_aim": (
                None
                if game_session.pending_aim is None
                else list(game_session.pending_aim)
            ),
            "last_sequence": game_session.last_sequence,
            "active_strike": None if strike is None else asdict(strike),
            "cooldown_until_tick": game_session.cooldown_until_tick,
            "attack_count": game_session.attack_count,
            "round_horizon_tick": game_session.spec.round_horizon_tick,
            "result": game_session.result,
            "result_reason": game_session.result_reason,
            "last_impact": game_session.last_impact,
            "last_motion": game_session.last_motion,
        }
    else:
        game_value = {"kind": "bench-trial", **(bench_state or {})}
    game_sha = _hash_json_context("game state", game_value)
    runner_value = {
        "control_tick": int(runner.control_tick),
        "held_escape_command": bool(runner.held_command),
        "backend": runner.backend,
        "output_clamp": bool(runner.output_clamp),
        "intervention_id": (
            None if runner.intervention is None else runner.intervention.intervention_id
        ),
        "neural_state_sha256": neural_sha,
        "environment_state_sha256": environment_sha,
        "game_state_sha256": game_sha,
    }
    whole_sha = _hash_json_context("whole authoritative state", runner_value)
    return {
        "control_tick": int(runner.control_tick),
        "neural_tick": int(neural.tick),
        "whole_state_sha256": whole_sha,
        "neural_state_sha256": neural_sha,
        "environment_state_sha256": environment_sha,
        "game_state_sha256": game_sha,
    }


@dataclass(frozen=True, slots=True)
class RecorderLimits:
    maximum_round_duration_ms: int = MAX_ROUND_DURATION_MS
    maximum_attacks: int = MAX_ATTACKS
    maximum_essential_records: int = MAX_ESSENTIAL_RECORDS
    maximum_optional_records: int = MAX_OPTIONAL_RECORDS
    maximum_archive_bytes: int = MAX_ARCHIVE_BYTES
    maximum_expanded_bytes: int = MAX_EXPANDED_BYTES

    def __post_init__(self) -> None:
        values = (
            self.maximum_round_duration_ms,
            self.maximum_attacks,
            self.maximum_essential_records,
            self.maximum_archive_bytes,
            self.maximum_expanded_bytes,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("positive integer recorder limits are required")
        if (
            type(self.maximum_optional_records) is not int
            or self.maximum_optional_records < 0
        ):
            raise ValueError("maximum_optional_records must be a nonnegative integer")
        if self.maximum_round_duration_ms > MAX_ROUND_DURATION_MS:
            raise ValueError("round duration exceeds the M09 hard limit")
        if self.maximum_attacks > MAX_ATTACKS:
            raise ValueError("attack count exceeds the M09 hard limit")
        if self.maximum_essential_records > MAX_ESSENTIAL_RECORDS:
            raise ValueError("essential record count exceeds the M09 hard limit")
        if self.maximum_optional_records > MAX_OPTIONAL_RECORDS:
            raise ValueError("optional record count exceeds the M09 hard limit")
        if self.maximum_archive_bytes > MAX_ARCHIVE_BYTES:
            raise ValueError("archive size exceeds the M09 hard limit")
        if self.maximum_expanded_bytes > MAX_EXPANDED_BYTES:
            raise ValueError("expanded size exceeds the M09 hard limit")

    def as_dict(self) -> dict[str, int]:
        return {
            "maximum_round_duration_ms": self.maximum_round_duration_ms,
            "maximum_attacks": self.maximum_attacks,
            "maximum_essential_records": self.maximum_essential_records,
            "maximum_optional_records": self.maximum_optional_records,
            "maximum_archive_bytes": self.maximum_archive_bytes,
            "maximum_expanded_bytes": self.maximum_expanded_bytes,
        }


@dataclass(frozen=True, slots=True)
class FlyRunResult:
    archive_bytes: bytes
    content_digest: str
    applied_input_digest: str
    scientific_record_digest: str
    essential_record_count: int
    optional_record_count: int
    optional_trace_status: str
    manifest: dict[str, Any]
    summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LoadedFlyRun:
    path: Path
    archive_bytes: int
    content_digest: str
    manifest: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


class FlyRunRecorder:
    """Collect bounded authoritative records without owning or advancing simulation."""

    def __init__(
        self,
        resolved: ResolvedLiveProfile,
        *,
        run_id: str,
        limits: RecorderLimits | None = None,
        code_git_sha: str | None = None,
        execution_kind: str = "game-session",
        execution_context: dict[str, Any] | None = None,
    ):
        if not run_id or len(run_id) > 96 or any(
            not (character.isalnum() or character in "-_.") for character in run_id
        ):
            raise ValueError("run_id must be 1-96 non-sensitive identifier characters")
        self.resolved = resolved
        self.run_id = run_id
        self.limits = limits or RecorderLimits()
        if resolved.game_spec.round_horizon_ms > self.limits.maximum_round_duration_ms:
            raise ValueError("GameSpec round horizon exceeds recorder duration limit")
        if resolved.game_spec.maximum_committed_attacks > self.limits.maximum_attacks:
            raise ValueError("GameSpec attack count exceeds recorder attack limit")
        self.code_git_sha = code_git_sha or _git_head(resolved.root)
        if execution_kind not in {"game-session", "bench-trial"}:
            raise ValueError("unsupported recorder execution kind")
        self.execution_kind = execution_kind
        self.execution_context = dict(execution_context or {})
        self.essential_events: list[dict[str, Any]] = []
        self.optional_events: list[dict[str, Any]] = []
        self.essential_dropped = 0
        self.optional_dropped = 0
        self.rejected_diagnostics: dict[str, int] = {}
        self._optional_gap_recorded = False
        self._finalized = False
        self._next_event_ordinal = 0

    @property
    def applied_input_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            event
            for event in self.essential_events
            if event["type"] in {"accepted_aim", "attack_commit"}
        )

    def note_rejected_input(self, code: str) -> None:
        self.rejected_diagnostics[code] = self.rejected_diagnostics.get(code, 0) + 1

    def record_essential(self, event: dict[str, Any]) -> bool:
        event = self._checked_event(event, recording_class="essential")
        if len(self.essential_events) >= self.limits.maximum_essential_records:
            self.essential_dropped += 1
            return False
        self.essential_events.append(event)
        return True

    def record_optional(self, event: dict[str, Any]) -> bool:
        event = self._checked_event(event, recording_class="optional")
        if len(self.optional_events) < self.limits.maximum_optional_records:
            self.optional_events.append(event)
            return True
        self.optional_dropped += 1
        if not self._optional_gap_recorded:
            self._optional_gap_recorded = True
            self.record_essential(
                {
                    "type": "recorder_gap",
                    "control_tick": event["control_tick"],
                    "phase": "recorder-boundary",
                    "stream": "optional",
                    "reason": "maximum-optional-records-reached",
                }
            )
        return False

    def _checked_event(
        self, event: dict[str, Any], *, recording_class: str
    ) -> dict[str, Any]:
        if self._finalized:
            raise FlyRunError("cannot append to a finalized recorder")
        value = dict(event)
        tick = value.get("control_tick")
        if type(tick) is not int or tick < 0:
            raise FlyRunError("every event requires a nonnegative integer control_tick")
        if not isinstance(value.get("type"), str) or not value["type"]:
            raise FlyRunError("every event requires a type")
        if not isinstance(value.get("phase"), str) or not value["phase"]:
            raise FlyRunError("every event requires a documented phase")
        value["recording_class"] = recording_class
        value["event_ordinal"] = self._next_event_ordinal
        self._next_event_ordinal += 1
        _canonical_json(value)
        return value

    def finalize(self, session: GameSession) -> FlyRunResult:
        if self._finalized:
            raise FlyRunError("recorder already finalized")
        if session.result is None:
            raise FlyRunError("cannot finalize before authoritative round termination")
        self._finalized = True
        runner_summary = session.runner.finish_run()
        applied_input_digest = canonical_applied_input_sha256(
            list(self.applied_input_events)
        )
        scientific_events = [
            event
            for event in self.essential_events
            if event["type"]
            in {
                "accepted_aim",
                "attack_commit",
                "sensory_input",
                "neural_output",
                "motor_command",
                "impact",
                "round_end",
                "state_digest",
            }
        ]
        scientific_record_digest = _sha256(
            b"".join(_canonical_json(event) for event in scientific_events)
        )
        optional_status = "TRUNCATED" if self.optional_dropped else "COMPLETE"
        essential_status = "INCOMPLETE" if self.essential_dropped else "COMPLETE"
        state_digests = [
            event for event in self.essential_events if event["type"] == "state_digest"
        ]
        expected_state_ticks = [0]
        expected_state_ticks.extend(
            range(STATE_DIGEST_INTERVALS, session.control_tick, STATE_DIGEST_INTERVALS)
        )
        if session.control_tick not in expected_state_ticks:
            expected_state_ticks.append(session.control_tick)
        actual_state_ticks = [int(event["control_tick"]) for event in state_digests]
        state_envelope_complete = (
            self.essential_dropped == 0
            and actual_state_ticks == expected_state_ticks
            and bool(state_digests)
            and state_digests[-1].get("digest_kind")
            in {"final", "periodic-final"}
        )
        summary = {
            "schema_version": FLYRUN_SCHEMA_VERSION,
            "run_id": self.run_id,
            "round_id": f"{self.run_id}-round-1",
            "authoritative_result": session.result,
            "authoritative_termination_reason": session.result_reason,
            "final_control_tick": session.control_tick,
            "final_neural_tick": runner_summary["neural_tick"],
            "attacks_committed": session.attack_count,
            "applied_input_sha256": applied_input_digest,
            "scientific_record_sha256": scientific_record_digest,
            "dnp01_spike_count": runner_summary["dnp01_spike_count"],
            "dnp01_spikes": runner_summary["dnp01_spikes"],
            "decoded_escape_command_control_ticks": runner_summary[
                "escape_command_control_ticks"
            ],
            "final_neural_state_sha256": runner_summary[
                "final_neural_state_sha256"
            ],
            "final_whole_state_sha256": (
                state_digests[-1]["whole_state_sha256"] if state_digests else None
            ),
            "finite_scientific_state": runner_summary["finite_state"],
            "recording": {
                "essential_status": essential_status,
                "essential_records": len(self.essential_events),
                "essential_records_dropped": self.essential_dropped,
                "optional_status": optional_status,
                "optional_records": len(self.optional_events),
                "optional_records_dropped": self.optional_dropped,
                "rejected_input_diagnostics": dict(
                    sorted(self.rejected_diagnostics.items())
                ),
                "coalesced_aim_updates": session.coalesced_aim_updates,
            },
            "reexecution": {
                "capture_envelope_complete": state_envelope_complete,
                "verified": False,
                "verification_milestone": "M10",
            },
            "process_status": {
                "m09_execution": "AT_RISK",
                "decision": M08_DEFER_DECISION_ID,
                "m08_g_game": "PENDING_UNMEASURED",
                "m08_usability_pass_claim": False,
                "public_release_blocked": True,
            },
        }
        ordered_events = [*self.essential_events, *self.optional_events]
        events = [
            event
            for event in sorted(
                ordered_events,
                key=lambda item: (
                    int(item["control_tick"]),
                    int(item["event_ordinal"]),
                ),
            )
        ]
        events_bytes = b"".join(_canonical_json(event) for event in events)
        summary_bytes = _canonical_json(summary)
        manifest = self._manifest(
            events_bytes=events_bytes,
            summary_bytes=summary_bytes,
            summary=summary,
            session=session,
        )
        manifest_bytes = _canonical_json(manifest)
        expanded_bytes = len(manifest_bytes) + len(events_bytes) + len(summary_bytes)
        if expanded_bytes > self.limits.maximum_expanded_bytes:
            raise FlyRunLimitError(
                f"expanded flyrun payload is {expanded_bytes} bytes; limit is "
                f"{self.limits.maximum_expanded_bytes}"
            )
        archive = _build_zip(
            {
                "manifest.json": manifest_bytes,
                "events.jsonl": events_bytes,
                "summary.json": summary_bytes,
            }
        )
        if len(archive) > self.limits.maximum_archive_bytes:
            raise FlyRunLimitError(
                f"flyrun archive is {len(archive)} bytes; limit is "
                f"{self.limits.maximum_archive_bytes}"
            )
        return FlyRunResult(
            archive_bytes=archive,
            content_digest=_sha256(manifest_bytes),
            applied_input_digest=applied_input_digest,
            scientific_record_digest=scientific_record_digest,
            essential_record_count=len(self.essential_events),
            optional_record_count=len(self.optional_events),
            optional_trace_status=optional_status,
            manifest=manifest,
            summary=summary,
        )

    def _manifest(
        self,
        *,
        events_bytes: bytes,
        summary_bytes: bytes,
        summary: dict[str, Any],
        session: GameSession,
    ) -> dict[str, Any]:
        value = self.resolved.value
        dependency_lock = self.resolved.root / "uv.lock"
        decision = self.resolved.root / M08_DEFER_DECISION_PATH
        if sha256_file(decision) != M08_DEFER_DECISION_SHA256:
            raise FlyRunError("M08 deferred-human-gate decision identity changed")
        profile_recipe_sha256 = _sha256(
            _canonical_json(
                {
                    "live_profile_sha256": self.resolved.sha256,
                    "game_spec_sha256": self.resolved.game_spec_sha256,
                    "execution_kind": self.execution_kind,
                    "execution_context": self.execution_context,
                }
            )
        )
        profile_paths = {
            "game_spec": value["game"]["path"],
            "base_model": value["model"]["profile_path"],
            "numerical_criteria": value["model"]["numerical_criteria_path"],
            "controller": value["controller"]["path"],
            "encoder": value["encoder"]["path"],
            "decoder": value["decoder"]["path"],
            "accepted_base_environment": value["environment"]["path"],
        }
        resolved_profiles = {
            name: json.loads(
                (self.resolved.root / relative).read_text(encoding="utf-8")
            )
            for name, relative in profile_paths.items()
        }
        return {
            "format_id": FLYRUN_FORMAT_ID,
            "schema_version": FLYRUN_SCHEMA_VERSION,
            "classification": "DATA-ONLY BOUNDED AUTHORITATIVE RUN RECORD",
            "executable_content": False,
            "run": {
                "run_id": self.run_id,
                "round_id": f"{self.run_id}-round-1",
                "profile_recipe_sha256": profile_recipe_sha256,
                "applied_input_sha256": summary["applied_input_sha256"],
                "execution_kind": self.execution_kind,
                "execution_context": self.execution_context,
            },
            "provenance": {
                "architecture_sha256": ARCHITECTURE_SHA256,
                "live_profile_path": "profiles/live.json",
                "live_profile_sha256": self.resolved.sha256,
                "game_spec_path": value["game"]["path"],
                "game_spec_sha256": self.resolved.game_spec_sha256,
                "graph": value["graph"],
                "selected_live_backend": value["backend"],
                "executed_backend": session.runner.backend,
                "identities": {
                    "m07_live_candidate_sha256": value["m07_live_candidate"]["sha256"],
                    "runtime_model_spec_sha256": value["model"][
                        "runtime_model_spec_sha256"
                    ],
                    "controller_sha256": value["controller"]["sha256"],
                    "encoder_sha256": value["encoder"]["sha256"],
                    "decoder_sha256": value["decoder"]["sha256"],
                    "environment_sha256": value["environment"]["sha256"],
                },
                "clock": value["clock"],
                "seeds": {
                    "neural": session.runner.neural.seed,
                    "environment": session.runner.environment.seed,
                    "environment_rng": "numpy.PCG64",
                },
                "code_git_sha": self.code_git_sha,
                "dependency_lock_path": "uv.lock",
                "dependency_lock_sha256": sha256_file(dependency_lock),
            },
            "resolved_configuration": {
                "live_profile": value,
                "profiles": resolved_profiles,
                "runtime_model_spec": session.runner.model_spec.canonical_payload(),
                "effective_environment": asdict(session.runner.environment.config),
            },
            "tested_runtime_envelope": {
                "python": ">=3.12,<3.13",
                "executed_backend": session.runner.backend,
                "selected_live_backend": "deterministic serial CPU Numba kernel",
                "parallel": False if session.runner.backend == "kernel" else None,
                "fastmath": False if session.runner.backend == "kernel" else None,
                "capture_eligibility": "reset-only under the pinned project dependency lock",
                "reexecution_verified": False,
                "verification_milestone": "M10",
            },
            "initial_conditions": {
                "neural_seed": session.runner.model_spec.seed,
                "environment_seed": session.runner.environment_seed,
                "control_tick": 0,
                "neural_tick": 0,
                "held_escape_command": False,
                "environment": {
                    "x": session.runner.environment.config.initial_x,
                    "y": session.runner.environment.config.initial_y,
                    "heading_rad": session.runner.environment.config.initial_heading_rad,
                    "control_tick": 0,
                    "takeoff_ticks_remaining": 0,
                    "takeoff_heading_rad": None,
                    "takeoff_active": False,
                    "scheduled_impact_ticks": [],
                    "resolved_impacts": [],
                },
                "game": {
                    **(
                        {
                            "latest_aim": None,
                            "pending_aim": None,
                            "active_strike": None,
                            "attack_count": 0,
                            "cooldown_until_tick": 0,
                            "result": None,
                            "result_reason": None,
                        }
                        if self.execution_kind == "game-session"
                        else {
                            "kind": "bench-trial",
                            **self.execution_context,
                            "completed_intervals": 0,
                            "result": None,
                        }
                    )
                },
                "state_digest": next(
                    (
                        {
                            key: event[key]
                            for key in (
                                "control_tick",
                                "neural_tick",
                                "whole_state_sha256",
                                "neural_state_sha256",
                                "environment_state_sha256",
                                "game_state_sha256",
                            )
                        }
                        for event in self.essential_events
                        if event["type"] == "state_digest"
                        and event.get("digest_kind") == "initial"
                    ),
                    None,
                ),
            },
            "sampling": {
                "environment_frame_control_intervals": self.resolved.game_spec.presentation_intervals,
                "dnp01_events": "all declared DNp01 spike events at neural-tick resolution",
                "full_neuron_state_arrays": False,
                "state_digest_control_intervals": STATE_DIGEST_INTERVALS,
                "state_digest_boundary": "after an authoritative control interval and all GameSession updates at that boundary; initial before inputs; final after termination",
            },
            "event_ordering": {
                "identity": EVENT_ORDER_ID,
                "sort_key": ["control_tick", "event_ordinal"],
                "ordinal_rule": "monotonic recorder observation order after authoritative application; applied pending aim precedes same-tick attack commit",
            },
            "applied_input_hash": {
                "algorithm": "SHA-256",
                "encoding": "concatenated UTF-8 canonical JSON records with sorted keys and one LF terminator per record",
                "included_types": ["accepted_aim", "attack_commit"],
                "excluded": [
                    "recording_class",
                    "event_ordinal",
                    "rejected messages",
                    "coalesced-but-never-applied aim values",
                    "browser timestamps",
                ],
            },
            "limits": self.limits.as_dict(),
            "payloads": {
                "events.jsonl": {
                    "sha256": _sha256(events_bytes),
                    "bytes": len(events_bytes),
                },
                "summary.json": {
                    "sha256": _sha256(summary_bytes),
                    "bytes": len(summary_bytes),
                },
            },
            "validity": {
                "essential_input_evidence": summary["recording"]["essential_status"],
                "optional_trace": summary["recording"]["optional_status"],
                "reexecution": summary["reexecution"],
            },
            "integrity": {
                "applied_input_sha256": summary["applied_input_sha256"],
                "scientific_record_sha256": summary["scientific_record_sha256"],
                "final_whole_state_sha256": summary[
                    "final_whole_state_sha256"
                ],
            },
            "process_deviation": {
                "decision_id": M08_DEFER_DECISION_ID,
                "decision_path": M08_DEFER_DECISION_PATH,
                "decision_sha256": M08_DEFER_DECISION_SHA256,
                "m09_execution": "AT_RISK",
                "m08_g_game": "PENDING_UNMEASURED",
                "m09_is_m08_usability_evidence": False,
                "public_release_blocked": True,
            },
            "attempt_2_provenance": {
                "attempt_1_format": "flybench.flyrun.v0.1",
                "attempt_1_candidate_product_sha": "067b3c831469ce2475201074ad47b39853694b60",
                "attempt_1_submission_sha": "d15bae9ccc6e8bf2952b5d14adaaaf06a86fd3dc",
                "attempt_1_review_zip_sha256": "cff7e065c6a45aade81e23614e0a00d7eb0ed379d5422531e68ba4f629f9ea66",
                "attempt_1_external_verdict": "CHANGES_REQUIRED",
            },
        }


class RecordedGameSession:
    """Observe one existing authoritative GameSession; never advance a second path."""

    def __init__(self, session: GameSession, recorder: FlyRunRecorder):
        self.session = session
        self.recorder = recorder
        self.runner = session.runner
        self.spec = session.spec
        self._last_phase = session.snapshot()["phase"]
        self._last_decoded_command = False
        self._recorded_impacts: set[str] = set()
        self._round_end_recorded = False
        self._applied_input_cursor = 0
        self.recorder.record_essential(
            {
                "type": "lifecycle",
                "control_tick": self.control_tick,
                "phase": "round-start",
                "state": "running",
            }
        )
        self._record_state_digest("initial")

    @property
    def control_tick(self) -> int:
        return self.session.control_tick

    @property
    def result(self) -> str | None:
        return self.session.result

    @property
    def result_reason(self) -> str | None:
        return self.session.result_reason

    @property
    def last_impact(self) -> dict[str, Any] | None:
        return self.session.last_impact

    @property
    def attack_count(self) -> int:
        return self.session.attack_count

    @property
    def active_strike(self) -> object:
        return self.session.active_strike

    def snapshot(self) -> dict[str, Any]:
        return self.session.snapshot()

    def observation_for_current_interval(self) -> object:
        return self.session.observation_for_current_interval()

    def update_aim(self, x: object, y: object, sequence: object) -> dict[str, Any]:
        try:
            acknowledgement = self.session.update_aim(x, y, sequence)
        except GameInputError as exc:
            self.recorder.note_rejected_input(exc.code)
            raise
        self._capture_applied_inputs()
        return acknowledgement

    def commit_attack(self, x: object, y: object, sequence: object) -> dict[str, Any]:
        try:
            acknowledgement = self.session.commit_attack(x, y, sequence)
        except GameInputError as exc:
            self.recorder.note_rejected_input(exc.code)
            raise
        self._capture_applied_inputs()
        self._record_phase_transition(self.snapshot())
        return acknowledgement

    def advance_interval(self) -> dict[str, Any]:
        prior_tick = self.control_tick
        state = self.session.advance_interval()
        if self.control_tick == prior_tick:
            return state
        self._capture_applied_inputs()
        interval = self.runner.interval_records[-1]
        self.recorder.record_essential(
            {
                "type": "sensory_input",
                "control_tick": int(interval["start_control_tick"]),
                "phase": "form-observation",
                "applies_through_control_tick": int(interval["end_control_tick"]),
                "observation": interval["observation"],
            }
        )
        spikes = interval["dnp01_spikes"]
        if spikes:
            self.recorder.record_essential(
                {
                    "type": "neural_output",
                    "control_tick": int(interval["end_control_tick"]),
                    "phase": "advance-neural-20-steps",
                    "start_neural_tick": int(interval["start_neural_tick"]),
                    "end_neural_tick": int(interval["end_neural_tick"]),
                    "dnp01_spikes": spikes,
                }
            )
        decoded = bool(interval["decoded_next_command"])
        if decoded != self._last_decoded_command:
            self.recorder.record_essential(
                {
                    "type": "motor_command",
                    "control_tick": int(interval["end_control_tick"]),
                    "phase": "decode-completed-neural-interval",
                    "escape_request": decoded,
                    "applies_from_control_tick": int(interval["end_control_tick"]),
                }
            )
            self._last_decoded_command = decoded
        impact = state["last_impact"]
        new_impact = (
            impact is not None
            and impact["attack_id"] not in self._recorded_impacts
        )
        if new_impact:
            self._recorded_impacts.add(impact["attack_id"])
            self.recorder.record_essential(
                {
                    "type": "impact",
                    "control_tick": int(impact["control_tick"]),
                    "phase": "resolve-impact",
                    "attack_id": impact["attack_id"],
                    "locked_target": impact["locked_target"],
                    "authoritative_fly_position": impact[
                        "authoritative_fly_position"
                    ],
                    "distance": impact["distance"],
                    "strike_radius": impact["strike_radius"],
                    "outcome": impact["outcome"],
                    "previously_held_command": impact["previously_held_command"],
                    "decoded_next_command": impact["decoded_next_command"],
                }
            )
        self._record_phase_transition(state)
        if (
            self.control_tick % self.spec.presentation_intervals == 0
            or new_impact
            or state["result"] is not None
        ):
            self.recorder.record_optional(
                {
                    "type": "environment_frame",
                    "control_tick": self.control_tick,
                    "phase": "authoritative-state-sample",
                    "logical_time_ms": state["logical_time_ms"],
                    "game_phase": state["phase"],
                    "fly": {
                        "x": state["fly"]["x"],
                        "y": state["fly"]["y"],
                        "heading_rad": state["fly"]["heading_rad"],
                        "motion_mode": (
                            "takeoff" if state["fly"]["takeoff_active"] else "walking"
                        ),
                        "takeoff_started": state["fly"]["takeoff_started"],
                    },
                    "strike": state["strike"],
                    "stimulus": interval["observation"],
                }
            )
        if state["result"] is not None and not self._round_end_recorded:
            self._round_end_recorded = True
            self.recorder.record_essential(
                {
                    "type": "round_end",
                    "control_tick": self.control_tick,
                    "phase": "round-termination",
                    "result": state["result"],
                    "termination_reason": state["result_reason"],
                }
            )
        if state["result"] is not None:
            self._record_state_digest(
                "periodic-final"
                if self.control_tick % STATE_DIGEST_INTERVALS == 0
                else "final"
            )
        elif self.control_tick % STATE_DIGEST_INTERVALS == 0:
            self._record_state_digest("periodic")
        return state

    def _capture_applied_inputs(self) -> None:
        records = self.session.applied_input_records
        for applied in records[self._applied_input_cursor :]:
            event = dict(applied)
            event["phase"] = "apply-authoritative-input"
            self.recorder.record_essential(event)
        self._applied_input_cursor = len(records)

    def _record_state_digest(self, digest_kind: str) -> None:
        digest = scientific_state_digest(
            self.runner,
            game_session=self.session,
        )
        self.recorder.record_essential(
            {
                "type": "state_digest",
                "control_tick": digest["control_tick"],
                "phase": "post-authoritative-boundary",
                "digest_kind": digest_kind,
                **{
                    key: value
                    for key, value in digest.items()
                    if key != "control_tick"
                },
            }
        )

    def _record_phase_transition(self, state: dict[str, Any]) -> None:
        current = str(state["phase"])
        if current == self._last_phase:
            return
        self.recorder.record_essential(
            {
                "type": "game_phase",
                "control_tick": self.control_tick,
                "phase": "game-phase-transition",
                "from": self._last_phase,
                "to": current,
            }
        )
        self._last_phase = current

    def finalize(self) -> FlyRunResult:
        return self.recorder.finalize(self.session)


@dataclass(slots=True)
class _BenchSessionView:
    runner: Any
    result: str = "trial-complete"
    result_reason: str = "fixed-duration-complete"
    attack_count: int = 0
    coalesced_aim_updates: int = 0

    @property
    def control_tick(self) -> int:
        return int(self.runner.control_tick)


class RecordedBenchTrial:
    """Observe the existing accepted scripted benchmark Runner path."""

    def __init__(
        self,
        runner: Any,
        recorder: FlyRunRecorder,
        *,
        scenario: str,
        interval_count: int,
    ):
        self.runner = runner
        self.recorder = recorder
        self.scenario = scenario
        self.interval_count = interval_count
        self.completed_intervals = 0
        self._last_decoded_command = False
        self.recorder.record_essential(
            {
                "type": "lifecycle",
                "control_tick": 0,
                "phase": "bench-trial-start",
                "state": "running",
            }
        )
        self._record_state_digest("initial", result=None)

    def capture_interval(self, record: dict[str, Any]) -> None:
        self.completed_intervals = int(record["end_control_tick"])
        self.recorder.record_essential(
            {
                "type": "sensory_input",
                "control_tick": int(record["start_control_tick"]),
                "phase": "form-observation",
                "applies_through_control_tick": int(record["end_control_tick"]),
                "observation": record["observation"],
            }
        )
        if record["dnp01_spikes"]:
            self.recorder.record_essential(
                {
                    "type": "neural_output",
                    "control_tick": int(record["end_control_tick"]),
                    "phase": "advance-neural-20-steps",
                    "start_neural_tick": int(record["start_neural_tick"]),
                    "end_neural_tick": int(record["end_neural_tick"]),
                    "dnp01_spikes": record["dnp01_spikes"],
                }
            )
        decoded = bool(record["decoded_next_command"])
        if decoded != self._last_decoded_command:
            self.recorder.record_essential(
                {
                    "type": "motor_command",
                    "control_tick": int(record["end_control_tick"]),
                    "phase": "decode-completed-neural-interval",
                    "escape_request": decoded,
                    "applies_from_control_tick": int(record["end_control_tick"]),
                }
            )
            self._last_decoded_command = decoded
        for impact in record["impacts"]:
            self.recorder.record_essential(
                {
                    "type": "impact",
                    "control_tick": int(impact["control_tick"]),
                    "phase": "resolve-impact",
                    "outcome": impact["outcome"],
                    "takeoff_was_active": impact["takeoff_was_active"],
                    "benchmark_scenario": self.scenario,
                }
            )
        if self.completed_intervals % 2 == 0:
            motion = record["motion"]
            self.recorder.record_optional(
                {
                    "type": "environment_frame",
                    "control_tick": self.completed_intervals,
                    "phase": "authoritative-state-sample",
                    "logical_time_ms": int(record["end_ms"]),
                    "game_phase": "bench-trial",
                    "fly": {
                        "x": motion["x"],
                        "y": motion["y"],
                        "heading_rad": motion["heading_rad"],
                        "motion_mode": (
                            "takeoff" if motion["takeoff_active"] else "walking"
                        ),
                        "takeoff_started": motion["takeoff_started"],
                    },
                    "strike": None,
                    "stimulus": record["observation"],
                }
            )
        if (
            self.completed_intervals < self.interval_count
            and self.completed_intervals % STATE_DIGEST_INTERVALS == 0
        ):
            self._record_state_digest("periodic", result=None)

    def _bench_state(self, *, result: str | None) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "fixed_interval_count": self.interval_count,
            "completed_intervals": self.completed_intervals,
            "result": result,
        }

    def _record_state_digest(self, digest_kind: str, *, result: str | None) -> None:
        digest = scientific_state_digest(
            self.runner,
            bench_state=self._bench_state(result=result),
        )
        self.recorder.record_essential(
            {
                "type": "state_digest",
                "control_tick": digest["control_tick"],
                "phase": "post-authoritative-boundary",
                "digest_kind": digest_kind,
                **{
                    key: value
                    for key, value in digest.items()
                    if key != "control_tick"
                },
            }
        )

    def finalize(self) -> FlyRunResult:
        if self.completed_intervals != self.interval_count:
            raise FlyRunError("cannot finalize an incomplete benchmark trial")
        self.recorder.record_essential(
            {
                "type": "round_end",
                "control_tick": self.completed_intervals,
                "phase": "bench-trial-termination",
                "result": "trial-complete",
                "termination_reason": "fixed-duration-complete",
            }
        )
        self._record_state_digest(
            "periodic-final"
            if self.completed_intervals % STATE_DIGEST_INTERVALS == 0
            else "final",
            result="trial-complete",
        )
        return self.recorder.finalize(_BenchSessionView(self.runner))  # type: ignore[arg-type]


def build_recorded_live_session(
    profile: ResolvedLiveProfile | Path,
    *,
    run_id: str,
    limits: RecorderLimits | None = None,
    code_git_sha: str | None = None,
) -> RecordedGameSession:
    resolved = load_live_profile(profile) if isinstance(profile, Path) else profile
    authoritative = build_live_session(resolved)
    recorder = FlyRunRecorder(
        resolved,
        run_id=run_id,
        limits=limits,
        code_git_sha=code_git_sha,
    )
    return RecordedGameSession(authoritative, recorder)


def run_representative_recording(
    profile: ResolvedLiveProfile | Path,
    *,
    run_id: str = "m09-representative-v1",
    code_git_sha: str | None = None,
) -> tuple[RecordedGameSession, FlyRunResult]:
    subject = build_recorded_live_session(
        profile, run_id=run_id, code_git_sha=code_git_sha
    )
    targets = (
        (10.0, 10.0),
        (-10.0, 10.0),
        (10.0, -10.0),
        (-10.0, -10.0),
        (10.0, 10.0),
        (-10.0, 10.0),
    )
    sequence = 0
    target_index = 0
    while subject.result is None:
        state = subject.snapshot()
        if state["phase"] == "ready" and target_index < len(targets):
            target = targets[target_index]
            sequence += 1
            subject.update_aim(target[0], target[1], sequence)
            sequence += 1
            subject.commit_attack(target[0], target[1], sequence)
            target_index += 1
        subject.advance_interval()
        if subject.control_tick > subject.spec.round_horizon_tick:
            raise RuntimeError("representative recording exceeded the GameSpec horizon")
    return subject, subject.finalize()


def run_selected_benchmark(
    stimulus_path: Path,
    *,
    record_directory: Path | None = None,
    code_git_sha: str | None = None,
) -> tuple[dict[str, Any], FlyRunResult | None]:
    """Run the accepted selected standard-looming trial, optionally observing it."""

    from flybench.bench import scripted_observation
    from flybench.catch import load_environment_config
    from flybench.model import load_candidate_model_spec
    from flybench.runner import CONTROL_INTERVAL_MS, NEURAL_DT_MS, Runner, load_graph

    root = stimulus_path.resolve().parent.parent
    resolved = load_live_profile(root / "profiles" / "live.json")
    stimulus = json.loads(stimulus_path.resolve().read_text(encoding="utf-8"))
    if (
        stimulus.get("profile_id") != "flybench.m06-looming-controls.v0.1"
        or "standard looming" not in stimulus.get("scenarios_in_execution_order", [])
    ):
        raise ValueError("selected benchmark requires the accepted looming controls")
    controller = json.loads(
        (root / resolved.value["controller"]["path"]).read_text(encoding="utf-8")
    )
    scale = float(controller["selected_runtime_synaptic_scale"])
    peak_drive = float(controller["selected_peak_sensory_external_drive"])
    seed = int(stimulus["seed"]["trial_seed"])
    model = load_candidate_model_spec(
        neural_dt_ms=NEURAL_DT_MS,
        runtime_synaptic_scale=scale,
        seed=seed,
        model_profile_path=root / resolved.value["model"]["profile_path"],
        criteria_path=root
        / resolved.value["model"]["numerical_criteria_path"],
    )
    runner = Runner(
        load_graph(root / resolved.value["graph"]["path"]),
        model,
        peak_sensory_external_drive=peak_drive,
        environment_config=load_environment_config(
            root / resolved.value["environment"]["path"]
        ),
        environment_seed=seed + 1,
        backend="reference",
    )
    interval_count = int(
        stimulus["trial"]["duration_ms"] / CONTROL_INTERVAL_MS
    )
    recorder_result: FlyRunResult | None = None
    observer: RecordedBenchTrial | None = None
    if record_directory is not None:
        context = {
            "scenario": "standard looming",
            "stimulus_profile_path": "profiles/looming-controls.json",
            "stimulus_profile_sha256": sha256_file(stimulus_path.resolve()),
            "fixture_name": "looming-seed-0.flyrun",
            "seed_index": 0,
            "actual_neural_seed": seed,
            "actual_environment_seed": seed + 1,
            "fixed_interval_count": interval_count,
        }
        recorder = FlyRunRecorder(
            resolved,
            run_id="m09-bench-standard-looming-seed-index-0",
            code_git_sha=code_git_sha,
            execution_kind="bench-trial",
            execution_context=context,
        )
        observer = RecordedBenchTrial(
            runner,
            recorder,
            scenario="standard looming",
            interval_count=interval_count,
        )
    for control_tick in range(interval_count):
        observation, impact = scripted_observation(
            stimulus, "standard looming", control_tick
        )
        record = runner.advance_control_interval(
            observation,
            impact_at_end=impact,
        )
        if observer is not None:
            observer.capture_interval(record)
    summary = runner.finish_run()
    if observer is not None:
        recorder_result = observer.finalize()
        assert record_directory is not None
        write_flyrun(record_directory / "looming-seed-0.flyrun", recorder_result)
    return summary, recorder_result


def write_flyrun(path: Path, result: FlyRunResult) -> None:
    if path.suffix != ".flyrun":
        raise ValueError("recording output must use the .flyrun suffix")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(result.archive_bytes)
    os.replace(temporary, path)


def _build_zip(entries: dict[str, bytes]) -> bytes:
    if tuple(entries) != FLYRUN_MEMBERS:
        raise FlyRunError("flyrun member order or inventory changed")
    archive = io.BytesIO()
    with zipfile.ZipFile(
        archive, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as bundle:
        for name in FLYRUN_MEMBERS:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            bundle.writestr(info, entries[name])
    return archive.getvalue()


def _safe_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    pure = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or info.is_dir()
    ):
        raise FlyRunSafetyError(f"unsafe flyrun member path: {name!r}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode) or mode & 0o111:
        raise FlyRunSafetyError(f"executable or linked flyrun member rejected: {name!r}")
    if info.flag_bits & 0x1:
        raise FlyRunSafetyError("encrypted flyrun members are unsupported")
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise FlyRunSafetyError("unsupported flyrun compression method")


def load_flyrun(path: Path) -> LoadedFlyRun:
    size = path.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        raise FlyRunLimitError(
            f"flyrun archive is {size} bytes; hard limit is {MAX_ARCHIVE_BYTES}"
        )
    try:
        bundle = zipfile.ZipFile(path, mode="r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise FlyRunSafetyError(f"invalid flyrun ZIP: {exc}") from exc
    with bundle:
        infos = bundle.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise FlyRunSafetyError("flyrun member count exceeds the hard allowlist")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise FlyRunSafetyError("duplicate flyrun members are forbidden")
        for info in infos:
            _safe_member(info)
        if tuple(names) != FLYRUN_MEMBERS:
            raise FlyRunSafetyError(
                "flyrun must contain only manifest.json, events.jsonl, and summary.json"
            )
        expanded = sum(info.file_size for info in infos)
        if expanded > MAX_EXPANDED_BYTES:
            raise FlyRunLimitError(
                f"expanded flyrun is {expanded} bytes; hard limit is {MAX_EXPANDED_BYTES}"
            )
        payloads = {info.filename: bundle.read(info) for info in infos}
    try:
        manifest = json.loads(
            payloads["manifest.json"], parse_constant=_reject_json_constant
        )
        summary = json.loads(
            payloads["summary.json"], parse_constant=_reject_json_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlyRunSafetyError(f"invalid flyrun JSON: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_id") != FLYRUN_FORMAT_ID
        or manifest.get("schema_version") != FLYRUN_SCHEMA_VERSION
        or manifest.get("executable_content") is not False
    ):
        raise FlyRunSafetyError("unsupported or executable flyrun manifest")
    declared_limits = manifest.get("limits")
    if not isinstance(declared_limits, dict):
        raise FlyRunSafetyError("flyrun limits are missing")
    hard_limits = RecorderLimits().as_dict()
    for name, hard_limit in hard_limits.items():
        value = declared_limits.get(name)
        if type(value) is not int or value < 0 or value > hard_limit:
            raise FlyRunSafetyError(f"unsafe declared flyrun limit: {name}")
    for name in ("events.jsonl", "summary.json"):
        entry = manifest.get("payloads", {}).get(name, {})
        if (
            entry.get("bytes") != len(payloads[name])
            or entry.get("sha256") != _sha256(payloads[name])
        ):
            raise FlyRunSafetyError(f"flyrun payload identity mismatch: {name}")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(payloads["events.jsonl"].splitlines(), start=1):
        if len(line) > MAX_EVENT_LINE_BYTES:
            raise FlyRunLimitError(f"events.jsonl line {line_number} is oversized")
        try:
            event = json.loads(line, parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FlyRunSafetyError(
                f"invalid events.jsonl record {line_number}: {exc}"
            ) from exc
        if not isinstance(event, dict):
            raise FlyRunSafetyError("every flyrun event must be a JSON object")
        if (
            type(event.get("control_tick")) is not int
            or event["control_tick"] < 0
            or event["control_tick"]
            > declared_limits["maximum_round_duration_ms"] // 10
            or not isinstance(event.get("type"), str)
            or not isinstance(event.get("phase"), str)
            or event.get("recording_class") not in {"essential", "optional"}
            or type(event.get("event_ordinal")) is not int
            or event["event_ordinal"] < 0
        ):
            raise FlyRunSafetyError("flyrun event schema validation failed")
        events.append(event)
    essential_count = sum(
        event["recording_class"] == "essential" for event in events
    )
    optional_count = len(events) - essential_count
    if essential_count > declared_limits["maximum_essential_records"]:
        raise FlyRunLimitError("essential event count exceeds the declared limit")
    if optional_count > declared_limits["maximum_optional_records"]:
        raise FlyRunLimitError("optional event count exceeds the declared limit")
    if not isinstance(summary, dict) or summary.get("schema_version") != FLYRUN_SCHEMA_VERSION:
        raise FlyRunSafetyError("flyrun summary schema validation failed")
    if summary.get("run_id") != manifest.get("run", {}).get("run_id"):
        raise FlyRunSafetyError("flyrun run identity mismatch")
    event_keys = [
        (int(event["control_tick"]), int(event["event_ordinal"])) for event in events
    ]
    if event_keys != sorted(event_keys) or len(
        {event["event_ordinal"] for event in events}
    ) != len(events):
        raise FlyRunSafetyError("flyrun event ordering is not canonical")
    applied_input_digest = canonical_applied_input_sha256(events)
    declared_applied = {
        summary.get("applied_input_sha256"),
        manifest.get("run", {}).get("applied_input_sha256"),
        manifest.get("integrity", {}).get("applied_input_sha256"),
    }
    if declared_applied != {applied_input_digest}:
        raise FlyRunSafetyError("flyrun applied-input identity mismatch")
    reexecution = manifest.get("validity", {}).get("reexecution", {})
    if (
        not isinstance(reexecution, dict)
        or reexecution.get("verified") is not False
        or reexecution.get("verification_milestone") != "M10"
        or summary.get("reexecution") != reexecution
    ):
        raise FlyRunSafetyError("flyrun re-execution status is unsupported or overstated")
    state_events = [event for event in events if event["type"] == "state_digest"]
    if not state_events or state_events[0].get("digest_kind") != "initial":
        raise FlyRunSafetyError("flyrun initial state digest is missing")
    if state_events[-1].get("digest_kind") not in {"final", "periodic-final"}:
        raise FlyRunSafetyError("flyrun final state digest is missing")
    final_control_tick = summary.get("final_control_tick")
    if type(final_control_tick) is not int or final_control_tick < 0:
        raise FlyRunSafetyError("flyrun final control tick is invalid")
    expected_state_ticks = [0]
    expected_state_ticks.extend(
        range(STATE_DIGEST_INTERVALS, final_control_tick, STATE_DIGEST_INTERVALS)
    )
    if final_control_tick not in expected_state_ticks:
        expected_state_ticks.append(final_control_tick)
    if [event["control_tick"] for event in state_events] != expected_state_ticks:
        raise FlyRunSafetyError("flyrun state-digest cadence is incomplete")
    for event in state_events:
        if event.get("recording_class") != "essential" or any(
            not isinstance(event.get(name), str)
            or len(event[name]) != 64
            or any(character not in "0123456789abcdef" for character in event[name])
            for name in (
                "whole_state_sha256",
                "neural_state_sha256",
                "environment_state_sha256",
                "game_state_sha256",
            )
        ):
            raise FlyRunSafetyError("flyrun state-digest schema validation failed")
    if (
        manifest.get("initial_conditions", {}).get("state_digest", {}).get(
            "whole_state_sha256"
        )
        != state_events[0].get("whole_state_sha256")
        or manifest.get("integrity", {}).get("final_whole_state_sha256")
        != state_events[-1].get("whole_state_sha256")
        or summary.get("final_whole_state_sha256")
        != state_events[-1].get("whole_state_sha256")
    ):
        raise FlyRunSafetyError("flyrun state-digest identity mismatch")
    return LoadedFlyRun(
        path=path,
        archive_bytes=size,
        content_digest=_sha256(payloads["manifest.json"]),
        manifest=manifest,
        events=tuple(events),
        summary=summary,
    )
