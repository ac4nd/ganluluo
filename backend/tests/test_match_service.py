from typing import ClassVar

from app.services.match_service import match_score


class FakeRoute:
    sport: ClassVar[str] = "hiking"
    difficulty: ClassVar[int] = 3
    required_gear: ClassVar[list[str]] = ["boots", "poles", "headlamp"]


def test_full_match_100():
    profile = {"sports": ["hiking"], "fitness": 3}
    assert match_score(profile, FakeRoute(), {"boots", "poles", "headlamp"}) == 100


def test_fitness_gap_penalty():
    profile = {"sports": ["hiking"], "fitness": 1}
    s = match_score(profile, FakeRoute(), {"boots", "poles", "headlamp"})
    # fit = max(0, 1-(3-1)*0.35) = 0.3 → 40*0.3 + 25*1 + 20*1 + 15*1 = 72
    assert s == 72


def test_missing_gear_penalty():
    profile = {"sports": ["hiking"], "fitness": 3}
    s = match_score(profile, FakeRoute(), {"boots"})
    assert s < 100 and s >= 60


def test_sport_mismatch_penalty():
    profile = {"sports": ["cycling"], "fitness": 3}
    s = match_score(profile, FakeRoute(), {"boots", "poles", "headlamp"})
    assert s < 100


def test_env_penalty():
    profile = {"sports": ["hiking"], "fitness": 3}
    s = match_score(profile, FakeRoute(), {"boots", "poles", "headlamp"}, env=0.7)
    assert s < match_score(profile, FakeRoute(), {"boots", "poles", "headlamp"}, env=1.0)
