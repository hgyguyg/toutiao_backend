# 今日头条风格新闻平台 · 后端

基于 **FastAPI + SQLAlchemy 2.0（异步）+ Redis** 的新闻资讯后端服务，实现用户注册登录、新闻浏览、收藏与浏览历史，并内置一套**基于 LangGraph 的新闻问答模块**（混合检索 + 流式作答）。

前端为单文件原生页面，已由后端静态挂载到根路径，打开即用；问答页面采用左侧会话列表 + 右侧消息流 + 底部输入区的对话式布局。

## 技术栈

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI 0.142（自带 OpenAPI 文档，Swagger UI 已本地化） |
| 数据库 | MySQL 8 + SQLAlchemy 2.1 异步 ORM（aiomysql 驱动） |
| 缓存 | Redis 8（缓存穿透 / 击穿 / 雪崩防护） |
| 密码存储 | passlib + bcrypt |
| 检索 | Chroma 向量库 + rank-bm25 关键词检索，RRF 融合后用 qwen3-rerank 重排 |
| 问答编排 | LangGraph 1.2（九个节点的工作流 + SQLite checkpointer 持久化会话） |
| 模型接入 | OpenAI 兼容协议（原生 `openai` SDK，未引入 LangChain 封装） |
| 前端 | 原生 HTML/CSS/JS 单文件，无构建步骤 |

## 快速开始

### 1. 环境准备

需要 Python 3.11+、MySQL 8、Redis。

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

本项目**没有 `.env` 文件**，也没有引入 `load_dotenv()`，所有配置都从进程环境变量读取。缺 `DATABASE_PASSWORD` 时，`config/db_conf.py` 在导入阶段就会直接抛 `RuntimeError`（服务根本起不来）。

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `DATABASE_PASSWORD` | **是** | 无 | MySQL root 密码 |
| `OPENAI_API_KEY` | 问答模块必需 | 无 | 百炼兼容端点的 API Key；缺失时新闻/收藏等功能正常，问答会 401 |
| `APP_HOST` | 否 | `127.0.0.1` | 仅 `python main.py` 启动方式生效 |
| `APP_PORT` | 否 | `8000` | 同上 |

```powershell
# PowerShell（当前会话）
$env:DATABASE_PASSWORD = "你的 MySQL 密码"
$env:OPENAI_API_KEY   = "你的百炼 API Key"

# 永久写入用户级环境变量（需重开终端 / IDE 才生效）
[Environment]::SetEnvironmentVariable('DATABASE_PASSWORD', '你的密码', 'User')
```

> 注意：PyCharm 等 IDE 的运行配置会缓存启动时的环境变量快照。设完环境变量后必须**重启 IDE**，否则仍会报「缺少 DATABASE_PASSWORD 环境变量」。

创建数据库：

```sql
CREATE DATABASE news_app DEFAULT CHARSET utf8mb4;
```

表结构由 SQLAlchemy ORM 模型定义（`models/` 目录，共 **6 张表**）：
`user`、`user_token`、`news_category`、`news`、`favorite`、`history`。

可自行手写建表语句，或用下面的方式自动建表：

```python
# 每个 models/*.py 各自定义了一个 Base（DeclarativeBase），四个 Base 互相独立，
# 所以不能只用一个 Base.metadata.create_all —— 必须先把四份 metadata 汇总起来。
import asyncio

from sqlalchemy import MetaData

import models.users, models.news, models.favorite, models.history
from config.db_conf import async_engine


async def create():
    meta = MetaData()
    for mod in (models.users, models.news, models.favorite, models.history):
        for table in mod.Base.metadata.tables.values():
            if table.name not in meta.tables:
                table.to_metadata(meta)
    async with async_engine.begin() as conn:
        await conn.run_sync(meta.create_all)
    await async_engine.dispose()  # 不关连接池的话，脚本退出时会报 Event loop is closed


asyncio.run(create())
```

至少需要插入一条 `news_category` 分类数据，否则分类接口返回空列表。

### 3. 建检索索引（问答模块必需）

问答模块依赖 `index_data/` 下的向量库与 BM25 语料。**这两个目录不入库**（见 `.gitignore`），克隆后必须自行重建：

```bash
python -m utils.indexer
```

它从 MySQL 的 `news` 表读取全部新闻，切块 → 向量化 → 写入 `index_data/chroma/` 与 `index_data/bm25_corpus.json`，结束打印 `建索引完成：新闻 N 条，切块 M 个`。

- 切块参数：`chunk_text(content, max_chars=500, overlap=100)`，按 `。！？!?；;` 与换行切句
- 向量模型：`text-embedding-v3`（每批 10 条）
- 未建索引时 `GET /api/qa/health` 会返回 `index_ready: false`，问答会一路降级到联网检索

