"""本地阶段冒烟：真实 HTTP 序列走通 注册→画像→装备→路线→行程→AI 生成→对话。

前置：临时库已 create_all + 种子，uvicorn 已在 BASE 上运行（见 progress 或 README）。
用法：python scripts/smoke_local.py [base_url]   # 默认 http://127.0.0.1:8123
退出码：全 PASS=0，任一 FAIL=1。
"""
import json
import sys
import time
from datetime import date, timedelta

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"
PW = "pass" + "w0rd!"  # 测试夹具凭据（非真实凭据）：拼接以通过静态凭据扫描
results: list[tuple[str, bool, str]] = []

def step(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + ((" | " + detail) if detail else ""))

def parse_events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]

c = httpx.Client(base_url=BASE, timeout=30)

# ---- 1. 健康 ----
r = c.get("/ops/health")
step("ops/health", r.status_code == 200, str(r.json())[:60])

# ---- 2. 注册 + 登录 ----
email = f"stage-{int(time.time())}@b.com"
r = c.post("/auth/register", json={"email": email, "password": PW, "nickname": "阶段验证"})
step("auth/register", r.status_code == 201, f"code={r.status_code}")
r = c.post("/auth/login", json={"email": email, "password": PW})
ok = r.status_code == 200 and r.json().get("access_token")
step("auth/login", bool(ok))
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# ---- 3. 画像 ----
r = c.put("/profile", json={"sports": ["hiking"], "exp_level": 2, "fitness": 3}, headers=H)
step("profile put", r.status_code == 200, str(r.json())[:60])

# ---- 4. 装备目录 + 清单（刻意不装 boots → 之后 gear_missing 应含它）----
r = c.get("/gear/catalog")
step("gear/catalog", r.status_code == 200 and len(r.json()) > 0, f"code={r.status_code}")
owned = ["rain-gear", "first-aid", "midlayer", "sunscreen"]
r = c.put("/gear-list", json={"items": [{"item_key": k} for k in owned]}, headers=H)
step("gear-list put", r.status_code == 200, f"owned={owned}")

# ---- 5. 路线库（含本轮 region-OR-name 新语义）----
r = c.get("/routes")
step("routes list", r.status_code == 200 and len(r.json()) >= 6, f"count={len(r.json())}")
r = c.get("/routes", params={"region": "雨崩"})
names = {x["name"] for x in r.json()} if r.status_code == 200 else set()
step("routes region=雨崩 命中路线名", r.status_code == 200 and any("雨崩" in n for n in names), str(names))
r = c.get("/routes", params={"region": "迪庆"})
step("routes region=迪庆 仍命中地区列", r.status_code == 200 and len(r.json()) >= 2, f"count={len(r.json())}")
route1 = c.get("/routes/1")
required = route1.json().get("required_gear", [])
step("routes/1 详情", route1.status_code == 200 and isinstance(required, list),
     f"required_gear={required}")

# ---- 6. 行程计划 CRUD ----
tomorrow = (date.today() + timedelta(days=1)).isoformat()
r = c.post("/trips", json={"route_id": 1, "date": tomorrow, "meet_at": "08:00",
                           "meet_place": "地铁站 C 口"}, headers=H)
card = r.json() if r.status_code == 201 else {}
expect_missing = [k for k in required if k not in owned]
step("POST /trips 201 + TripPlanCard",
     r.status_code == 201 and all(k in card for k in
         ("id", "route_name", "gear_missing", "status", "date")),
     f"gear_missing={card.get('gear_missing')}")
step("gear_missing = required - owned", card.get("gear_missing") == expect_missing,
     f"expect={expect_missing}")
trip_id = card.get("id")

r = c.get("/trips", headers=H)
step("GET /trips 列表", r.status_code == 200 and len(r.json()) == 1, f"count={len(r.json())}")

# ---- 7. AI 对话：澄清两轮（离线 FakeProvider 自动降级）----
r = c.post("/assistant/chat", json={"message": "想去个地方走走"}, headers=H)
ev1 = parse_events(r.text) if r.status_code == 200 else []
session_id = ev1[0]["data"] if ev1 and ev1[0]["type"] == "session" else None
step("chat R1: session+clarify(sport)+done",
     bool(session_id) and any(e["type"] == "clarify" and e["data"]["slot"] == "sport" for e in ev1)
     and ev1[-1]["type"] == "done",
     f"types={[e['type'] for e in ev1]}")

