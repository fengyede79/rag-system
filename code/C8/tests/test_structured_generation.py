from langchain_core.documents import Document

from rag_modules.generation_integration import GenerationIntegrationModule


def _module() -> GenerationIntegrationModule:
    return GenerationIntegrationModule.__new__(GenerationIntegrationModule)


def test_tips_can_fall_back_to_steps_when_no_tips_section_exists():
    module = _module()
    doc = Document(
        page_content=(
            "# 老干妈拌面的做法\n"
            "这是一道快手主食。\n"
            "## 操作\n"
            "1. 将水倒入锅中并煮沸\n"
            "2. 将面放入锅中，过程中注意搅拌，避免面粘成一坨\n"
        ),
        metadata={"dish_name": "老干妈拌面"},
    )

    answer = module._try_build_structured_answer(
        "老干妈拌面有什么制作技巧",
        [doc],
        "tips",
    )

    assert answer is not None
    assert "老干妈拌面" in answer
    assert "搅拌" in answer


def test_placeholder_only_section_is_not_returned_as_structured_answer():
    module = _module()
    doc = Document(
        page_content=(
            "# 示例菜的做法\n"
            "## 必备原料和工具\n"
            "<!-- 在这里列出必需原料。 -->\n"
            "<!-- 注意：这里不要输出模板注释。 -->\n"
        ),
        metadata={"dish_name": "示例菜"},
    )

    answer = module._try_build_structured_answer(
        "示例菜需要什么食材",
        [doc],
        "ingredients",
    )

    assert answer is None


def test_rule_router_keeps_dish_name_for_tips_queries():
    module = _module()

    intent = module._rule_based_routing("老干妈拌面有什么制作技巧")

    assert intent["type"] == "detail"
    assert intent["filters"]["content_type"] == "tips"
    assert intent["dish_name"] == "老干妈拌面"
