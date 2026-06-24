from langchain_core.documents import Document

from evaluation.process_diagnostics import (
    analyze_context_layer,
    analyze_generation_layer,
    analyze_retrieval_layer,
    build_turn_diagnostic_report,
)


def _doc(dish_name: str, content_type: str, text: str, score: float = 0.0) -> Document:
    return Document(
        page_content=text,
        metadata={
            "dish_name": dish_name,
            "content_type": content_type,
            "rrf_score": score,
        },
    )


def test_retrieval_layer_reports_target_ranks_and_type_hits():
    trace = {
        "query": "鸡蛋三明治需要什么食材",
        "filters": {"content_type": "ingredients", "dish_name": "鸡蛋三明治"},
        "vector_candidates": [
            _doc("麻婆豆腐", "ingredients", "豆腐"),
            _doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司", 0.9),
        ],
        "bm25_candidates": [
            _doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司", 0.9),
            _doc("红烧鲤鱼", "steps", "红烧"),
        ],
        "reranked_candidates": [
            _doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司", 1.2),
            _doc("麻婆豆腐", "ingredients", "豆腐", 0.8),
        ],
        "final_candidates": [
            _doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司", 1.2),
        ],
    }

    layer = analyze_retrieval_layer(
        retrieval_trace=trace,
        expected_dish="鸡蛋三明治",
        expected_content_type="ingredients",
    )

    assert layer["metrics"]["vector_target_rank"] == 2
    assert layer["metrics"]["bm25_target_rank"] == 1
    assert layer["metrics"]["rerank_target_rank"] == 1
    assert layer["metrics"]["final_target_rank"] == 1
    assert layer["metrics"]["final_content_type_hit_rate"] == 1.0
    assert layer["metrics"]["rerank_promotion_gain"] == 1
    assert layer["metrics"]["initial_target_purity"] == 0.5
    assert layer["metrics"]["purity_gain"] == 0.5
    assert layer["metrics"]["final_target_purity"] == 1.0
    assert layer["metrics"]["final_irrelevant_ratio"] == 0.0
    assert layer["metrics"]["same_dish_cluster_ratio"] == 1.0
    assert layer["metrics"]["content_type_mismatch_ratio"] == 0.0
    assert layer["metrics"]["filter_overkill_risk"] is False


def test_retrieval_layer_reports_purity_and_filter_retention_for_noisy_results():
    trace = {
        "query": "红烧鲤鱼怎么做",
        "filters": {"content_type": "steps", "dish_name": "红烧鲤鱼"},
        "vector_candidates": [
            _doc("糖醋鲤鱼", "steps", "糖醋"),
            _doc("红烧鲤鱼", "steps", "红烧"),
            _doc("麻婆豆腐", "steps", "豆腐"),
        ],
        "bm25_candidates": [
            _doc("红烧鲤鱼", "steps", "红烧"),
            _doc("红烧鱼头", "steps", "鱼头"),
        ],
        "reranked_candidates": [
            _doc("红烧鲤鱼", "steps", "红烧", 1.2),
            _doc("糖醋鲤鱼", "steps", "糖醋", 1.0),
            _doc("麻婆豆腐", "steps", "豆腐", 0.8),
        ],
        "final_candidates": [
            _doc("红烧鲤鱼", "steps", "红烧", 1.2),
            _doc("糖醋鲤鱼", "steps", "糖醋", 1.0),
        ],
    }

    layer = analyze_retrieval_layer(
        retrieval_trace=trace,
        expected_dish="红烧鲤鱼",
        expected_content_type="steps",
    )

    assert layer["metrics"]["retrieval_candidate_count"] == 3
    assert layer["metrics"]["filter_retention_ratio"] == 0.6667
    assert layer["metrics"]["initial_target_purity"] == 0.3333
    assert layer["metrics"]["purity_gain"] == 0.1667
    assert layer["metrics"]["final_target_purity"] == 0.5
    assert layer["metrics"]["final_irrelevant_ratio"] == 0.5
    assert layer["metrics"]["same_dish_cluster_ratio"] == 0.5
    assert layer["metrics"]["content_type_mismatch_ratio"] == 0.0
    assert layer["metrics"]["filter_overkill_risk"] is False


