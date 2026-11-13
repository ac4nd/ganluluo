# 系统设计（System Design）— V2 基线

本文是赶路咯（GANLULUO）的系统设计参考：架构总览、模块与时序、技术选型明细、数据结构（DDL + Pydantic 契约）、部署拓扑。上游依据为[产品与技术规格说明书](specification.md)，技术栈决策依据为 [ADR：原生多端方案](../notes/2026-11-13-native-frontend-security.md)、[ADR：技术栈选型](../notes/2026-11-13-tech-stack-choice.md)、[ADR：模块化单体优先](../notes/2026-11-13-monolith-first.md)。

## 1. 架构总览

```
┌─ 客户端层 ─────────────────────────────────────────────┐
│ iOS(SwiftUI)  Android(Compose)  鸿蒙(ArkUI)  小程序/H5(Taro) │
└──────────┬────────────────────────────────────────────┘
           │ HTTPS(TLS1.3) · WAF · CDN(静态/媒体)
┌──────────▼────────────────────────────────────────────┐
│ API 网关：JWT 校验 · 限流 · 路由 · OpenAPI 聚合            │
└──────────┬────────────────────────────────────────────┘
┌──────────▼────────────────────────────────────────────┐
│ 后端（FastAPI 模块化单体，按域拆分 Router）                 │
│  auth · profile · route · trip · assistant · media      │
└───┬──────────┬──────────┬──────────┬──────────────────┘
    │          │          │          │
 PostgreSQL   Redis     对象存储    Celery worker
 (PostGIS)  (缓存/限流)  (媒体/签名)  (轨迹/天气/审核/LLM离线)
                                    │
                          外部：LLM 网关 · 天气/灾害 · 地图 · 内容审核
```

架构形态为**模块化单体优先**（理由与演进路径见 [ADR](../notes/2026-11-13-monolith-first.md)）：单仓库、单部署单元、模块间只经 `services/` 层函数调用与领域事件（Outbox 表）通信，禁止跨模块直连对方表；拆分微服务的触发条件为「单模块 CPU/内存占比 > 60% 或独立扩缩容需求持续两周」。

## 2. 领域划分与职责（DDD）

后端按业务领域（Domain）组织，每个域是独立的业务单元，拥有自己的路由、服务层、数据模型。域之间通过**服务层函数调用**通信（禁止跨域直查对方表）。AI 助手域是**中间层**——它编排 LLM 并调用其他域的服务获取数据，不持有业务数据。

```
┌─────────────────────────────────────────────────────────┐
│                    客户端层（四端）                        │
│  iOS(SwiftUI)  Android(Compose)  鸿蒙(ArkUI)  小程序/H5   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────┐
│              API 网关（JWT · 限流 · 路由聚合）              │
└──────────────────────┬──────────────────────────────────┘
┌──────────────────────▼──────────────────────────────────┐
│                    领域层（Domain）                       │
│                                                         │
│  ┌─── 认证域 auth ──────────────────────────────────┐   │
│  │ 注册/登录/JWT 签发刷新/会话管理                       │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌─── 户外运动域 sports ────────────────────────────┐   │
│  │ 运动画像 · 装备目录与清单 · 路线/轨迹 · 匹配评分      │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌─── AI 助手域 assistant（中间层）──────────────────┐   │
│  │ LLM 编排 · RAG 检索 · 记忆 · 澄清 · 工具调用         │   │
│  │  └── 调用 sports 域服务获取数据，不持有业务数据       │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌─── 系统管理域 admin（预留）───────────────────────┐   │
│  │ 用户管理 · 权限管理 · 额度管理                        │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
┌──────────────────────▼──────────────────────────────────┐
│  PostgreSQL(PostGIS+pgvector) · Redis · 对象存储 · Celery  │
└─────────────────────────────────────────────────────────┘
```

| 领域 | 路由前缀 | 职责 | 持有数据 | 禁止事项 |
|---|---|---|---|---|
| **auth** | `/auth` | 注册、登录（密码/Apple/微信/华为）、JWT 签发与刷新、注销 | users, refresh_tokens | 不读业务表 |
| **sports** | `/profile` `/gear` `/routes` | 运动画像、装备目录与清单、路线库检索、轨迹处理、匹配评分 | user_profiles, gear_models, user_gear, routes | 不调用 LLM |
| **assistant** | `/assistant` | LLM 编排（SSE）、RAG 检索（攻略知识库）、记忆系统、澄清引导、工具调用 | assistant_sessions, assistant_messages, user_memories, kb_docs, kb_chunks | **不持有运动/用户业务数据**——只经 sports 域服务函数获取 |
| **admin**（预留） | `/admin` | 用户管理、权限管理、额度管理（quota tier 分配/调整） | quota_tiers, llm_usage, sub_tokens | 不做 LLM 编排 |
| `/ops` | `/ops` | 健康检查、指标 | — | 不对外暴露 |

