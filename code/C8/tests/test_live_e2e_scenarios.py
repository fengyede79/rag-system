from pathlib import Path

from e2e.scenarios import flatten_turns, load_scenarios


SCENARIO_FILE = Path(__file__).resolve().parents[1] / "e2e" / "scenarios" / "live_e2e_scenarios.json"


def test_live_e2e_scenario_file_has_at_least_fifty_turns_and_required_categories():
    scenarios = load_scenarios(SCENARIO_FILE)
    turns = flatten_turns(scenarios)
    categories = {scenario.category for scenario in scenarios}

    assert len(turns) >= 50
    assert {
        "single_recipe_detail",
        "recommendation_list",
        "multi_turn_reference",
        "substitution_constraint",
        "low_evidence",
        "domain_reject",
        "streaming_sse",
        "rapid_followup_conflict",
    }.issubset(categories)


def test_flatten_turns_preserves_scenario_order_and_limit():
    scenarios = load_scenarios(SCENARIO_FILE)
    limited = flatten_turns(scenarios, limit_turns=3)

    assert len(limited) == 3
    assert [turn.question for _, turn in limited] == [
        scenarios[0].turns[0].question,
        scenarios[0].turns[1].question,
        scenarios[0].turns[2].question,
    ]


def test_each_turn_has_http_status_and_min_answer_assertion():
    scenarios = load_scenarios(SCENARIO_FILE)
    for scenario, turn in flatten_turns(scenarios):
        assert turn.endpoint in {"chat", "stream"}
        assert "http_status" in turn.assertions
        assert "min_answer_chars" in turn.assertions or turn.endpoint == "stream"
        assert scenario.session_id
