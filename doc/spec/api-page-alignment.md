# 原型页 ↔ 后端 API 对齐矩阵

> 基线：openapi.json（迁移 0014，commit 4fe5d69 时代）× protype V2 十页。状态：✅ 可对接 / ⚠️ 字段或参数缺口 / ❌ 无对应端点 / 🎨 纯展示无需后端。
> 数据口径来源：`backend/openapi.json` 权威契约 + protype 各页静态 mock。缺口分级见文末。

## 对齐总表

| 页 | 数据点 | 后端端点 | 状态 | 说明 |
|---|---|---|---|---|
| 01 | 登录/注册/记住我 | `POST /auth/login`、`/auth/register`、`/auth/refresh`、`GET /auth/me` | ✅ | TokenPair(access/refresh)；gl_last_user 为前端本地 |
| 01 | 第三方登录（Google/Apple） | — | ❌ G-11 | users 有 oauth 列无端点；后续迭代 |
| 01 | 背景视频清单 | — | ❌ G-12 | 原型硬编码 assets/videos 清单 |
| 02 | 8 种运动多选 → 画像 | `PUT /profile` {sports} | ✅ | Sport 枚举 8 值与 data-sport 完全一致 |
| 03 | 经验 4 档 / 体能 5 档 | `PUT /profile` {exp_level 1-4, fitness 1-5} | ✅ | 页面档位文案→数值映射由前端做；页默认=进阶(3)/良好(3) |
| 04 | 装备三级目录 | `GET /gear/catalog` | ⚠️ F-1 | catalog 响应层级结构需与三级 UI 对核（分类→项→型号） |
| 04 | 装备清单保存/回读、自定义型号 | `PUT /gear-list`、`GET /gear-list`（GearItemIn: item_key/model_id/custom_name） | ✅ | 种子 116 型号 vs 原型 130+ 卡，型号库内容需对核 |
| 05 | 用户问候/头像 | `GET /auth/me` + `GET /profile` | ✅ | |
| 05 | AI 为你挑选（匹配 96%） | — | ❌ G-7 | 无推荐端点；match 仅 assistant 场景回填 |
| 05 | 天气区间（本周末 12–19℃） | — | ❌ G-9 | 无 HTTP 天气端点（tools 假数据非对外） |
| 05 | 附近热门（热度排序） | `GET /routes` | ⚠️ G-8 | 无 popularity 字段/排序 |
| 05 | 最近足迹 | `GET /trips` | ⚠️ F-2 | = status=done 计划；GET /trips 缺 status 过滤参数 |
| 05 | 最近足迹卡里程/状态 | TripPlanCard(route_name/distance_km/status) | ✅ | 经 F-2 后可对接 |
| 06 | SSE 对话（澄清/检索/卡片/正文） | `POST /assistant/chat`（session/token/clarify/cards/sources/done） | ✅ | |
| 06 | 生成完整计划按钮 | `POST /assistant/plan`（槽位选线）或 `POST /trips` | ✅ | |
| 06 | 配额环形 + hover 明细 | — | ❌ **G-1** | **用户侧无配额查询端点**（UsageOut 仅 admin 路径） |
| 07 | 计划卡（集合/里程/爬升/难度） | `GET /trips`、`POST /trips`（TripPlanCard 全字段） | ✅ | |
| 07 | 装备提醒 N 条 | TripPlanCard.gear_missing | ✅ | length 即条数 |
| 07 | 日期轴（按日期排计划） | `GET /trips` | ⚠️ F-2 | 同上，缺 status 过滤 |
| 07 | 地图 chips 天气/预警 | — | ❌ G-9 | 同 05 |
| 07 | 日期轴点选切计划 | `PATCH /trips/{id}/status`、`DELETE` | ✅ | |
| 08 | 指标四项/清晰度/安全提醒 | `GET /routes/{id}`（RouteDetailOut） | ✅ | warning 字段=安全提醒 |
| 08 | 高程折线 | RouteDetailOut.elevation [{km,m}] | ✅ | |
| 08 | 建议配速折线 | RouteDetailOut.pace [{km,pace}] | ✅ F-4 | 当前为通用配速，非按画像个性化 |
| 08 | 地形构成 | RouteDetailOut.terrain [{type,pct}] | ✅ | |
| 08 | 3D 影像轨迹飞行 | — | ⚠️ **F-3** | **RouteDetailOut 未暴露 track_points**（process_track 已落库） |
| 08 | 信号/补给点/下撤点 chips | — | ❌ G-10 | 无字段（数据采集问题） |
| 08 | 热度（2.3w 人走过） | — | ❌ G-8 | 同 05 |
| 08 | 最高海拔 1180m | elevation 派生 | ✅ | 前端 max(m) |
| 08 | 收藏 | — | ❌ G-13 | 无收藏模型/端点 |
| 09 | 画像摘要/编辑 | `GET/PUT /profile` | ✅ | |
| 09 | 三项统计（28 徒步/342km/15.6k） | — | ❌ **G-2** | 无用户统计聚合端点 |
| 09 | 额度卡（trial/vip 双态） | — | ❌ **G-1** | 同 06 |
| 09 | （后端已有未上 UI）记忆列表 | `GET /assistant/memory`、`DELETE` | 🎨 | 前端后续加记忆管理入口 |
| 09 | （后端已有未上 UI）媒体 | `/media/*` | 🎨 | 前端后续加我的作品 |
| 10 | 筛选：运动/难度≤3/轨迹清晰 | `GET /routes` q=sport/difficulty_max/clarity | ✅ | |
| 10 | 筛选：当天往返 | `GET /routes` | ⚠️ F-5 | 缺 max_duration_h 参数 |
| 10 | 搜索「徽杭」「临安」 | `GET /routes` q=region（region OR name 匹配） | ✅ | 4fe5d69 修复后支持路线名 |
| 10 | 热度 | — | ❌ G-8 | |
| 10 | 分页 | `GET /routes` | ⚠️ F-6 | 无分页参数（MVP 42 条可暂缓） |

