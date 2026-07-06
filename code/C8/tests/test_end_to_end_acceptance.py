from acceptance_fixtures import ask_and_trace, build_acceptance_system


def test_acceptance_fixture_uses_real_runtime_boundaries():
    system = build_acceptance_system()

    answer, trace = ask_and_trace(system, "推荐三个鸡肉菜", session_id="fixture-smoke")

    session = system.generation_module.conversation_manager.get_session("fixture-smoke")
    assert "宫保鸡丁" in answer
    assert session.recent_recommendations
    assert trace["query_plan"]["route_type"] == "list"
    assert trace["retrieval_quality"]["enough_evidence"] is True
    assert trace["context_pack_trace"]["selected_section_count"] >= 1
    assert trace["commit_result"]["committed"] is True


def test_primary_multi_turn_recipe_chain_preserves_state_and_trace():
    system = build_acceptance_system()
    session_id = "primary-chain"

    first_answer, first_trace = ask_and_trace(system, "推荐三个鸡肉菜", session_id=session_id)
    assert "宫保鸡丁" in first_answer
    assert first_trace["query_plan"]["route_type"] == "list"
    assert first_trace["retrieval_quality"]["enough_evidence"] is True

    second_answer, second_trace = ask_and_trace(system, "第一个怎么做", session_id=session_id)
    assert "宫保鸡丁" in second_answer
    assert second_trace["query_plan"]["route_type"] == "detail"
    assert second_trace["retrieval_quality"]["quality_reason"] == "exact_dish_matched"

    third_answer, third_trace = ask_and_trace(system, "这个能不放辣吗", session_id=session_id)
    assert "不放辣" in third_answer or "辣椒" in third_answer
    assert third_trace["query_plan"]["route_type"] == "detail"

    fourth_answer, fourth_trace = ask_and_trace(system, "没有豆瓣酱怎么办", session_id=session_id)
    assert "生抽" in fourth_answer
    assert fourth_trace["query_plan"]["route_type"] == "detail"

    fifth_answer, fifth_trace = ask_and_trace(system, "给我换个不辣的", session_id=session_id)
    assert "香菇滑鸡" in fifth_answer or "可乐鸡翅" in fifth_answer
    assert fifth_trace["query_plan"]["route_type"] == "list"

    sixth_answer, sixth_trace = ask_and_trace(system, "谢谢", session_id=session_id)
    assert "不客气" in sixth_answer
    assert sixth_trace.get("query_plan", {}) == {}

    session = system.generation_module.conversation_manager.get_session(session_id)
    assert session.current_entity == "宫保鸡丁"
    assert session.recent_recommendations
    assert session.last_answer_type == "smalltalk"
    assert session.pending_clarification is None
    assert session.state_version >= 6
