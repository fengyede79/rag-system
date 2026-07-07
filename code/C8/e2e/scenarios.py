from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScenarioTurn:
    question: str
    endpoint: str
    assertions: dict[str, Any]


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    session_id: str
    turns: list[ScenarioTurn]
    suite: str = "core"


def load_scenarios(path: Path) -> list[Scenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios: list[Scenario] = []
    for raw in payload["scenarios"]:
        turns = [
            ScenarioTurn(
                question=str(turn["question"]),
                endpoint=str(turn.get("endpoint", "chat")),
                assertions=dict(turn.get("assertions") or {}),
            )
            for turn in raw["turns"]
        ]
        scenarios.append(
            Scenario(
                id=str(raw["id"]),
                category=str(raw["category"]),
                session_id=str(raw["session_id"]),
                turns=turns,
                suite=str(raw.get("suite", "core")),
            )
        )
    return scenarios


def filter_scenarios_by_suite(scenarios: list[Scenario], suite: str) -> list[Scenario]:
    if suite == "all":
        return list(scenarios)
    if suite not in {"core", "extended"}:
        raise ValueError("suite must be one of: core, extended, all")
    return [scenario for scenario in scenarios if scenario.suite == suite]


def flatten_turns(
    scenarios: list[Scenario],
    limit_turns: int | None = None,
) -> list[tuple[Scenario, ScenarioTurn]]:
    flattened: list[tuple[Scenario, ScenarioTurn]] = []
    for scenario in scenarios:
        for turn in scenario.turns:
            flattened.append((scenario, turn))
            if limit_turns is not None and len(flattened) >= limit_turns:
                return flattened
    return flattened
