"""One authoritative integer-clock headless Runner for M06."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np

from flybench.catch import CatchEnvironment, EnvironmentConfig
from flybench.decoder import decode_dnp01
from flybench.encoding import (
    ThreatObservation,
    compute_features,
    encode_population_drive,
)
from flybench.model import ModelSpec
from flybench.reference import ReferenceGraph, ReferenceState
from flybench.kernel import KernelGraph, KernelState


ACCEPTED_CIRCUIT_DIGEST = (
    "53d87e2c9ea9c21f601ab372ae4fd058298e2a67f7530e3f0054c5e38c66d8e5"
)
ACCEPTED_FULL_GRAPH_DIGEST = (
    "429cffb53e11ca2ea353163aa07f695c730df053db58b18ab2f85c59fa90b3c0"
)
ACCEPTED_SELECTION_SHA256 = (
    "29a6b4fb98d29f2fbf76fc031bea2f75d7ed534540666fc50279168358f5232b"
)
ACCEPTED_SOURCE_LOCK_SHA256 = (
    "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c"
)
CONTROL_INTERVAL_MS = 10.0
NEURAL_DT_MS = 0.5
NEURAL_STEPS_PER_CONTROL_INTERVAL = 20
RUNNER_ORDER = (
    "apply-scripted-input",
    "form-observation",
    "encode-held-drive",
    "advance-neural-20-steps",
    "advance-environment-with-previous-command",
    "resolve-impact",
    "decode-completed-neural-interval",
    "store-next-command",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _immutable_int_indices(ids: np.ndarray, body_ids: list[str]) -> np.ndarray:
    requested = np.asarray([int(value) for value in body_ids], dtype=np.uint64)
    indices = np.searchsorted(ids, requested).astype(np.int64)
    if np.any(indices >= ids.size) or not np.array_equal(ids[indices], requested):
        raise ValueError("population body ID is absent from the compiled graph")
    indices.flags.writeable = False
    return indices


@dataclass(frozen=True, slots=True)
class GraphBundle:
    directory: Path
    graph: ReferenceGraph | KernelGraph
    body_ids: np.ndarray
    counts: np.ndarray
    lc4_indices: np.ndarray
    lplc2_indices: np.ndarray
    dnp01_indices: np.ndarray
    semantic_graph_digest: str
    selection_profile_sha256: str
    source_lock_sha256: str

    @property
    def n(self) -> int:
        return self.graph.n


@dataclass(frozen=True, slots=True)
class PathwayIntervention:
    intervention_id: str
    profile_sha256: str
    graph: ReferenceGraph | KernelGraph
    edge_mask: np.ndarray
    audit: dict[str, Any]


def load_graph(directory: Path) -> GraphBundle:
    """Identity-check and load only the accepted compiled escape circuit."""

    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    digest = manifest.get("semantic_digest", {}).get("value")
    selection_sha = manifest.get("selection_profile", {}).get("sha256")
    source_sha = manifest.get("source_lock_sha256")
    if digest != ACCEPTED_CIRCUIT_DIGEST:
        raise ValueError("compiled circuit semantic identity mismatch")
    if selection_sha != ACCEPTED_SELECTION_SHA256:
        raise ValueError("compiled circuit selection/profile identity mismatch")
    if source_sha != ACCEPTED_SOURCE_LOCK_SHA256:
        raise ValueError("compiled circuit source-lock identity mismatch")
    if _sha256_file(directory / "selection-profile.json") != selection_sha:
        raise ValueError("copied selection profile bytes do not match manifest")

    arrays: dict[str, np.ndarray] = {}
    for name in ("ids", "offsets", "targets", "counts", "weights"):
        entry = manifest["arrays"][name]
        path = directory / entry["filename"]
        if _sha256_file(path) != entry["sha256"]:
            raise ValueError(f"compiled circuit array identity mismatch: {name}")
        value = np.load(path, allow_pickle=False)
        if list(value.shape) != entry["shape"] or value.dtype.name != entry["dtype"]:
            raise ValueError(f"compiled circuit array metadata mismatch: {name}")
        arrays[name] = value
    if arrays["ids"].size != 313 or arrays["targets"].size != 20607:
        raise ValueError("compiled circuit cardinality mismatch")
    if int(np.sum(arrays["counts"], dtype=np.uint64)) != 79112:
        raise ValueError("compiled circuit source-contact total mismatch")

    profile = json.loads((directory / "selection-profile.json").read_text(encoding="utf-8"))
    populations = profile["populations"]
    ids = np.array(arrays["ids"], dtype=np.uint64, copy=True)
    counts = np.array(arrays["counts"], dtype=np.uint64, copy=True)
    ids.flags.writeable = False
    counts.flags.writeable = False
    bundle = GraphBundle(
        directory=directory,
        graph=ReferenceGraph(
            offsets=arrays["offsets"],
            targets=arrays["targets"],
            weights=arrays["weights"],
        ),
        body_ids=ids,
        counts=counts,
        lc4_indices=_immutable_int_indices(ids, populations["LC4"]["body_ids_decimal"]),
        lplc2_indices=_immutable_int_indices(
            ids, populations["LPLC2"]["body_ids_decimal"]
        ),
        dnp01_indices=_immutable_int_indices(
            ids, populations["DNp01"]["body_ids_decimal"]
        ),
        semantic_graph_digest=digest,
        selection_profile_sha256=selection_sha,
        source_lock_sha256=source_sha,
    )
    if tuple(int(ids[index]) for index in bundle.dnp01_indices) != (10001, 10010):
        raise ValueError("compiled DNp01 port identity mismatch")
    if (bundle.lc4_indices.size, bundle.lplc2_indices.size) != (126, 185):
        raise ValueError("compiled sensory-port cardinality mismatch")
    return bundle


def load_full_graph(directory: Path, ports_profile_path: Path) -> GraphBundle:
    """Identity-check and mmap the accepted M03 full graph for bounded M07 probes."""

    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    digest = manifest.get("semantic_digest", {}).get("value")
    selection_sha = manifest.get("selection_profile", {}).get("sha256")
    source_sha = manifest.get("source_lock_sha256")
    if digest != ACCEPTED_FULL_GRAPH_DIGEST:
        raise ValueError("compiled full graph semantic identity mismatch")
    if source_sha != ACCEPTED_SOURCE_LOCK_SHA256:
        raise ValueError("compiled full graph source-lock identity mismatch")
    if _sha256_file(directory / "selection-profile.json") != selection_sha:
        raise ValueError("full graph copied selection profile identity mismatch")
    if _sha256_file(ports_profile_path) != ACCEPTED_SELECTION_SHA256:
        raise ValueError("full graph port-resolution profile identity mismatch")

    arrays: dict[str, np.ndarray] = {}
    for name in ("ids", "offsets", "targets", "counts", "weights"):
        entry = manifest["arrays"][name]
        path = directory / entry["filename"]
        if _sha256_file(path) != entry["sha256"]:
            raise ValueError(f"compiled full graph array identity mismatch: {name}")
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if list(value.shape) != entry["shape"] or value.dtype.name != entry["dtype"]:
            raise ValueError(f"compiled full graph array metadata mismatch: {name}")
        arrays[name] = value
    if arrays["ids"].size != 166700 or arrays["targets"].size != 25582938:
        raise ValueError("compiled full graph cardinality mismatch")
    if int(np.sum(arrays["counts"], dtype=np.uint64)) != 124177617:
        raise ValueError("compiled full graph source-contact total mismatch")

    ports = json.loads(ports_profile_path.read_text(encoding="utf-8"))["populations"]
    ids = arrays["ids"]
    counts = arrays["counts"]
    graph = KernelGraph(
        offsets=arrays["offsets"], targets=arrays["targets"], weights=arrays["weights"]
    )
    bundle = GraphBundle(
        directory=directory,
        graph=graph,
        body_ids=ids,
        counts=counts,
        lc4_indices=_immutable_int_indices(ids, ports["LC4"]["body_ids_decimal"]),
        lplc2_indices=_immutable_int_indices(ids, ports["LPLC2"]["body_ids_decimal"]),
        dnp01_indices=_immutable_int_indices(ids, ports["DNp01"]["body_ids_decimal"]),
        semantic_graph_digest=digest,
        selection_profile_sha256=selection_sha,
        source_lock_sha256=source_sha,
    )
    resolved = tuple(int(ids[index]) for index in bundle.dnp01_indices)
    if resolved != (10001, 10010):
        raise ValueError("full graph DNp01 port identity mismatch")
    if (bundle.lc4_indices.size, bundle.lplc2_indices.size) != (126, 185):
        raise ValueError("full graph sensory-port cardinality mismatch")
    return bundle


def build_direct_visual_to_dnp01_zero(
    bundle: GraphBundle, profile_path: Path
) -> PathwayIntervention:
    """Construct the predeclared in-memory direct-pathway zero-weight mask."""

    profile_bytes = profile_path.read_bytes()
    profile = json.loads(profile_bytes)
    if profile.get("intervention_id") != "direct_visual_to_dnp01_zero":
        raise ValueError("unsupported pathway intervention profile")
    mask = np.zeros(bundle.graph.weights.size, dtype=np.bool_)
    target_set = {int(index) for index in bundle.dnp01_indices}
    groups: dict[str, dict[str, int]] = {}
    for name, sources in (("LC4", bundle.lc4_indices), ("LPLC2", bundle.lplc2_indices)):
        edge_count = 0
        contact_count = 0
        for source in sources:
            start = int(bundle.graph.offsets[int(source)])
            stop = int(bundle.graph.offsets[int(source) + 1])
            for edge in range(start, stop):
                if int(bundle.graph.targets[edge]) in target_set:
                    if mask[edge]:
                        raise RuntimeError("pathway mask selected an edge twice")
                    mask[edge] = True
                    edge_count += 1
                    contact_count += int(bundle.counts[edge])
        groups[name] = {"pair_edges": edge_count, "source_contacts": contact_count}
    expected = {
        "LC4": {"pair_edges": 126, "source_contacts": 6362},
        "LPLC2": {"pair_edges": 185, "source_contacts": 4862},
    }
    if groups != expected or int(np.count_nonzero(mask)) != 311:
        raise ValueError("direct-pathway mask does not match accepted M04 edges")
    weights = bundle.graph.weights.copy()
    weights[mask] = 0.0
    mask.flags.writeable = False
    audit = {
        "intervention_id": "direct_visual_to_dnp01_zero",
        "classification": "modeled intervention; not a biological lesion claim",
        "groups": groups,
        "total_pair_edges": 311,
        "total_source_contacts": 11224,
        "source_ids_preserved": True,
        "compiled_graph_files_modified": False,
        "only_selected_executable_weights_zeroed": True,
    }
    intervention_graph: ReferenceGraph | KernelGraph
    if isinstance(bundle.graph, KernelGraph):
        intervention_graph = KernelGraph(
            offsets=bundle.graph.offsets,
            targets=bundle.graph.targets,
            weights=weights,
        )
    else:
        intervention_graph = ReferenceGraph(
            offsets=bundle.graph.offsets,
            targets=bundle.graph.targets,
            weights=weights,
        )
    return PathwayIntervention(
        intervention_id="direct_visual_to_dnp01_zero",
        profile_sha256=hashlib.sha256(profile_bytes).hexdigest(),
        graph=intervention_graph,
        edge_mask=mask,
        audit=audit,
    )


def _state_digest(state: ReferenceState) -> str:
    digest = hashlib.sha256(b"FlyBench M06 complete neural state v1\0")
    digest.update(int(state.tick).to_bytes(8, "little", signed=False))
    for value in (
        state.voltage,
        state.synaptic_current,
        state.refractory_until_tick,
        state.pending_spikes,
        state.pending_inputs,
    ):
        digest.update(np.ascontiguousarray(value).tobytes())
    return digest.hexdigest()


class Runner:
    """Concrete owner of neural, environment, command, and logical-clock state."""

    def __init__(
        self,
        graph_bundle: GraphBundle,
        model_spec: ModelSpec,
        *,
        peak_sensory_external_drive: float,
        environment_config: EnvironmentConfig,
        environment_seed: int,
        output_clamp: bool = False,
        intervention: PathwayIntervention | None = None,
        backend: Literal["reference", "kernel"] = "reference",
    ):
        if model_spec.neural_dt_ms != NEURAL_DT_MS:
            raise ValueError("M06 requires the accepted 0.5 ms neural timestep")
        if not math.isclose(
            CONTROL_INTERVAL_MS / model_spec.neural_dt_ms,
            NEURAL_STEPS_PER_CONTROL_INTERVAL,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise ValueError("control interval must contain exactly 20 neural steps")
        self.graph_bundle = graph_bundle
        self.model_spec = model_spec
        self.peak_sensory_external_drive = float(peak_sensory_external_drive)
        self.environment_seed = environment_seed
        self.output_clamp = bool(output_clamp)
        self.intervention = intervention
        if backend not in ("reference", "kernel"):
            raise ValueError("backend must be 'reference' or 'kernel'")
        self.backend = backend
        graph = intervention.graph if intervention is not None else graph_bundle.graph
        if backend == "reference":
            if not isinstance(graph, ReferenceGraph):
                raise ValueError("reference backend requires an in-memory ReferenceGraph")
            self.neural = ReferenceState(model_spec, graph)
        else:
            self.neural = KernelState(model_spec, graph)
        self.environment = CatchEnvironment(environment_config, seed=environment_seed)
        if self.neural.rng is self.environment.rng:
            raise RuntimeError("neural and environment RNG ownership must be distinct")
        self.reset_run()

    @property
    def control_tick(self) -> int:
        return self._control_tick

    def reset_run(self) -> None:
        """Explicitly and completely reset all mutable experimental state."""

        self.neural.reset(seed=self.model_spec.seed)
        self.environment.reset(seed=self.environment_seed)
        self._control_tick = 0
        self.held_command = False
        self.interval_records: list[dict[str, Any]] = []
        self.command_control_ticks: list[int] = []
        self.dnp01_spikes: list[tuple[int, int]] = []

    def advance_control_interval(
        self,
        observation: ThreatObservation,
        *,
        impact_at_end: bool = False,
    ) -> dict[str, Any]:
        """Advance one authoritative interval in the frozen M06 phase order."""

        start_control_tick = self._control_tick
        start_neural_tick = self.neural.tick
        expected_start = start_control_tick * NEURAL_STEPS_PER_CONTROL_INTERVAL
        if start_neural_tick != expected_start:
            raise RuntimeError("Runner neural and control clocks diverged")

        features = compute_features(observation)
        encoded = encode_population_drive(
            features,
            self.peak_sensory_external_drive,
            neuron_count=self.graph_bundle.n,
            lc4_indices=self.graph_bundle.lc4_indices,
            lplc2_indices=self.graph_bundle.lplc2_indices,
            dnp01_indices=self.graph_bundle.dnp01_indices,
        )
        interval_spikes: list[tuple[int, int]] = []
        all_spike_count = 0
        finite_state = True
        for _ in range(NEURAL_STEPS_PER_CONTROL_INTERVAL):
            result = self.neural.step(encoded.vector)
            all_spike_count += int(np.count_nonzero(result.spikes))
            for index in self.graph_bundle.dnp01_indices:
                if result.spikes[int(index)]:
                    event = (result.end_tick, int(self.graph_bundle.body_ids[int(index)]))
                    interval_spikes.append(event)
                    self.dnp01_spikes.append(event)
            finite_state = finite_state and bool(
                np.all(np.isfinite(self.neural.voltage))
                and np.all(np.isfinite(self.neural.synaptic_current))
            )

        end_control_tick = start_control_tick + 1
        if impact_at_end:
            self.environment.schedule_impact(end_control_tick)
        previous_command = self.held_command
        motion = self.environment.advance_motion(previous_command)
        impacts = self.environment.resolve_due_impacts()

        declared_events = () if self.output_clamp else tuple(
            body_id for _, body_id in interval_spikes
        )
        next_command = decode_dnp01(declared_events)
        if next_command:
            self.command_control_ticks.append(end_control_tick)
        self.held_command = next_command
        self._control_tick = end_control_tick
        if self.neural.tick != end_control_tick * NEURAL_STEPS_PER_CONTROL_INTERVAL:
            raise RuntimeError("Runner did not execute exactly 20 neural steps")
        if self.environment.control_tick != end_control_tick:
            raise RuntimeError("Runner and environment control clocks diverged")

        record = {
            "start_control_tick": start_control_tick,
            "end_control_tick": end_control_tick,
            "start_ms": start_control_tick * CONTROL_INTERVAL_MS,
            "end_ms": end_control_tick * CONTROL_INTERVAL_MS,
            "start_neural_tick": start_neural_tick,
            "end_neural_tick": self.neural.tick,
            "phase_order": list(RUNNER_ORDER),
            "observation": {
                "visual_threat_present": observation.visual_threat_present,
                "distance": observation.distance,
                "radial_velocity_per_ms": observation.radial_velocity_per_ms,
            },
            "features": {
                "angular_size_rad": features.angular_size_rad,
                "angular_velocity_rad_per_ms": features.angular_velocity_rad_per_ms,
                "positive_expansion": features.positive_expansion,
                "size_feature": features.size_feature,
                "expansion_feature": features.expansion_feature,
            },
            "held_drive": {
                "LC4": encoded.lc4_drive,
                "LPLC2": encoded.lplc2_drive,
                "DNp01": 0.0,
                "hold_neural_steps": NEURAL_STEPS_PER_CONTROL_INTERVAL,
            },
            "dnp01_spikes": [
                {"neural_tick": tick, "body_id": body_id}
                for tick, body_id in interval_spikes
            ],
            "all_population_spike_count": all_spike_count,
            "previously_held_command": previous_command,
            "decoded_next_command": next_command,
            "output_clamp": self.output_clamp,
            "motion": {
                "takeoff_started": motion.takeoff_started,
                "takeoff_active": motion.takeoff_active,
                "x": motion.x,
                "y": motion.y,
                "heading_rad": motion.heading_rad,
            },
            "impacts": [
                {
                    "control_tick": item.control_tick,
                    "outcome": item.outcome,
                    "takeoff_was_active": item.takeoff_was_active,
                }
                for item in impacts
            ],
            "finite_state": finite_state,
            "backend": self.backend,
            "neural_state_sha256": _state_digest(self.neural),
            "dnp01_voltage": [
                float(self.neural.voltage[int(index)])
                for index in self.graph_bundle.dnp01_indices
            ],
            "dnp01_synaptic_current": [
                float(self.neural.synaptic_current[int(index)])
                for index in self.graph_bundle.dnp01_indices
            ],
        }
        self.interval_records.append(record)
        return record

    def finish_run(self) -> dict[str, Any]:
        """Return a bounded authoritative summary without mutating state."""

        return {
            "control_intervals": self._control_tick,
            "control_tick": self._control_tick,
            "neural_tick": self.neural.tick,
            "neural_steps_per_control_interval": NEURAL_STEPS_PER_CONTROL_INTERVAL,
            "backend": self.backend,
            "dnp01_spike_count": len(self.dnp01_spikes),
            "dnp01_spikes": [
                {"neural_tick": tick, "body_id": body_id}
                for tick, body_id in self.dnp01_spikes
            ],
            "escape_command_count": len(self.command_control_ticks),
            "escape_command_control_ticks": list(self.command_control_ticks),
            "impacts": [
                {
                    "control_tick": item.control_tick,
                    "outcome": item.outcome,
                    "takeoff_was_active": item.takeoff_was_active,
                }
                for item in self.environment.impacts
            ],
            "finite_state": all(
                record["finite_state"] for record in self.interval_records
            ),
            "final_neural_state_sha256": _state_digest(self.neural),
        }
