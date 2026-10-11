from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import news, users, favorite,history
from utils.exception_handler import register_exception_handler

app = FastAPI()
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

#把前端页面挂到根路径，直接访问 http://127.0.0.1:8000/ 即可使用。
#这样页面与接口同源，不受 CORS 限制，也不用再单独起一个静态服务器。
#注意：直接双击 index.html（file:// 协议）打开时浏览器 Origin 为 null，仍会被 CORS 拦截。
FRONTEND_DIR = Path(__file__).parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")