### 4. 启动

```bash
# 方式一（含 reload，等价于 uvicorn --reload）
python main.py

# 方式二
uvicorn main:app --reload
```

> **必须在项目根目录下运行。** 七个包目录（`config / models / schemas / crud / routers / cache / utils`）都没有 `__init__.py`，靠 namespace package 工作，换个工作目录会 `ModuleNotFoundError`。

访问：

- **应用首页**：http://127.0.0.1:8000/
- **问答页面**：http://127.0.0.1:8000/#/chat
- **接口文档**：http://127.0.0.1:8000/docs （Swagger UI，可直接调试全部 22 个接口）

> `/docs` 的 swagger-ui 资源已下载到 `frontend/vendor/`，**不依赖 CDN**，断网也能打开。若该目录缺失，`main.py` 会自动回退到 CDN 并打印 `[warn]`，此时网络不通会白屏并报 `SwaggerUIBundle is not defined`。

## 项目结构

```
.
├── main.py                   # 应用入口：lifespan、CORS、路由注册、/docs、静态挂载
├── config/
│   ├── db_conf.py            # 数据库引擎、会话依赖（强制 DATABASE_PASSWORD）
│   ├── qa_conf.py            # 问答模块配置：模型名、端点、索引路径、checkpoint 路径
│   └── redis_conf.py         # Redis 客户端 + 原子操作封装
├── models/                   # SQLAlchemy ORM 模型（6 张表）
│   ├── users.py              # user / user_token
│   ├── news.py               # news_category / news
│   ├── favorite.py           # favorite
│   └── history.py            # history
├── schemas/                  # Pydantic 数据校验
│   ├── qa.py                 # AskRequest / ChatMessage
│   └── ...                   # news / users / favorite / history
├── crud/                     # 数据访问层：数据库读写 + 缓存编排
├── routers/                  # 接口层
│   ├── news.py  users.py  favorite.py  history.py
│   └── qa.py                 # 问答：SSE 流式作答、会话列表、会话回放、会话清除
├── cache/                    # 缓存层
│   ├── base_cache.py         # 缓存读写统一入口（穿透/击穿/雪崩）
│   ├── news_cache.py  user_cache.py
│   └── favorite_cache.py  history_cache.py
├── utils/
│   ├── response.py           # 统一响应体
│   ├── exception.py          # 业务异常定义
│   ├── exception_handler.py  # 全局异常处理器
│   ├── auth.py  security.py  # 鉴权、bcrypt 哈希
│   ├── state.py              # QAState（LangGraph 状态定义）与 initial_state
│   ├── nodes.py              # 九个图节点 + @_node 装饰器（trace/降级）
│   ├── graph.py              # 图装配、双缓存编译、流式作答入口
│   ├── llm.py                # 原生 openai SDK：chat / chat_json / chat_stream
│   ├── embeddings.py         # 文本向量化（线程池包装同步 SDK）
│   ├── retriever.py          # 混合检索：BM25 + 向量 → RRF → rerank
│   ├── rerank.py             # qwen3-rerank 调用与降级
│   ├── search.py             # 联网检索：Bing RSS → ddgs 双路兜底
│   └── indexer.py            # 建索引入口（python -m utils.indexer）
└── frontend/
    ├── index.html            # 前端单文件页面（含问答视图）
    └── vendor/               # swagger-ui 本地资源（离线可用）
        ├── swagger-ui-bundle.js
        └── swagger-ui.css
```

采用**分层架构**，每一层职责单一、依赖单向向下：
`routers → crud → (models | cache | config)`。接口层不直接碰数据库，缓存逻辑集中在 crud 层编排，避免业务代码里散落 Redis 调用。

问答模块自成一条链路：`routers/qa.py → utils/graph.py → utils/nodes.py → (retriever | rerank | search | llm)`，与新闻业务共享同一份 MySQL 新闻数据，但走独立的 `index_data/` 索引。

## 接口一览

统一响应体格式为 `{"code": 200, "message": "...", "data": {...}}`，异常由全局处理器保证同一结构。
共 **22 个接口**，分 5 组。鉴权方式是 `Authorization: Bearer <token>` 请求头。

### 新闻 `/api/news`

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/categories` | `skip=0`、`limit=100` | 分类列表 |
| GET | `/list` | `categoryId`（必填）、`page=1`、`pageSize=10` | 分页新闻列表（按分类） |
| GET | `/detail` | `id`（必填） | 新闻详情，浏览量自增 |

### 用户 `/api/users`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/register` | 注册 |
| POST | `/login` | 登录，返回令牌 |
| GET | `/info` | 当前用户资料（需鉴权） |
| PUT | `/update` | 修改资料（需鉴权） |
| PUT | `/password` | 修改密码（需鉴权） |

