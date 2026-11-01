import os
from pathlib import Path

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = "https://ws-s00wtjjrfhr26ld0.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
CHAT_MODEL= "qwen3-max"
EMBEDDING_MODEL = "text-embedding-v3"
RERANK_MODEL= "gte-rerank"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT_ROOT / "index_data"
CHROMA_DIR = INDEX_DIR / "chroma"
BM25_FILE = INDEX_DIR / "bm25_corpus.json"

