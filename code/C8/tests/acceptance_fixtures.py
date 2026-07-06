from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langchain_core.documents import Document

from main import RecipeRAGSystem
from rag_modules.context_packer import ContextPacker
from rag_modules.conversation_manager import ConversationManager
from rag_modules.retrieval_executor import RetrievalExecutor


RECIPE_DOCS: dict[str, str] = {
    "宫保鸡丁": (
        "# 宫保鸡丁的做法\n\n"
        "## 必备原料和工具\n\n"
        "- 鸡腿肉\n- 花生\n- 干辣椒\n- 豆瓣酱可选\n\n"
        "## 操作\n\n"
        "1. 鸡肉切丁腌制。\n2. 先炒鸡丁，再加入调味汁。\n3. 最后放花生。\n\n"
        "## 附加内容\n\n"
        "- 不吃辣可以减少干辣椒，用甜椒补香味。\n"
        "- 没有豆瓣酱时可用少量生抽、醋和糖调味。\n"
    ),
    "香菇滑鸡": (
        "# 香菇滑鸡的做法\n\n"
        "## 必备原料和工具\n\n"
        "- 鸡腿肉\n- 香菇\n- 姜片\n\n"
        "## 操作\n\n"
        "1. 鸡肉腌制。\n2. 香菇炒香。\n3. 合炒后小火焖熟。\n\n"
        "## 附加内容\n\n"
        "- 口味温和，不辣。\n"
    ),
    "可乐鸡翅": (
        "# 可乐鸡翅的做法\n\n"
        "## 必备原料和工具\n\n"
        "- 鸡翅\n- 可乐\n- 生抽\n\n"
        "## 操作\n\n"
        "1. 鸡翅煎上色。\n2. 加可乐和生抽焖煮。\n3. 收汁。\n\n"
        "## 附加内容\n\n"
        "- 甜口，不辣。\n"
    ),
    "番茄炒蛋": (
        "# 番茄炒蛋的做法\n\n"
        "## 必备原料和工具\n\n"
        "- 番茄\n- 鸡蛋\n\n"
        "## 操作\n\n"
        "1. 先炒鸡蛋。\n2. 再炒番茄出汁。\n3. 合炒调味。\n"
    ),
}


def _chunk(dish_name: str, content_type: str = "general", **metadata: Any) -> Document:
    return Document(
        page_content=f"{dish_name} {content_type}",
        metadata={
            "dish_name": dish_name,
            "parent_id": f"{dish_name}-parent",
            "content_type": content_type,
            **metadata,
        },
    )


class AcceptanceRetrievalModule:
    def __init__(self):
        self.last_search_trace: dict[str, Any] = {}

    def extract_filters_from_query(self, query: str) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if "不辣" in query or "不放辣" in query:
            filters["taste"] = "不辣"
        if "鸡" in query:
            filters["ingredient"] = "鸡"
        return filters

    def metadata_filtered_search(
        self,
        query: str,
        filters: dict[str, Any],
        top_k: int = 3,
        query_dish: str | None = None,
    ):
        self.last_search_trace = {
            "method": "metadata_filtered_search",
            "query": query,
            "filters": dict(filters),
            "query_dish": query_dish,
        }
        if "不存在的菜" in query or query_dish == "不存在的菜":
            return []

        dish_name = filters.get("dish_name") or query_dish
        if dish_name:
            if dish_name not in RECIPE_DOCS:
                return []
            return [_chunk(dish_name, filters.get("content_type", "general"))]

        if filters.get("taste") == "不辣":
            return [
                _chunk("香菇滑鸡", "general"),
                _chunk("可乐鸡翅", "general"),
            ][:top_k]

        if filters.get("ingredient") == "鸡" or "鸡" in query:
            return [
                _chunk("宫保鸡丁", "general"),
                _chunk("香菇滑鸡", "general"),
                _chunk("可乐鸡翅", "general"),
            ][:top_k]

        return [_chunk("番茄炒蛋", "general")][:top_k]

    def hybrid_search(self, query: str, top_k: int = 3, query_dish: str | None = None):
        self.last_search_trace = {
            "method": "hybrid_search",
            "query": query,
            "query_dish": query_dish,
        }
        if "不存在的菜" in query or query_dish == "不存在的菜":
            return []
        if query_dish and query_dish in RECIPE_DOCS:
            return [_chunk(query_dish, "general")]
        if "鸡" in query:
            return [
                _chunk("宫保鸡丁", "general"),
                _chunk("香菇滑鸡", "general"),
                _chunk("可乐鸡翅", "general"),
            ][:top_k]
        return [_chunk("番茄炒蛋", "general")][:top_k]


class AcceptanceDataModule:
    def get_parent_documents(self, chunks, target_dish_name: str | None = None):
        dishes: list[str] = []
        if target_dish_name:
            dishes.append(target_dish_name)
        for chunk in chunks:
            dish_name = (chunk.metadata or {}).get("dish_name")
            if dish_name and dish_name not in dishes:
                dishes.append(dish_name)

        return [
            Document(
                page_content=RECIPE_DOCS[dish_name],
                metadata={
                    "dish_name": dish_name,
                    "parent_id": f"{dish_name}-parent",
                    "rrf_score": 1.0,
                },
            )
            for dish_name in dishes
            if dish_name in RECIPE_DOCS
        ]