### 收藏 `/api/favorite`（均需鉴权）

| 方法 | 路径 | 参数 |
|---|---|---|
| GET | `/check` | `newsId` |
| POST | `/add` | body |
| DELETE | `/remove` | `newsId` |
| GET | `/list` | `page`、`pageSize` |
| DELETE | `/clear` | — |

### 历史 `/api/history`（均需鉴权）

| 方法 | 路径 | 参数 |
|---|---|---|
| POST | `/add` | body |
| GET | `/list` | `page=1`、`pageSize=10` |
| DELETE | `/delete/{history_id}` | — |
| DELETE | `/clear` | — |

### 问答 `/api/qa`

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/health` | — | 服务状态：`{index_ready, chunks, memory}` |
| POST | `/ask` | body `AskRequest` | **SSE 流式作答**，见下节 |
| GET | `/sessions` | `limit=50` | 左侧会话列表（thread_id + 首问标题 + 最后活动时间） |
| GET | `/history/{thread_id}` | — | 会话详情：回放出的完整 `messages` + 末轮 `answer`/`route`/`status` |
| DELETE | `/thread/{thread_id}` | — | 清除某会话的 checkpoint |

## 问答模块

### 工作流拓扑

九个节点，两条降级分支（知识库答不了就联网）：

```
START → rewrite → classify
                     ├─ direct → direct_answer ─┐
                     ├─ web ───→ web_search ────┤
                     └─ kb ───→ kb_retrieve     │
                                  ├─ (无召回) → web_search
                                  └─ judge
                                       ├─ (充分) → answer_kb ─┐
                                       └─ (不充分) → web_search
                                                                ↓
                                                             persist → END
```

| 节点 | 职责 |
|---|---|
| `rewrite` | 结合最近 6 条历史把问题改写成独立可检索的句子 |
| `classify` | 判定意图：`direct` / `web` / `kb` |
| `direct_answer` | 闲聊类直接作答（不检索） |
| `kb_retrieve` | 混合检索知识库，写入 `kb_hits` |
| `judge` | 判断召回内容是否足以回答 |
| `answer_kb` | 基于知识库片段作答，标注来源编号 |
| `web_search` | 联网检索（Bing RSS → ddgs 双路兜底） |
| `answer_web` | 基于网页结果作答 |
| `persist` | 把本轮问答追加进 `history`（保留最近 6 条） |

每个节点都用 `@_node` 装饰器包了一层，负责三件事：记录 `trace`（模块名 / 耗时 / 是否成功 / 摘要）、异常降级、把状态推给 SSE 流。`trace` 会随 `done` 事件一起返回，前端据此展示"哪一步做了什么、花了多久"。

### SSE 事件契约

`POST /api/qa/ask` 返回 `text/event-stream`（`response_class=EventSourceResponse`），帧分隔符是 `\n\n`。

| 事件 | data 结构 |
|---|---|
| `meta` | `{thread_id, question}` |
| `node` | `{type, model, node, ok, ms, detail}` |
| `answer_token` | `{type, text}` —— 增量文本，逐 token 推送 |
| `done` | `{thread_id, answer, sources, route, status, rewritten, intent, trace}` |
| `error` | `{message}` |

请求体（`AskRequest`）：

| 字段 | 类型 | 约束 | 别名 | 说明 |
|---|---|---|---|---|
| `question` | str | 1–500 字 | — | 用户问题 |
| `history` | ChatMessage[] | ≤40 条 | — | 不传则由 checkpointer 承继 |
| `top_k` | int | 1–20，默认 6 | `topK` | 知识库召回条数 |
| `thread_id` | str \| None | ≤64 字 | `threadId` | 会话 ID，不传则单轮无记忆 |

`ChatMessage` 为 `{role: "user"|"assistant", content: str}`。

> **前端不能用原生 `EventSource`**：它只支持 GET、无法携带请求体。必须用 `fetch` + `response.body.getReader()` 手动分帧。
> `data:` 行里的中文由服务端 `raw_data=json.dumps(..., ensure_ascii=False)` 直接输出，不是 `\uXXXX` 转义。

### 会话记忆

- 传了 `threadId` 且 checkpointer 可用时，LangGraph 会把每轮状态写入 `data/qa_memory.sqlite`，下一轮自动继承上下文
- 不传 `threadId` 则走无记忆的单轮模式（每次都是全新的 state）
- `data/` 目录不入库（含真实对话内容），首次启动时自动创建

会话列表没有独立的会话表，直接从 `checkpoints` 表算出来：`checkpoint_id` 是 UUIDv7，字典序即时间序，`ORDER BY checkpoint_id DESC` 就是"最后活动时间倒序"。

### 检索链路

```
问题
 ├─ BM25（jieba 分词，rank-bm25）        ─┐
 └─ 向量（Chroma，text-embedding-v3）    ─┴→ RRF 融合（k=60）→ 候选 10 条
                                            → qwen3-rerank 重排（top_n=5）
                                            → 返回 5 条
