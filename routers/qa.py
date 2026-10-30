from fastapi import APIRouter
from fastapi.sse import EventSourceResponse

from schemas.qa import AskRequest
from utils.response import success_response
from utils.retriever import HybridRetriever
from utils.graph import _checkpointer

router = APIRouter(prefix="/api/qa", tags=["qa"])
@router.get("/health")
async def health_check():
    retriever = HybridRetriever.get()
    return success_response(
        "问答服务状态",
        {
            "index_ready": retriever.ready,
            "chunks": retriever.count,
            "memory": _checkpointer is not None,
        }
    )
@router.post("/ask")
async def ask(req: AskRequest):
    history = [m.model_dump() for m in req.history] or None
    thread_id = req.thread_id or ""

    async def event_source():
        pass

    return EventSourceResponse(event_source())