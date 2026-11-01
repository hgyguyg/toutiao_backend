from openai import AsyncOpenAI, APIStatusError, APIConnectionError, APITimeoutError

from config.qa_conf import OPENAI_API_KEY, RERANK_BASE_URL, RERANK_MODEL

_client = None

class RerankUnavailable(Exception):
    """重排不可用（缺 key / 网络 / 鉴权 / 额度），调用方应退回 RRF 顺序。"""
    pass

def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RerankUnavailable("未配置 OPENAI_API_KEY")
        _client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=RERANK_BASE_URL,
            timeout=10.0,
            max_retries=1,
        )
    return _client

async def rerank_documents(question,documents):
    if not documents:
        return []
    if not question:
        raise RerankUnavailable("question 为空")

    docs = [d or " " for d in documents]
    try:
        response = await _get_client().post(
            "/reranks",
            body={
                "model": RERANK_MODEL,
                "query": question,
                "documents": docs,
                "top_n": 5,
            },
            cast_to=object
        )
    except APIStatusError as exc:
        raise RerankUnavailable(f"HTTP {exc.status_code}: {str(exc.body)[:120]}") from exc
    except (APITimeoutError, APIConnectionError) as exc:
        raise RerankUnavailable(f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        raise RerankUnavailable(f"{type(exc).__name__}: {exc}") from exc

    out = []
    resp = response or {}
    items = resp.get("results")
    if items is None:  # 兼容另一种可能的嵌套形态
        items = (resp.get("output") or {}).get("results") or []
    for item in items:
        idx, score = item.get("index"), item.get("relevance_score")
        if isinstance(idx, int) and 0 <= idx < len(documents) and score is not None:
            out.append({"index": idx, "score": float(score)})
    out.sort(key=lambda x:x.get("score"),reverse= True)
    return out[:5]