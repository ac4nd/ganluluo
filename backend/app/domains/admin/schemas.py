"""admin 域跨层共享契约：供 admin_router 与 assistant 层（用户侧配额查询）共用。"""
from pydantic import BaseModel


class UsageOut(BaseModel):
    chats_used: int
    tokens_used: int
    tier: str
    daily_chats_limit: int
    daily_tokens_limit: int
    allowed: bool
