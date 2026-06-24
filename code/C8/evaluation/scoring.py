from __future__ import annotations

from typing import Dict, Iterable, List


FALLBACK_MARKERS = [
    "不知道",
    "无法得知",
    "不能确定",
    "不清楚",
    "可以推荐",
    "如果你愿意",
    "我可以帮你",
]


def _contains_all(text: str, terms: Iterable[str]) -> bool:
    return all(term in text for term in terms)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _contains_none(text: str, terms: Iterable[str]) -> bool:
    return all(term not in text for term in terms)


def _infer_response_policy(answer: str) -> str:
    if _contains_any(answer, FALLBACK_MARKERS):
        return "polite_fallback"
    return "grounded_answer"


def score_rule_metrics(answer: str, expectation: Dict) -> Dict:
    checks: Dict[str, bool] = {}
    weighted_results: List[float] = []

    expected_dish = expectation.get("expected_dish")
    if expected_dish:
        checks["dish_match"] = expected_dish in answer
        weighted_results.append(1.0 if checks["dish_match"] else 0.0)

    required_terms = expectation.get("required_terms", [])
    if required_terms:
        checks["required_terms"] = _contains_all(answer, required_terms)
        weighted_results.append(1.0 if checks["required_terms"] else 0.0)

    required_terms_any = expectation.get("required_terms_any", [])
    if required_terms_any:
        checks["required_terms_any"] = _contains_any(answer, required_terms_any)
        weighted_results.append(1.0 if checks["required_terms_any"] else 0.0)

    forbidden_terms = expectation.get("forbidden_terms", [])
    if forbidden_terms:
        checks["forbidden_terms"] = _contains_none(answer, forbidden_terms)
        weighted_results.append(1.0 if checks["forbidden_terms"] else 0.0)

    response_policy = expectation.get("response_policy")
    if response_policy:
        inferred_policy = _infer_response_policy(answer)
        checks["policy_match"] = inferred_policy == response_policy
        weighted_results.append(1.0 if checks["policy_match"] else 0.0)

    score = sum(weighted_results) / len(weighted_results) if weighted_results else 0.0
    passed = score >= 0.75 and all(checks.values())

    return {
        "score": round(score, 4),
        "passed": passed,
        "checks": checks,
        "policy_detected": _infer_response_policy(answer),
    }
