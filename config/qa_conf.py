import os
from pathlib import Path

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = "https://ws-s00wtjjrfhr26ld0.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
CHAT_MODEL= "qwen-max"
EMBEDDING_MODEL = "text-embedding-v3"
RERANK_MODEL= "qwen3-rerank"
RERANK_BASE_URL= "https://ws-s00wtjjrfhr26ld0.cn-beijing.maas.aliyuncs.com/compatible-api/v1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT_ROOT / "index_data"
CHROMA_DIR = INDEX_DIR / "chroma"
BM25_FILE = INDEX_DIR / "bm25_corpus.json"
CKPT_DB = PROJECT_ROOT / "data" / "qa_memory.sqlite"

