from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from langchain_core.documents import Document

from evaluation.scoring import score_rule_metrics


def _doc_summary(doc: Document) -> Dict:
    return {
        "dish_name": doc.metadata.get("dish_name"),
        "content_type": doc.metadata.get("content_type"),
        "rrf_score": doc.metadata.get("rrf_score"),
        "preview": doc.page_content.strip().splitlines()[0][:80] if doc.page_content else "",
    }


def _summarize_docs(docs: Iterable[Document], limit: int = 5) -> List[Dict]:
    return [_doc_summary(doc) for doc in list(docs)[:limit]]


def _find_rank(docs: Iterable[Document], expected_dish: Optional[str]) -> Optional[int]:
    if not expected_dish:
        return None
    normalized = expected_dish.strip()
    for index, doc in enumerate(docs, start=1):
        if doc.metadata.get("dish_name", "").strip() == normalized:
            return index
    return None


def _content_type_hit_rate(docs: Iterable[Document], expected_content_type: Optional[str]) -> Optional[float]:
    docs = list(docs)
    if not docs or not expected_content_type:
        return None
    hit_count = sum(doc.metadata.get("content_type") == expected_content_type for doc in docs)
    return round(hit_count / len(docs), 4)


def _target_purity(docs: Iterable[Document], expected_dish: Optional[str]) -> Optional[float]:
    docs = list(docs)
    if not docs or not expected_dish:
        return None
    hit_count = sum(doc.metadata.get("dish_name", "").strip() == expected_dish.strip() for doc in docs)
    return round(hit_count / len(docs), 4)


def _irrelevant_ratio(docs: Iterable[Document], expected_dish: Optional[str]) -> Optional[float]:
    purity = _target_purity(docs, expected_dish)
    if purity is None:
        return None
    return round(1 - purity, 4)


def _filter_retention_ratio(before_docs: Iterable[Document], after_docs: Iterable[Document]) -> Optional[float]:
    before_docs = list(before_docs)
    after_docs = list(after_docs)
    if not before_docs:
        return None
    return round(len(after_docs) / len(before_docs), 4)


def _same_dish_cluster_ratio(docs: Iterable[Document]) -> Optional[float]:
    docs = list(docs)
    if not docs:
        return None
    top_dish = docs[0].metadata.get("dish_name", "")
    if not top_dish:
        return None
    same_count = sum(doc.metadata.get("dish_name", "") == top_dish for doc in docs)
    return round(same_count / len(docs), 4)


def _content_type_mismatch_ratio(docs: Iterable[Document], expected_content_type: Optional[str]) -> Optional[float]:
    docs = list(docs)
    if not docs or not expected_content_type:
        return None
    mismatch_count = sum(doc.metadata.get("content_type") != expected_content_type for doc in docs)
    return round(mismatch_count / len(docs), 4)


def analyze_retrieval_layer(
    retrieval_trace: Dict,
    expected_dish: Optional[str] = None,
    expected_content_type: Optional[str] = None,
) -> Dict:
    vector_candidates = retrieval_trace.get("vector_candidates", [])
    bm25_candidates = retrieval_trace.get("bm25_candidates", [])
    reranked_candidates = retrieval_trace.get("reranked_candidates", [])
    final_candidates = retrieval_trace.get("final_candidates", [])
    vector_target_rank = _find_rank(vector_candidates, expected_dish)
    rerank_target_rank = _find_rank(reranked_candidates, expected_dish)
    initial_target_purity = _target_purity(reranked_candidates, expected_dish)
    final_target_purity = _target_purity(final_candidates, expected_dish)
    filter_retention_ratio = _filter_retention_ratio(reranked_candidates, final_candidates)

    return {
        "query": retrieval_trace.get("query"),
        "applied_filters": retrieval_trace.get("filters", {}),
        "metrics": {
            "vector_target_rank": vector_target_rank,
            "bm25_target_rank": _find_rank(bm25_candidates, expected_dish),
            "rerank_target_rank": rerank_target_rank,
            "final_target_rank": _find_rank(final_candidates, expected_dish),
            "final_content_type_hit_rate": _content_type_hit_rate(final_candidates, expected_content_type),
            "retrieval_candidate_count": len(reranked_candidates),
            "final_candidate_count": len(final_candidates),
            "filter_retention_ratio": filter_retention_ratio,
            "initial_target_purity": initial_target_purity,
            "final_target_purity": final_target_purity,
            "purity_gain": round(final_target_purity - initial_target_purity, 4)
            if initial_target_purity is not None and final_target_purity is not None
            else None,
            "final_irrelevant_ratio": _irrelevant_ratio(final_candidates, expected_dish),
            "same_dish_cluster_ratio": _same_dish_cluster_ratio(final_candidates),
            "content_type_mismatch_ratio": _content_type_mismatch_ratio(reranked_candidates, expected_content_type),
            "filter_overkill_risk": bool(
                reranked_candidates
                and expected_dish
                and _find_rank(reranked_candidates, expected_dish) is not None
                and not final_candidates
            ),
            "rerank_promotion_gain": (vector_target_rank - rerank_target_rank)
            if vector_target_rank is not None and rerank_target_rank is not None
            else None,
        },
        "vector_candidates": _summarize_docs(vector_candidates),
        "bm25_candidates": _summarize_docs(bm25_candidates),
        "reranked_candidates": _summarize_docs(reranked_candidates),
        "final_candidates": _summarize_docs(final_candidates),
    }


