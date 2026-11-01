import threading

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from utils import nodes
from utils.state import QAState, initial_state

_checkpointer = None
_graph = None        # 带 checkpointer 的编译结果（多轮会话）
_graph_plain = None  # 无 checkpointer 的编译结果（一次性问答，绝不写盘）
_graph_lock = threading.Lock()

def set_checkpointer(saver) -> None:
    """注入 / 解除 checkpointer（由 main.py 的 lifespan 调用），并强制重编译两份图。"""
    global _checkpointer, _graph, _graph_plain
    _checkpointer = saver
    with _graph_lock:
        _graph = None
        _graph_plain = None

def get_checkpointer():
    return _checkpointer

def build_graph(checkpointer=None):
    graph = StateGraph(QAState)

    graph.add_node("rewrite", nodes.node_rewrite)
    graph.add_node("classify", nodes.node_classify)
    graph.add_node("direct_answer", nodes.node_direct_answer)
    graph.add_node("kb_retrieve", nodes.node_kb_retrieve)
    graph.add_node("judge", nodes.node_judge)
    graph.add_node("web_search", nodes.node_web_search)
    graph.add_node("answer_web", nodes.node_answer_web)
    graph.add_node("answer_kb", nodes.node_answer_kb)
    graph.add_node("persist", nodes.node_persist)

    graph.add_edge(START, "rewrite")
    graph.add_edge("rewrite", "classify")
    graph.add_conditional_edges(
        "classify",
        nodes.route_after_classify,
        {
            "direct": "direct_answer",
            "web": "web_search",
            "kb": "kb_retrieve",
        },
    )
    graph.add_conditional_edges(
        "kb_retrieve",
        nodes.route_after_retrieve,
        {"web_search": "web_search", "judge": "judge"},
    )

    graph.add_conditional_edges(
        "judge",
        nodes.route_after_judge,
        {"answer_kb": "answer_kb", "web_search": "web_search"},
    )
    # 三条作答路径都汇到收尾节点，由它统一维护 history
    graph.add_edge("direct_answer", "persist")
    graph.add_edge("answer_web", "persist")
    graph.add_edge("answer_kb", "persist")
    graph.add_edge("web_search", "answer_web")
    graph.add_edge("persist", END)
    return graph.compile(checkpointer=checkpointer)


def _config(thread_id: str):
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}

def get_graph(with_memory: bool = True):
    """带记忆版 / 无记忆版各缓存一个编译结果。

    无记忆版必须是真的不挂 checkpointer：只把 use_memory 当开关而不换图，
    LangGraph 依然会把这一轮写进 thread_id 指向的线程，匿名请求会互相串话。
    """
    global _graph, _graph_plain
    if with_memory:
        if _graph is None:
            with _graph_lock:
                if _graph is None:
                    _graph = build_graph(_checkpointer)
        return _graph
    if _graph_plain is None:
        with _graph_lock:
            if _graph_plain is None:
                _graph_plain = build_graph(None)
    return _graph_plain


def get_plain_graph():
    """无 checkpointer 的图：一次性问答用它，绝不产生 checkpoint。"""
    return get_graph(with_memory=False)

def _result(values: dict, question: str) -> dict:
    answer = values.get("answer", "")
    return {
        "answer": answer,
        "sources": values.get("sources", []),
        "route": values.get("route", ""),
        "status": "failed" if not answer else values.get("status", "ok"),
        "rewritten": values.get("rewritten") or question,
        "intent": values.get("intent", ""),
        "trace": values.get("trace") or [],
    }

async def answer_question(
        question: str,
        history: list[dict] = None,
        thread_id: str = None,
):
    """流式问答：产出 (event, data) 二元组，由 router 包成 SSE。

    事件类型：
      meta         会话建立（回带真正生效的 thread_id）
      node         某个模块执行完成（含耗时）
      answer_token 答案递增片段
      done         最终结果（含 sources / trace）
    """
    use_memory = bool(thread_id) and get_checkpointer() is not None
    state = initial_state(question, history, thread_id)
    config = _config(thread_id) if use_memory else {"recursion_limit": 30}
    graph = get_graph() if use_memory else get_plain_graph()

    yield "meta", {"thread_id": thread_id, "question": question}

    merged: dict = {}
    stream_kwargs = {"stream_mode": ["custom"] if use_memory else ["custom","updates"]}
    stream_kwargs["durability"] = "async"
    async for mode, chunk in graph.astream(state, config, **stream_kwargs):
        if mode == "custom":
            yield chunk.get("type", "token"), chunk
        elif mode == "updates":
            # trace 在真实状态里走 operator.add，这里必须同样追加而不是覆盖。
            for _node_name, patch in (chunk or {}).items():
                if not isinstance(patch, dict):
                    continue
                for key, val in patch.items():
                    if key == "trace":
                        merged["trace"] = list(merged.get("trace") or []) + list(val or [])
                    else:
                        merged[key] = val

    if use_memory:
        # 最终态从快照读：既能拿到完整 trace，也顺带确认 checkpoint 真的落盘了
        snapshot = await graph.aget_state(config)
        values = snapshot.values or {}
    else:
        values = merged
    yield "done", {"thread_id": thread_id, **_result(values, question)}