**跨域规则**：assistant 域的 `tools.py` 调用 `sports.domain` 的服务函数获取路线/画像/装备数据——这是唯一的跨域调用点；admin 域独立。

## 3. 关键时序

**AI 对话规划（SSE 流式）**：客户端 `POST /assistant/chat`（SSE）→ 网关校验 → assistant 组装上下文（画像 + 装备摘要 + 最近会话，Redis）→ LLM Provider 流式转发（逐 token SSE）→ 模型触发工具调用（`search_routes` / `check_weather` / `check_alerts`，白名单注册）→ 工具结果回灌 → 生成路线缩略卡结构段 → 会话与消息落库。首 token 目标 < 1.5s。

**RAG 检索与澄清引导**（assistant 多轮）：用户消息 → 意图判定（plan/info/chat）→ plan 意图进入澄清状态机：缺槽（运动/地区/日期/时长/强度/同行者）时一次追问一项（SSE 事件 `clarify`，附选项），填齐或用户跳过后槽位转结构化过滤 + 查询改写 → 混合检索（pgvector 余弦 + FTS，RRF 融合 top8）→ bge-reranker 重排 top4 → 上下文注入（人设 + 画像摘要 + 长期记忆 topK + rolling summary + 检索块）→ 流式生成（SSE 事件 `token`，路线卡片结构段 `cards`，引用标注 `sources`）→ 会话结束触发异步记忆抽取 worker。

**轨迹处理管线**（Celery）：客户端预签名直传 GPX → `POST /tracks` 登记 → worker `process_track(track_id)`：GPX 解析 → Douglas-Peucker 抽稀（ε=8m）→ 高程采样（DEM 30m 格点）→ 累计爬升（阈值 10m 去抖）→ 清晰度评分（点密度 + 重复率）→ 难度评分（爬升率/里程/路面标签加权）→ 写入 `routes` 并生成检索向量。

**路线匹配评分**（assistant 与 route 共用 services 函数，输出 0–100）：

```
match = 40*fitness + 25*gear + 20*pref + 15*env
fitness = max(0, 1 - max(0, D - L) * 0.35)      # D=路线难度(1-5) L=体能等级(1-5)
gear    = |required_gear ∩ user_gear| / |required_gear|
pref    = sport ∈ user_sports ? 1 : 0.4          # 多偏好取最高
env     = 1.0 无预警；0.7 有预警；恶劣天气再 -0.3
```

## 4. 技术选型明细

**后端**：Python 3.12、FastAPI ≥0.115、Pydantic v2（严格模式 + mypy）、SQLAlchemy 2.0（async）+ asyncpg、PostgreSQL 16 + PostGIS 3.4、Redis 7、Celery 5（Redis broker）、PyJWT（RS256）、httpx（外联，强制 SSRF 白名单）、slowapi（限流）、pytest + testcontainers。

**LLM 网关**：`Provider` 抽象接口（`chat_stream(messages, tools)` 统一 OpenAI 兼容 wire 协议），国产模型供应商以配置切换；工具调用白名单注册表 `TOOL_REGISTRY: dict[str, ToolSpec]`。

**客户端四端**（系统特性与降级矩阵见 [ADR：原生多端方案](../notes/2026-11-13-native-frontend-security.md)）：iOS SwiftUI + iOS 26 SDK（Liquid Glass `glassEffect`、灵动岛实况、WeatherKit、MapKit、HealthKit）；安卓 Jetpack Compose + Material 3（动态取色、Glance 小组件、media3、WorkManager）；鸿蒙 ArkUI + ArkTS（实况窗、星闪投送、万能卡片、元服务）；轻端 Taro 4（React + TS）覆盖微信小程序与 H5。共享资产：设计令牌 tokens.json（CI 生成四端主题）与 OpenAPI 生成的 API 客户端。

**各端仓库结构**（单仓库后端 + 四端各自仓库）：

