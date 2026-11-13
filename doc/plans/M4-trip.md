# M4-trip · 户外运动领域：行程计划实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** 行程计划落进 sports 域：trip_plans 数据层（迁移 0010）+ /trips CRUD API（计划卡带装备提醒）+ `POST /assistant/plan` 一键从对话槽位生成计划。media（上传/审核）与 M3.5 配额不在本计划（配额并入 admin 域后续统一开发，media 延后）。

**Architecture:** trip_plans 归 sports 域（`trip_service`/`trip_router`），遵循域规则：assistant 层只经 `trip_service` 函数创建计划，不直查业务表。计划生成是确定性编排（槽位 → 路线检索+匹配 top1 → 落库），MVP 不调 LLM；chat 流内 `plan` SSE 事件留票（与生产 LLM 接入一起做）。

**Tech Stack:** 无新依赖。

## Global Constraints

- 全部测试保持绿色（89 基线）；覆盖率 ≥ 85 不回退（当前 93.57%）
- 迁移只增不改：本计划从 **0010** 起（0009 已被 M3.5 预占概念占用——实施时若 0009 未存在可用 0009，否则顺延；以当时 head 为准，在报告中记录实际号）
- assistant 层不直查业务表：/assistant/plan 经 `trip_service` + `route_service`/`match_service` 落库与选线
- route 引用校验：route 必须存在且 status='published'
- status 枚举 planned/done/cancelled，非法值服务层拒绝
- DDL 漂移决策：ER 行的 `trip_items` 本期不建表（DDL §5.2 亦未定义）——MVP 单表 trip_plans，一行 = 一次出行（路线×日期×集合点）；多日行程留票
- 测试凭据走 tests/test_auth_login.py 的 `TEST_PW`/`register_and_login`（Mimosa 门禁）
- 提交前缀白名单：feat:/fix:/refactor:/docs:/test:/chore:

---

### Task 1: trip 数据层（模型 + 迁移 + trip_service）

**Files:**
- Create: `backend/app/models/trip.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0010_trip_plans.py`（号位以当时 head 顺延，报告记录）
- Create: `backend/app/domains/sports/trip_service.py`
- Create: `backend/tests/test_trip_service.py`

**Interfaces:**
- Produces:
  - 模型：`TripPlan(id, user_id FK users CASCADE, route_id FK routes, date: date, meet_at: time, meet_place: str|None(96), status default 'planned', created_at)`；对照 DDL §5.2：非 Optional 列 nullable=False，date/meet_at 无 server_default，status server_default='planned'
  - `trip_service.create_plan(session, user_id, route_id, date, meet_at, meet_place=None) -> TripPlan`（route 不存在或非 published → ValueError("路线不存在或未发布")）
  - `trip_service.list_plans(session, user_id) -> list[TripPlan]`（date 升序，未来计划在前：先 status='planned' 按 date asc，再其余按 date desc；简单实现：全部按 (status=='planned') desc, date asc）
  - `trip_service.get_plan(session, user_id, plan_id) -> TripPlan | None`（归属校验）
  - `trip_service.set_status(session, user_id, plan_id, status) -> TripPlan | None`（status ∉ {planned,done,cancelled} → ValueError；不存在/非本人 → None）
  - `trip_service.delete_plan(session, user_id, plan_id) -> bool`

- [ ] **Step 1: 写失败测试**（用例：create 成功+route 校验失败 ValueError；list 排序 planned 在前；set_status 合法/非法/非本人 None；delete 属主 True/非本人 False）

- [ ] **Step 2: 确认失败** → **Step 3: 实现** → **Step 4: 通过**（全量 89→94+，ruff/mypy 绿）

- [ ] **Step 5: Commit** `feat: trip plan data layer in sports domain`

---

### Task 2: /trips CRUD API + 计划卡装备提醒

**Files:**
- Create: `backend/app/domains/sports/trip_router.py`
- Modify: `backend/app/main.py`（include trip_router，prefix="/trips"，tags=["trips"]）
- Create: `backend/tests/test_trip_api.py`