def test_retrieval_layer_detects_type_mismatch_and_filter_overkill_risk():
    trace = {
        "query": "红烧鲤鱼怎么做",
        "filters": {"content_type": "steps", "dish_name": "红烧鲤鱼"},
        "vector_candidates": [
            _doc("红烧鲤鱼", "steps", "红烧"),
            _doc("红烧鲤鱼", "ingredients", "鲤鱼"),
        ],
        "bm25_candidates": [
            _doc("红烧鲤鱼", "steps", "红烧"),
        ],
        "reranked_candidates": [
            _doc("红烧鲤鱼", "steps", "红烧", 1.2),
            _doc("红烧鲤鱼", "ingredients", "鲤鱼", 1.0),
        ],
        "final_candidates": [],
    }

    layer = analyze_retrieval_layer(
        retrieval_trace=trace,
        expected_dish="红烧鲤鱼",
        expected_content_type="steps",
    )

    assert layer["metrics"]["content_type_mismatch_ratio"] == 0.5
    assert layer["metrics"]["filter_retention_ratio"] == 0.0
    assert layer["metrics"]["filter_overkill_risk"] is True


def test_context_layer_flags_pollution_and_requested_section_presence():
    docs = [
        _doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司 培根"),
        _doc("麻婆豆腐", "steps", "豆腐 下锅"),
    ]

    layer = analyze_context_layer(
        relevant_docs=docs,
        expected_dish="鸡蛋三明治",
        expected_content_type="ingredients",
    )

    assert layer["metrics"]["parent_doc_hit"] is True
    assert layer["metrics"]["target_doc_preserved"] is True
    assert layer["metrics"]["requested_content_type_present"] is True
    assert layer["metrics"]["context_pollution_ratio"] == 0.5


def test_generation_layer_tags_fallback_and_missing_grounding():
    docs = []
    generation_trace = {
        "strategy": "no_context",
        "content_type": "tips",
        "context_doc_count": 0,
        "reason": "missing_parent_docs",
    }

    layer = analyze_generation_layer(
        answer="抱歉，我现在没有足够完整的信息，如果你愿意我可以先推荐别的菜。",
        expectation={
            "expected_dish": "老干妈拌面",
            "response_policy": "polite_fallback",
        },
        relevant_docs=docs,
        generation_trace=generation_trace,
    )

    assert layer["metrics"]["fallback_detected"] is True
    assert "context_lost" in layer["failure_tags"]
    assert "generation_fallback" in layer["failure_tags"]


def test_build_turn_diagnostic_report_includes_all_layers():
    report = build_turn_diagnostic_report(
        question="鸡蛋三明治需要什么食材",
        answer="鸡蛋三明治需要鸡蛋、吐司和培根。",
        query_plan={
            "route_type": "detail",
            "filters": {"content_type": "ingredients"},
            "dish_name": "鸡蛋三明治",
            "confidence": 0.95,
        },
        rewritten_query="鸡蛋三明治需要什么食材",
        retrieval_trace={
            "query": "鸡蛋三明治需要什么食材",
            "vector_candidates": [_doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司")],
            "bm25_candidates": [_doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司")],
            "reranked_candidates": [_doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司")],
            "final_candidates": [_doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司")],
        },
        relevant_docs=[_doc("鸡蛋三明治", "ingredients", "鸡蛋 吐司 培根")],
        generation_trace={"strategy": "structured", "content_type": "ingredients", "context_doc_count": 1},
        expectation={
            "expected_dish": "鸡蛋三明治",
            "response_policy": "grounded_answer",
        },
    )

    assert report["routing"]["route_type"] == "detail"
    assert "retrieval" in report
    assert "context" in report
    assert "generation" in report
    assert report["summary"]["primary_failure_layer"] in {"none", "retrieval", "context", "generation"}
