# 赶路咯 · AI 徒步助手 — 交互原型 V1

> 环保绿 Dark 主题。视觉语言完全贴合 `design/` 文件夹的界面设计：
> 暗色屏幕、荧光绿强调色、玻璃拟态浮层卡片、发光药丸按钮、倾斜 3D 地图、悬浮胶囊底部导航、聊天气泡、发光星球。
> 原设计中的荧光黄绿（Lime）整体调整为**环保绿色**（`#A4F150 → #5FD23C` 渐变）。

## 打开方式

直接用浏览器打开 `index.html`（总览画板，10 台手机并排展示）；
或单独打开任一页面。页面间可点击跳转，形成可点走的核心流程。

## 页面清单

| # | 文件 | 页面 | 对应需求 |
|---|------|------|----------|
| 01 | `01-login.html` | 欢迎 / 登录 | 环保绿**液态玻璃能量球**（WebGL：菲涅尔边缘折射 + FBM 噪声流体 + 方向性受光/临边压暗/镜面高光营造体积感；编译失败自动切换兜底着色器，无 WebGL 时 Canvas 2D 降级）+ 账号登录 + 画像注册入口 |
| 02 | `02-onboard-sport.html` | 画像 1/3 运动偏好 | 徒步 / 越野跑 / 攀岩 / 溯溪…**图标 + 文字**区分运动类型，可点选 |
| 03 | `03-onboard-exp.html` | 画像 2/3 经验与体能 | 徒步经验四档、体能五级自评（供配速与里程估算） |
| 04 | `04-onboard-gear.html` | 画像 3/3 装备清单 | **三级结构**：分类（8 类 41 项）→ 装备（含细分维度，如登山鞋的低/中/高帮·碳板·防水·透气·耐磨）→ **预设品牌型号图卡**（约 80 个常见品牌/型号）+ **添加自定义装备**；勾选参与安全匹配 |
| 05 | `05-home.html` | 首页 | AI 为你挑选 / 附近热门 / 最近足迹，**缩略卡片**点击进详情 |
| 06 | `06-ai-plan-chat.html` | AI 规划对话 | 「附近有什么路线」→ 核查**天气 + 灾害预警** → 结合**画像筛选** → 缩略卡片 + 匹配度 |
| 07 | `07-plan-trip.html` | 行程计划 | 日期轴、倾斜 3D 地图轨迹、计划卡片（集合时间/里程/爬升/难度）、装备提醒 |
| 08 | `08-route-detail.html` | 路线详情 | 对标两步路：**高程变化折线图、建议配速折线图、地形变化分析、3D 影像地图轨迹飞行（可播放）**、轨迹清晰度 / 下撤点 / 安全提醒 |
| 09 | `09-profile.html` | 我的画像 | 画像摘要、足迹统计、偏好与装备维护入口 |
| 10 | `10-routes.html` | 成熟路线库 | 难度 / 地形 / 轨迹清晰度标签化，类型筛选 |

## 设计令牌（`assets/style.css`）

- 主色 `--accent:#A4F150`，渐变按钮 `#C2F96A → #5FD23C`，发光 `rgba(140,235,80,.38)`
- 屏幕底 `#0C110A`（带绿色晕光），卡片 `#161E0F / #1D2712`
- 文字 `#F1F7E6 / #A7B494 / #74825F`；警示 `#FFC857`；危险 `#FF6D5A`
- 手机壳 390×844、圆角 56、灵动岛、状态栏、Home 条与 design 一致

## 运动图标库（SVG Sprite）

统一 24×24 线性图标：`currentColor` / `stroke-width:1.8` / 圆角端点。
源文件 [`assets/sprite.html`](assets/sprite.html)，已内嵌到用到图标的页面（file:// 下 `<use>` 不能跨文件引用）。

| 名称 | Symbol ID |
|---|---|
| 徒步 | `icon-hiking` |
| 攀岩 | `icon-climbing` |
| 溯溪 | `icon-stream` |
| 越野跑 | `icon-trail-running` |
| 骑行 | `icon-cycling` |
| 露营 | `icon-camping` |
| 滑雪 | `icon-skiing` |
| 定向越野 | `icon-orienteering` |

