import re
from json import JSONDecoder, JSONDecodeError

from openai import AsyncOpenAI

from config.qa_conf import OPENAI_API_KEY, BASE_URL, CHAT_MODEL

_client = None

SYSTEM_PROMPT = (
    "你是「今日头条」风格新闻平台的智能问答助手。回答要求："
    "①只依据提供的资料作答，资料不足就明确说明，不编造；"
    "②引用资料时用 [编号] 标注来源；"
    "③用简洁、准确的中文回答，条理清晰。"
)

def extract_json(text):
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    decoder = JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
            if isinstance(obj, dict):
                return obj
        except JSONDecodeError:
            start = text.find("{", start + 1)
    return None

def get_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=BASE_URL,
            timeout=60,
            max_retries=2
        )
    return _client

async def chat(prompt,system=None,temperature = 0.0):
    response = await get_client().chat.completions.create(
        messages=[
            {"role": "system", "content": system or SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        model=CHAT_MODEL,
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()

async def chat_json(prompt,system=None,temperature = 0.0):
    messages = [
        {"role": "system", "content": system or SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    for use_json_mode in [True,False]:
        try:
            kwargs = {
                "model": CHAT_MODEL,
                "messages": messages,
                "temperature": temperature,
            }
            if use_json_mode:
                kwargs["response_format"] = {"type":"json_object"}
            response = await get_client().chat.completions.create(**kwargs)
            data = extract_json(response.choices[0].message.content or "")
            if data is not None:
                return data
        except Exception as e:
            if not use_json_mode:
                raise
    return {}

async def chat_stream(prompt,system=None,temperature = 0.0,on_token = None):
    messages = [
        {"role": "system", "content": system or SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    stream = await get_client().chat.completions.create(
        messages=messages,
        model=CHAT_MODEL,
        temperature=temperature,
        stream=True
    )
    chunks = []
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if not delta:
            continue
        chunks.append(delta)
        if on_token is not None:
            on_token(delta)

    return "".join(chunks).strip()