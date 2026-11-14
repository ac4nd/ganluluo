"""配额数据层（M5-admin Task 2，吸收 M3.5 Task 1）：档位限额、当日用量聚合、用量流水、档位种子。"""

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quota import LlmUsage, QuotaTier

# 档位行缺失时的兜底限额（与 trial 同值）：quota_tiers 空表时 get_status 不得放行无限额请求
FALLBACK_DAILY_CHATS = 5
FALLBACK_DAILY_TOKENS = 20000


@dataclass
class QuotaStatus:
    daily_chats_used: int
    daily_chats_limit: int
    daily_tokens_used: int
    daily_tokens_limit: int
    allowed: bool


async def get_status(session: AsyncSession, user_id: int, tier: str) -> QuotaStatus:
    """当日（本地日期）llm_usage 聚合 vs 档位限额；档位缺失用 trial 限额兜底。"""
    row = (await session.execute(select(QuotaTier).where(QuotaTier.tier == tier))).scalar_one_or_none()
    chats_limit = row.daily_chats if row else FALLBACK_DAILY_CHATS
    tokens_limit = row.daily_tokens if row else FALLBACK_DAILY_TOKENS
    # 当日口径：created_at >= 本地今日 00:00。record_usage 显式存本地时间（见其 docstring），
    # 两处口径自洽；上 PG 统一 UTC/时区处理后再整体切换。
    day_start = datetime.combine(date.today(), time.min)
    stmt = select(func.count(), func.coalesce(func.sum(LlmUsage.total_tokens), 0)).where(
        LlmUsage.user_id == user_id,
        LlmUsage.created_at >= day_start,
    )
    counts = (await session.execute(stmt)).one()
    chats_used = int(counts[0])
    tokens_used = int(counts[1])
    return QuotaStatus(
        daily_chats_used=chats_used,
        daily_chats_limit=chats_limit,
        daily_tokens_used=tokens_used,
        daily_tokens_limit=tokens_limit,
        # allowed = 两维度均未超限（恰好等于限额也算超）
        allowed=chats_used < chats_limit and tokens_used < tokens_limit,
    )


async def record_usage(
    session: AsyncSession, user_id: int, session_id: str, model: str, pt: int, ct: int
) -> None:
    """写一条 llm_usage 流水（total = pt + ct），随即提交。"""
    # created_at 显式传本地 naive 时间、覆盖 server_default func.now()：SQLite 下 func.now()
    # 产 UTC，而 get_status 按“本地今日 00:00”比较；北京时间 0-8 点窗口内 UTC 时间戳会落
    # 在“昨日”导致当天用量漏计。写读同用本地时钟保证口径自洽（未来上 PG/UTC 时统一，见报告）。
    session.add(
        LlmUsage(
            user_id=user_id,
            session_id=session_id,
            model=model,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=pt + ct,
            created_at=datetime.now(),
        )
    )
    await session.commit()


# 档位种子（M3.5 计划原文数值）；seed_tiers 只补缺不覆盖，幂等
_TIERS: dict[str, tuple[int, int, str]] = {
    "trial": (5, 20000, "试用档"),
    "vip": (50, 500000, "VIP 档"),
}


async def seed_tiers(session: AsyncSession) -> int:
    """确保 trial/vip 档位行存在（已存在则跳过），返回本次新建行数。"""
    try:
        existing = set(await session.scalars(select(QuotaTier.tier)))
        created = 0
        for tier, (chats, tokens, desc) in _TIERS.items():
            if tier in existing:
                continue
            session.add(QuotaTier(tier=tier, daily_chats=chats, daily_tokens=tokens, description=desc))
            created += 1
        await session.commit()
        return created
    except IntegrityError:
        # 并发首注册竞态：两进程同时对空表 INSERT 同主键档位行，输者在 flush/commit
        # 期撞唯一约束。吞错 + 回滚保证幂等（对手进程已建行，本侧按 0 新建计），
        # 否则 IntegrityError 上抛会被 auth/router 的注册 409 分支误捕（此时用户行
        # 已在 seed_tiers 之前建成，造成"注册失败但用户已存在"）。
        await session.rollback()
        return 0