def analyze_context_layer(
    relevant_docs: List[Document],
    expected_dish: Optional[str] = None,
    expected_content_type: Optional[str] = None,
    context_chunks: Optional[List[Document]] = None,
) -> Dict:
    dish_names = [doc.metadata.get("dish_name", "") for doc in relevant_docs]
    pollution_count = sum(name != expected_dish for name in dish_names if expected_dish) if relevant_docs else 0
    context_chunks = context_chunks or []
    requested_content_type_present = None
    if expected_content_type:
        requested_content_type_present = any(
            doc.metadata.get("content_type") == expected_content_type for doc in context_chunks
        )
        if not requested_content_type_present and relevant_docs:
            requested_content_type_present = any(
                doc.metadata.get("content_type") == expected_content_type for doc in relevant_docs
            )

    return {
        "parent_docs": _summarize_docs(relevant_docs),
        "metrics": {
            "parent_doc_hit": bool(relevant_docs),
            "parent_doc_count": len(relevant_docs),
            "target_doc_preserved": expected_dish in dish_names if expected_dish else None,
            "requested_content_type_present": requested_content_type_present,
            "context_pollution_ratio": round(pollution_count / len(relevant_docs), 4) if relevant_docs and expected_dish else 0.0,
        },
    }


def analyze_generation_layer(
    answer: str,
    expectation: Dict,
    relevant_docs: List[Document],
    generation_trace: Optional[Dict] = None,
) -> Dict:
    generation_trace = generation_trace or {}
    rule_result = score_rule_metrics(answer, expectation)
    fallback_detected = rule_result["policy_detected"] == "polite_fallback"

    failure_tags: List[str] = []
    if generation_trace.get("strategy") == "no_context":
        failure_tags.append("context_lost")
    if fallback_detected:
        failure_tags.append("generation_fallback")
    if not rule_result["passed"]:
        if not rule_result["checks"].get("dish_match", True):
            failure_tags.append("generation_wrong_scope")
        if not rule_result["checks"].get("required_terms", True) or not rule_result["checks"].get("required_terms_any", True):
            failure_tags.append("generation_ungrounded")

    return {
        "strategy": generation_trace.get("strategy"),
        "reason": generation_trace.get("reason"),
        "content_type": generation_trace.get("content_type"),
        "metrics": {
            "fallback_detected": fallback_detected,
            "rule_score": rule_result["score"],
            "rule_passed": rule_result["passed"],
            "context_doc_count": generation_trace.get("context_doc_count", len(relevant_docs)),
        },
        "failure_tags": failure_tags,
        "rule_result": rule_result,
        "answer_preview": answer[:300],
    }


def build_turn_diagnostic_report(
    question: str,
    answer: str,
    query_plan: Dict,
    rewritten_query: str,
    retrieval_trace: Dict,
    relevant_docs: List[Document],
    generation_trace: Optional[Dict],
    expectation: Dict,
) -> Dict:
    expected_dish = expectation.get("expected_dish") or query_plan.get("dish_name")
    expected_content_type = query_plan.get("filters", {}).get("content_type")

    retrieval_layer = analyze_retrieval_layer(
        retrieval_trace=retrieval_trace,
        expected_dish=expected_dish,
        expected_content_type=expected_content_type,
    )
    context_layer = analyze_context_layer(
        relevant_docs=relevant_docs,
        expected_dish=expected_dish,
        expected_content_type=expected_content_type,
        context_chunks=retrieval_trace.get("final_candidates", []),
    )
    generation_layer = analyze_generation_layer(
        answer=answer,
        expectation=expectation,
        relevant_docs=relevant_docs,
        generation_trace=generation_trace,
    )

    primary_failure_layer = "none"
    if retrieval_layer["metrics"]["final_target_rank"] is None and expected_dish:
        primary_failure_layer = "retrieval"
    elif not context_layer["metrics"]["parent_doc_hit"]:
        primary_failure_layer = "context"
    elif not generation_layer["metrics"]["rule_passed"]:
        primary_failure_layer = "generation"

    return {
        "question": question,
        "rewritten_query": rewritten_query,
        "routing": {
            "route_type": query_plan.get("route_type"),
            "filters": query_plan.get("filters", {}),
            "dish_name": query_plan.get("dish_name"),
            "confidence": query_plan.get("confidence"),
        },
        "retrieval": retrieval_layer,
        "context": context_layer,
        "generation": generation_layer,
        "summary": {
            "primary_failure_layer": primary_failure_layer,
            "failure_tags": generation_layer["failure_tags"],
        },
    }