```
backend/            app/(api|services|models|schemas|workers|core)  tests/
ios/GanLuLuo/       App/ Features/(Login|Home|Plan|Detail|Profile) Core/(DesignSystem|Network|Services)
android/            app/ core/(designsystem|network|model) feature/(home|plan|detail|profile)
harmony/            entry/src/main/ets/(pages|components|viewmodel) commons/
miniapp/            src/(pages|components|services) config/  # Taro 4, React+TS
design/             tokens.json(单一来源) → CI 生成四端主题
```

## 5. 数据结构

### 5.1 ER 概览

`users 1—1 user_profiles`；`users 1—N user_gear N—1 gear_models`；`users 1—N trip_plans 1—N trip_items N—1 routes`；`routes 1—N route_tracks`；`users 1—N assistant_sessions 1—N assistant_messages`；`routes N—1 spots`（起点/途经地标）。

### 5.2 SQL DDL（核心表，PostGIS）

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE users (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email         CITEXT UNIQUE,
  phone         VARCHAR(20) UNIQUE,
  password_hash TEXT,
  nickname      VARCHAR(32) NOT NULL,
  avatar_url    TEXT,
  oauth_provider VARCHAR(16),            -- apple/wechat/huawei
  oauth_subject TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ,
  CHECK (email IS NOT NULL OR phone IS NOT NULL)
);

CREATE TABLE user_profiles (
  user_id      BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  sports       TEXT[] NOT NULL DEFAULT '{}',   -- 枚举: hiking/trail-running/...
  exp_level    SMALLINT NOT NULL DEFAULT 1,    -- 1..4
  fitness      SMALLINT NOT NULL DEFAULT 2,    -- 1..5
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gear_models (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  item_key   TEXT NOT NULL,                -- boots/poles/snowboard/...
  brand      VARCHAR(48) NOT NULL,
  model      VARCHAR(64) NOT NULL,
  spec       VARCHAR(128),                -- 中帮 · GTX 防水
  UNIQUE (item_key, brand, model)
);

CREATE TABLE user_gear (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_key    TEXT NOT NULL,
  model_id    BIGINT REFERENCES gear_models(id),
  custom_name TEXT,
  acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, item_key, model_id)
);