用法：`<svg class="icon"><use href="#icon-hiking"/></svg>`；
尺寸随字号（`1em`），`.icon-lg`（24px）/ `.icon-md`（21px）用于图标位。

另有 26 个**装备产品图形**（`ic-boot` / `ic-axe` / `ic-pole` / `ic-pack` / `ic-jacket` / `ic-tee` / `ic-pants` / `ic-lamp` / `ic-watch` / `ic-battery` / `ic-cap` / `ic-buff` / `ic-helmet` / `ic-glove` / `ic-knee` / `ic-rain` / `ic-radio` / `ic-tent` / `ic-sleep` / `ic-mat` / `ic-stove` / `ic-bottle` / `ic-filter` / `ic-kit` / `ic-blanket` / `ic-spray`），用于 04 页型号图卡缩略图。

## iOS Liquid Glass 适配（iOS 26/27 透明玻璃）

- **环境色斑**：`.screen::before` 常驻绿/青光斑垫底，让玻璃材质有内容可折射
- **真·玻璃层**（`backdrop-filter: blur+saturate` + 内高光描边）：悬浮底部导航、聊天输入条、地图计划卡、标题胶囊、圆形图标钮
- **轻玻璃层**（半透明白 + 内高光环，无 blur 保性能）：全部卡片、选项、chips、聊天气泡
- **荧光控件**：主按钮 / 选中态加 `inset 0 1px 0` 高光，模拟玻璃折射顶光
- 提供 `.glass` 工具类；`--glass-line / --glass-hi` 令牌可整体调节玻璃浓度
- 兼容写法：全部带 `-webkit-backdrop-filter` 前缀

## 多平台适配（iOS / 鸿蒙 / 安卓）

同一套环保绿品牌色与信息架构，按各系统交互惯例分别表达，对照画板见 [`platforms.html`](platforms.html)：

| 平台 | 页面 | 系统语言表达 |
|---|---|---|
| iOS 26 | `05` / `08` | 灵动岛 · 悬浮胶囊底部导航 · Liquid Glass 玻璃浮层 |
| 鸿蒙 NEXT | `h-home.html` / `h-detail.html` | **实况窗**胶囊（顶部呼吸点）· **万能卡片**（天气/计划服务卡）· 页签**呼吸点指示器** · HarmonyOS Sans · 24 连续圆角卡片 |
| 安卓 M3 | `a-home.html` / `a-detail.html` | **打孔摄像头** · Material 3 底部导航（**药丸指示器**）· **FAB**（AI 规划）· Roboto · 16dp 卡片圆角 · Filled+Tonal 双按钮 |

平台组件样式（`.hm-live` / `.nav-hm` / `.hm-widgets` / `.cam-dot` / `.nav-md` / `.fab` / `.btn-tonal` / `.m3-card`）集中于 `assets/style.css` 末尾「多平台适配」段落；`.phone.ph-android / .ph-harmony` 切换平台字体栈。

## 说明

- 所有图形（山野场景、地图、图表、3D 地形）均为内联 SVG 手绘，无外部依赖，可离线打开。
- 页面数据（路线名、里程、天气）为演示样例。
- 登录页能量球为单文件 WebGL 片元着色器实现（三层域扭曲 FBM 模拟液态流体，`refract()` 模拟玻璃折射，受光方向调制的菲涅尔边缘 + 临边压暗 + Blinn 高光斑 + 球外贴边溢光共同塑造立体感），主着色器编译失败自动降级为兜底渐变着色器，仍不支持 WebGL 时降级 Canvas 2D；`prefers-reduced-motion` 时静止。零外部依赖。
- 08 页 3D 演示点击播放按钮：轨迹线飞行绘制 + 视角缓摆 + 进度条，模拟"根据轨迹播放的 3D 影像地图"。
