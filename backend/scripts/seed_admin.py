"""管理员种子脚本：把 GL_ADMIN_EMAIL 指定的用户置为 is_admin=True（幂等）。

用法（在 backend/ 目录下）：
    python -m scripts.seed_admin
    GL_ADMIN_EMAIL=admin@example.com python -m scripts.seed_admin

行为（幂等，可重复执行）：
- GL_ADMIN_EMAIL 未配置     → stderr 提示 + 退出码 1
- 邮箱未注册（含已注销）    → stderr 提示 + 退出码 1（不静默建号）
- 已是管理员               → no-op 打印 + 退出码 0
- 普通用户                 → is_admin=True + commit + 打印
"""
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.user import User


async def _seed(email: str) -> int:
    engine = create_async_engine(get_settings().database_url)
    try:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None or user.deleted_at is not None:
                print(f"用户不存在：{email}（请先通过 /auth/register 注册）", file=sys.stderr)
                return 1
            if user.is_admin:
                print(f"no-op：{email} 已是管理员")
                return 0
            user.is_admin = True
            await session.commit()
            print(f"已将 {email} 设为管理员")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    email = get_settings().admin_email.strip()
    if not email:
        print("GL_ADMIN_EMAIL 未配置（.env 或环境变量），拒绝执行", file=sys.stderr)
        return 1
    return asyncio.run(_seed(email))


if __name__ == "__main__":
    raise SystemExit(main())