## 缺口清单（分级）

### P0 · 对接必需（原型已展示、后端缺口直接卡住页面核心功能）

- **G-1 用户侧配额端点**：新增 `GET /assistant/quota` → UsageOut（复用 quota_service.get_status，用户取自身 user.quota_tier）。06 环形按钮与 09 额度卡的数据源。
- **F-3 RouteDetailOut 暴露 track_points**：`process_track` 已写 route.track_points（≤500 点 lat/lon/ele），详情响应未带——08 高程折线放大与 3D 飞行必需。
- **F-2 GET /trips 加 status 过滤参数**：05「最近足迹」=done、07「日期轴」=planned。

### P1 · 快补（小改动，对接质量）

- **G-2 用户统计端点**：`GET /profile/stats`（完成次数/累计里程/累计爬升，由 trips done + 轨迹聚合）→ 09 三项统计。
- **F-5 /routes 加 max_duration_h**（当天往返筛选）。
- **F-6 /routes 分页**（page/size + total）。
- **F-1 gear/catalog 层级结构对核**（分类→项→型号树）。
- **F-4 pace 个性化**（按画像 fitness 生成，现通用口径）。

### P2 · 后续迭代（需要外部依赖或新模型）

- G-7 推荐端点（AI 挑选 + match 回填）；G-8 热度字段与排序；G-9 天气/预警真实端点（需 API key）；G-10 信号/补给/下撤点数据字段；G-11 第三方 OAuth；G-12 视频清单下发；G-13 收藏。

## 结论

- **可直接对接**：01 登录注册、02/03 画像、04 装备（F-1 核结构）、06 对话与生成计划、07 行程 CRUD、08 详情四指标+高程/配速/地形/安全提醒、10 路线库主筛选——核心闭环无阻塞。
- **P0 三项补齐后**：06/09 配额可视化有数据源、08 3D 轨迹可用、05/07 的足迹与日期轴语义完整。
- P2 均不阻塞前端启动：可先按 mock 渐进对接。
