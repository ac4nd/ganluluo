# M7-miniapp · Taro 轻端实现计划（小程序 + H5 一套代码）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** 启动四端中的轻端：`design/tokens.json` 令牌单一来源 + OpenAPI 生成的 TS 类型 + Taro 4（React+TS）工程，完成 7 页核心闭环（登录/首页/路线库/详情/AI 对话/行程/我的），H5 直接对接本地后端 uvicorn 预览验证；微信小程序为同码构建目标。

**Architecture:** 视觉令牌单一来源（tokens.json → 脚本生成 `miniapp/src/styles/tokens.css` CSS variables，CI 先用本地脚本）；API 类型用 `openapi-typescript` 从后端 openapi.json 生成；请求层 `Taro.request` 封装（Bearer 注入、401→refresh→重试一次、错误归一）；SSE 用 H5 fetch ReadableStream 实现（weapp enableChunked 适配留接口）。登录态 `Taro.setStorageSync` 存 token pair。视觉对齐原型（环保绿暗色主题，style.css 为设计源）。

**Tech Stack:** Taro 4 + React 18 + TypeScript 5 + webpack5；无 UI 组件库（自绘组件对齐原型）。

## Global Constraints

- 令牌只从 design/tokens.json 改，生成的 tokens.css 不手改
- API 类型从 openapi.json 生成，不手写 duplicate
- 页面契约以 doc/spec/api-page-alignment.md 为准：P2 缺口（推荐/热度/天气/收藏）UI 位置保留、数据用 mock 占位并标注"待后端"
- 凭据纪律：baseURL 走 `GL_API_BASE` / dev 配置，不硬编码生产地址
- 提交前缀白名单

---

### Task 1: 地基（tokens + 脚手架 + API 层）

**Files:**
- Create: `design/tokens.json`（从 protype/assets/style.css :root 提取语义令牌）
- Create: `design/build-tokens.mjs`（→ miniapp/src/styles/tokens.css）
- Create: `miniapp/`（Taro 4 脚手架：package.json / config/ / babel.config.js / tsconfig / src/app* / src/pages/index 占位）
- Create: `miniapp/src/api/schema.d.ts`（openapi-typescript 生成）
- Create: `miniapp/src/api/client.ts`（request 封装 + auth 存取 + sse() H5 实现）
- Create: `miniapp/src/api/auth.ts` / `routes.ts` / `trips.ts` / `assistant.ts` / `media.ts`（类型化端点封装）

**Steps:**
- [ ] taro init 或手工最小工程（npm i 可装齐、`npm run build:h5` 产出 dist）
- [ ] tokens.css 生成接入 app.scss
- [ ] client 自测：对本地 uvicorn（8123 stage）GET /ops/health 走通（页面挂调试按钮）
- [ ] Commit `feat(miniapp): taro scaffold, design tokens, typed api client`

---

### Task 2: 登录页 + 我的页（auth 链路 + 额度卡）

**Files:** `miniapp/src/pages/login/*`、`pages/profile/*`、`pages/gear/*`（04 简化清单页）

**要点:**
- 登录：邮箱/密码 → login → 存 token → reLaunch 首页；注册（邮箱/昵称/密码）；未登录拦截（路由守卫：无 token → login）
- 我的：/auth/me 昵称、GET/PUT /profile（运动多选 tiles + 经验/体能选择器）、额度卡（GET /assistant/quota，trial/vip 徽章双态 + 双进度条，对齐原型 09）、退出登录
- 装备：GET /gear/catalog 分组渲染 + GET/PUT /gear-list 勾选（custom_name 输入）
- [ ] Commit `feat(miniapp): login, profile with quota card, gear list`

---

### Task 3: 路线库 + 路线详情

**Files:** `pages/routes/*`、`pages/route-detail/*`

**要点:**
- 路线库：GET /routes（chips：sport 枚举/difficulty_max/clarity；region 关键词搜索含路线名命中）+ RouteOut 卡片（难度/里程/爬升/用时/清晰度）
- 详情：RouteDetailOut 指标四项 + elevation SVG 折线 + pace 折线 + terrain 比例条 + warning 安全提醒 + track_points 折线（有轨迹时）+「加入计划」→ POST /trips
- [ ] Commit `feat(miniapp): routes list with filters, route detail with charts`

---

### Task 4: AI 对话 + 行程计划

**Files:** `pages/chat/*`、`pages/trips/*`、`pages/trip-detail/*`（或合并）

**要点:**
- AI 对话：POST /assistant/chat SSE 流渲染（气泡、clarify 选项 chips、cards 路线卡、sources 折叠）；输入框内嵌配额环（GET /assistant/quota，对齐原型 06：环形 + hover 明细在小程序改为点击弹出 ActionSheet/HalfScreen）；「生成完整计划」→ POST /assistant/plan
- 行程：GET /trips（planned/done tab）+ TripPlanCard（集合/里程/爬升/难度/装备提醒 N 条）+ PATCH 状态 + DELETE；空态引导去 AI 对话
- [ ] Commit `feat(miniapp): chat with sse stream and quota ring, trips`

---

### Task 5: 质量门 + 收尾

- [ ] `tsc --noEmit` 零错误；`build:h5` + `build:weapp` 双目标构建通过
- [ ] H5 截图自检 7 页（无头 Chrome，dev:h5 对接 uvicorn 真数据）
- [ ] 台账 + defer 票：weapp SSE enableChunked 适配、02-04 引导三页、推荐/热度/天气 P2 占位、收藏/第三方登录
- [ ] Commit `chore(miniapp): quality gates`

---

## Self-Review 记录

- 7 页 MVP 不含 02-04 引导页：画像编辑入口收敛到「我的」（PUT /profile 已支持），引导页第二波
- SSE 的 weapp 适配层：client.sse() 定义平台无关接口（onChunk 回调），H5 实现先行
- 图表零依赖：SVG 手绘折线（高程/配速/track_points），地形用比例条——不引 echarts
- P2 数据点（推荐/热度/天气）在 05/07/08 预留 UI 位 + mock 标注，与对齐矩阵 G 组对应
- 后端对接契约全部来自 openapi.json 生成类型，页面不手写字段名