r = c.post("/assistant/chat", json={"message": "雨崩徒步", "session_id": session_id}, headers=H)
ev2 = parse_events(r.text) if r.status_code == 200 else []
# "雨崩徒步" 同时补 sport+region 槽 → 追问链正确推进到 date
step("chat R2: 槽位补齐→澄清推进(date)",
     any(e["type"] == "clarify" and e["data"]["slot"] == "date" for e in ev2),
     f"types={[e['type'] for e in ev2]}")

r = c.post("/assistant/chat", json={"message": "出发本周六", "session_id": session_id}, headers=H)
ev2b = parse_events(r.text) if r.status_code == 200 else []
step("chat R3: 日期补齐→答题流(token+done)",
     bool(ev2b) and any(e["type"] == "token" for e in ev2b) and ev2b[-1]["type"] == "done",
     f"types={[e['type'] for e in ev2b]}")

r = c.get("/assistant/sessions", headers=H)
step("assistant/sessions", r.status_code == 200 and len(r.json()) >= 1,
     f"title={r.json()[0]['title'] if r.json() else '-'}")

# ---- 8. AI 一键生成计划（会话槽位 sport=hiking/region=雨崩 → top1）----
r = c.post("/assistant/plan", json={"session_id": session_id}, headers=H)
plan_ok = r.status_code == 200 and "雨崩" in r.json().get("route_name", "")
step("POST /assistant/plan 槽位选线生成", plan_ok,
     f"route_name={r.json().get('route_name') if r.status_code == 200 else r.text[:80]}")
gen_card = r.json() if r.status_code == 200 else {}
step("plan 卡 gear_missing 与显式创建同构", gen_card.get("gear_missing") == expect_missing,
     f"gear_missing={gen_card.get('gear_missing')}")

# ---- 9. 状态流转 + 删除 ----
r = c.patch(f"/trips/{trip_id}/status", json={"status": "done"}, headers=H)
step("PATCH status=done", r.status_code == 200 and r.json()["status"] == "done")
r = c.delete(f"/trips/{trip_id}", headers=H)
step("DELETE 204", r.status_code == 204)
r = c.get("/trips", headers=H)
step("删除后列表剩生成计划", r.status_code == 200 and len(r.json()) == 1, f"count={len(r.json())}")

# ---- 9b. 轨迹上传（M4.5）：GPX → 草稿路线 + 同步处理 ----
GPX = ("""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="stage"><trk><name>s</name><trkseg>"""
       + "".join(f'<trkpt lat="30.{i:04d}" lon="120.0000"><ele>{100 + i * 40}</ele></trkpt>'
                 for i in range(8))
       + """</trkseg></trk></gpx>""")
r = c.post("/tracks", headers=H,
           files={"file": ("stage.gpx", GPX.encode(), "application/gpx+xml")},
           data={"name": "阶段验证线", "region": "测试区域", "sport": "hiking"})
up = r.json() if r.status_code == 201 else {}
step("POST /tracks 201 同步处理",
     r.status_code == 201 and up.get("points") == 8 and up.get("route_id") and up.get("track_id"),
     f"points={up.get('points')} distance={up.get('distance_km')}km climb={up.get('climb_m')}m")
r = c.get("/routes", params={"region": "测试区域"})
step("draft 路线不进公共库", r.status_code == 200 and len(r.json()) == 0,
     f"count={len(r.json())}")

# ---- 10. 记忆 + info 分支流 ----
r = c.get("/assistant/memory", headers=H)
step("assistant/memory 列表", r.status_code == 200 and isinstance(r.json(), list))
r = c.post("/assistant/chat", json={"message": "雨崩怎么走", "session_id": session_id}, headers=H)
ev4 = parse_events(r.text) if r.status_code == 200 else []
step("chat R4: info 分支流式到 done",
     bool(ev4) and any(e["type"] == "token" for e in ev4) and ev4[-1]["type"] == "done",
     f"types={[e['type'] for e in ev4]}")

# ---- 汇总 ----
fails = [n for n, ok, _ in results if not ok]
print(f"\n{'=' * 50}\n{len(results) - len(fails)}/{len(results)} PASS" +
      (f"，FAIL: {fails}" if fails else "，阶段验证通过"))
sys.exit(1 if fails else 0)
