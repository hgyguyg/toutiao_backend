import json

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from schemas.qa import AskRequest
from utils.response import success_response
from utils.retriever import HybridRetriever
from utils.graph import get_checkpointer, answer_question, get_graph

router = APIRouter(prefix="/api/qa", tags=["qa"])

# 回放一个会话时最多往回翻多少个 checkpoint（一轮问答会产生多条快照）
MAX_REPLAY_CHECKPOINTS = 120


def _decode_checkpoint(saver, type_: str, blob: bytes) -> dict:
    """把一行 msgpack 解成 dict。解不开就返回空，不让一条脏数据拖垮整个列表。"""
    try:
        data = saver.serde.loads_typed((type_, blob))
    except Exception:  # noqa: BLE001 - 历史数据里混着旧类型，序列化告警不该中断接口
        return {}
    return data if isinstance(data, dict) else {}


def _replay_messages(decoded: list[dict]) -> list[dict]:
    """按 question 变化切轮次，每轮取最后一条带答案的快照，拼成 user/assistant 交替的对话。

    state 里的 history 只保留最近几轮，想要整段对话只能回到 checkpoint 里捞。
    同一轮会产生多条快照（改写前/检索后/作答后各一条），所以必须先按 question 归并。
    """
    rounds: list[dict] = []
    for item in decoded:
        values = item.get("channel_values") or {}
        question = (values.get("question") or "").strip()
        if not question:
            continue
        answer = values.get("answer") or ""
        if rounds and rounds[-1]["question"] == question:
            if answer:
                rounds[-1]["answer"] = answer
        else:
            rounds.append({"question": question, "answer": answer})

    messages: list[dict] = []
    for item in rounds:
        messages.append({"role": "user", "content": item["question"]})
        if item["answer"]:
            messages.append({"role": "assistant", "content": item["answer"]})
    return messages


@router.get("/health")
async def health_check():
    retriever = HybridRetriever.get()
    return success_response(
        "问答服务状态",
        {
            "index_ready": retriever.ready,
            "chunks": retriever.count,
            "memory": get_checkpointer() is not None,
        }
    )


@router.post("/ask", response_class=EventSourceResponse)
async def ask(req: AskRequest):
    # ChatMessage 是 pydantic 对象，下游 nodes 用 msg.get("role") 读，
    # 必须先 model_dump 成 dict，否则一轮对话就会降级成 'ChatMessage' object has no attribute 'get'
    history = (
        [m.model_dump() for m in req.history]
        if "history" in req.model_fields_set
        else None
    )
    thread_id = req.thread_id or ""

    try:
        async for event, data in answer_question(
            req.question, history, thread_id
        ):
            yield ServerSentEvent(
                event=event,
                # raw_data 原样输出，绕开 fastapi 内部 json.dumps 的 ensure_ascii=True
                raw_data=json.dumps(data, ensure_ascii=False, default=str)
            )

    except Exception as exc:  # noqa: BLE001 - 流内异常无法改状态码，改用 error 事件
        yield ServerSentEvent(
            event="error",
            raw_data=json.dumps({"message": str(exc)}, ensure_ascii=False, default=str)
        )


@router.get("/sessions")
async def qa_sessions(limit: int = 50):
    """左侧会话列表：thread_id + 首问标题 + 最后活动时间。

    checkpointer 只存 checkpoint，没有“会话表”，所以会话列表直接从 checkpoints 里算。
    checkpoint_id 是 UUIDv7，字典序就是时间序，ORDER BY 它即“最后活动时间倒序”。
    """
    saver = get_checkpointer()
    conn = getattr(saver, "conn", None) if saver is not None else None
    if conn is None:
        return success_response("会话列表", {"sessions": [], "memory": False})

    limit = max(1, min(int(limit), 200))
    sessions: list[dict] = []
    try:
        # saver.lock 是 AsyncSqliteSaver 自己的互斥锁，直接读它的 conn 必须拿着，
        # 否则会和 aget_state / aput 抢同一个 sqlite 连接
        async with saver.lock:
            cur = await conn.execute(
                "SELECT thread_id, COUNT(*) AS n, MAX(checkpoint_id) AS cid "
                "FROM checkpoints "
                "WHERE thread_id != '' AND checkpoint_ns = '' "
                "GROUP BY thread_id ORDER BY cid DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()

            for thread_id, total, _cid in rows:
                # 标题：最早几条里第一个非空 question（首条快照通常还没写入 question）
                title = ""
                cur_first = await conn.execute(
                    "SELECT type, checkpoint FROM checkpoints "
                    "WHERE thread_id = ? AND checkpoint_ns = '' "
                    "ORDER BY checkpoint_id ASC LIMIT 5",
                    (thread_id,),
                )
                for type_, blob in await cur_first.fetchall():
                    values = _decode_checkpoint(saver, type_, blob).get("channel_values") or {}
                    question = (values.get("question") or "").strip()
                    if question:
                        title = question
                        break

                # 最后活动时间：最后一条快照里的 ts（UTC ISO 字符串）
                updated_at = ""
                cur_last = await conn.execute(
                    "SELECT type, checkpoint FROM checkpoints "
                    "WHERE thread_id = ? AND checkpoint_ns = '' "
                    "ORDER BY checkpoint_id DESC LIMIT 1",
                    (thread_id,),
                )
                row = await cur_last.fetchone()
                if row:
                    updated_at = _decode_checkpoint(saver, row[0], row[1]).get("ts") or ""

                sessions.append(
                    {
                        "thread_id": thread_id,
                        "title": title or thread_id,
                        "updated_at": updated_at,
                        "checkpoints": total,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取会话列表失败：{exc}") from exc

    return success_response("会话列表", {"sessions": sessions, "memory": True})


@router.get("/history/{thread_id}")
async def qa_history(thread_id: str):
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = await get_graph().aget_state(cfg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取会话失败：{exc}") from exc
    values = snapshot.values or {}

    # 回放整段对话：state.history 只留最近几轮，完整记录在 checkpoint 里
    messages: list[dict] = []
    saver = get_checkpointer()
    conn = getattr(saver, "conn", None) if saver is not None else None
    if conn is not None:
        try:
            async with saver.lock:
                cur = await conn.execute(
                    "SELECT type, checkpoint FROM checkpoints "
                    "WHERE thread_id = ? AND checkpoint_ns = '' "
                    "ORDER BY checkpoint_id DESC LIMIT ?",
                    (thread_id, MAX_REPLAY_CHECKPOINTS),
                )
                decoded = [_decode_checkpoint(saver, t, b) for t, b in await cur.fetchall()]
            decoded.reverse()
            messages = _replay_messages(decoded)
        except Exception:  # noqa: BLE001 - 回放失败不该让整条会话打不开
            messages = []

    if not messages:
        # 回放不出东西时退回 state.history，至少别让页面空白
        messages = [
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in (values.get("history") or [])
            if isinstance(item, dict)
        ]

    return success_response(
        "会话记录",
        {
            "thread_id": thread_id,
            "history": values.get("history", []),
            "messages": messages,
            "answer": values.get("answer", ""),
            "route": values.get("route", ""),
            "status": values.get("status", ""),
        },
    )


@router.delete("/thread/{thread_id}")
async def qa_clear_thread(thread_id: str):
    saver = get_checkpointer()
    if saver is None:
        return success_response("会话记忆未启用", {"thread_id": thread_id, "cleared": False})
    try:
        await saver.adelete_thread(thread_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"清除会话失败：{exc}") from exc
    return success_response("会话已清除", {"thread_id": thread_id, "cleared": True})
