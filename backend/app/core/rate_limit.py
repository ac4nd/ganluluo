"""共享限流组件（M6.5-polish I-6）：limiter 单例 + per-user 限流键。

limiter 从 app.main 模块级下移到 core：auth/assistant/media 三处 router 改从本
模块 import，消除 `from app.main import limiter` 的循环导入债。main.py 仍负责
挂 app.state.limiter 与 RateLimitExceeded → 429 handler（注册顺序保留）。

user_key：per-user 限流键——Bearer JWT 的 sub，解析失败回退客户端 IP；逻辑自
assistant/router._user_key 搬运（原函数已删除改 import，语义逐字不变）。
"""
import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.security import decode_token

# 登录 / assistant chat / 媒体登记共用同一 limiter（in-memory 存储；测试经
# conftest 的 limiter.reset() 每用例清零，保持用例顺序无关）
limiter = Limiter(key_func=get_remote_address)


def user_key(request: Request) -> str:
    """per-user 限流键：Bearer JWT 的 sub；解析失败回退客户端 IP。"""
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer "):
        try:
            sub = decode_token(auth[7:]).get("sub")
        except jwt.PyJWTError:
            sub = None
        if sub is not None:
            return str(sub)
    return request.client.host if request.client else "anon"
