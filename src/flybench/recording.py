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

from flybench.game import (
    GameInputError,
    GameSession,
    ResolvedLiveProfile,
    build_live_session,
    load_live_profile,
    sha256_file,
)


FLYRUN_FORMAT_ID = "flybench.flyrun.v0.1"
FLYRUN_SCHEMA_VERSION = 1
FLYRUN_MEMBERS = ("manifest.json", "events.jsonl", "summary.json")
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
        self.essential_events: list[dict[str, Any]] = []
        self.optional_events: list[dict[str, Any]] = []
        self.essential_dropped = 0
        self.optional_dropped = 0
        self.rejected_diagnostics: dict[str, int] = {}
        self._optional_gap_recorded = False
        self._finalized = False

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
        _canonical_json(value)
        return value

    def finalize(self, session: GameSession) -> FlyRunResult:
        if self._finalized:
            raise FlyRunError("recorder already finalized")
        if session.result is None:
            raise FlyRunError("cannot finalize before authoritative round termination")
        self._finalized = True
        runner_summary = session.runner.finish_run()
        applied_input_digest = _sha256(
            b"".join(_canonical_json(event) for event in self.applied_input_events)
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
            }
        ]
        scientific_record_digest = _sha256(
            b"".join(_canonical_json(event) for event in scientific_events)
        )
        optional_status = "TRUNCATED" if self.optional_dropped else "COMPLETE"
        essential_status = "INCOMPLETE" if self.essential_dropped else "COMPLETE"
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
                "reexecution_certifiable": self.essential_dropped == 0,
            },
            "process_status": {
                "m09_execution": "AT_RISK",
                "decision": M08_DEFER_DECISION_ID,
                "m08_g_game": "PENDING_UNMEASURED",
                "m08_usability_pass_claim": False,
                "public_release_blocked": True,
            },
        }
        ordered_events = [
            (event, 0, index)
            for index, event in enumerate(self.essential_events)
        ] + [
            (event, 1, index)
            for index, event in enumerate(self.optional_events)
        ]
        events = [
            event
            for event, _recording_class_order, _stream_index in sorted(
                ordered_events,
                key=lambda item: (
                    int(item[0]["control_tick"]),
                    item[1],
                    item[2],
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
            },
            "provenance": {
                "architecture_sha256": ARCHITECTURE_SHA256,
                "live_profile_path": "profiles/live.json",
                "live_profile_sha256": self.resolved.sha256,
                "game_spec_path": value["game"]["path"],
                "game_spec_sha256": self.resolved.game_spec_sha256,
                "graph": value["graph"],
                "backend": value["backend"],
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
                    "neural": value["model"]["seed"],
                    "environment": value["environment"]["seed"],
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
                "backend": "deterministic serial CPU Numba kernel",
                "parallel": False,
                "fastmath": False,
                "exact_reexecution_scope": "reset-only on the pinned project dependency lock",
            },
            "initial_conditions": {
                "fly": {"x": 0.0, "y": 0.0, "heading_rad": 0.0},
                "held_escape_command": False,
                "control_tick": 0,
                "neural_tick": 0,
            },
            "sampling": {
                "environment_frame_control_intervals": self.resolved.game_spec.presentation_intervals,
                "dnp01_events": "all declared DNp01 spike events at neural-tick resolution",
                "full_neuron_state_arrays": False,
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
                "reexecution_certifiable": summary["recording"][
                    "reexecution_certifiable"
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
        self.recorder.record_essential(
            {
                "type": "lifecycle",
                "control_tick": self.control_tick,
                "phase": "round-start",
                "state": "running",
            }
        )

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
        aim = self.session.latest_aim
        assert aim is not None
        self.recorder.record_essential(
            {
                "type": "accepted_aim",
                "control_tick": int(acknowledgement["server_tick"]),
                "phase": "apply-accepted-input",
                "sequence": int(acknowledgement["sequence"]),
                "aim": {"x": aim[0], "y": aim[1]},
            }
        )
        return acknowledgement

    def commit_attack(self, x: object, y: object, sequence: object) -> dict[str, Any]:
        try:
            acknowledgement = self.session.commit_attack(x, y, sequence)
        except GameInputError as exc:
            self.recorder.note_rejected_input(exc.code)
            raise
        self.recorder.record_essential(
            {
                "type": "attack_commit",
                "control_tick": int(acknowledgement["server_tick"]),
                "phase": "apply-accepted-input",
                "sequence": int(acknowledgement["sequence"]),
                "attack_id": acknowledgement["attack_id"],
                "locked_target": acknowledgement["locked_target"],
                "impact_tick": int(acknowledgement["impact_tick"]),
            }
        )
        self._record_phase_transition(self.snapshot())
        return acknowledgement

    def advance_interval(self) -> dict[str, Any]:
        prior_tick = self.control_tick
        state = self.session.advance_interval()
        if self.control_tick == prior_tick:
            return state
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
        return state

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
    if not isinstance(summary, dict) or summary.get("schema_version") != 1:
        raise FlyRunSafetyError("flyrun summary schema validation failed")
    if summary.get("run_id") != manifest.get("run", {}).get("run_id"):
        raise FlyRunSafetyError("flyrun run identity mismatch")
    return LoadedFlyRun(
        path=path,
        archive_bytes=size,
        content_digest=_sha256(payloads["manifest.json"]),
        manifest=manifest,
        events=tuple(events),
        summary=summary,
    )
