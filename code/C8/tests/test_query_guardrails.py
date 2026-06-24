from rag_modules.generation_integration import GenerationIntegrationModule


def _module() -> GenerationIntegrationModule:
    return GenerationIntegrationModule.__new__(GenerationIntegrationModule)


def test_detects_temporal_personal_question():
    module = _module()

    assert module._classify_query_guardrail("\u6211\u6628\u5929\u5403\u4e86\u4ec0\u4e48") == "temporal_personal"
    assert module._classify_query_guardrail(
        "\u4f60\u8bb0\u5f97\u6211\u524d\u5929\u665a\u996d\u5403\u4e86\u5565\u5417"
    ) == "temporal_personal"
    assert module._classify_query_guardrail("\u6211\u660e\u5929\u4e2d\u5348\u4f1a\u5403\u4ec0\u4e48") == "temporal_personal"
    assert module._classify_query_guardrail("\u6211\u4e0a\u6b21\u716e\u7684\u6c64\u662f\u54ea\u4e00\u79cd") == "temporal_personal"
    assert module._classify_query_guardrail("\u4eca\u5929\u5403\u4ec0\u4e48") is None


def test_detects_out_of_domain_question_without_blocking_recipe_queries():
    module = _module()

    assert (
        module._classify_query_guardrail("\u4e0d\u9508\u94a2\u73bb\u7483\u600e\u4e48\u6e05\u6d17")
        == "out_of_domain"
    )
    assert (
        module._classify_query_guardrail("\u8def\u7531\u5668\u603b\u65ad\u7f51\u600e\u4e48\u529e")
        == "out_of_domain"
    )
    assert (
        module._classify_query_guardrail("\u7fbd\u7ed2\u670d\u600e\u4e48\u6d17\u4e0d\u7ed3\u56e2")
        == "out_of_domain"
    )
    assert module._classify_query_guardrail("\u7a7a\u6c14\u70b8\u9505\u7f8a\u6392\u600e\u4e48\u505a") is None
    assert module._classify_query_guardrail("\u63a8\u8350\u51e0\u4e2a\u4e3b\u98df") is None


def test_detects_boundary_mixed_queries_as_guardrail_cases():
    module = _module()

    assert module._classify_query_guardrail("\u63a8\u8350\u4e2a\u65e9\u9910\uff0c\u518d\u544a\u8bc9\u6211\u600e\u4e48\u4fee\u73bb\u7483") is None
    assert module._classify_query_guardrail("\u9ebb\u5a46\u8c46\u8150\u548c\u7ea2\u70e7\u9ca4\u9c7c\u662f\u4e00\u4e2a\u83dc\u5417") == "unsupported_food_judgement"
    assert module._classify_query_guardrail("\u9e21\u86cb\u4e09\u660e\u6cbb\u9700\u8981\u725b\u6392\u5417") == "unsupported_food_judgement"


def test_recipe_signal_overrides_polluted_tokens():
    module = _module()

    assert module._classify_query_guardrail("\u7528\u94c1\u9489\u600e\u4e48\u7092\u86cb\u7092\u996d") is None
    assert module._classify_query_guardrail("\u86cb\u7092\u996d\u91cc\u653e\u87ba\u4e1d\u53ef\u4ee5\u5417") is None


def test_only_clearly_non_recipe_queries_route_to_polite_feedback():
    module = _module()

    assert module._classify_query_guardrail("\u4f60\u600e\u4e48\u56de\u7b54\u8fd9\u4e48\u5feb") == "out_of_domain"
    assert module._classify_query_guardrail("\u4eca\u5929\u5929\u6c14\u600e\u4e48\u6837") == "out_of_domain"


def test_builds_polite_guardrail_answers():
    module = _module()

    temporal_answer = module.build_guardrail_answer(
        "\u6211\u4e0a\u5468\u505a\u8fc7\u54ea\u9053\u83dc",
        "temporal_personal",
    )
    out_of_domain_answer = module.build_guardrail_answer(
        "\u624b\u673a\u58f3\u53d1\u9ec4\u600e\u4e48\u5904\u7406",
        "out_of_domain",
    )
    unsupported_answer = module.build_guardrail_answer(
        "\u9ebb\u5a46\u8c46\u8150\u548c\u7ea2\u70e7\u9ca4\u9c7c\u662f\u4e00\u4e2a\u83dc\u5417",
        "unsupported_food_judgement",
    )

    assert "\u4e0d\u77e5\u9053" in temporal_answer
    assert "\u53ef\u4ee5\u63a8\u8350" in temporal_answer
    assert "\u4e0d\u6e05\u695a" in out_of_domain_answer
    assert "\u98df\u8c31" in out_of_domain_answer
    assert "\u4e0d\u77e5\u9053" in unsupported_answer or "\u4e0d\u6e05\u695a" in unsupported_answer


def test_polite_feedback_answer_invites_recipe_follow_up():
    module = _module()

    answer = module.build_guardrail_answer(
        "\u4f60\u600e\u4e48\u56de\u7b54\u8fd9\u4e48\u5feb",
        "out_of_domain",
    )

    assert "\u7ee7\u7eed" in answer
    assert "\u505a\u83dc" in answer or "\u98df\u8c31" in answer
