"""M08 local Catch the Fly session around the accepted authoritative Runner."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from flybench.catch import load_environment_config
from flybench.encoding import ThreatObservation
from flybench.kernel import KERNEL_IMPLEMENTATION_ID, kernel_configuration
from flybench.model import load_candidate_model_spec
from flybench.runner import (
    ACCEPTED_CIRCUIT_DIGEST,
    CONTROL_INTERVAL_MS,
    NEURAL_DT_MS,
    NEURAL_STEPS_PER_CONTROL_INTERVAL,
    Runner,
    load_graph,
)


ACCEPTED_GRAPH_PROFILE_SHA256 = (
    "29a6b4fb98d29f2fbf76fc031bea2f75d7ed534540666fc50279168358f5232b"
)
ACCEPTED_LIVE_CANDIDATE_SHA256 = (
    "df1f06266c4fb2274ae32a269b538104567c7fc79369b9a88a761ae47fd0cd88"
)
ACCEPTED_KERNEL_SOURCE_SHA256 = (
    "5b1db14f97974dd377a3cbd66ecaca5f0b307c309001c7f2620ab5bcd2c12723"
)
ACCEPTED_MODEL_SPEC_SHA256 = (
    "8fb910576dd01bb28dece1198274072302e03cd7a00808dcec8948e4b2dac2bc"
)
ACCEPTED_CONTROLLER_SHA256 = (
    "0b3577ec2dc257f130d59f0219544ad0dae479080027e25bdeca2182673bf817"
)
ACCEPTED_ENCODER_SHA256 = (
    "7840fa564c7f34d188797899ced5c87ffd9825469172f3a7c1076e36873c7de7"
)
ACCEPTED_DECODER_SHA256 = (
    "7fec8cef8d5ca3679fbf65456f236bab2c5e15e7902aafc5146ce8d83838ca4f"
)
ACCEPTED_ENVIRONMENT_SHA256 = (
    "9119848704b84416e1eed25ed8ae84735216ccb251e83147ea8970e2754968f7"
)
ACCEPTED_N = 313
ACCEPTED_E = 20607
ACCEPTED_CONTACTS = 79112
M08_STARTING_GAME_SPEC_SHA256 = (
    "521dc8f33457155b0f5c5438f11da2c6b489d9a5667b7d63421ed863fbb62cd7"
)
ACCEPTED_GAME_SPEC_SHA256 = (
    "4d28775a7c69f063d7aab0cee44d6f8b1c4eaa72687644f96a59c65ae7220a25"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _ticks(milliseconds: int, *, name: str) -> int:
    if type(milliseconds) is not int or milliseconds <= 0:
        raise ValueError(f"{name} must be a positive integer number of milliseconds")
    if milliseconds % int(CONTROL_INTERVAL_MS):
        raise ValueError(f"{name} must be an exact number of control intervals")
    return milliseconds // int(CONTROL_INTERVAL_MS)


@dataclass(frozen=True, slots=True)
class GameSpec:
    """Versioned game-only rules; none of these fields are physiology."""

    profile_id: str
    classification: str
    arena_min: float
    arena_max: float
    round_horizon_ms: int
    maximum_committed_attacks: int
    attack_wind_up_ms: int
    stimulus_start_offset_ms: int
    stimulus_end_offset_ms: int
    impact_offset_ms: int
    cooldown_after_impact_ms: int
    strike_radius: float
    stimulus_start_distance: float
    stimulus_end_distance: float
    stimulus_radial_velocity_per_ms: float
    presentation_intervals: int

    def __post_init__(self) -> None:
        if self.profile_id not in {
            "flybench.catch-game.v0.1",
            "flybench.catch-game.v0.2",
        }:
            raise ValueError("unsupported GameSpec identity")
        if not self.classification.startswith("PROVISIONAL GAME MECHANICS"):
            raise ValueError("GameSpec classification must remain explicitly provisional")
        if not math.isfinite(self.arena_min) or not math.isfinite(self.arena_max):
            raise ValueError("arena bounds must be finite")
        if not self.arena_min < self.arena_max:
            raise ValueError("arena bounds must be strictly ordered")
        if type(self.maximum_committed_attacks) is not int or self.maximum_committed_attacks <= 0:
            raise ValueError("maximum committed attacks must be a positive integer")
        for name, value in (
            ("round_horizon_ms", self.round_horizon_ms),
            ("attack_wind_up_ms", self.attack_wind_up_ms),
            ("stimulus_start_offset_ms", self.stimulus_start_offset_ms),
            ("stimulus_end_offset_ms", self.stimulus_end_offset_ms),
            ("impact_offset_ms", self.impact_offset_ms),
            ("cooldown_after_impact_ms", self.cooldown_after_impact_ms),
        ):
            _ticks(value, name=name)
        if self.attack_wind_up_ms != self.impact_offset_ms:
            raise ValueError("wind-up and impact offsets must identify one boundary")
        if not 0 < self.stimulus_start_offset_ms < self.stimulus_end_offset_ms:
            raise ValueError("stimulus window must be strictly ordered")
        if self.stimulus_end_offset_ms != self.impact_offset_ms:
            raise ValueError("stimulus must end at the impact boundary")
        if not math.isfinite(self.strike_radius) or self.strike_radius <= 0.0:
            raise ValueError("strike radius must be finite and positive")
        if not self.stimulus_start_distance > self.stimulus_end_distance > 0.0:
            raise ValueError("looming distances must be positive and approaching")
        if not math.isfinite(self.stimulus_radial_velocity_per_ms) or self.stimulus_radial_velocity_per_ms >= 0.0:
            raise ValueError("looming radial velocity must be finite and negative")
        if type(self.presentation_intervals) is not int or self.presentation_intervals <= 0:
            raise ValueError("presentation interval count must be positive")

    @property
    def round_horizon_tick(self) -> int:
        return _ticks(self.round_horizon_ms, name="round_horizon_ms")

    @property
    def stimulus_start_ticks(self) -> int:
        return _ticks(self.stimulus_start_offset_ms, name="stimulus_start_offset_ms")

    @property
    def impact_ticks(self) -> int:
        return _ticks(self.impact_offset_ms, name="impact_offset_ms")

    @property
    def cooldown_ticks(self) -> int:
        return _ticks(self.cooldown_after_impact_ms, name="cooldown_after_impact_ms")


def load_game_spec(path: Path) -> GameSpec:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("unsupported GameSpec schema")
    if value.get("policy") != {
        "hidden_difficulty_adjustment": False,
        "adaptive_handicap": False,
        "neural_parameter_change": False,
        "client_authoritative_collision": False,
    }:
        raise ValueError("M08 GameSpec policy boundaries changed")
    arena = value["arena"]
    round_value = value["round"]
    attack = value["attack"]
    stimulus = value["stimulus"]
    clock = value["clock"]
    presentation = value["presentation"]
    if (
        float(clock["control_interval_ms"]) != CONTROL_INTERVAL_MS
        or float(clock["neural_dt_ms"]) != NEURAL_DT_MS
        or int(clock["neural_steps_per_control_interval"])
        != NEURAL_STEPS_PER_CONTROL_INTERVAL
        or clock["ordering_identity"] != "flybench.neural-order.v1"
    ):
        raise ValueError("GameSpec clock differs from the accepted Runner clock")
    if round_value.get("first_attack_available_immediately") is not True:
        raise ValueError("the first attack must be immediately available")
    if stimulus.get("direction_or_bearing") is not False:
        raise ValueError("direction or bearing must not enter the scalar stimulus")
    if value.get("profile_id") == "flybench.catch-game.v0.2":
        provenance = value.get("provenance", {})
        if (
            provenance.get("previous_game_spec_path") != "profiles/game-v0.1.json"
            or provenance.get("previous_game_spec_sha256")
            != M08_STARTING_GAME_SPEC_SHA256
            or provenance.get("bounded_change")
            != {
                "field": "attack.strike_radius",
                "previous": 1.0,
                "current": 0.55,
                "units": "abstract arena units",
            }
            or provenance.get("scientific_runtime_changes") is not False
            or provenance.get("automatic_win_rate_tuning") is not False
        ):
            raise ValueError("M08 GameSpec revision provenance is incomplete")
    return GameSpec(
        profile_id=value["profile_id"],
        classification=value["classification"],
        arena_min=float(arena["minimum"]),
        arena_max=float(arena["maximum"]),
        round_horizon_ms=int(round_value["horizon_ms"]),
        maximum_committed_attacks=int(round_value["maximum_committed_attacks"]),
        attack_wind_up_ms=int(attack["wind_up_ms"]),
        stimulus_start_offset_ms=int(attack["stimulus_start_offset_ms"]),
        stimulus_end_offset_ms=int(attack["stimulus_end_offset_ms"]),
        impact_offset_ms=int(attack["impact_offset_ms"]),
        cooldown_after_impact_ms=int(attack["cooldown_after_impact_ms"]),
        strike_radius=float(attack["strike_radius"]),
        stimulus_start_distance=float(stimulus["start_distance"]),
        stimulus_end_distance=float(stimulus["end_distance"]),
        stimulus_radial_velocity_per_ms=float(stimulus["radial_velocity_per_ms"]),
        presentation_intervals=int(presentation["control_intervals_per_state"]),
    )


@dataclass(frozen=True, slots=True)
class ResolvedLiveProfile:
    path: Path
    root: Path
    sha256: str
    value: dict[str, Any]
    game_spec: GameSpec
    game_spec_sha256: str


def _checked_reference(root: Path, value: dict[str, Any], expected: str, label: str) -> Path:
    path = root / value["path"]
    actual = sha256_file(path)
    if value.get("sha256") != expected or actual != expected:
        raise ValueError(f"{label} identity mismatch")
    return path


def load_live_profile(path: Path) -> ResolvedLiveProfile:
    path = path.resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("profile_id") != "flybench.local-live.v0.1":
        raise ValueError("unsupported M08 live profile")
    root = path.parent.parent
    graph = value.get("graph", {})
    if graph != {
        "path": "data/compiled/escape",
        "semantic_digest": ACCEPTED_CIRCUIT_DIGEST,
        "N": ACCEPTED_N,
        "E": ACCEPTED_E,
        "represented_contacts": ACCEPTED_CONTACTS,
        "profile_path": "profiles/escape-circuit.json",
        "profile_sha256": ACCEPTED_GRAPH_PROFILE_SHA256,
    }:
        raise ValueError("live graph declaration differs from the accepted circuit")
    if sha256_file(root / graph["profile_path"]) != ACCEPTED_GRAPH_PROFILE_SHA256:
        raise ValueError("accepted circuit profile bytes changed")
    _checked_reference(
        root,
        value["m07_live_candidate"],
        ACCEPTED_LIVE_CANDIDATE_SHA256,
        "M07 live candidate",
    )
    for key, expected in (
        ("controller", ACCEPTED_CONTROLLER_SHA256),
        ("encoder", ACCEPTED_ENCODER_SHA256),
        ("decoder", ACCEPTED_DECODER_SHA256),
        ("environment", ACCEPTED_ENVIRONMENT_SHA256),
    ):
        _checked_reference(root, value[key], expected, key)
    backend = value.get("backend", {})
    if (
        backend.get("name") != "kernel"
        or backend.get("kernel_id") != KERNEL_IMPLEMENTATION_ID
        or backend.get("source_sha256") != ACCEPTED_KERNEL_SOURCE_SHA256
        or sha256_file(root / backend["source_path"]) != ACCEPTED_KERNEL_SOURCE_SHA256
        or backend.get("serial") is not True
        or backend.get("parallel") is not False
        or backend.get("fastmath") is not False
    ):
        raise ValueError("live backend differs from accepted M07 kernel")
    configuration = kernel_configuration()
    if configuration["parallel"] is not False or configuration["fastmath"] is not False:
        raise ValueError("runtime kernel compiler options changed")
    clock = value.get("clock", {})
    if clock != {
        "neural_dt_ms": NEURAL_DT_MS,
        "control_interval_ms": int(CONTROL_INTERVAL_MS),
        "neural_steps_per_control_interval": NEURAL_STEPS_PER_CONTROL_INTERVAL,
        "ordering_identity": "flybench.neural-order.v1",
    }:
        raise ValueError("live clock differs from the accepted Runner clock")
    game_path = _checked_reference(
        root, value["game"], ACCEPTED_GAME_SPEC_SHA256, "GameSpec"
    )
    game_spec = load_game_spec(game_path)
    return ResolvedLiveProfile(
        path=path,
        root=root,
        sha256=sha256_file(path),
        value=value,
        game_spec=game_spec,
        game_spec_sha256=value["game"]["sha256"],
    )


def build_live_session(profile: ResolvedLiveProfile | Path) -> "GameSession":
    resolved = load_live_profile(profile) if isinstance(profile, Path) else profile
    value = resolved.value
    model_value = value["model"]
    if model_value.get("runtime_model_spec_sha256") != ACCEPTED_MODEL_SPEC_SHA256:
        raise ValueError("declared runtime ModelSpec identity mismatch")
    model = load_candidate_model_spec(
        neural_dt_ms=NEURAL_DT_MS,
        runtime_synaptic_scale=float(model_value["runtime_synaptic_scale"]),
        seed=int(model_value["seed"]),
        model_profile_path=resolved.root / model_value["profile_path"],
        criteria_path=resolved.root / model_value["numerical_criteria_path"],
    )
    if model.semantic_sha256 != ACCEPTED_MODEL_SPEC_SHA256:
        raise ValueError("runtime ModelSpec identity mismatch")
    bundle = load_graph(resolved.root / value["graph"]["path"])
    if bundle.n != ACCEPTED_N or bundle.graph.weights.size != ACCEPTED_E:
        raise ValueError("loaded graph cardinality differs from live profile")
    if int(bundle.counts.sum()) != ACCEPTED_CONTACTS:
        raise ValueError("loaded graph contact count differs from live profile")
    controller = json.loads(
        (resolved.root / value["controller"]["path"]).read_text(encoding="utf-8")
    )
    runner = Runner(
        bundle,
        model,
        peak_sensory_external_drive=float(
            controller["selected_peak_sensory_external_drive"]
        ),
        environment_config=load_environment_config(
            resolved.root / value["environment"]["path"]
        ),
        environment_seed=int(value["environment"]["seed"]),
        backend="kernel",
    )
    return GameSession(runner, resolved.game_spec)


@dataclass(frozen=True, slots=True)
class ActiveStrike:
    attack_id: str
    target_x: float
    target_y: float
    commit_tick: int
    stimulus_tick: int
    impact_tick: int


class GameInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GameSession:
    """One reusable authoritative M08 game session with persistent neural state."""

    def __init__(self, runner: Runner, spec: GameSpec):
        self.runner = runner
        self.spec = spec
        self.reset_round()

    @property
    def control_tick(self) -> int:
        return self.runner.control_tick

    def reset_round(self) -> None:
        self.runner.reset_run()
        self.latest_aim: tuple[float, float] | None = None
        self.last_sequence = -1
        self.active_strike: ActiveStrike | None = None
        self.cooldown_until_tick = 0
        self.attack_count = 0
        self.result: str | None = None
        self.result_reason: str | None = None
        self.last_impact: dict[str, Any] | None = None
        self.last_motion = {
            "takeoff_started": False,
            "takeoff_active": False,
            "x": self.runner.environment.x,
            "y": self.runner.environment.y,
            "heading_rad": self.runner.environment.heading_rad,
        }

    def _coordinate(self, value: object, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GameInputError("malformed", f"{name} must be a finite number")
        number = float(value)
        if not math.isfinite(number):
            raise GameInputError("non_finite", f"{name} must be finite")
        if number < self.spec.arena_min or number > self.spec.arena_max:
            raise GameInputError("out_of_arena", f"{name} is outside the arena")
        return number

    def _accept_sequence(self, value: object) -> int:
        if (
            isinstance(value, bool)
            or type(value) is not int
            or value < 0
            or value > 2**53 - 1
        ):
            raise GameInputError(
                "malformed", "sequence must be a bounded nonnegative integer"
            )
        if value <= self.last_sequence:
            raise GameInputError("stale_sequence", "sequence must increase monotonically")
        self.last_sequence = value
        return value

    def update_aim(self, x: object, y: object, sequence: object) -> dict[str, Any]:
        target_x = self._coordinate(x, name="x")
        target_y = self._coordinate(y, name="y")
        accepted_sequence = self._accept_sequence(sequence)
        self.latest_aim = (target_x, target_y)
        return {
            "type": "ack",
            "kind": "aim",
            "sequence": accepted_sequence,
            "server_tick": self.control_tick,
        }

    def commit_attack(self, x: object, y: object, sequence: object) -> dict[str, Any]:
        target_x = self._coordinate(x, name="x")
        target_y = self._coordinate(y, name="y")
        if self.result is not None:
            raise GameInputError("round_complete", "the round has ended")
        if self.active_strike is not None:
            raise GameInputError("attack_active", "a committed strike is already active")
        if self.control_tick < self.cooldown_until_tick:
            raise GameInputError("cooldown", "the strike is cooling down")
        if self.attack_count >= self.spec.maximum_committed_attacks:
            raise GameInputError("attack_limit", "the attack limit is exhausted")
        accepted_sequence = self._accept_sequence(sequence)
        self.latest_aim = (target_x, target_y)
        self.attack_count += 1
        commit_tick = self.control_tick
        self.active_strike = ActiveStrike(
            attack_id=f"attack-{self.attack_count}",
            target_x=target_x,
            target_y=target_y,
            commit_tick=commit_tick,
            stimulus_tick=commit_tick + self.spec.stimulus_start_ticks,
            impact_tick=commit_tick + self.spec.impact_ticks,
        )
        return {
            "type": "ack",
            "kind": "attack",
            "sequence": accepted_sequence,
            "attack_id": self.active_strike.attack_id,
            "server_tick": commit_tick,
            "locked_target": {"x": target_x, "y": target_y},
            "impact_tick": self.active_strike.impact_tick,
        }

    def observation_for_current_interval(self) -> ThreatObservation:
        strike = self.active_strike
        tick = self.control_tick
        if strike is None or not strike.stimulus_tick <= tick < strike.impact_tick:
            return ThreatObservation(False)
        window_ticks = strike.impact_tick - strike.stimulus_tick
        fraction = (tick - strike.stimulus_tick) / window_ticks
        distance = self.spec.stimulus_start_distance + (
            self.spec.stimulus_end_distance - self.spec.stimulus_start_distance
        ) * fraction
        return ThreatObservation(
            True,
            distance,
            self.spec.stimulus_radial_velocity_per_ms,
        )

    def advance_interval(self) -> dict[str, Any]:
        if self.result is not None:
            return self.snapshot()
        strike = self.active_strike
        impact_at_end = bool(
            strike is not None and self.control_tick + 1 == strike.impact_tick
        )
        record = self.runner.advance_control_interval(
            self.observation_for_current_interval(),
            impact_at_end=impact_at_end,
        )
        self.last_motion = dict(record["motion"])
        if impact_at_end:
            assert strike is not None
            fly_x = float(record["motion"]["x"])
            fly_y = float(record["motion"]["y"])
            distance = math.hypot(strike.target_x - fly_x, strike.target_y - fly_y)
            caught = distance <= self.spec.strike_radius
            self.last_impact = {
                "attack_id": strike.attack_id,
                "control_tick": self.control_tick,
                "locked_target": {"x": strike.target_x, "y": strike.target_y},
                "authoritative_fly_position": {"x": fly_x, "y": fly_y},
                "distance": distance,
                "strike_radius": self.spec.strike_radius,
                "outcome": "caught" if caught else "missed",
                "previously_held_command": record["previously_held_command"],
                "decoded_next_command": record["decoded_next_command"],
                "phase_order": record["phase_order"],
            }
            self.active_strike = None
            if caught:
                self.result = "caught"
                self.result_reason = "geometric-impact"
            elif self.attack_count >= self.spec.maximum_committed_attacks:
                self.result = "fly-survived"
                self.result_reason = "maximum-attacks-consumed"
            else:
                self.cooldown_until_tick = self.control_tick + self.spec.cooldown_ticks
        if self.result is None and self.control_tick >= self.spec.round_horizon_tick:
            self.active_strike = None
            self.result = "fly-survived"
            self.result_reason = "round-horizon-reached"
        return self.snapshot()

    def _strike_value(self) -> dict[str, Any] | None:
        strike = self.active_strike
        if strike is None:
            return None
        phase = "wind-up" if self.control_tick < strike.stimulus_tick else "approach"
        elapsed = self.control_tick - strike.commit_tick
        progress = min(max(elapsed / self.spec.impact_ticks, 0.0), 1.0)
        return {
            "attack_id": strike.attack_id,
            "locked_target": {"x": strike.target_x, "y": strike.target_y},
            "commit_tick": strike.commit_tick,
            "stimulus_tick": strike.stimulus_tick,
            "impact_tick": strike.impact_tick,
            "phase": phase,
            "progress": progress,
            "strike_radius": self.spec.strike_radius,
        }

    def snapshot(self) -> dict[str, Any]:
        cooldown_ticks = max(self.cooldown_until_tick - self.control_tick, 0)
        if self.result is not None:
            phase = "complete"
        elif self.active_strike is not None:
            phase = self._strike_value()["phase"]  # type: ignore[index]
        elif cooldown_ticks:
            phase = "cooldown"
        else:
            phase = "ready"
        return {
            "type": "state",
            "server_tick": self.control_tick,
            "logical_time_ms": int(self.control_tick * CONTROL_INTERVAL_MS),
            "round_remaining_ms": max(
                self.spec.round_horizon_ms - int(self.control_tick * CONTROL_INTERVAL_MS),
                0,
            ),
            "phase": phase,
            "aim": (
                None
                if self.latest_aim is None
                else {"x": self.latest_aim[0], "y": self.latest_aim[1]}
            ),
            "strike": self._strike_value(),
            "cooldown_remaining_ms": int(cooldown_ticks * CONTROL_INTERVAL_MS),
            "attacks_used": self.attack_count,
            "attempts_remaining": max(
                self.spec.maximum_committed_attacks - self.attack_count, 0
            ),
            "fly": dict(self.last_motion),
            "last_impact": self.last_impact,
            "result": self.result,
            "result_reason": self.result_reason,
            "backend": self.runner.backend,
            "model": {
                "N": self.runner.graph_bundle.n,
                "E": int(self.runner.graph_bundle.graph.weights.size),
                "represented_contacts": int(self.runner.graph_bundle.counts.sum()),
            },
        }


class DemoProtocol:
    """Small message adapter shared by the WebSocket and deterministic parity tests."""

    def __init__(self, session: GameSession):
        self.session = session

    def handle(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise GameInputError("malformed", "message must be a JSON object")
        kind = payload.get("type")
        if set(payload) != {"type", "sequence", "x", "y"}:
            raise GameInputError("malformed", "message fields are not recognized")
        if kind == "aim":
            return self.session.update_aim(
                payload.get("x"), payload.get("y"), payload.get("sequence")
            )
        if kind == "attack":
            return self.session.commit_attack(
                payload.get("x"), payload.get("y"), payload.get("sequence")
            )
        raise GameInputError("malformed", "unsupported message type")

    def advance(self) -> dict[str, Any]:
        return self.session.advance_interval()
