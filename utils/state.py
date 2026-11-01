"""LangGraph 状态定义。"""
import operator
from typing import Annotated, Any, TypedDict

from langgraph.types import Overwrite


class QAState(TypedDict, total=False):
    # 输入
    question: str
    history: list[dict]  # [{"role": "user"|"assistant", "content": str}]
    top_k: int
    thread_id: str  # 会话 ID（由 checkpointer 的 thread_id 透传，便于 trace 溯源）

    # 模块一
    rewritten: str

    # 模块二
    intent: str  # direct | web | kb
    intent_reason: str
    web_hits: list[dict]  # [{"title","url","snippet"}]

    # 模块三
    kb_hits: list[dict]  # [{"id","text","title","news_id","url","score","publish_time","chunk_ids","category_id"}]

    # 模块四
    sufficient: bool
    judge_reason: str

    # 输出
    answer: str
    sources: list[dict]
    route: str  # 最终实际走的路径
    status: str  # ok | degraded | failed
    degraded: bool  # 是否发生过降级
    error: str
    trace: Annotated[list[dict], operator.add]

    # 内部
    meta: dict[str, Any]


def initial_state(
    question: str,
    history: list[dict] | None = None,
    thread_id: str = "",
) -> dict:
    state: dict = {
        "question": question,
        "thread_id": thread_id,
        # ---- 瞬时字段：必须显式清零，否则上一轮的结果会串进本轮 ----
        "rewritten": "",
        "intent": "",
        "intent_reason": "",
        "web_hits": [],
        "kb_hits": [],
        "sufficient": False,
        "judge_reason": "",
        "answer": "",
        "sources": [],
        "route": "",
        "status": "ok",
        "degraded": False,
        "error": "",
        # ---- reducer 字段：只有 Overwrite 才能真清空 ----
        "trace": Overwrite([]),
    }
    if history is not None:
        state["history"] = list(history)
    return state
