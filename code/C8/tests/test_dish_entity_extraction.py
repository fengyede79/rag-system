from rag_modules.dish_entity_extraction import extract_dish_entity_from_query


def test_extracts_dish_before_intent_suffix_without_exact_question_special_case():
    cases = [
        ("可乐鸡翅需要准备什么？", "可乐鸡翅", "需要准备什么"),
        ("鱼香肉丝需要准备哪些配菜？", "鱼香肉丝", "需要准备哪些配菜"),
        ("麻婆豆腐怎么不容易碎？", "麻婆豆腐", "怎么不容易碎"),
        ("老干妈拌面有什么制作技巧？", "老干妈拌面", "有什么制作技巧"),
        ("土豆丝怎么炒更脆？", "土豆丝", "怎么炒更脆"),
    ]

    for query, dish, suffix in cases:
        result = extract_dish_entity_from_query(query)
        assert result.dish_candidate == dish, f"failed for {query}: got {result.dish_candidate}"
        assert result.intent_suffix == suffix, f"failed for {query}: got {result.intent_suffix}"
        assert result.confidence >= 0.8
        assert result.extraction_reason == "intent_suffix_split"


def test_normalizes_bounded_alias_after_general_extraction():
    result = extract_dish_entity_from_query("拍黄瓜怎么调味？")

    assert result.dish_candidate == "凉拌黄瓜"
    assert result.intent_suffix == "怎么调味"
    assert result.extraction_reason == "intent_suffix_split_alias_normalized"


def test_does_not_extract_pronoun_or_ordinal_as_dish():
    for query in ["这个适合带饭吗？", "那第二个怎么做？", "第一个需要什么食材？"]:
        result = extract_dish_entity_from_query(query)
        assert result.dish_candidate is None, f"should not extract dish from: {query}"
        assert result.confidence == 0.0
        assert result.extraction_reason in {"reference_like_query", "no_intent_suffix_match"}
