# M5-admin · 系统管理域实现计划（配额 + 用户管理 + 审核发布）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** admin 域落地：① admin 身份与禁用拦截（users.is_admin/disabled）；② 配额数据层与执行（吸收 M3.5：quota_tiers/llm_usage/sub_tokens 结构、run_chat 入口检查、quota_exceeded 事件、per-user 限流）；③ 管理 API（用户列表/调整档位/禁用/用量、草稿路线审核发布）。

**Architecture:** quota_service 归 `app/domains/admin/`；assistant 层仅在 run_chat 入口消费 admin 域 `get_status`（与 tools.py 调 sports 服务同模式）。配额检查在用户消息持久化之前（超额不落库不调 LLM）。配额计数走 DB（llm_usage 当日聚合），无 Redis 依赖。官方 LLM key 只在后端环境变量。

**Tech Stack:** 无新依赖（slowapi/smt 已有）。

## Global Constraints

- 全部测试保持绿色（131 基线）；覆盖率 ≥ 93% 不回退
- 迁移只增不改：从 **0012** 起（当前 head 0011）
- admin 端点全部经 `get_current_admin` 依赖（非 admin → 403）；disabled 用户在 get_current_user 与 /auth/login 双双拦截（403 "账号已禁用"）
- 超额响应：SSE 事件 `{"type":"quota_exceeded","data":{tier,daily_chats_used,daily_chats_limit,reset_at}}` 后 `done`；**用户消息不落库、不调 Provider**
- 凭据纪律：LLM key 只在环境变量；测试凭据走 register_and_login（Mimosa 门禁）
- sub_tokens 仅建结构（M5 后开放平台用）
- 提交前缀白名单

---

### Task 1: admin 身份 + 禁用拦截

**Files:**
- Modify: `backend/app/models/user.py`（is_admin/disabled bool 列，default false）
- Create: `backend/alembic/versions/0012_user_admin_flags.py`（op.add_column ×2，SQLite/PG 兼容）
- Create: `backend/scripts/seed_admin.py`（GL_ADMIN_EMAIL 环境变量指定邮箱 → is_admin=True，幂等）
- Modify: `backend/app/api/deps.py`（get_current_user 查 disabled → 403；新增 `get_current_admin`）
- Modify: `backend/app/domains/auth/service.py`（login 对 disabled 用户 403）
- Modify: `backend/.env.example`（GL_ADMIN_EMAIL 说明）
- Create: `backend/tests/test_admin_auth.py`

**Interfaces:**
- `get_current_admin(user: User) -> User`：非 is_admin → HTTPException 403 "需要管理员权限"
- seed_admin 幂等：邮箱不存在 → 打印提示退出码 1；存在 → 置 is_admin（已 admin 则 no-op）

- [ ] **Step 1: 失败测试**（admin 依赖放行/403；disabled 用户登录 403；disabled 用户带有效 token 访问 403；普通用户访问 admin 端点样例 403）→ **Step 2-4: 红→实现→绿** → **Step 5: Commit** `feat: admin identity and disabled-user gate`

---

### Task 2: 配额数据层（吸收 M3.5 Task 1）

