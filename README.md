# 今日头条风格新闻平台 · 后端

基于 **FastAPI + SQLAlchemy 2.0（异步）+ Redis** 的新闻资讯后端服务，实现用户注册登录、新闻浏览、收藏与浏览历史等功能。
前端为单文件原生页面，已由后端静态挂载到根路径，打开即用。

## 技术栈

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI 0.142（自带 OpenAPI 文档） |
| 数据库 | MySQL 8 + SQLAlchemy 2.1 异步 ORM（aiomysql 驱动） |
| 缓存 | Redis 8（缓存穿透 / 击穿 / 雪崩防护） |
| 密码存储 | passlib + bcrypt |
| 前端 | 原生 HTML/CSS/JS 单文件，无构建步骤 |

## 快速开始

### 1. 环境准备

需要 Python 3.11+、MySQL 8、Redis。

```bash
# 安装依赖
pip install -r requirements.txt
```

### 2. 配置数据库

修改 `config/db_conf.py` 中的 `SQL_PASSWORD` 为你的 MySQL 密码，并创建数据库：

```sql
CREATE DATABASE news_app DEFAULT CHARSET utf8mb4;
```

表结构由 SQLAlchemy ORM 模型定义（`models/` 目录，共 5 张表）：
`user`、`user_token`、`news_category`、`news`、`favorite`、`history`。

可自行手写建表语句，或临时用下面的方式自动建表：

```python
from config.db_conf import async_engine
from models import *  # 确保所有模型都已导入

async def create():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# 或直接在 Python 交互式环境执行 asyncio.run(create())
```

至少需要插入一条 `news_category` 分类数据，否则分类接口返回空列表。

### 3. 启动

```bash
uvicorn main:app --reload
```

访问：

- **应用首页**：http://127.0.0.1:8000/
- **接口文档**：http://127.0.0.1:8000/docs （Swagger UI，可直接调试 17 个接口）

## 项目结构

```
.
├── main.py              # 应用入口：路由注册、CORS、静态文件挂载
├── config/              # 配置层
│   ├── db_conf.py           # 数据库引擎、会话依赖
│   └── redis_conf.py        # Redis 客户端 + 原子操作封装
├── models/              # SQLAlchemy ORM 模型（数据库表定义）
│   ├── users.py     # user / user_token
│   ├── news.py      # news_category / news
│   ├── favorite.py  # favorite
│   └── history.py   # history
├── schemas/            # Pydantic 数据校验（请求体 / 响应体）
├── crud/               # 数据访问层：数据库读写 + 缓存编排
├── routers/            # 接口层：路由、参数校验、依赖注入
├── cache/              # 缓存层：通用封装 + 各模块缓存键管理
│   ├── base_cache.py       # 缓存读写统一入口
│   ├── news_cache.py
│   ├── user_cache.py
│   ├── favorite_cache.py
│   └── history_cache.py
├── utils/              # 工具层：响应封装、异常处理、鉴权、密码哈希
└── frontend/
    └── index.html      # 前端单文件页面
```

采用**分层架构**，每一层职责单一、依赖单向向下：
`routers → crud → (models | cache | config)`。接口层不直接碰数据库，缓存逻辑集中在 crud 层编排，避免业务代码里散落 Redis 调用。

## 接口一览

统一响应体格式为 `{"code": 200, "message": "...", "data": {...}}`，异常由全局处理器保证同一结构。

### 新闻 `/api/news`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/categories` | 分类列表 |
| GET | `/list` | 分页新闻列表（按分类） |
| GET | `/detail` | 新闻详情，浏览量自增 |

### 用户 `/api/users`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/register` | 注册 |
| POST | `/login` | 登录，返回令牌 |
| GET | `/info` | 当前用户资料（需鉴权） |
| PUT | `/update` | 修改资料（需鉴权） |
| PUT | `/password` | 修改密码（需鉴权） |

### 收藏 `/api/favorite`（均需鉴权）

`GET /check`、`POST /add`、`GET /list`、`DELETE /remove`、`DELETE /clear`

### 历史 `/api/history`（均需鉴权）

`POST /add`、`GET /list`、`DELETE /delete/{history_id}`、`DELETE /clear`

## 实现要点

### 缓存：cache-aside + 三重防护

所有读操作经`cache/base_cache.py` 的 `get_or_set_cache_data()` 统一入口，避免各处重复造轮子。

- **缓存穿透**：查询无结果时写入空值占位符 `{"__empty__": "list"|"none"}`（TTL 60s），区分列表与单对象两种形态，保证回源后返回类型一致
- **缓存击穿**：热点键失效时用 `SET NX EX` 抢互斥锁，只有持锁者回源数据库重建，未抢到者等待后重试（3次 × 50ms）
- **缓存雪崩**：TTL 在基础值上叠加 0~20% 随机偏移，避免大批键同时失效
- **按前缀批量删除**：用 `SCAN` 游标分批（每批 200 个）而非 `KEYS`，避免遍历全库阻塞 Redis

### 缓存与写操作的一致性

写操作触发对应缓存失效。其中浏览量自增做了特殊处理：**原地更新缓存中的 views 并保留剩余 TTL**，而不是删缓存——否则每次浏览都让列表缓存失效，缓存就失去意义了。

### 鉴权

令牌为 UUID，存于 `user_token` 表并在 Redis 中缓存（TTL 1800s）。请求经`Authorization: Bearer <token>` 头传递，由 `utils/auth.py` 解析。
**缓存 TTL 不长于令牌有效期**，避免令牌已过期但缓存仍返回用户。

密码使用 bcrypt 哈希存储，任何环节都不存明文。

### 异常处理

`utils/exception_handler.py` 注册全局处理器，所有异常统一转为三段式响应体，前端只需判断 `code` 字段。

## 已知问题

- `config/db_conf.py` 中数据库密码为硬编码，仅适用于本地开发。对外分享前请改用环境变量注入（见下方）。
- 新闻列表接口返回下划线命名字段（`category_id`、`publish_time`），而收藏/历史/详情接口返回驼峰别名，前后端需要分别处理。
- 后端无"全部分类"聚合接口，前端不渲染"全部"标签。

## 安全建议

若需将本项目公开到 GitHub，请先把 `config/db_conf.py` 的密码改为从环境变量读取，并确保 `.env` 已被 `.gitignore` 排除。
