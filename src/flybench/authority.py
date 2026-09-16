"""Bounded structural dependency evidence for M06 authority boundaries."""

from __future__ import annotations

import ast
import dis
import inspect
from pathlib import Path
import types
from typing import Any, Callable


FORBIDDEN_DECODER_TOKENS = (
    "threat",
    "cursor",
    "strike",
    "attack",
    "target",
    "bearing",
    "distance",
    "impact",
    "environment",
    "position",
    "away",
    "observation",
    "geometry",
    "encoder",
)
FORBIDDEN_AMBIENT_TOKENS = (
    "threat",
    "cursor",
    "strike",
    "attack",
    "target",
    "bearing",
    "distance",
    "impact",
    "away",
    "observation",
    "feature",
    "encoder",
)


def _safe_object_description(value: object) -> dict[str, str]:
    return {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "module": getattr(value, "__module__", type(value).__module__),
        "qualname": getattr(value, "__qualname__", type(value).__qualname__),
    }


def _helper_graph(root: Callable[..., object]) -> list[dict[str, Any]]:
    pending = [root]
    visited: set[int] = set()
    graph: list[dict[str, Any]] = []
    while pending:
        function = pending.pop()
        if id(function) in visited:
            continue
        visited.add(id(function))
        closure = inspect.getclosurevars(function)
        helpers: list[str] = []
        modules: list[str] = []
        for name, value in sorted(closure.globals.items()):
            if inspect.isfunction(value) and value.__module__ == root.__module__:
                helpers.append(name)
                pending.append(value)
            elif isinstance(value, types.ModuleType):
                modules.append(value.__name__)
        graph.append(
            {
                "callable": f"{function.__module__}.{function.__qualname__}",
                "same_module_helpers": helpers,
                "referenced_modules": modules,
                "bytecode_global_names": sorted(
                    {
                        str(instruction.argval)
                        for instruction in dis.get_instructions(function)
                        if instruction.opname in {"LOAD_GLOBAL", "LOAD_NAME"}
                    }
                ),
            }
        )
    return sorted(graph, key=lambda item: item["callable"])


def _reachable_inventory(
    roots: dict[str, object], *, maximum_depth: int = 2
) -> list[dict[str, Any]]:
    pending = [(name, value, 0) for name, value in sorted(roots.items())]
    visited: set[int] = set()
    inventory: list[dict[str, Any]] = []
    while pending:
        path, value, depth = pending.pop(0)
        if id(value) in visited:
            continue
        visited.add(id(value))
        description = _safe_object_description(value)
        inventory.append({"path": path, **description})
        if depth >= maximum_depth or isinstance(
            value, (str, bytes, int, float, bool, type(None), types.ModuleType)
        ):
            continue
        if inspect.isfunction(value):
            nested = inspect.getclosurevars(value)
            for name, item in sorted(
                {**nested.nonlocals, **nested.globals}.items()
            ):
                pending.append((f"{path}.{name}", item, depth + 1))
        elif isinstance(value, dict):
            for name, item in sorted(value.items(), key=lambda pair: str(pair[0])):
                pending.append((f"{path}[{name!r}]", item, depth + 1))
        elif isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                pending.append((f"{path}[{index}]", item, depth + 1))
        elif hasattr(value, "__dict__"):
            for name, item in sorted(vars(value).items()):
                pending.append((f"{path}.{name}", item, depth + 1))
    return inventory


def audit_callable_dependencies(
    function: Callable[..., object],
    *,
    forbidden_tokens: tuple[str, ...],
    explicit_state_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Inventory signature, closure, globals, helper graph, and source tokens."""

    source = inspect.getsource(function)
    source_path = Path(inspect.getsourcefile(function) or "")
    closure = inspect.getclosurevars(function)
    parsed = ast.parse(source)
    called_names = sorted(
        {
            node.func.id
            for node in ast.walk(parsed)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
    )
    global_inventory = {
        name: _safe_object_description(value)
        for name, value in sorted(closure.globals.items())
    }
    nonlocal_inventory = {
        name: _safe_object_description(value)
        for name, value in sorted(closure.nonlocals.items())
    }
    mutable_referenced_globals = sorted(
        name
        for name, value in closure.globals.items()
        if isinstance(value, (dict, list, set, bytearray))
    )
    helper_graph = _helper_graph(function)
    helper_sources = [source]
    for value in closure.globals.values():
        if inspect.isfunction(value) and value.__module__ == function.__module__:
            helper_sources.append(inspect.getsource(value))
    scanned_source = "\n".join(helper_sources).lower()
    token_scan = {token: scanned_source.count(token.lower()) for token in forbidden_tokens}
    relevant_modules = sorted(
        {
            module
            for node in helper_graph
            for module in node["referenced_modules"]
        }
    )
    forbidden_hits = {name: count for name, count in token_scan.items() if count}
    reachable_inventory = _reachable_inventory(
        {**closure.nonlocals, **closure.globals}
    )
    reachable_environment_objects = [
        item
        for item in reachable_inventory
        if "catchenvironment" in item["type"].lower()
        or item["module"] == "flybench.catch"
        and item["qualname"] == "CatchEnvironment"
    ]
    passed = (
        not forbidden_hits
        and not nonlocal_inventory
        and not mutable_referenced_globals
        and not reachable_environment_objects
    )
    return {
        "callable": f"{function.__module__}.{function.__qualname__}",
        "source_path": source_path.as_posix(),
        "signature": str(inspect.signature(function)),
        "closure_variables": {
            "nonlocals": nonlocal_inventory,
            "globals": global_inventory,
            "builtins": sorted(closure.builtins),
            "unbound": sorted(closure.unbound),
        },
        "helper_call_graph": helper_graph,
        "ast_direct_call_names": called_names,
        "imported_modules_relevant_to_callable": relevant_modules,
        "explicit_state_fields": list(explicit_state_fields),
        "mutable_referenced_globals": mutable_referenced_globals,
        "reachable_object_inventory": reachable_inventory,
        "forbidden_token_scan": {
            "tokens": list(forbidden_tokens),
            "hits": forbidden_hits,
            "scope": "callable source plus recursively inventoried same-module helpers",
        },
        "reachable_environment_objects": reachable_environment_objects,
        "status": "PASS" if passed else "FAIL",
        "conclusion": (
            "No forbidden input, closure/nonlocal, mutable singleton, or reachable shared object was found."
            if passed
            else "Forbidden or mutable dependency evidence was found."
        ),
    }
