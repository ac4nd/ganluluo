from app.models.route import Route


def match_score(profile: dict, route: Route, gear_keys: set[str], env: float = 1.0) -> int:
    """0-100 匹配度：40 体能 + 25 装备 + 20 偏好 + 15 环境权重。"""
    d = route.difficulty
    fitness_level = profile.get("fitness", 2)
    fit = max(0.0, 1.0 - max(0.0, d - fitness_level) * 0.35)
    required = set(route.required_gear or [])
    gear = 1.0 if not required else len(required & gear_keys) / len(required)
    pref = 1.0 if route.sport in (profile.get("sports") or []) else 0.4
    env_w = max(0.0, min(1.0, env))
    raw = 40 * fit + 25 * gear + 20 * pref + 15 * env_w
    return round(raw)
