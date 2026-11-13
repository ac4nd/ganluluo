# 赶路咯 · 产品与技术规格说明书（V2 基线）

本文是赶路咯（GANLULUO）AI 徒步助手的产品与技术规格参考，基线对应原型版本 [protype/V2 工作副本](../../protype/README.md)（继承 [V1 归档](../../protype/V1/README.md)）。文档定位为 reference：定义页面规格、设计系统引用、四端前端方案与后端技术栈。选型理由见 [技术栈选型 ADR](../notes/2026-11-13-tech-stack-choice.md)，变更记录见 [changelog](../changelog/)。

## 1. 产品概述与核心流程

产品定位：AI 徒步助手——通过用户画像预设、AI 对话式路线规划、结构化路线详情帮助用户完成户外徒步活动。

核心流程：用户画像预设（运动偏好 → 经验体能 → 装备清单）→ AI 对话询问附近路线（天气 + 灾害预警核查 + 画像匹配筛选）→ 缩略卡片 → 路线详情（高程/配速/地形/3D 影像）→ 行程计划 → 出行。画像数据（`gl_sports`、`gl_last_user`）与路线安全匹配（装备缺失 → 谨慎推荐）贯穿全流程。

## 2. 信息架构与页面规格

| 页面 | 模块规格 | 关键交互 | 数据依赖 |
|---|---|---|---|
| 01 登录 | 双态视觉：未登录 = 地球轮廓 + 探险航线（Canvas2D 线框地球：大陆线稿/经纬网格/18 景点脉冲/大圆航线流光/拖拽旋转）；已登录 = 上次登录头像框 + 续登按钮 | 账号/第三方登录；`gl_last_user` 状态切换；`?state=` 演示参数 | 登录态存储、用户资料 |
| 02 画像·运动偏好 | 8 种运动多选 tile（1–4 项） | 点击即切对应运动实拍视频背景；选择写入 `gl_sports` | 画像·偏好字段 |
| 03 画像·经验体能 | 徒步经验 4 档单选；体能 5 级自评（含能量条） | 单选切换 | 画像·经验/体能 |
| 04 画像·装备清单 | 三级结构：8 分类 49 项装备 → 细分维度 chips → 品牌型号图卡（约 100 预设）+ 自定义型号添加 | 分类筛选、行勾选、型号勾选、计数联动 | 画像·装备清单 |
| 05 首页 | 风景视频轮播背景（13 地貌，高对比优先）、问候、AI 为你挑选、附近热门路线、最近足迹 | 卡片点击进详情；底部导航 | 推荐接口、天气接口 |
| 06 AI 规划对话 | 对话流：AI 气泡 + 用户气泡 + 条件核查 chips（天气/灾害/装备/体能）+ 路线缩略卡（匹配度）+ 生成计划按钮 | 消息发送、卡片跳转 | LLM 对话接口、路线检索 |
| 07 行程计划 | 日期轴、3D 倾斜地图轨迹、计划卡（集合时间/里程/爬升/难度）、装备提醒 | 查看详情、开始旅程 | 行程计划接口 |
| 08 路线详情 | 难度/里程/爬升/用时指标、轨迹清晰度/信号/补给/下撤点 chips、高程折线图、建议配速折线图、地形构成条、3D 影像轨迹飞行（可播放）、安全提醒 | 收藏、加入计划、开始徒步 | 路线详情接口、轨迹数据 |
| 09 我的 | 画像摘要、三项统计、偏好 tile、常用装备、重走画像入口 | 编辑画像 | 用户资料 |
| 10 路线库 | 筛选 chips（运动类型/难度/轨迹清晰/当天往返）、路线卡（难度/里程/爬升/热度/清晰度） | 卡片进详情 | 路线库接口 |

三平台系统语言适配（iOS Liquid Glass / 鸿蒙 NEXT 实况窗与万能卡片 / 安卓 M3 药丸导航与 FAB）见 [platforms.html 对照板](../../protype/platforms.html)。

## 3. 设计系统（引用唯一归属源）

