import time
from functools import wraps

from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp

from utils import llm
from utils.llm import chat_stream
from utils.retriever import HybridRetriever
from utils.search import web_search

MODULE_LABEL = {
    "rewrite": "模块一·问题改写",
    "classify": "模块二·分类路由",
    "direct_answer": "模块二·直接回答",
    "kb_retrieve": "模块三·混合检索",
    "judge": "模块四·充分性判断",
    "answer_kb": "模块四·知识库作答",
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

def _token_emitter(event_type: str = "token"):
    """返回一个 on_token 回调，把增量文本包装成自定义事件。"""

    def on_token(text: str) -> None:
        _emit({"type": event_type, "text": text})

    return on_token

def _node(name):
    """返回一个节点装饰器，用于包装节点函数。"""
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
                    "model": label,
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

@_node("rewrite")
async def node_rewrite(state):
    """对用户问题进行改写，使其更适合检索。"""
    history = state.get("history") or []
    question = state.get("question","").strip()

    lines = []
    for msg in history[-6:]:
        role = "用户" if msg.get("role") == "user" else "助手"
        lines.append(f"{role}: {msg.get("content") or ""}")
    prompt = (
        "你是新闻平台的问答助手。请结合对话历史，把用户最新问题改写成一个独立、完整、"
        "适合检索的问题：补全省略的主语和指代，但不要改变原意、不要添加用户没问的内容。\n\n"
        "对话历史：\n" + "\n".join(lines) + f"\n\n最新问题：{question}\n\n"
        "只输出改写后的问题本身，不要解释。"
    )
    rewrite = (await llm.chat(prompt) or question).strip()
    return {
        "rewritten": rewrite,
        "_detail": f"改写为：{rewrite[:80]}"
    }

@_node("classify")
async def node_classify(state):
    """根据意图判断，决定问题的处理路径。"""
    question = state.get("rewritten") or state.get("question")
    prompt = (
        "你是新闻平台问答系统的路由器，只判断问题应该走哪条路径。\n"
        "路径定义：\n"
        "- direct：闲聊、通用常识，或仅凭对话历史即可回答，不需要检索新闻库、也不需要联网。\n"
        "- web：明确需要「此刻/今天」的实时信息（今天的新闻、天气、比分、股价、汇率），"
        "或站内新闻库几乎不可能覆盖的内容。\n"
        "- kb：问题与新闻事件、新闻中出现的人物/政策/产品/数据有关（包括历史事件），"
        "站内新闻库可以回答。\n\n"
        "判断原则：只要问题的答案可能存在于新闻库里，就选 kb；只有确实需要实时信息时才选 web。\n\n"
        "示例：\n"
        "- 「2023年我国GDP增长了多少」→ kb（站内新闻有该新闻）\n"
        "- 「美联储最近一次加息是什么时候」→ kb（新闻库覆盖）\n"
        "- 「今天天气怎么样」→ web（实时信息）\n"
        "- 「你好，你能做什么」→ direct（闲聊，无需检索）\n"
        "- 「刚才那条新闻具体讲了什么」→ kb（结合对话历史，站内新闻）\n\n"
        f"待判断问题：{question}\n\n"
        '只输出 JSON，格式：{"intent": "direct|web|kb", "reason": "一句话理由"}'
    )
    data = await llm.chat_json(prompt)
    raw = data.get("intent")
    intent = raw.lower().strip() if isinstance(raw, str) else ""
    if intent not in {"kb", "web", "direct"}:
        intent = "kb"
    if intent not in {"kb","web","direct"}:
        intent = "kb"
    return {
        "intent": intent,
        "intent_reason": data.get("reason",""),
        "_detail": f"意图：{intent}, 原因：{data.get('reason','')}"
    }

@_node("direct_answer")
async def node_direct_answer(state):
    """直接回答问题，不需要检索。"""
    question = state.get("rewritten") or state.get("question")
    history = state.get("history") or []
    history_block = ""
    if history:
        lines = []
        for msg in history[-6:]:
            role = "用户" if msg.get("role") == "user" else "助手"
            lines.append(f"{role}: {msg.get('content', '')}")
        history_block = "\n".join(lines)
    prompt = (f"对话历史：{history_block}"
              f"用户问题：{question}"
              f"请直接回答。如果信息不足或不确定，请明确说明，不要编造。")
    answer = await chat_stream(prompt=prompt,on_token=_token_emitter("answer_token"))
    return {
        "answer": answer,
        "sources":[],
        "_detail": "直接作答",
        "route": "direct"
    }

@_node("kb_retrieve")
async def node_kb_retrieve(state):
    """根据问题，从知识库中检索相关文档。"""
    question = state.get("rewritten") or state.get("question")
    retriever = HybridRetriever.get()
    if not retriever.ready:
        return {
            "kb_hits":[],
            "degraded": True,
            "_detail": "知识库检索未就绪，回退到网页检索",
        }
    hits = await retriever._search(question)
    return {
        "kb_hits": hits,
        "_detail": f"检索到 {len(hits)} 篇相关文档",
    }


@_node("judge")
async def node_judge(state):
    """判断检索结果是否足以回答问题。"""
    question = state.get("rewritten") or state.get("question")
    hits = state.get("kb_hits") or []

    candidates = "\n".join([hit.get("text") for hit in hits])

    prompt = (
        "你是答案质量审核员。请判断下面提取到的信息是否足以完整、准确地回答用户问题。\n"
        "信息足以回答主要问题 → sufficient 为 true；关键信息缺失（缺时间、缺数字、缺结论等）"
        "→ sufficient 为 false，并说明缺什么。\n\n"
        f"用户问题：{question}\n\n已提取信息：\n{candidates}\n\n"
        '只输出 JSON：{"sufficient": true, "reason": "判断理由"}'
    )

    data = await llm.chat_json(prompt)
    raw = data.get("sufficient")
    if isinstance(raw, str):
        sufficient = raw.strip().lower() in {"true", "yes", "1"}
    else:
        sufficient = bool(raw)

    kwargs = {"sufficient": data.get("sufficient"),"judge_reason": data.get("reason")}
    if sufficient:
        kwargs["_detail"] = "信息充分，请直接回答"
    else:
        kwargs.update({
            "_detail": f"信息不足，原因：{data.get('reason','')}",
            "degraded": True,
        })
    return kwargs

@_node("answer_kb")
async def node_answer_kb(state):
    """根据检索结果，生成答案。"""
    question = state.get("rewritten") or state.get("question")
    hits = state.get("kb_hits") or []
    candidates = "\n".join([hit.get("text") for hit in hits])
    prompt = (
        f"用户问题：{question}\n\n已提取的新闻信息：\n{candidates}\n\n"
        "请基于以上信息回答问题，引用时用 [编号] 标注来源。"
        "信息不足的部分明确说明，不要编造。"
    )
    sources = []
    answer = await chat_stream(prompt=prompt,on_token=_token_emitter("answer_token"))
    for idx, hit in enumerate(hits, start=1):
        sources.append(
            {
                "type": "news",
                "title": hit.get("title", ""),
                "url": hit.get("url", ""),
                "news_id": hit.get("news_id"),
            }
        )
    return {
        "answer": answer,
        "sources": sources,
        "route": "kb",
        "status": "degraded" if state.get("degraded") else "ok",
        "_detail": "基于知识库信息作答",
    }

@_node("web_search")
async def node_web_search(state):
    question = state.get("rewritten") or state.get("question")
    hits = await web_search(question)
    if not hits:
        return {
            "web_hits": [],
            "degraded": True,
            "status": "degraded",
            "_detail": "网页搜索无结果",
        }
    return {"web_hits": hits, "_detail": f"搜索到 {len(hits)} 条网页结果"}

@_node("answer_web")
async def node_answer_web(state):
    question = state.get("rewritten") or state.get("question")
    web_hits = state.get("web_hits") or []
    kb_hits = state.get("kb_hits") or []

    if not web_hits:
        return {
            "answer": "抱歉，我没有搜索到与这个问题相关的信息，暂时无法回答。",
            "sources": [],
            "route": "web",
            "status": "degraded",
            "degraded": True,
            "_detail": "搜索无结果，如实告知",
        }

    blocks = "\n\n".join(
        f"[{i}] {h['title']}\n{h['description']}" for i, h in enumerate(web_hits, start=1)
    )
    candidates = ""
    if kb_hits:
        candidates = "站内新闻库提取信息：" + "\n".join([hit.get("text") for hit in kb_hits])
    prompt = (
        f"用户问题：{question}\n\n网页搜索结果：\n{blocks}\n{candidates}\n\n"
        "请基于以上资料回答问题，引用时用 [编号] 标注。资料不足时明确说明。"
    )
    answer = await llm.chat_stream(prompt, on_token=_token_emitter("answer_token"))

    sources = [
        {"type": "web", "title": h["title"], "url": h["url"], "description": h["description"]}
        for h in web_hits
    ]
    if kb_hits:
        for hit in kb_hits:
            sources.append(
                {
                    "type": "news",
                    "title": hit.get("title", ""),
                    "url": hit.get("url", ""),
                    "news_id": hit.get("news_id"),
                }
            )

    route = "web" if state.get("intent") == "web" else "kb→web"
    return {
        "answer": answer,
        "sources": sources,
        "route": route,
        "status": "degraded" if state.get("degraded") else "ok",
        "_detail": f"基于 {len(web_hits)} 条网页结果作答",
    }

@_node("persist")
async def node_persist(state):
    """把本轮问答追加进 history，供下一轮改写模块做指代消解。"""
    history = list(state.get("history") or [])
    question = state.get("question", "")
    answer = state.get("answer", "")
    added = 0
    if question:
        history.append({"role": "user", "content": question})
        added += 1
    if answer:
        history.append({"role": "assistant", "content": answer})
        added += 1
    else:
        history.pop()  # 没答案就把刚加的 user 撤掉，保持成对
        added -= 1
    trimmed = history[-6:]
    return {
        "history": trimmed,
        "_detail": f"历史 {len(trimmed)} 条（本轮 +{added}）",
    }

def route_after_classify(state):
    return state.get("intent") or "kb"

def route_after_retrieve(state):
    return "web_search" if not state.get("kb_hits") else "judge"

def route_after_judge(state):
    return "answer_kb" if state.get("sufficient") else "web_search"