CREATE TABLE routes (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name         VARCHAR(64) NOT NULL,
  region       VARCHAR(64) NOT NULL,
  sport        TEXT NOT NULL,
  difficulty   SMALLINT NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  distance_km  NUMERIC(6,2) NOT NULL,
  climb_m      INT NOT NULL,
  duration_h   NUMERIC(4,1) NOT NULL,
  clarity      TEXT NOT NULL,              -- high/mid/low
  terrain      JSONB NOT NULL,             -- [{type,pct}]
  elevation    JSONB NOT NULL,             -- 采样点 [{km,m}]
  pace         JSONB NOT NULL,             -- [{km,pace}]
  start_pt     geography(Point,4326) NOT NULL,
  geom         geography(LineString,4326),
  required_gear TEXT[] NOT NULL DEFAULT '{}',
  warning      TEXT,
  status       TEXT NOT NULL DEFAULT 'published',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_routes_region ON routes(region);
CREATE INDEX idx_routes_start  ON routes USING GIST (start_pt);

CREATE TABLE route_tracks (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  route_id   BIGINT NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  gpx_object TEXT NOT NULL,                -- 对象存储 key
  points     INT NOT NULL,
  processed  BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE trip_plans (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  route_id   BIGINT NOT NULL REFERENCES routes(id),
  date       DATE NOT NULL,
  meet_at    TIME NOT NULL,
  meet_place VARCHAR(96),
  status     TEXT NOT NULL DEFAULT 'planned',  -- planned/done/cancelled
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assistant_sessions (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE assistant_messages (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES assistant_sessions(id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
  content    TEXT NOT NULL,
  tool_name  TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 5.3 Pydantic 契约（与 OpenAPI 生成共用）

```python
from datetime import date, datetime, time
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class Sport(str, Enum):
    HIKING = "hiking"
    TRAIL_RUNNING = "trail-running"
    CLIMBING = "climbing"
    STREAM = "stream"
    CYCLING = "cycling"
    CAMPING = "camping"
    SKIING = "skiing"
    ORIENTEERING = "orienteering"

class GearModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    brand: str
    model: str
    spec: str | None

class GearItemIn(BaseModel):
    item_key: str
    model_id: int | None = None
    custom_name: str | None = Field(None, max_length=48)

class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    sports: list[Sport]
    exp_level: int
    fitness: int

class RouteCard(BaseModel):           # 列表/缩略卡
    id: int
    name: str
    region: str
    sport: Sport
    difficulty: int
    distance_km: float
    climb_m: int
    duration_h: float
    clarity: str
    match: int | None = None          # 0-100，assistant 场景回填

class RouteDetail(RouteCard):
    elevation: list[dict]             # [{km: float, m: int}]
    pace: list[dict]                  # [{km: float, pace: int}]
    terrain: list[dict]               # [{type: str, pct: int}]
    required_gear: list[str]
    warning: str | None

class TripPlanIn(BaseModel):
    route_id: int
    date: date
    meet_at: time
    meet_place: str | None = Field(None, max_length=96)

class ChatMessageOut(BaseModel):
    role: str
    content: str
    tool_name: str | None = None
```

### 5.5 知识库、记忆与澄清（RAG 相关表）

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE kb_docs (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_name VARCHAR(128) NOT NULL,
  sport       TEXT,
  doc_type    TEXT NOT NULL,               -- md/docx/pdf/html
  version     INT NOT NULL DEFAULT 1,
  status      TEXT NOT NULL DEFAULT 'draft',  -- draft/indexed/failed
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE kb_chunks (
  id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  doc_id    BIGINT NOT NULL REFERENCES kb_docs(id) ON DELETE CASCADE,
  chunk_no  INT NOT NULL,
  content   TEXT NOT NULL,
  sport     TEXT,
  region    TEXT,
  section   TEXT,                          -- 所属攻略章节
  embedding vector(1024) NOT NULL,         -- bge-m3
  tsv       tsvector NOT NULL,
  tokens    INT NOT NULL
);
CREATE INDEX idx_chunks_hnsw ON kb_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_tsv  ON kb_chunks USING GIN (tsv);
CREATE INDEX idx_chunks_meta ON kb_chunks (sport, region);

CREATE TABLE user_memory (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL CHECK (kind IN ('preference','constraint','fact')),
  content     TEXT NOT NULL,
  confidence  REAL NOT NULL DEFAULT 0.8,
  source_session UUID,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ
);
CREATE INDEX idx_memory_user ON user_memory (user_id, kind);
```

```python
class ClarifyState(BaseModel):
    intent: Literal["plan", "info", "chat"] = "chat"
    slots: dict[str, str] = Field(default_factory=dict)   # sport/region/date/length/level/party
    asked: list[str] = Field(default_factory=list)        # 已追问槽位，防重复
    round_no: int = 0                                     # 追问轮次，上限 3

class MemoryFact(BaseModel):
    kind: Literal["preference", "constraint", "fact"]
    content: str
    confidence: float = 0.8
    source_session: uuid.UUID | None = None

class RetrievedChunk(BaseModel):
    doc_id: int
    source_name: str
    chunk_no: int
    content: str
    score: float
    sport: str | None = None
```

SSE 事件类型：`token`（正文流）、`clarify`（引导问题 + 选项）、`cards`（路线缩略卡）、`sources`（引用文档列表）、`plan`（结构化计划）。API 增量：`GET /assistant/memory`、`DELETE /assistant/memory/{id}`（用户可见可删）；`POST /kb/documents`、`GET /kb/docs`（admin，摄取状态）。

### 5.4 Redis 键设计

`sess:{session_id}`（最近 20 条消息哈希，TTL 7d）、`rl:{user_id}:{route_prefix}`（固定窗口限流计数，TTL 60s）、`wx:{grid}`（天气缓存，TTL 600s）、`outbox`（领域事件流，轮询派发）。

## 6. 部署拓扑

开发环境 docker compose：`api`、`worker`、`postgres`、`redis`、`minio`。生产：容器编排（2+ api 副本、1+ worker）、托管 PostgreSQL（PostGIS）、托管 Redis、对象存储 + CDN、WAF；健康探针 `GET /ops/health`（含 DB/Redis 就绪）；结构化 JSON 日志 + OpenTelemetry trace（trace-id 贯穿 SSE）。

## 7. 测试与后续实现计划

后端 pytest + testcontainers（真实 PostGIS/Redis）；契约测试锁定 OpenAPI；LLM 层以录制的 Provider 假体测试编排逻辑。实现计划按模块拆分（`plans/` 目录，每模块一份 writing-plans 格式计划）：M1 auth+profile、M2 route+track 管线、M3 assistant 对话、M4 trip+media；各端仓库按端内里程碑另行计划。
