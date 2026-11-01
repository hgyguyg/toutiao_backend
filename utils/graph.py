import threading

from langgraph.graph import StateGraph

from utils.state import QAState

_checkpointer = None
graph = None

def get_checkpointer():
    return _checkpointer

def build_graph(checkpointer = None):
    graph = StateGraph(QAState)


def _config(thread_id: str):
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 30}

def get_graph():
    global graph
    if graph is None:
        with threading.Lock():
            if graph is None:
                pass

async def answer_question(
        question: str,
        history: list[dict] = None,
        thread_id: str = None,
        top_k: int = 6,
):
    pass