设计令牌与组件样式以 [`protype/assets/style.css`](../../protype/assets/style.css) 为唯一权威来源：环保绿主题（`--accent:#A4F150`、`--grad:#C2F96A→#5FD23C`、暗底 `#0C110A`）、玻璃层（`.glass`、`--glass-line/--glass-hi`）、cinema 视频层与 32 段素材规格。图标系统以 [`protype/assets/sprite.html`](../../protype/assets/sprite.html) 为源：8 个运动 symbol（`icon-*`）+ 32 个装备产品图形（`ic-*`），24×24、currentColor、stroke 1.8、圆角端点。本目录与各端实现均只链接不复述，令牌变更以该文件为准。

## 4. 前端架构（各端原生重写 + 轻端统一）

决定（[ADR：原生多端方案](../notes/2026-11-13-native-frontend-security.md)）：移动端三系统**各端原生重写**以充分表达系统特性；小程序与网页端由 **Taro 4（React + TS）一套代码**统一适配；设计令牌单一来源（tokens.json 生成各端主题）与 OpenAPI 生成的 API 客户端保证四端一致性。

| 端 | 技术栈 | 系统特性表达 |
|---|---|---|
| iOS | SwiftUI + iOS 26 SDK | Liquid Glass `glassEffect` 材质（导航/卡片/播放控件）、灵动岛实况（进行中徒步的里程/配速/海拔）、Sign in with Apple、WeatherKit、MapKit、HealthKit 徒步记录、触感反馈 |
| 安卓 | Jetpack Compose + Material 3 | Material You 动态取色、Predictive back 手势、edge-to-edge、Glance 小组件（下次计划/天气卡）、WorkManager 轨迹离线同步、Media3 背景播放 |
| 鸿蒙 NEXT | ArkUI + ArkTS | 实况窗 Live View、星闪投送（轨迹/照片 NearLink 向车机平板秒传）、万能卡片（天气/计划服务卡片）、元服务免安装、分布式跨端接续、HarmonyOS Sans |
| 小程序 + 网页 | Taro 4（React + TS） | 微信小程序与 H5 同构；易用优先：精简动效、接口预取、分享卡片 |

特效实现矩阵（同一设计，各端表达；原型 Canvas2D 引擎为共享资产）：

| 特效 | iOS | 安卓 | 鸿蒙 | 小程序 / H5 |
|---|---|---|---|---|
| 地球轮廓 + 探险航线 | SwiftUI Canvas | Compose Canvas | ArkUI Canvas | canvas 2d 直接复用 |
| cinema 视频背景 | AVPlayerLayer | media3 ExoPlayer | ArkUI Video | video 组件 / H5 video |
| 玻璃材质 | Liquid Glass glassEffect | M3 表面色 + blur | 模糊材质 | backdrop-filter（H5）/ 半透明（小程序） |
| 高程 / 配速图表 | Swift Charts | Compose 自绘 | ArkUI Canvas | SVG / canvas |

一致性验收以 [platforms.html 对照板](../../protype/platforms.html) 与设计令牌单一来源为准；选型权衡与放弃方案见 [ADR](../notes/2026-11-13-native-frontend-security.md)。

## 5. 后端技术选型（Python FastAPI · 已决定）

按本项目六项核心负载评估：LLM 对话编排、轨迹/地理计算、推荐匹配、天气与灾害预警聚合、内容审核与媒体分发、用户/画像/装备 CRUD。

| 维度 | Python（FastAPI） | Java（Spring Boot） |
|---|---|---|
| LLM/RAG/Agent 生态 | ✓✓ 主流模型 SDK、编排框架、embedding 工具链齐全 | △ Spring AI 起步阶段 |
| 轨迹与地理计算 | ✓✓ geopandas/PostGIS/GDAL 轨迹抽稀、高程采样、地貌判读 | ✓ GeoTools/PostGIS 可用，数据科学链路弱 |
| 推荐与画像匹配迭代 | ✓✓ numpy/sklearn 快速实验 | ✓ 需自建实验链路 |
| 并发与事务 | ✓ IO 密集场景 asyncio 足够；CPU 密集走 Celery 任务队列 | ✓✓ 强事务、大规模并发、多团队工程化 |
| 原型到 MVP 迭代速度 | ✓✓ 快 | △ 慢 |
| 长期大规模演进 | △ 需引入类型约束（pydantic/mypy） | ✓✓ 强 |