```

- 两路各召回 20 条，按 `news_id` 折叠后 RRF 融合（`score += 1/(60+rank)`）
- 重排调用 `POST {RERANK_BASE_URL}/reranks`，请求体是扁平结构 `{model, query, documents, top_n}`，响应取 `results[]` 的 `{index, relevance_score}`
- **重排失败自动降级**：接口报错或返回空列表时退回 RRF 的候选前 5 条，不会因为重排挂掉就返回空

### 模型配置

见 `config/qa_conf.py`：

| 常量 | 当前值 | 说明 |
|---|---|---|
| `CHAT_MODEL` | `qwen-max` | 对话模型。`qwen3-max` 在百炼兼容端点会 404 |
| `EMBEDDING_MODEL` | `text-embedding-v3` | 向量模型 |
| `RERANK_MODEL` | `qwen3-rerank` | 重排模型。`gte-rerank` 已下线 |
| `BASE_URL` | `.../compatible-mode/v1` | 对话与向量端点 |
| `RERANK_BASE_URL` | `.../compatible-api/v1` | 重排端点（注意是 `api` 不是 `mode`） |

## 实现要点

### 缓存：cache-aside + 三重防护

所有读操作经 `cache/base_cache.py` 的 `get_or_set_cache_data()` 统一入口，避免各处重复造轮子。

- **缓存穿透**：查询无结果时写入空值占位符 `{"__empty__": "list"|"none"}`（TTL 60s），区分列表与单对象两种形态，保证回源后返回类型一致
- **缓存击穿**：热点键失效时用 `SET NX EX` 抢互斥锁，只有持锁者回源数据库重建，未抢到者等待后重试（3 次 × 50ms）
- **缓存雪崩**：TTL 在基础值上叠加 0~20% 随机偏移，避免大批键同时失效
- **按前缀批量删除**：用 `SCAN` 游标分批（每批 200 个）而非 `KEYS`，避免遍历全库阻塞 Redis

### 缓存与写操作的一致性

写操作触发对应缓存失效。其中浏览量自增做了特殊处理：**原地更新缓存中的 views 并保留剩余 TTL**，而不是删缓存——否则每次浏览都让列表缓存失效，缓存就失去意义了。

### 鉴权

令牌为 UUID，存于 `user_token` 表并在 Redis 中缓存（TTL 1800s）。请求经 `Authorization: Bearer <token>` 头传递，由 `utils/auth.py` 的 `get_current_user` 解析。
**缓存 TTL 不长于令牌有效期**，避免令牌已过期但缓存仍返回用户。

密码使用 bcrypt 哈希存储，任何环节都不存明文。

### 异常处理

`utils/exception_handler.py` 注册全局处理器，所有异常统一转为三段式响应体，前端只需判断 `code` 字段。

### 流式输出为什么要绕一层

`fastapi` 内置的 SSE 编码用 `json.dumps(...)`，默认 `ensure_ascii=True`，中文会变成 `\u4f60\u597d` 这样的转义序列。`routers/qa.py` 里改用 `ServerSentEvent(raw_data=...)`，`raw_data` 会被原样写入帧，配合 `json.dumps(..., ensure_ascii=False, default=str)` 才能输出可读中文（体积也小约 30%）。

## 已知问题

- 新闻列表接口返回下划线命名字段（`category_id`、`publish_time`），而收藏/历史/详情接口返回驼峰别名，前后端需要分别处理。
- 后端无"全部分类"聚合接口，前端不渲染"全部"标签。
- `utils/retriever.py` 的检索入口是私有方法 `_search`，被 `utils/nodes.py` 直接调用；按约定应改成公开的 `search`。
- `utils/auth.py:14` 用 `authorization.split()[1]` 取令牌，请求头格式不规范（缺 `Bearer` 前缀）时会抛 `IndexError`，返回 500 而不是 401。
- 问答模块目前串行执行九个节点，单次问答涉及 3~5 次模型调用，端到端耗时通常在 3~10 秒；`rewrite` 与 `classify` 在语义上可合并，是后续优化的首选。