**Files:**
- Create: `backend/app/models/quota.py`（QuotaTier/LlmUsage/SubToken）
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/user.py`（quota_tier: str default 'trial'）
- Create: `backend/alembic/versions/0013_quota.py`（三表 + users.quota_tier 列）
- Create: `backend/app/domains/admin/quota_service.py`
- Modify: `backend/app/domains/auth/service.py`（注册建默认 trial 档：seed_tiers 幂等调用或在用户创建时确保档位存在——以服务实现为准，报告记录）
- Create: `backend/tests/test_quota_service.py`

**Interfaces:**
- 模型：`QuotaTier(tier PK str(16), daily_chats: int, daily_tokens: int, description: str|None)`；`LlmUsage(id, user_id idx, session_id str(32), model str(64), prompt_tokens int, completion_tokens int, total_tokens int, created_at)`；`SubToken(id, user_id, token_hash str(64), tier str(16), revoked bool, created_at)`（结构预留，无端点）
- users.quota_tier 列 default 'trial'（server_default）
- `get_status(session, user_id, tier) -> QuotaStatus(dataclass: daily_chats_used/daily_chats_limit/daily_tokens_used/daily_tokens_limit/allowed)`——当日（本地日期）llm_usage 聚合 vs 档位限额；档位缺失 → 默认 trial 限额（5 次/20000 token）兜底
- `record_usage(session, user_id, session_id, model, pt, ct) -> None`
- `seed_tiers(session) -> int`（幂等：trial 5/20000、vip 50/500000，返回新建数）
- 测试照 M3.5 计划用例（计数/超限 allowed=False/seed 幂等）

- [ ] **Step 1: 失败测试** → **Step 2-4: 红→实现→绿**（全量 131→137±） → **Step 5: Commit** `feat: quota data layer with tier seed`

---

### Task 3: 配额执行（吸收 M3.5 Task 2）

**Files:**
- Modify: `backend/app/assistant/orchestrator.py`（run_chat 首段增可选 quota 参数；超额 yield quota_exceeded + done，不落消息）
- Modify: `backend/app/assistant/router.py`（chat 端点：get_status → 传入 run_chat；流 done 后 record_usage 估算 token；@limiter.limit per-user 5/minute）
- Create: `backend/tests/test_quota_api.py`

**Interfaces:**
- `run_chat(session, user, sess, message, provider, quota: QuotaStatus | None = None)`：quota.allowed is False → 事件 `quota_exceeded`（data 含 tier/used/limit/reset_at "明天 00:00"）→ `done`；不 append_message 不调 provider
- record_usage 估算：prompt_tokens=len(组装的 system 上下文+消息)//2、completion_tokens=len(生成文本)//2（流结束累计后一次写入；报告记录估算口径）
- 限流：`@limiter.limit("5/minute", key_func=_user_key)`，_user_key 从 Authorization Bearer token 解 user id（解析失败回退 client IP）；第 6 次 429
- 测试：超额（record_usage 造满 5 次 → chat 收 quota_exceeded+done、消息未落库、provider 未被调用）；未超额正常流不受影响；第 6 次 429

- [ ] **Step 1: 失败测试** → **Step 2-4: 红→实现→绿**（全量 137→142±） → **Step 5: Commit** `feat: quota enforcement in chat pipeline`

---

### Task 4: 管理 API

**Files:**
- Create: `backend/app/domains/admin/admin_router.py`
- Modify: `backend/app/main.py`（include，prefix="/admin"，tags=["admin"]）
- Create: `backend/tests/test_admin_api.py`

**Interfaces:**
- `GET /admin/users?query=&page=&size=`：用户列表（id/email/nickname/quota_tier/is_admin/disabled/created_at），email/nickname ilike 搜索，分页（默认 size 20 ≤100，返回 {items, total, page, size}）
- `PATCH /admin/users/{id}` body `{quota_tier?: 'trial'|'vip', disabled?: bool}`：校验档位合法（非法 400）、自身禁用保护（admin 禁自己 → 400 "不能禁用自己"）；200 返回更新后用户摘要
- `GET /admin/users/{id}/usage`：当日 {chats_used, tokens_used, tier}（复用 quota_service.get_status）
- `GET /admin/routes/drafts`：草稿路线列表（id/name/region/sport/created_at）
- `POST /admin/routes/{id}/publish`：draft → published（非 draft 400）；发布后 GET /routes 可见
- 全部 get_current_admin；测试覆盖 403（普通用户）与各校验分支

- [ ] **Step 1: 失败测试** → **Step 2-4: 红→实现→绿**（全量 142→150±） → **Step 5: Commit** `feat: admin user management and route review API`

---

### Task 5: 质量门 + 收尾

- [ ] openapi.json 重新生成（/admin/*）；全量 pytest / ruff / mypy / 覆盖率 ≥93%
- [ ] 台账 + defer 票：sub_tokens 开放平台端点、admin 操作审计日志、草稿驳回流程、quota VIP 支付联动
- [ ] Commit `chore: m5-admin quality gates`

---

## Self-Review 记录

- 配额检查在 append_message 之前（计划硬约束），超额路径零写库零 Provider 调用
- run_chat quota 参数带默认 None → 既有测试/test_agent_api 全部签名兼容，无需改断言
- limiter per-user key：Bearer 解析失败回退 IP，登录前无 token 也安全
- is_admin/disabled 默认 false + server_default：存量用户行为不变
- draft publish 与 M4.5 上传管线衔接：draft 数据已由同步处理补全，发布仅改 status
