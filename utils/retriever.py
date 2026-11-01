import json
import threading

import chromadb
import jieba
from rank_bm25 import BM25Okapi

from config.qa_conf import BM25_FILE, CHROMA_DIR
from utils.embeddings import embed_question

COLLECTION_NAME = "news_chunks"

def tokenize(text: str) -> list[str]:
    return [w for w in jieba.lcut(text or "") if w.strip()]

class HybridRetriever:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.ready = False
        self.count = 0
        self._chunks: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._tokenized: list[list[str]] = []
        self._bm25: BM25Okapi | None = None
        self._collection = None
        self._load()

    def _load(self):
        if not BM25_FILE.exists():
            return
        payload = json.loads(BM25_FILE.read_text(encoding="utf-8"))
        self._chunks = payload["chunks"]
        self._by_id = {c["id"]: c for c in self._chunks}
        self._tokenized = [tokenize(c["text"]) for c in self._chunks]
        self._bm25 = BM25Okapi(self._tokenized)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._collection = client.get_collection(COLLECTION_NAME)
        self.count = self._collection.count()
        self.ready = True

    async def _search(self, question: str):
        if not self.ready:
            return []
        question = (question or "").strip()
        if not question:
            return []
        lexical = self._lexical(question)
        vector = await self._vector(question)
        return self._rrf(lexical, vector)

    def _lexical(self,question:str):
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(question))
        ranked = sorted(range(len(scores)),key= lambda x: float(scores[x]),reverse=True)
        return [
            self._chunks[i]["id"]
            for i in ranked[:20]
            if float(scores[i]) > 0
        ]

    async def _vector(self,question):
        if self._collection is None:
            return []
        embedding = await embed_question(question)
        result = self._collection.query(
            query_embeddings=embedding,
            n_results=20,
        )
        ids = result.get("ids") or []
        return ids[0] if ids else []

    def fold_by_news(self,chunks_ids):
        best_rank = {}
        chunks_of = {}
        for rank,chunk_id in enumerate(chunks_ids,start=1):
            chunk = self._by_id.get(chunk_id)
            if not chunk:
                continue
            news_id = (chunk.get("metadata") or {}).get("news_id")
            if news_id is None:
                continue
            news_id = int(news_id)
            best_rank.setdefault(news_id, rank)
            chunks_of.setdefault(news_id, []).append(chunk_id)
        return best_rank,chunks_of

    def _rrf(self,lexical,vector):
        lex_rank,lex_chunks = self.fold_by_news(lexical)
        vec_rank,vec_chunks = self.fold_by_news(vector)

        scores = {}
        for rank_map in (lex_rank,vec_rank):
            for news_id,rank in rank_map.items():
                scores[news_id] = scores.get(news_id,0.0) + 1.0 / (60 + float(rank))

        ordered = sorted(scores.items(),key= lambda x:x[1],reverse=True)[:10]

        hits = []
        for news_id,score in ordered:
            merged = []
            for chunk_id in lex_chunks.get(news_id,[]) + vec_chunks.get(news_id,[]):
                if chunk_id not in merged:
                    merged.append(chunk_id)

            if not merged:
                continue

            meta = self._by_id.get(merged[0], {}).get("metadata") or {}

            text = "\n".join(
                [self._by_id.get(chunk_id, {}).get("text") for chunk_id in merged]
            )
            hits.append({
                "id": merged[0],
                "news_id": news_id,
                "text": text,
                "title": meta.get("title", ""),
                "category_id": meta.get("category_id"),
                "publish_time": meta.get("publish_time", ""),
                "url": f"/api/news/detail?id={news_id}",
                "score": round(score, 6),
                "chunk_ids": merged,
            })
        return hits

