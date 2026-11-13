"""澄清状态机：意图判定、槽位抽取、追问决策。"""

import re
from datetime import date, timedelta

from app.assistant.clarify_schemas import ClarifyState

PLAN_KEYWORDS = ("推荐", "规划", "想去", "走一条", "安排")
INFO_KEYWORDS = ("怎么", "是什么", "攻略", "介绍")

SPORT_KEYWORDS: dict[str, str] = {
    "徒步": "hiking",
    "爬山": "hiking",
    "越野跑": "trail-running",
    "骑行": "cycling",
    "露营": "camping",
    "滑雪": "skiing",
    "溯溪": "stream",
    "攀岩": "climbing",
    "定向": "orienteering",
}

# 种子路线地区词表（ROUTES 地区匹配用）
REGION_KEYWORDS = (
    "雨崩", "虎跳峡", "五台山", "太行", "武功山", "徽杭", "梅里", "迪庆", "香格里拉",
    "山西", "河南", "江西", "安徽", "浙江", "云南",
)

DATE_RE = re.compile(r"周六|周日|周末|周[一二三四五]?|明天|后天|\d{1,2}月\d{1,2}[日号]")
LENGTH_RE = re.compile(r"(\d{1,3})\s*(?:km|公里|千米)")
SKIP_KEYWORDS = ("随便", "都行", "无所谓", "推荐", "推荐就好", "你定")

# 追问顺序：sport > region > date
SLOT_PRIORITY = ("sport", "region", "date")
MAX_ROUNDS = 3

CLARIFY_QUESTIONS: dict[str, tuple[str, list[str]]] = {
    "sport": ("想做哪类运动？", ["徒步", "越野跑", "骑行", "露营", "滑雪"]),
    "region": ("想去哪个地区？", ["云南 迪庆", "山西 五台山", "河南 南太行", "江西 武功山"]),
    "date": ("大概哪天出发？", ["本周六", "本周日"]),
}


def detect_intent(text: str) -> str:
    """关键词意图判定：plan（推荐/规划类）> info（问答类）> chat。"""
    if any(k in text for k in PLAN_KEYWORDS):
        return "plan"
    if any(k in text for k in INFO_KEYWORDS):
        return "info"
    return "chat"


_WEEKDAY_NUM: dict[str, int] = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}


def _date_token(text: str) -> str | None:
    """文本中的第一个日期词（明天/后天/周X/周末/M月D日）；无 → None。

    extract_slots 存槽位原文，parse_date_text 负责转具体日期，共用同一抽取。
    """
    return m.group(0) if (m := DATE_RE.search(text)) else None


def _next_weekday(today: date, target: int) -> date:
    """今天（含）起下一个 target 星期（0=周一）。"""
    return today + timedelta(days=(target - today.weekday()) % 7)


def parse_date_text(text: str) -> date | None:
    """把文本中的日期词解析为具体日期；无日期词或无法确定 → None。

    明天/后天 → 今天偏移；周X/周末 → 今天（含）起下一个对应日；
    M月D日 → 今年，已过则顺延一年；裸"周"、非法月日 → None。
    """
    token = _date_token(text)
    if token is None:
        return None
    today = date.today()
    if token == "明天":
        return today + timedelta(days=1)
    if token == "后天":
        return today + timedelta(days=2)
    if token == "周末":
        return _next_weekday(today, 5)  # 周末按周六
    if token.startswith("周") and token[-1] in _WEEKDAY_NUM:
        return _next_weekday(today, _WEEKDAY_NUM[token[-1]])
    if (m := re.fullmatch(r"(\d{1,2})月(\d{1,2})[日号]", token)) is not None:
        try:
            parsed = date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:  # 如 2月30日
            return None
        if parsed < today:  # 今年已过 → 明年同月日
            try:
                parsed = date(today.year + 1, int(m.group(1)), int(m.group(2)))
            except ValueError:  # 如今年 2月29日、明年非闰年
                return None
        return parsed
    return None  # 裸"周"无法确定星期


def extract_slots(text: str, state: ClarifyState) -> ClarifyState:
    """从用户消息抽取槽位，返回新状态（不改动入参；round_no 由调用方推进）。"""
    slots = dict(state.slots)
    for keyword, sport in SPORT_KEYWORDS.items():
        if keyword in text:
            slots["sport"] = sport
            break
    for region in REGION_KEYWORDS:
        if region in text:
            slots["region"] = region
            break
    if (date_token := _date_token(text)) is not None:
        slots["date"] = date_token
    if m := LENGTH_RE.search(text):
        slots["length"] = m.group(1)
    if any(k in text for k in SKIP_KEYWORDS):
        slots["skip"] = "1"
    return state.model_copy(update={"slots": slots})


def next_clarification(state: ClarifyState) -> dict[str, object] | None:
    """plan 意图且缺槽且未超轮数上限且未 skip 时，按优先级返回下一个追问。"""
    if state.slots.get("skip"):
        return None
    if state.intent != "plan":
        return None
    missing = [s for s in SLOT_PRIORITY if s not in state.slots and s not in state.asked]
    if not missing or state.round_no >= MAX_ROUNDS:
        return None
    slot = missing[0]
    question, options = CLARIFY_QUESTIONS[slot]
    return {"slot": slot, "question": question, "options": options}
