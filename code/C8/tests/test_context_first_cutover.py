from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_uses_context_first_contracts_not_old_front_door_or_qualification():
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "from rag_modules.front_door_guardrail import check_front_door" not in source
    assert "from rag_modules.turn_qualification import qualify_turn" not in source
    assert "check_front_door(" not in source
    assert "qualify_turn(" not in source
    assert "basic_safety_gate(question)" in source
    assert "understand_turn(question, snapshot)" in source


def test_context_first_order_is_visible_in_main_source():
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    safety_index = source.index("basic_safety_gate(question)")
    snapshot_index = source.index("build_conversation_snapshot(")
    understanding_index = source.index("understand_turn(question, snapshot)")

    assert safety_index < snapshot_index < understanding_index


def test_old_turn_qualification_module_is_removed():
    assert not (ROOT / "rag_modules" / "turn_qualification.py").exists()


def test_front_door_exports_only_basic_safety_gate_contract():
    source = (ROOT / "rag_modules" / "front_door_guardrail.py").read_text(encoding="utf-8")

    assert "def basic_safety_gate(" in source
    assert "def check_front_door(" not in source
    assert "direct_reply" not in source
    assert "smalltalk" not in source.lower()
    assert "out_of_domain" not in source