**Interfaces:**
- Produces:
  - `TripPlanIn(route_id: int, date: date, meet_at: time, meet_place: str|None = Field(None, max_length=96))`
  - `TripPlanOut(id, user_id, route_id, date, meet_at, meet_place, status)`（from_attributes）
  - `TripPlanCard(TripPlanOut)`: + route 摘要 `route_name/region/sport/difficulty/distance_km/climb_m/duration_h` + `gear_missing: list[str]`
  - `POST /trips`（201 TripPlanCard；route 无效 → 404）；`GET /trips`（list[TripPlanCard]，含装备提醒）；`GET /trips/{id}`（404 归属）；`PATCH /trips/{id}/status`（body {status}，200/400 非法/404）；`DELETE /trips/{id}`（204/404）
  - 装备提醒：`gear_missing = route.required_gear − 用户 user_gear.item_keys`（参照 `app/assistant/tools.py` 与 `match_service` 取用户装备键的现有方式）
  - 全部端点鉴权（`get_current_user`），参照 `app/domains/sports/route_router.py` 风格

- [ ] **Step 1: 写失败测试**（创建 201 卡片字段齐全；GET 列表含 gear_missing；PATCH done；非法 status 400；他人 plan 404；DELETE 204）→ **Step 2-4: 红→实现→绿** → **Step 5: Commit** `feat: trips CRUD API with gear reminder card`

---

### Task 3: POST /assistant/plan 一键生成计划

**Files:**
- Create: `backend/app/assistant/plan_router.py`
- Modify: `backend/app/main.py`（include，prefix="/assistant"，tags=["assistant"]）
- Create: `backend/tests/test_plan_api.py`

**Interfaces:**
- Produces:
  - `PlanIn(session_id: str|None = None, route_id: int|None = None, date: date|None = None, meet_at: time|None = None, meet_place: str|None = None)`
  - `POST /assistant/plan`（鉴权；200 TripPlanCard）：
    1. `route_id` 缺省 → 取 `session_id` 会话的澄清槽位（sport/region，经 `session_store.own_session` + `sess.clarify`；无会话/无槽位 → 422 "无法确定路线"）→ `route_service` 按 sport/region 检索 + `match_service` 评分取 top1（无候选 → 404 "无匹配路线"）
    2. `date` 缺省 → 槽位 `date`（clarify 已有日期抽取逻辑，复用 `app/assistant/clarify.py` 的日期解析；解析失败 → 422 "无法确定日期"）
    3. `meet_at` 缺省 → 08:00
    4. 经 `trip_service.create_plan` 落库 → 返回 TripPlanCard（与 Task 2 同构，装备提醒同样计算）
  - 检索+评分复用：`app/assistant/tools.py` 中 search_routes 处理器的现有关卡（不复制逻辑，抽公共函数或调用 service 层）
- [ ] **Step 1: 写失败测试**（显式 route_id+date 201 式 200 生成；仅 session 槽位生成 top1；无会话无 route 422；无日期 422；他人 session 422——own_session 对不存在/非本人一律 None，归入"无会话"分支，裁定记录 2026-11-14）→ **Step 2-4: 红→实现→绿** → **Step 5: Commit** `feat: assistant plan generation from clarify slots`

---

### Task 4: 质量门 + 收尾

- [ ] openapi.json 重新生成，零 agent/路径漂移
- [ ] 全量 pytest（预期 89→104±）/ ruff / mypy 全绿；覆盖率 ≥ 93%
- [ ] 台账更新（progress.md 各 task 一行 + defer 票：trip_items 多日行程、chat 流内 plan SSE 事件、spots 地标表）
- [ ] Commit `chore: m4-trip quality gates`

---

## Self-Review 记录

- TripPlanOut 字段与 §5.3 契约一致（补 status 字段供状态流转）
- trip_plans.route_id 无 ON DELETE（DDL 原样）：路线删除受 routes 侧管理，模型用默认 RESTRICT 行为并在报告注明
- 排序口径（planned 优先）为计划新定，DDL/契约未定义——Task 1 测试锁定该行为
