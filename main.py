from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config.qa_conf import CKPT_DB
from routers import news, users, favorite, history, qa
from utils.exception_handler import register_exception_handler
from utils.graph import set_checkpointer

@asynccontextmanager
async def lifespan(app: FastAPI):
    """把 checkpointer 的生命周期绑到应用上。

    AsyncSqliteSaver 内部用 asyncio.get_running_loop()，必须在事件循环内构造；
    而且 async with 一退出连接就关闭，所以不能写 `with ... as saver` 用完即走，
    必须由 lifespan 在整个应用运行期持有。
    """
    CKPT_DB.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(CKPT_DB)) as saver:
        set_checkpointer(saver)
        try:
            yield
        finally:
            set_checkpointer(None)

#接口文档改用本地静态资源。FastAPI 默认的 /docs 从 jsdelivr CDN 取 swagger-ui-bundle.js，
#网络不稳定或 CDN 被墙时页面会白屏并报 "SwaggerUIBundle is not defined"。
#这里把两个静态文件下载到 frontend/vendor/，改用 get_swagger_ui_html 指过去，彻底离线可用。
FRONTEND_DIR = Path(__file__).parent / "frontend"
VENDOR_DIR = FRONTEND_DIR / "vendor"
LOCAL_DOCS = (VENDOR_DIR / "swagger-ui-bundle.js").exists()

#关掉内置 /docs，否则它先注册、会挡住下面自定义的那条路由
app = FastAPI(lifespan=lifespan, docs_url=None if LOCAL_DOCS else "/docs")

#前端页面与接口不同源时会被浏览器拦截，这里显式声明允许的来源
#开发期前端跑在 5500 端口，localhost 与 127.0.0.1 都要列出（浏览器按实际访问地址匹配）
#生产环境应改为具体域名，不要用通配符
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000", "http://127.0.0.1:8000",
        "http://localhost:5500", "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#注册全局异常处理器
register_exception_handler(app)
app.include_router(news.router)
app.include_router(users.router)
app.include_router(favorite.router)
app.include_router(history.router)
app.include_router(qa.router)

#把前端页面挂到根路径，直接访问 http://127.0.0.1:8000/ 即可使用。
#这样页面与接口同源，不受 CORS 限制，也不用再单独起一个静态服务器。
#注意：直接双击 index.html（file:// 协议）打开时浏览器 Origin 为 null，仍会被 CORS 拦截。
#FRONTEND_DIR / VENDOR_DIR / LOCAL_DOCS 已在文件上方定义（供 docs_url 判断使用）。
if LOCAL_DOCS:
    from fastapi.openapi.docs import get_swagger_ui_html

    @app.get("/docs", include_in_schema=False)
    async def local_docs():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - 接口文档",
            swagger_js_url="/vendor/swagger-ui-bundle.js",
            swagger_css_url="/vendor/swagger-ui.css",
        )
else:
    # 本地资源缺失时退回 FastAPI 默认行为（走 CDN）。若网络不通会白屏，
    # 此时把 swagger-ui-bundle.js / swagger-ui.css 放进 frontend/vendor/ 即可。
    print(
        f"[warn] 未找到 {VENDOR_DIR / 'swagger-ui-bundle.js'}，/docs 将回退到 CDN，"
        "内网或 CDN 不通时页面会白屏。"
    )

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    # 直接运行 `python main.py`（含 IDE 里的绿色运行按钮）也能起服务。
    # 没有这一段时，import 完就结束，进程静默退出，看起来像是"运行了但没有接口"。
    import os

    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )