from app.schemas.clarify import ClarifyState
from app.services.clarify_service import detect_intent, extract_slots, next_clarification


def test_detect_intent_three_branches():
    # plan：含推荐/规划/想去/走一条/安排；info：含怎么/是什么/攻略/介绍；其余 chat
    assert detect_intent("推荐一条路线") == "plan"
    assert detect_intent("雨崩怎么走") == "info"
    assert detect_intent("你好") == "chat"


def test_extract_slots_fills_region_date_sport():
    state = ClarifyState(intent="plan", round_no=2)
    new_state = extract_slots("周六想去雨崩徒步", state)
    # 返回新对象，不改动入参；round_no 由调用方推进，此处保持不变
    assert new_state is not state
    assert state.slots == {} and state.round_no == 2
    assert new_state.slots["sport"] == "hiking"
    assert new_state.slots["region"] == "雨崩"
    assert new_state.slots["date"] == "周六"
    assert new_state.round_no == 2


def test_next_clarification_priority_sport_then_region():
    first = next_clarification(ClarifyState(intent="plan"))
    assert first == {
        "slot": "sport",
        "question": "想做哪类运动？",
        "options": ["徒步", "越野跑", "骑行", "露营", "滑雪"],
    }
    # sport 已填充后，下一轮优先追问 region
    second = next_clarification(
        ClarifyState(intent="plan", slots={"sport": "hiking"}, asked=["sport"])
    )
    assert second is not None
    assert second["slot"] == "region"
    assert second["question"] == "想去哪个地区？"
    assert second["options"] == ["云南 迪庆", "山西 五台山", "河南 南太行", "江西 武功山"]


def test_next_clarification_round_no_cap():
    assert next_clarification(ClarifyState(intent="plan", round_no=3)) is None


def test_next_clarification_skip_returns_none():
    assert next_clarification(ClarifyState(intent="plan", slots={"skip": "1"})) is None


def test_next_clarification_info_intent_returns_none():
    assert next_clarification(ClarifyState(intent="info")) is None


def test_extract_slots_recommend_skips():
    state = ClarifyState(intent="plan")
    new = extract_slots("推荐一条路线", state)
    assert new.slots.get("skip") == "1"
    assert next_clarification(new) is None
