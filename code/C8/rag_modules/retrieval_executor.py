from __future__ import annotations

"""Retrieval execution boundary for the runtime chat path."""

from typing import Any, Dict, Iterable, List

from langchain_core.documents import Document


SOFT_FILTER_KEYS = ["ingredient", "taste", "difficulty", "time", "health_preference"]


def _copy_dict(value: dict | None) -> dict:
    return dict(value or {})


def _resolved_dish(base_query_plan: dict, resolution: dict | None) -> str | None:
    if resolution:
        resolved = resolution.get("resolved_target") or resolution.get("resolved_entity")
        if resolved:
            return resolved
    return base_query_plan.get("dish_name")


def _merge_preference_constraints(filters: dict, preference_constraints: dict | None) -> dict:
    merged = dict(filters)
    for key, value in (preference_constraints or {}).items():
        if value:
            merged[key] = value
    return merged


def _answer_mode_hint(execution_plan: dict, base_query_plan: dict) -> str:
    if execution_plan.get("answer_mode"):
        return execution_plan["answer_mode"]
    action = execution_plan.get("action")
    if action == "retrieve_list" or base_query_plan.get("route_type") == "list":
        return "recommendation"
    return "recipe_detail"


def _fallback_policy(route_type: str, hard_filters: list[str], filters: dict) -> str:
    if "dish_name" in hard_filters:
        return "disabled"
    if route_type == "list" or any(key in filters for key in SOFT_FILTER_KEYS):
        return "relaxed_filters"
    return "disabled"


def build_retrieval_query_plan(
    *,
    original_query: str,
    rewritten_query: str,
    base_query_plan: dict,
    execution_plan: dict,
    resolution: dict | None,
    preference_constraints: dict | None,
    top_k: int,
) -> dict:
    """Normalize the runtime query plan into the retrieval-facing contract."""
    route_type = base_query_plan.get("route_type", "detail")
    dish_name = _resolved_dish(base_query_plan, resolution)
    filters = _merge_preference_constraints(
        _copy_dict(base_query_plan.get("filters")),
        preference_constraints,
    )

    hard_filters: list[str] = []
    if dish_name:
        filters["dish_name"] = dish_name
        hard_filters.append("dish_name")

    soft_filters = list(SOFT_FILTER_KEYS)
    if "content_type" in filters:
        soft_filters.append("content_type")

    return {
        "query": rewritten_query,
        "original_query": original_query,
        "dish_name": dish_name,
        "filters": filters,
        "top_k": top_k,
        "fallback_policy": _fallback_policy(route_type, hard_filters, filters),
        "hard_filters": hard_filters,
        "soft_filters": soft_filters,
        "answer_mode_hint": _answer_mode_hint(execution_plan, base_query_plan),
        "route_type": route_type,
    }


class RetrievalExecutor:
    """Execute retrieval and return chunks plus explicit evidence quality."""

    def __init__(self, retrieval_module):
        self.retrieval_module = retrieval_module

    def execute(self, query_plan: dict) -> dict:
        primary_chunks = self._primary_retrieval(query_plan)
        quality = self._check_quality(query_plan, primary_chunks, fallback_used=False, relaxed_filter=False)
        trace = self._build_trace(
            query_plan=query_plan,
            strategy="primary",
            primary_count=len(primary_chunks),
            fallback_count=0,
            quality=quality,
        )

        return {
            "chunks": primary_chunks if quality["enough_evidence"] else [],
            "quality": quality,
            "low_evidence": None if quality["enough_evidence"] else self._low_evidence(quality["quality_reason"]),
            "trace": trace,
        }

    def _primary_retrieval(self, query_plan: dict) -> list[Document]:
        query = query_plan["query"]
        filters = dict(query_plan.get("filters") or {})
        top_k = query_plan.get("top_k", 3)
        dish_name = query_plan.get("dish_name")
        if filters:
            return list(
                self.retrieval_module.metadata_filtered_search(
                    query,
                    filters,
                    top_k=top_k,
                    query_dish=dish_name,
                )
            )
        return list(
            self.retrieval_module.hybrid_search(
                query,
                top_k=top_k,
                query_dish=dish_name,
            )
        )

    def _selected_dishes(self, chunks: Iterable[Document]) -> list[str]:
        dishes: list[str] = []
        for chunk in chunks:
            dish_name = (chunk.metadata or {}).get("dish_name")
            if dish_name and dish_name not in dishes:
                dishes.append(dish_name)
        return dishes

    def _check_quality(
        self,
        query_plan: dict,
        chunks: list[Document],
        *,
        fallback_used: bool,
        relaxed_filter: bool,
    ) -> dict:
        selected_dishes = self._selected_dishes(chunks)
        dish_name = query_plan.get("dish_name")
        hard_filters = set(query_plan.get("hard_filters") or [])

        enough = bool(chunks)
        reason = "primary_candidates_found" if enough else "no_candidates"

        if enough and dish_name and "dish_name" in hard_filters:
            if dish_name not in selected_dishes:
                enough = False
                reason = "exact_dish_not_found"
            elif len(selected_dishes) > 1:
                enough = False
                reason = "conflicting_dishes_for_exact_request"
            else:
                reason = "exact_dish_matched"

        return {
            "enough_evidence": enough,
            "quality_reason": reason,
            "fallback_used": fallback_used,
            "relaxed_filter": relaxed_filter,
            "candidate_count": len(chunks),
            "selected_dishes": selected_dishes,
        }

    def _low_evidence(self, quality_reason: str) -> dict:
        return {
            "answer_type": "no_result",
            "answer": "知识库里没有找到可靠的食谱信息。",
            "state_diff_policy": "low_evidence",
            "quality_reason": quality_reason,
        }

    def _build_trace(
        self,
        *,
        query_plan: dict,
        strategy: str,
        primary_count: int,
        fallback_count: int,
        quality: dict,
    ) -> dict:
        return {
            "strategy": strategy,
            "fusion_strategy": "delegated",
            "query": query_plan.get("query"),
            "original_query": query_plan.get("original_query"),
            "filters": dict(query_plan.get("filters") or {}),
            "hard_filters": list(query_plan.get("hard_filters") or []),
            "soft_filters": list(query_plan.get("soft_filters") or []),
            "fallback_policy": query_plan.get("fallback_policy", "disabled"),
            "primary_count": primary_count,
            "fallback_count": fallback_count,
            "selected_dishes": list(quality.get("selected_dishes") or []),
            "quality_reason": quality.get("quality_reason"),
        }
