import time
from functools import wraps

from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp

MODULE_LABEL = {
    "rewrite": "模块一·问题改写",
    "classify": "模块二·分类路由",
    "direct_answer": "模块二·直接回答",
    "kb_retrieve": "模块三·混合检索",
    "extract": "模块四·信息提取",
    "judge": "模块五·充分性判断",
    "answer_kb": "模块五·知识库作答",
    "web_search": "模块二·网页搜索",
    "answer_web": "模块二·搜索作答",
    "persist": "收尾·写入历史",
}

def _emit(payload: dict) -> None:
    """向 custom 流推送一条事件；非流式路径下静默忽略。"""
    try:
        get_stream_writer()(payload)
    except Exception:  # noqa: BLE001 - 流式出口绝不能影响主流程
        pass

def _node(name):
    label = MODULE_LABEL.get(name,name)
    def deco(fn):
        @wraps(fn)
        async def wrapper(state):
            start = time.perf_counter()
            try:
                result = await fn(state)
                detail = result.pop("_detail","")
                ms = (time.perf_counter() - start) * 1000
                entry = {
                    "model": label,
                    "node": name,
                    "ok": True,
                    "ms": ms,
                    "detail": detail
                }
                result.setdefault("trace", [])
                result["trace"] = [entry] + list(result["trace"])
                _emit({"type": "node",**entry})
                return result
            except GraphBubbleUp:
                raise
            except Exception as e:
                ms = int((time.perf_counter() - start) * 1000)
                entry = {
                    "module": label,
                    "node": name,
                    "ok": False,
                    "ms": ms,
                    "detail": str(e)[:300],
                }
                _emit({"type": "node", **entry})
                return {
                    "degraded": True,
                    "error": f"{label}: {e}",
                    "trace": [entry],
                }
        return wrapper
    return deco

