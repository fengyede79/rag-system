from rag_modules.front_door_guardrail import basic_safety_gate


def test_basic_safety_gate_blocks_empty_and_punctuation_only_inputs():
    for query in ["", " ", "？", "!!!", "..."]:
        result = basic_safety_gate(query)

        assert result == {
            "decision": "block",
            "reason": "empty_or_punctuation",
            "message": "请输入一个具体的食谱或做菜问题。",
        }


def test_basic_safety_gate_continues_isolated_references_for_snapshot_handling():
    for query in ["这个", "它", "第一个", "那道菜"]:
        assert basic_safety_gate(query) == {
            "decision": "continue",
            "reason": "default_continue",
            "message": None,
        }


def test_basic_safety_gate_does_not_classify_smalltalk_or_domain():
    for query in ["你好", "谢谢", "Python怎么学", "股票怎么买", "蛋炒饭怎么做"]:
        assert basic_safety_gate(query) == {
            "decision": "continue",
            "reason": "default_continue",
            "message": None,
        }


def test_basic_safety_gate_result_shape_has_no_semantic_fields():
    forbidden = {
        "dish_name",
        "intent_type",
        "route_type",
        "filters",
        "content_type",
        "semantic_result",
        "rewritten_query",
        "action",
        "answer_mode_hint",
    }

    result = basic_safety_gate("第一个怎么做")

    assert set(result) == {"decision", "reason", "message"}
    assert forbidden.isdisjoint(result)
