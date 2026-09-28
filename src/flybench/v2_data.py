"""V2B annotation follow-up, port resolution, and circuit candidates."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import pyarrow.feather as feather

from flybench.circuit import _full_arrays, _json_value, build_bundle, select_indices
from flybench.encoding import ThreatObservation, compute_features, encode_population_drive
from flybench.game import build_live_session, load_live_profile
from flybench.graph import write_json
from flybench.kernel import KernelState
from flybench.runner import (
    CONTROL_INTERVAL_MS,
    NEURAL_STEPS_PER_CONTROL_INTERVAL,
    load_full_graph,
    load_graph,
)


ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = ROOT / "data/raw/body-annotations-male-cns-v1.0-minconf-0.5.feather"
FULL_GRAPH = ROOT / "data/compiled/full"
ACCEPTED_CIRCUIT = ROOT / "data/compiled/escape"
ESCAPE_PORTS = ROOT / "profiles/escape-circuit.json"
VISUAL_SIDES = ROOT / "profiles/visual-ports-sides-v1.json"
PORTS_V2 = ROOT / "profiles/ports-v2.json"
CANDIDATES_V2 = ROOT / "profiles/walking-dn-candidates-v2.json"
BUILDER_V2 = ROOT / "profiles/circuit-builder-v2.json"
SEARCH_NAMES = ("DNp09", "DNg13", "DNb02", "oDN1")
FINAL_MDN = (10763, 11332, 11288, 12348)
FINAL_DNA02 = (10360, 523769)
FINAL_DNP01 = (10001, 10010)


def _tokens(value: str | None) -> list[str]:
    return [token for token in re.split(r"[^A-Za-z0-9]+", value or "") if token]


def _normalized(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _match_kind(name: str, neuron_type: str | None, instance: str | None) -> str | None:
    if neuron_type == name:
        return "exact type"
    if name in _tokens(instance):
        return "exact instance token"
    normalized = _normalized(name)
    values = ([neuron_type] if neuron_type else []) + _tokens(instance)
    if any(value != name and _normalized(value) == normalized for value in values):
        return "near match"
    return None


def _annotation_rows() -> list[dict[str, Any]]:
    return feather.read_table(ANNOTATIONS, memory_map=True).to_pylist()


def _annotation_by_id(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(row["bodyId"]): row for row in rows}


def _index_by_id(arrays: dict[str, np.ndarray]) -> dict[int, int]:
    return {int(body_id): index for index, body_id in enumerate(arrays["ids"])}


def _edge(arrays: dict[str, np.ndarray], index_by_id: dict[int, int], source: int, target: int) -> dict[str, Any]:
    source_index = index_by_id.get(source)
    target_index = index_by_id.get(target)
    if source_index is None or target_index is None:
        return {"present": False, "contacts": 0, "effective_sign": None, "signed_weight": None}
    start = int(arrays["offsets"][source_index])
    stop = int(arrays["offsets"][source_index + 1])
    row_targets = arrays["targets"][start:stop]
    position = int(np.searchsorted(row_targets, target_index))
    if position >= row_targets.size or int(row_targets[position]) != target_index:
        return {
            "present": False,
            "contacts": 0,
            "effective_sign": int(arrays["effective_signs"][source_index]),
            "signed_weight": None,
        }
    edge_index = start + position
    return {
        "present": True,
        "contacts": int(arrays["counts"][edge_index]),
        "effective_sign": int(arrays["effective_signs"][source_index]),
        "signed_weight": float(arrays["weights"][edge_index]),
    }


def _contacts_with_set(
    arrays: dict[str, np.ndarray],
    index_by_id: dict[int, int],
    body_id: int,
    other_ids: set[int],
) -> tuple[int, int]:
    body_index = index_by_id[body_id]
    other_indices = np.asarray(
        sorted(index_by_id[value] for value in other_ids if value in index_by_id and value != body_id),
        dtype=np.int64,
    )
    start = int(arrays["offsets"][body_index])
    stop = int(arrays["offsets"][body_index + 1])
    outgoing = int(
        arrays["counts"][start:stop][np.isin(arrays["targets"][start:stop], other_indices)].sum(
            dtype=np.uint64
        )
    )
    incoming_edges = np.flatnonzero(arrays["targets"] == body_index)
    incoming_sources = np.searchsorted(arrays["offsets"], incoming_edges, side="right") - 1
    incoming = int(
        arrays["counts"][incoming_edges][np.isin(incoming_sources, other_indices)].sum(
            dtype=np.uint64
        )
    )
    return outgoing, incoming


def walking_candidates(
    rows: list[dict[str, Any]], arrays: dict[str, np.ndarray]
) -> dict[str, Any]:
    fields = ("bodyId", "type", "instance", "somaSide", "superclass", "class")
    names: dict[str, list[dict[str, Any]]] = {}
    candidate_ids: set[int] = set()
    for name in SEARCH_NAMES:
        matches = []
        for row in rows:
            kind = _match_kind(name, row.get("type"), row.get("instance"))
            if kind is None:
                continue
            body_id = int(row["bodyId"])
            candidate_ids.add(body_id)
            value = {field: _json_value(row.get(field)) for field in fields}
            value["body_id"] = str(value.pop("bodyId"))
            value["match_kind"] = kind
            matches.append(value)
        matches.sort(
            key=lambda value: (
                {"exact type": 0, "exact instance token": 1, "near match": 2}[value["match_kind"]],
                int(value["body_id"]),
            )
        )
        names[name] = matches
    visual = json.loads(ESCAPE_PORTS.read_text(encoding="utf-8"))["populations"]
    visual_ids = {
        int(value)
        for population in ("LC4", "LPLC2")
        for value in visual[population]["body_ids_decimal"]
    }
    seed_ids = visual_ids | candidate_ids | set(FINAL_MDN) | set(FINAL_DNA02) | set(FINAL_DNP01)
    index_by_id = _index_by_id(arrays)
    for matches in names.values():
        for match in matches:
            outgoing, incoming = _contacts_with_set(
                arrays, index_by_id, int(match["body_id"]), seed_ids
            )
            match["synapse_contacts_to_other_seeds"] = outgoing
            match["synapse_contacts_from_other_seeds"] = incoming
    return {
        "schema_version": 1,
        "profile_id": "flybench.walking-dn-candidates.v2",
        "status": "CANDIDATE_REVIEW_REQUIRED",
        "source_lock_sha256": "2e72e5c99708751fc9f6251d41e4fbed6456f4592fea76b8778a7453d5b18d4c",
        "annotation_source": str(ANNOTATIONS.relative_to(ROOT)),
        "reviewer_search_hints": {
            "P9": "Search DNp09 as the MaleCNS annotation name.",
            "DNg13": "Reported as strongly correlated with rotational velocity.",
            "DNb02": "Reported as a direct DNp09 target.",
            "oDN1": "No connectome alias is assumed.",
        },
        "exclusions": {
            "BPN": "Excluded because the supplied literature fact identifies BPN as higher brain interneurons, not descending neurons, and this project has no known connectome type name."
        },
        "names": names,
        "finalized_ports": False,
    }


def _sign_label(value: int | None) -> str:
    return {1: "EXCITATORY", -1: "INHIBITORY", 0: "UNKNOWN_OR_DISABLED", None: "UNAVAILABLE"}[value]


def dna01_conflict(
    rows: list[dict[str, Any]], arrays: dict[str, np.ndarray], candidates: dict[str, Any]
) -> dict[str, Any]:
    claimants = [row for row in rows if row.get("type") in {"DNa01", "DNae001"}]
    claimants.sort(key=lambda row: int(row["bodyId"]))
    index_by_id = _index_by_id(arrays)
    dnp09 = [
        int(match["body_id"])
        for match in candidates["names"]["DNp09"]
        if match["match_kind"] == "exact type"
    ]
    details = []
    for row in claimants:
        body_id = int(row["bodyId"])
        body_index = index_by_id[body_id]
        outgoing_start = int(arrays["offsets"][body_index])
        outgoing_stop = int(arrays["offsets"][body_index + 1])
        incoming_edges = np.flatnonzero(arrays["targets"] == body_index)
        details.append(
            {
                "body_id": str(body_id),
                "type": row.get("type"),
                "instance": row.get("instance"),
                "somaSide": row.get("somaSide"),
                "total_input_synapses": int(arrays["counts"][incoming_edges].sum(dtype=np.uint64)),
                "total_output_synapses": int(
                    arrays["counts"][outgoing_start:outgoing_stop].sum(dtype=np.uint64)
                ),
                "contacts_received_from_each_mdn": {
                    str(source): _edge(arrays, index_by_id, source, body_id)
                    for source in FINAL_MDN
                },
                "contacts_with_dnp09": {
                    str(other): {
                        "from_dnp09": _edge(arrays, index_by_id, other, body_id),
                        "to_dnp09": _edge(arrays, index_by_id, body_id, other),
                    }
                    for other in dnp09
                },
            }
        )
    differing_fields: dict[str, dict[str, Any]] = {}
    for field in claimants[0]:
        values = {str(row["bodyId"]): _json_value(row.get(field)) for row in claimants}
        markers = {json.dumps(value, sort_keys=True) for value in values.values()}
        if len(markers) > 1:
            differing_fields[field] = values
    connection_checks = []
    for source in dnp09:
        for target in (*FINAL_DNA02, *[
            int(match["body_id"])
            for match in candidates["names"]["DNb02"]
            if match["match_kind"] == "exact type"
        ]):
            value = _edge(arrays, index_by_id, source, target)
            connection_checks.append(
                {
                    "reported_connection": "DNp09 to DNa02" if target in FINAL_DNA02 else "DNp09 to DNb02",
                    "source_body_id": str(source),
                    "target_body_id": str(target),
                    **value,
                    "sign_label": _sign_label(value["effective_sign"]),
                }
            )
    for source in FINAL_MDN:
        for target_row in claimants:
            target = int(target_row["bodyId"])
            value = _edge(arrays, index_by_id, source, target)
            connection_checks.append(
                {
                    "reported_connection": "MDN to DNa01 claimant",
                    "source_body_id": str(source),
                    "target_body_id": str(target),
                    "target_annotation_type": target_row["type"],
                    **value,
                    "sign_label": _sign_label(value["effective_sign"]),
                }
            )
    return {
        "status": "UNRESOLVED",
        "selection_made": False,
        "claimants": details,
        "annotation_fields_that_differ": differing_fields,
        "literature_connection_consistency": connection_checks,
    }


def ports_v2(candidates: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    annotations = _annotation_by_id(rows)

    def entry(body_id: int, status: str) -> dict[str, Any]:
        row = annotations[body_id]
        return {
            "body_id": str(body_id),
            "status": status,
            "annotation_type": row.get("type"),
            "instance": row.get("instance"),
            "somaSide": row.get("somaSide"),
        }

    groups: dict[str, list[dict[str, Any]]] = {
        "escape_left": [entry(10010, "FINAL")],
        "escape_right": [entry(10001, "FINAL")],
        "backward": [entry(value, "FINAL") for value in FINAL_MDN],
        "turn_left": [entry(523769, "FINAL")],
        "turn_right": [entry(10360, "FINAL")],
        "forward": [],
    }
    for match in candidates["names"]["DNp09"]:
        if match["match_kind"] == "exact type":
            groups["forward"].append(entry(int(match["body_id"]), "PROVISIONAL"))
    for name in ("DNg13", "DNb02"):
        for match in candidates["names"][name]:
            if match["match_kind"] != "exact type":
                continue
            side = match["somaSide"]
            if side not in {"L", "R"}:
                continue
            groups["turn_left" if side == "L" else "turn_right"].append(
                entry(int(match["body_id"]), "PROVISIONAL")
            )
    for values in groups.values():
        values.sort(key=lambda value: int(value["body_id"]))
    return {
        "schema_version": 1,
        "profile_id": "flybench.ports.v2-draft-1",
        "status": "FINAL_AND_PROVISIONAL_PORTS",
        "visual_ports_profile": "profiles/visual-ports-sides-v1.json",
        "reviewer_receipt": {
            "DNp01": ["10001", "10010"],
            "MDN": [str(value) for value in FINAL_MDN],
            "DNa02": [str(value) for value in FINAL_DNA02],
        },
        "groups": groups,
        "excluded": {
            "DNa01": "Excluded until the DNa01 versus DNae001 annotation conflict is resolved.",
            "BPN": "Excluded because BPN are higher brain interneurons and no connectome type name is known to this project.",
            "oDN1": "Excluded because no annotation match was found.",
        },
        "side_rule": "Left and right groups are assigned from annotation somaSide only.",
        "turn_direction_assumption": "Whether a right-side descending neuron turns the fly right is a model assumption for the decoder card, not a measured fact.",
    }


def _simulate_context(bundle: Any, model_spec: Any, game_spec: Any) -> dict[str, Any]:
    state = KernelState(model_spec, bundle.graph)
    spike_ticks: dict[int, list[int]] = defaultdict(list)
    target_indices = {int(bundle.body_ids[index]): int(index) for index in bundle.dnp01_indices}
    target_trace = {str(body_id): [] for body_id in target_indices}
    for control_tick in range(int(1000 / CONTROL_INTERVAL_MS)):
        if game_spec.stimulus_start_ticks <= control_tick < game_spec.impact_ticks:
            fraction = (control_tick - game_spec.stimulus_start_ticks) / (
                game_spec.impact_ticks - game_spec.stimulus_start_ticks
            )
            distance = game_spec.stimulus_start_distance + (
                game_spec.stimulus_end_distance - game_spec.stimulus_start_distance
            ) * fraction
            observation = ThreatObservation(True, distance, game_spec.stimulus_radial_velocity_per_ms)
        else:
            observation = ThreatObservation(False)
        encoded = encode_population_drive(
            compute_features(observation),
            4.0,
            neuron_count=bundle.n,
            lc4_indices=bundle.lc4_indices,
            lplc2_indices=bundle.lplc2_indices,
            dnp01_indices=bundle.dnp01_indices,
        )
        for _ in range(NEURAL_STEPS_PER_CONTROL_INTERVAL):
            result = state.step(encoded.vector)
            for index in np.flatnonzero(result.spikes):
                spike_ticks[int(bundle.body_ids[int(index)])].append(int(result.end_tick))
            for body_id, index in target_indices.items():
                target_trace[str(body_id)].append(
                    {
                        "end_tick": int(result.end_tick),
                        "arrival_increment": float(result.arrival_increment[index]),
                        "synaptic_current": float(state.synaptic_current[index]),
                        "voltage": float(state.voltage[index]),
                        "spike": bool(result.spikes[index]),
                    }
                )
    return {"spike_ticks": spike_ticks, "target_trace": target_trace}


def context_followup(rows: list[dict[str, Any]], arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    resolved = load_live_profile(ROOT / "profiles/live.json")
    session = build_live_session(resolved)
    circuit = load_graph(ACCEPTED_CIRCUIT)
    full = load_full_graph(FULL_GRAPH, ESCAPE_PORTS)
    circuit_run = _simulate_context(circuit, session.runner.model_spec, resolved.game_spec)
    full_run = _simulate_context(full, session.runner.model_spec, resolved.game_spec)
    accepted_ids = {int(value) for value in circuit.body_ids}
    outside_ids = sorted(
        body_id for body_id, ticks in full_run["spike_ticks"].items()
        if body_id not in accepted_ids and ticks
    )
    annotations = _annotation_by_id(rows)
    index_by_id = _index_by_id(arrays)
    accepted_ports = json.loads(ESCAPE_PORTS.read_text(encoding="utf-8"))["populations"]
    visual_ids = {
        int(value)
        for name in ("LC4", "LPLC2")
        for value in accepted_ports[name]["body_ids_decimal"]
    }
    dnp_ids = set(FINAL_DNP01)
    outside = []
    for body_id in outside_ids:
        to_dnp, from_dnp = _contacts_with_set(arrays, index_by_id, body_id, dnp_ids)
        to_visual, from_visual = _contacts_with_set(arrays, index_by_id, body_id, visual_ids)
        row = annotations.get(body_id, {})
        outside.append(
            {
                "body_id": str(body_id),
                "type": row.get("type"),
                "instance": row.get("instance"),
                "somaSide": row.get("somaSide"),
                "spike_ticks": full_run["spike_ticks"][body_id],
                "contacts_to_dnp01": to_dnp,
                "contacts_from_dnp01": from_dnp,
                "contacts_to_visual_ports": to_visual,
                "contacts_from_visual_ports": from_visual,
            }
        )
    explanations = []
    circuit_index = {int(value): index for index, value in enumerate(circuit.body_ids)}
    full_index = {int(value): index for index, value in enumerate(full.body_ids)}
    for target in FINAL_DNP01:
        circuit_trace = circuit_run["target_trace"][str(target)]
        full_trace = full_run["target_trace"][str(target)]
        first_difference = next(
            (
                {
                    "end_tick": left["end_tick"],
                    "circuit_arrival_increment": left["arrival_increment"],
                    "full_arrival_increment": right["arrival_increment"],
                    "delta_full_minus_circuit": right["arrival_increment"] - left["arrival_increment"],
                }
                for left, right in zip(circuit_trace, full_trace, strict=True)
                if left["arrival_increment"] != right["arrival_increment"]
            ),
            None,
        )
        circuit_first = circuit_run["spike_ticks"].get(target, [None])[0]
        full_first = full_run["spike_ticks"].get(target, [None])[0]
        comparison_tick = circuit_first
        circuit_at = circuit_trace[comparison_tick - 1] if comparison_tick else None
        full_at = full_trace[comparison_tick - 1] if comparison_tick else None
        differing_inputs = []
        target_circuit_index = circuit_index[target]
        target_full_index = full_index[target]
        for source_body in sorted(set(circuit_run["spike_ticks"]) | set(full_run["spike_ticks"])):
            edge_full = _edge(arrays, index_by_id, source_body, target)
            if not edge_full["present"]:
                continue
            circuit_ticks = circuit_run["spike_ticks"].get(source_body, [])
            full_ticks = full_run["spike_ticks"].get(source_body, [])
            if circuit_ticks == full_ticks and source_body in accepted_ids:
                continue
            differing_inputs.append(
                {
                    "source_body_id": str(source_body),
                    "type": annotations.get(source_body, {}).get("type"),
                    "source_in_accepted_circuit": source_body in accepted_ids,
                    "contacts": edge_full["contacts"],
                    "signed_weight": edge_full["signed_weight"],
                    "effective_sign": edge_full["effective_sign"],
                    "circuit_source_spike_ticks": circuit_ticks,
                    "full_source_spike_ticks": full_ticks,
                    "full_arrival_boundary_ticks": [
                        tick + session.runner.model_spec.delay_ticks for tick in full_ticks
                    ],
                }
            )
        explanations.append(
            {
                "target_body_id": str(target),
                "circuit_local_index": circuit_index[target],
                "full_local_index": full_index[target],
                "circuit_first_spike_tick": circuit_first,
                "full_first_spike_tick": full_first,
                "first_differing_arrival": first_difference,
                "state_at_circuit_first_spike_tick": {
                    "circuit": circuit_at,
                    "full": full_at,
                },
                "differing_presynaptic_inputs": differing_inputs,
                "explanation_found": bool(
                    circuit_first is not None
                    and full_first == circuit_first + 1
                    and circuit_at is not None
                    and full_at is not None
                    and circuit_at["spike"]
                    and not full_at["spike"]
                ),
            }
        )
    return {
        "schedule": "The unchanged V2A standard looming schedule and accepted parameters.",
        "outside_accepted_circuit_spiking_neurons": outside,
        "dnp01_input_trace": explanations,
    }


def _candidate_markdown(profile: dict[str, Any]) -> str:
    lines = [
        "# Walking descending neuron candidates, round 2",
        "",
        "Status: CANDIDATE_REVIEW_REQUIRED. Literature facts are search hints and consistency checks only.",
        "",
        "| Search name | Body ID | Type | Instance | Side | Superclass | Class | Match kind | Contacts to seeds | Contacts from seeds |",
        "|---|---:|---|---|---|---|---|---|---:|---:|",
    ]
    for name in SEARCH_NAMES:
        matches = profile["names"][name]
        if not matches:
            lines.append(f"| {name} | No match |  |  |  |  |  |  |  |  |")
        for match in matches:
            lines.append(
                f"| {name} | {match['body_id']} | {match['type'] or ''} | {match['instance'] or ''} | {match['somaSide'] or ''} | {match['superclass'] or ''} | {match['class'] or ''} | {match['match_kind']} | {match['synapse_contacts_to_other_seeds']} | {match['synapse_contacts_from_other_seeds']} |"
            )
    lines.extend(
        [
            "",
            "BPN is excluded because the supplied literature fact identifies BPN as higher brain interneurons, not descending neurons, and no connectome type name is known to this project.",
            "",
        ]
    )
    return "\n".join(lines)


def _conflict_markdown(conflict: dict[str, Any]) -> str:
    lines = [
        "# DNa01 annotation conflict",
        "",
        "Status: UNRESOLVED. No claimant is selected.",
        "",
        "## Claimants and totals",
        "",
        "| Body ID | Type | Instance | Side | Total input contacts | Total output contacts |",
        "|---:|---|---|---|---:|---:|",
    ]
    for value in conflict["claimants"]:
        lines.append(
            f"| {value['body_id']} | {value['type']} | {value['instance']} | {value['somaSide']} | {value['total_input_synapses']} | {value['total_output_synapses']} |"
        )
    lines.extend(["", "## MDN input to each claimant", "", "| Claimant | MDN | Present | Contacts | Sign |", "|---:|---:|---|---:|---|"])
    for claimant in conflict["claimants"]:
        for source, value in claimant["contacts_received_from_each_mdn"].items():
            lines.append(
                f"| {claimant['body_id']} | {source} | {value['present']} | {value['contacts']} | {_sign_label(value['effective_sign'])} |"
            )
    lines.extend(["", "## DNp09 connections", "", "| Claimant | DNp09 | Direction | Present | Contacts | Sign |", "|---:|---:|---|---|---:|---|"])
    for claimant in conflict["claimants"]:
        for other, pair in claimant["contacts_with_dnp09"].items():
            for direction, value in pair.items():
                lines.append(
                    f"| {claimant['body_id']} | {other} | {direction} | {value['present']} | {value['contacts']} | {_sign_label(value['effective_sign'])} |"
                )
    lines.extend(["", "## Annotation fields that differ", ""])
    for field, values in conflict["annotation_fields_that_differ"].items():
        rendered = "; ".join(f"{body_id}={json.dumps(value, sort_keys=True)}" for body_id, value in values.items())
        lines.append(f"- `{field}`: {rendered}")
    lines.extend(["", "## Literature connection consistency", "", "| Reported connection | Source | Target | Target type | Present | Contacts | Sign |", "|---|---:|---:|---|---|---:|---|"])
    for value in conflict["literature_connection_consistency"]:
        lines.append(
            f"| {value['reported_connection']} | {value['source_body_id']} | {value['target_body_id']} | {value.get('target_annotation_type', '')} | {value['present']} | {value['contacts']} | {value['sign_label']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _context_markdown(context: dict[str, Any]) -> str:
    lines = [
        "# V2A context follow-up",
        "",
        "## Outside-circuit neurons that spiked",
        "",
        "| Body ID | Type | Instance | Side | Spike ticks | To DNp01 | From DNp01 | To visual | From visual |",
        "|---:|---|---|---|---|---:|---:|---:|---:|",
    ]
    for value in context["outside_accepted_circuit_spiking_neurons"]:
        lines.append(
            f"| {value['body_id']} | {value['type'] or ''} | {value['instance'] or ''} | {value['somaSide'] or ''} | {', '.join(str(tick) for tick in value['spike_ticks'])} | {value['contacts_to_dnp01']} | {value['contacts_from_dnp01']} | {value['contacts_to_visual_ports']} | {value['contacts_from_visual_ports']} |"
        )
    lines.extend(["", "## DNp01 one-tick shift", ""])
    for value in context["dnp01_input_trace"]:
        if value["explanation_found"]:
            state = value["state_at_circuit_first_spike_tick"]
            first = value["first_differing_arrival"]
            outside_sources = [
                input_value["source_body_id"]
                for input_value in value["differing_presynaptic_inputs"]
                if not input_value["source_in_accepted_circuit"]
            ]
            shared_count = sum(
                input_value["source_in_accepted_circuit"]
                for input_value in value["differing_presynaptic_inputs"]
            )
            lines.append(
                f"- DNp01 {value['target_body_id']} spikes at tick {value['circuit_first_spike_tick']} in the circuit and tick {value['full_first_spike_tick']} in the full graph. The first differing arrival is at end tick {first['end_tick']}, with full-minus-circuit increment {first['delta_full_minus_circuit']!r}. At the circuit spike tick, the circuit state crosses threshold and resets while the full-graph voltage is {state['full']['voltage']!r}, below threshold. The accumulated input history therefore accounts for the one-tick delay."
            )
            lines.append(
                f"  Differing presynaptic histories include {shared_count} sources present in the accepted circuit and {len(outside_sources)} outside sources. Outside source body IDs: {', '.join(outside_sources) if outside_sources else 'none'}. No single edge is claimed as the sole cause."
            )
        else:
            lines.append(
                f"- DNp01 {value['target_body_id']}: the one-tick shift was reproduced, but a sufficient input-trace explanation was not found."
            )
    lines.extend(["", "Full input traces are in `context-followup.json`.", ""])
    return "\n".join(lines)


def build_v2(out: Path) -> dict[str, Any]:
    arrays = _full_arrays()
    rows = _annotation_rows()
    candidates = walking_candidates(rows, arrays)
    conflict = dna01_conflict(rows, arrays, candidates)
    ports = ports_v2(candidates, rows)
    context = context_followup(rows, arrays)
    write_json(CANDIDATES_V2, candidates)
    write_json(PORTS_V2, ports)
    out.mkdir(parents=True, exist_ok=True)
    (out / "walking-dn-candidates.md").write_text(_candidate_markdown(candidates), encoding="utf-8")
    (out / "dna01-conflict.md").write_text(_conflict_markdown(conflict), encoding="utf-8")
    write_json(out / "dna01-conflict.json", conflict)
    write_json(out / "context-followup.json", context)
    (out / "context-followup.md").write_text(_context_markdown(context), encoding="utf-8")
    builder = json.loads(BUILDER_V2.read_text(encoding="utf-8"))
    visual_profile = json.loads(VISUAL_SIDES.read_text(encoding="utf-8"))["populations"]
    visual_ids = {
        int(value)
        for population in visual_profile.values()
        for field in ("left_body_ids_decimal", "right_body_ids_decimal")
        for value in population[field]
    }
    output_ids = {
        int(entry["body_id"])
        for entries in ports["groups"].values()
        for entry in entries
    }
    circuits = []
    for candidate in builder["candidates"]:
        threshold = int(candidate["synapse_threshold"])
        hops = int(candidate["hops"])
        selected = select_indices(arrays, visual_ids, output_ids, threshold, hops)
        directory = ROOT / builder["bundle_output_root"] / candidate["id"].lower()
        value = build_bundle(
            arrays,
            selected,
            directory,
            threshold,
            hops,
            profile_id=f"flybench.v2-circuit.{candidate['id'].lower()}.draft-1",
            seed_status="PROVISIONAL_SEEDS",
            selection_rule=f"Plan-v2 seed expansion candidate {candidate['id']} with S={threshold} and hops={hops}",
            build_command=["python", "-m", "flybench.circuit", "build-v2"],
            compiler_id="flybench.v2-circuit-builder.v2",
        )
        value.update(
            {
                "candidate": candidate["id"],
                "purpose": candidate["purpose"],
                "synapse_threshold": threshold,
                "hops": hops,
                "seed_status": "PROVISIONAL_SEEDS",
                "seed_count": len(visual_ids | output_ids),
            }
        )
        circuits.append(value)
    report = {
        "schema": "flybench.v2b.circuits",
        "version": 1,
        "status": "SUBMITTED",
        "ports_profile": str(PORTS_V2.relative_to(ROOT)),
        "visual_ports_profile": str(VISUAL_SIDES.relative_to(ROOT)),
        "circuits": circuits,
    }
    write_json(out / "circuits.json", report)
    return report
