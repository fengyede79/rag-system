"""Basic safety gate for the context-first turn pipeline.

This module only decides whether a query is structurally safe enough to enter
the context-aware runtime. It does not classify domain, smalltalk, recipes,
references, dishes, filters, routes, answer modes, or rewritten queries.
"""

from __future__ import annotations

import re
from typing import Dict


def _normalize(query: str) -> str:
    return query.strip()


def _is_empty_or_punctuation(text: str) -> bool:
    if not text:
        return True
    return re.fullmatch(r"[\s\W_]+", text) is not None


def _block(reason: str, message: str) -> Dict[str, str | None]:
    return {"decision": "block", "reason": reason, "message": message}


def _continue() -> Dict[str, str | None]:
    return {"decision": "continue", "reason": "default_continue", "message": None}


def basic_safety_gate(query: str) -> Dict[str, str | None]:
    """Return whether a query may enter context-aware turn understanding."""
    normalized = _normalize(query)
    if _is_empty_or_punctuation(normalized):
        return _block("empty_or_punctuation", "请输入一个具体的食谱或做菜问题。")
    return _continue()