结论：**Python（FastAPI）为后端主栈**（已决定，权衡过程见 ADR）——本应用的差异化核心是 AI 规划助手与轨迹数据处理，两者均为 Python 生态强项；当前负载以 IO 密集为主，FastAPI 异步 + Celery 异步任务即可覆盖。Java 的强项（强事务、超大规模并发）在本应用当前阶段非瓶颈；若未来扩展交易类能力（装备电商、报名付费），可按模块引入 Java 微服务，通过网关共存。完整权衡见 [ADR：技术栈选型](../notes/2026-11-13-tech-stack-choice.md)。

## 6. 后端架构与核心契约（草案）

模块划分、关键时序、部署拓扑与完整数据结构（DDL + Pydantic 契约、Redis 键设计）详见 [system-design.md](system-design.md)。概要：

模块划分：`api-gateway`（鉴权/限流）、`agent`（LLM 编排与工具调用）、`route-service`（路线库/检索/匹配）、`trip-service`（计划）、`profile-service`（画像/装备）、`media-service`（视频/审核/对象存储）、`worker`（Celery：轨迹处理、天气拉取、推荐离线计算）。

技术栈：FastAPI + PostgreSQL（PostGIS）+ Redis + 对象存储 + Celery + WebSocket（对话流式输出）+ LLM 网关（模型抽象层，可切换国产大模型供应商）。

核心数据模型：`User`、`UserProfile`（偏好/经验/体能）、`GearItem`（含型号库引用）、`Route`（轨迹 GPX、难度、地貌标签、清晰度）、`TripPlan`、`Spot`（地标/景点）、`AssistantSession`。

关键 API（草案）：`POST /auth/login`、`GET/PUT /profile`、`GET /gear-catalog`、`PUT /gear-list`、`GET /routes?filters`、`GET /routes/{id}`（含高程/配速/地形数据）、`POST /agent/chat`（SSE 流式）、`POST /agent/plan`（生成计划）、`GET /weather?loc`、`GET /alerts?loc`。

## 7. 非功能需求

性能：首屏视频背景渐进加载（低清海报帧优先）、路线详情接口 P95 < 300ms、AI 对话首 token < 1.5s。安全：登录态 JWT + 刷新令牌、UGC 视频先审后发、接口限流。合规：境内地图需使用有审图号的地图 SDK；位置权限最小化采集；运动健康数据仅用于推荐计算。兼容：iOS 14+、Android 8+、鸿蒙 NEXT、微信小程序基础库 2.30+。

## 8. 安全规格（网络安全基线）

传输与网关：全站 TLS 1.3 + HSTS；App 端证书锁定；WAF + 接口限流（登录 / AI 对话 / 上传接口独立阈值）；CDN 回源鉴权。

认证与会话：JWT 短时效 + 刷新令牌轮换与复用检测；第三方登录（Apple / 微信 / 华为）服务端票据与签名校验；设备指纹绑定与异常登录检测；账号注销与数据删除闭环。

输入与注入防护：pydantic 全量入参校验；ORM 参数化杜绝 SQL 注入；**服务端外联请求仅允许 http/https，请求前校验 host 并拒绝 localhost、环回、私有与保留地址**（天气 / 地图等第三方拉取的 SSRF 防护）；文件路径与模板拼接前规范化。

LLM 安全：系统提示与用户输入隔离；工具调用白名单化（仅预注册函数可被模型触发）；输出内容过滤与敏感词审查；每会话 token 成本限额与滥用检测。

上传与媒体：类型 / 大小白名单 + magic number 校验；转码剥离元数据；UGC 视频先审后发（机审 + 人审）；媒体走独立域名与签名 URL。

数据安全：数据库与对象存储静态加密；位置与健康数据最小化采集并脱敏存储；日志脱敏与审计留痕；备份加密。

依赖与部署：pip-audit 依赖扫描与容器镜像扫描进 CI；密钥经 KMS / 环境注入，不入仓库；最小权限 IAM。

合规：个人信息保护法（告知同意、最小必要、可删除）；地图使用有审图号的 SDK；生成式与推荐算法按监管要求备案。