class AcceptanceGenerationModule:
    def __init__(self):
        self.conversation_manager = ConversationManager()
        self.last_generation_trace: dict[str, Any] = {}
        self.llm = None

    def resolve_query_reference(self, query, session_id):
        return query

    def query_router(self, query: str) -> dict[str, Any]:
        if "推荐" in query or "换个" in query:
            filters = {}
            if "鸡" in query:
                filters["ingredient"] = "鸡"
            if "不辣" in query or "不放辣" in query:
                filters["taste"] = "不辣"
            return {"type": "list", "filters": filters, "dish_name": None, "confidence": 0.95}

        dish_name = None
        for name in RECIPE_DOCS:
            if name in query:
                dish_name = name
                break
        if "不存在的菜" in query:
            dish_name = "不存在的菜"

        content_type = "steps"
        if "豆瓣酱" in query or "替代" in query or "不放辣" in query:
            content_type = "tips"
        if "材料" in query or "食材" in query:
            content_type = "ingredients"

        return {
            "type": "detail",
            "filters": {"content_type": content_type},
            "dish_name": dish_name,
            "confidence": 0.95,
        }

    def get_current_entity(self, session_id):
        return self.conversation_manager.get_current_entity(session_id)

    def _classify_query_guardrail(self, query):
        return None

    def query_rewrite(self, query):
        return query

    def _dish_names(self, context_docs):
        names: list[str] = []
        for doc in context_docs:
            name = (doc.metadata or {}).get("dish_name")
            if name and name not in names:
                names.append(name)
        return names

    def generate_smalltalk_answer(self, query: str) -> str:
        self.last_generation_trace = {"strategy": "smalltalk"}
        return "不客气，继续想做菜也可以问我。"

    def generate_list_answer(self, query, context_docs):
        names = self._dish_names(context_docs)
        self.last_generation_trace = {"strategy": "list", "dishes": names}
        return "为你推荐：\n" + "\n".join(f"{index + 1}. {name}" for index, name in enumerate(names))

    def generate_step_by_step_answer(self, query, context_docs, content_type=None):
        names = self._dish_names(context_docs)
        joined = "\n".join(doc.page_content for doc in context_docs)
        self.last_generation_trace = {
            "strategy": "detail",
            "dishes": names,
            "content_type": content_type,
        }
        if "豆瓣酱" in query:
            return f"{names[0]}可以不用豆瓣酱，改用生抽、醋和糖。" if names else "可以换成生抽、醋和糖。"
        if "不放辣" in query:
            return f"{names[0]}可以少放或不放辣椒。" if names else "可以不放辣椒。"
        if names:
            return f"{names[0]}做法：{joined[:120]}"
        return "知识库里没有找到可靠的食谱信息。"

    def generate_step_by_step_answer_stream(self, query, context_docs, content_type=None):
        text = self.generate_step_by_step_answer(query, context_docs, content_type=content_type)
        for part in [text[:10], text[10:]]:
            if part:
                yield part

    def generate_basic_answer(self, query, context_docs, content_type=None):
        return self.generate_step_by_step_answer(query, context_docs, content_type=content_type)

    def generate_basic_answer_stream(self, query, context_docs, content_type=None):
        yield self.generate_basic_answer(query, context_docs, content_type=content_type)


def build_acceptance_system() -> RecipeRAGSystem:
    system = RecipeRAGSystem.__new__(RecipeRAGSystem)
    system.config = SimpleNamespace(
        top_k=3,
        context_pack_max_chars_total=2400,
        context_pack_max_chars_per_doc=1200,
        context_pack_max_docs=5,
    )
    system.data_module = AcceptanceDataModule()
    system.retrieval_module = AcceptanceRetrievalModule()
    system.retrieval_executor = RetrievalExecutor(system.retrieval_module)
    system.context_packer = ContextPacker(
        max_chars_total=system.config.context_pack_max_chars_total,
        max_chars_per_doc=system.config.context_pack_max_chars_per_doc,
        max_docs=system.config.context_pack_max_docs,
    )
    system.generation_module = AcceptanceGenerationModule()
    system._latest_parent_docs = []
    system.last_query_diagnostics = {}
    system.last_execution_result = {}
    return system


def ask_and_trace(system: RecipeRAGSystem, question: str, *, session_id: str, stream: bool = False):
    answer = system.ask_question(question, stream=stream, session_id=session_id)
    if stream:
        answer = "".join(list(answer))
    result = dict(system.last_execution_result or {})
    query_plan = {
        "route_type": result.get("route_type"),
        "filters": result.get("filters", {}),
        "dish_name": result.get("dish_name"),
    }
    if result.get("retrieval_query_plan"):
        query_plan["retrieval_query_plan"] = result["retrieval_query_plan"]
    if result.get("retrieval_quality") and "retrieval_quality" not in query_plan:
        query_plan["retrieval_quality"] = result["retrieval_quality"]
    trace = {
        "query_plan": query_plan,
        "retrieval_quality": result.get("retrieval_quality") or {},
        "context_pack_trace": result.get("context_pack_trace") or {},
        "runtime": result.get("runtime") or {},
        "commit_result": result.get("commit_result") or result.get("writeback_result") or {},
        "answer_type": result.get("answer_type"),
    }
    return answer, trace
