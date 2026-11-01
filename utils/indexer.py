import asyncio
import json
import re
from datetime import datetime

import chromadb
from sqlalchemy import text as sql_text

from config.db_conf import AsyncSessionLocal

from config.qa_conf import BM25_FILE, CHROMA_DIR,INDEX_DIR
from .embeddings import embed_texts

COLLECTION_NAME = "news_chunks"


def chunk_text(
    content: str,
    max_chars: int = 500,
    overlap: int = 100,
) -> list[str]:
    """按句切块，块间保留少量重叠，避免上下文被切断。"""
    content = (content or "").strip()
    if not content:
        return []
    if len(content) <= max_chars:
        return [content]

    sentences = [s for s in re.split(r"(?<=[。！？!?；;\n])", content) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current.strip())
            current = (current[-overlap:] + sentence) if overlap else sentence
        else:
            current += sentence
    if current.strip():
        chunks.append(current.strip())
    return chunks


async def fetch_news() -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                sql_text(
                    "SELECT id, title, description, content, category_id, publish_time "
                    "FROM news ORDER BY id"
                )
            )
        ).all()
    return [dict(row._mapping) for row in rows]


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


async def build_index(limit: int | None = None) -> dict:
    news = await fetch_news()
    if limit:
        news = news[:limit]
    if not news:
        raise RuntimeError("新闻表为空，无法建索引")

    chunks: list[dict] = []
    for item in news:
        title = _to_text(item.get("title")).strip()
        description = _to_text(item.get("description")).strip()
        content = _to_text(item.get("content")).strip()
        full_text = "\n".join(x for x in (title, description, content) if x)
        for idx, piece in enumerate(chunk_text(full_text)):
            chunks.append(
                {
                    "id": f"news_{item['id']}_{idx}",
                    "text": piece,
                    "metadata": {
                        "news_id": int(item["id"]),
                        "title": title,
                        "category_id": int(item.get("category_id") or 0),
                        "publish_time": _to_text(item.get("publish_time")),
                        "chunk_index": idx,
                    },
                }
            )

    if not chunks:
        raise RuntimeError("切块结果为空，无法建索引")

    print(f"[1/3] 共 {len(news)} 条新闻，切出 {len(chunks)} 个块，开始向量化……")
    texts = [c["text"] for c in chunks]
    vectors = await embed_texts(texts)
    print(f"[2/3] 向量化完成，写入 Chroma：{CHROMA_DIR}")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=texts,
        embeddings=vectors,
        metadatas=[c["metadata"] for c in chunks],
    )

    payload = {
        "model": "text-embedding-v3",
        "count": len(chunks),
        "chunks": chunks,
    }
    BM25_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"[3/3] BM25 语料已保存：{BM25_FILE}")
    return {"news": len(news), "chunks": len(chunks)}


def main() -> None:
    result = asyncio.run(build_index())
    print(f"建索引完成：新闻 {result['news']} 条，切块 {result['chunks']} 个")


if __name__ == "__main__":
    main()
