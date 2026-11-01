import asyncio

from openai import OpenAI

from config.qa_conf import OPENAI_API_KEY, BASE_URL

_client = None

def embed_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY,base_url=BASE_URL,timeout=120,max_retries=2)
    return _client

def embed_texts_sync(texts):
    client = embed_client()
    vectors = []
    for i in range(0,len(texts),10):
        batch = texts[i:i+10]
        responses = client.embeddings.create(model="text-embedding-v3",input=batch)
        ordered = sorted(responses.data,key=lambda d: d.index)
        vectors.extend(d.embedding for d in ordered)
    return vectors

async def embed_texts(texts):
    return await asyncio.to_thread(embed_texts_sync,texts)

async def embed_question(question):
    vector = await asyncio.to_thread(embed_texts_sync, [question])
    return vector[0]