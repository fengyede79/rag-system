from __future__ import annotations

import re
from dataclasses import dataclass


ALIAS_NORMALIZATION = {
    "拍黄瓜": "凉拌黄瓜",
    "番茄炒蛋": "西红柿炒鸡蛋",
    "番茄鸡蛋": "西红柿炒鸡蛋",
    "番茄炒鸡蛋": "西红柿炒鸡蛋",
}

REFERENCE_PREFIXES = (
    "这个",
    "这个菜",
    "这道",
    "这道菜",
    "那个",
    "那道",
    "那道菜",
    "它",
    "第一个",
    "第二个",
    "第三个",
    "第四个",
    "第五个",
    "那第一个",
    "那第二个",
    "那第三个",
    "刚才那个",
)

INTENT_SUFFIX_PATTERNS = (
    r"需要准备哪些配菜",
    r"需要准备什么",
    r"需要什么食材",
    r"需要什么材料",
    r"需要什么原料",
    r"需要什么配料",
    r"需要什么",
    r"有什么制作技巧",
    r"有什么小技巧",
    r"有什么技巧",
    r"有哪些配菜",
    r"有哪些食材",
    r"怎么不容易碎",
    r"怎么不粘锅",
    r"怎么炒更脆",
    r"怎么调味",
    r"怎么制作",
    r"怎么做",
    r"制作方法",
    r"制作步骤",
    r"做法",
    r"步骤",
    r"食材",
    r"材料",
    r"配料",
    r"技巧",
)


@dataclass(frozen=True)
class DishEntityExtraction:
    dish_candidate: str | None
    intent_suffix: str
    confidence: float
    extraction_reason: str


def _normalize_query(query: str) -> str:
    return query.strip().rstrip("?!？！。")


def _is_reference_like(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in REFERENCE_PREFIXES)


def _clean_candidate(candidate: str) -> str:
    cleaned = candidate.strip(" ，,。！？?的")
    cleaned = re.sub(r"^(请问|帮我看看|我想知道|想问下)", "", cleaned).strip(" ，,。！？?的")
    return cleaned


def _valid_candidate(candidate: str) -> bool:
    if not (2 <= len(candidate) <= 12):
        return False
    if any(token in candidate for token in ("怎么", "需要", "什么", "哪些", "这个", "那个", "第一个", "第二个")):
        return False
    return all("\u4e00" <= ch <= "\u9fff" for ch in candidate)


def _normalize_alias(candidate: str) -> tuple[str, bool]:
    normalized = ALIAS_NORMALIZATION.get(candidate)
    if normalized:
        return normalized, True
    return candidate, False


def extract_dish_entity_from_query(query: str) -> DishEntityExtraction:
    text = _normalize_query(query)
    if not text:
        return DishEntityExtraction(None, "", 0.0, "empty_query")
    if _is_reference_like(text):
        return DishEntityExtraction(None, "", 0.0, "reference_like_query")

    for suffix in sorted(INTENT_SUFFIX_PATTERNS, key=len, reverse=True):
        index = text.find(suffix)
        if index <= 0:
            continue
        raw_candidate = _clean_candidate(text[:index])
        if not _valid_candidate(raw_candidate):
            continue
        dish_candidate, alias_used = _normalize_alias(raw_candidate)
        return DishEntityExtraction(
            dish_candidate=dish_candidate,
            intent_suffix=text[index:],
            confidence=0.9,
            extraction_reason="intent_suffix_split_alias_normalized" if alias_used else "intent_suffix_split",
        )

    return DishEntityExtraction(None, "", 0.0, "no_intent_suffix_match")
