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
