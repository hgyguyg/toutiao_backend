from openai import AsyncOpenAI

from config.qa_conf import OPENAI_API_KEY, BASE_URL

_client = None

SYSTEM_PROMPT = (
    "你是「今日头条」风格新闻平台的智能问答助手。回答要求："
    "①只依据提供的资料作答，资料不足就明确说明，不编造；"
    "②引用资料时用 [编号] 标注来源；"
    "③用简洁、准确的中文回答，条理清晰。"
)

def get_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=BASE_URL,
            timeout=60,
            max_retries=2
        )

async def chat(prompt,system,temperature = 0.0):
    response = await get_client().chat.completion.create(
        messages=[
            {"role": "system", "content": system or SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        model="qwen3-max",
        temperature=0,
    )
    return (response.choices[0].message.content).strip()