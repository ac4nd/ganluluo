# ADR 2026-11-13 · 移动端三系统原生重写 + 轻端统一 + 安全强化

> 状态：生效中。取代 [技术栈选型 ADR](2026-11-13-tech-stack-choice.md) 中的**前端部分**（uni-app 四端一壳方案废弃）；该 ADR 的后端部分（Python/FastAPI）继续有效。

## 背景

原型验证阶段结束后进入工程化。产品要求调整：移动端三大系统（iOS / 安卓 / 鸿蒙）要「精致和有特点」——充分表达系统级特性（iOS 液态玻璃、鸿蒙实况窗与星闪投送、安卓的灵活定制），跨端框架（uni-app / Flutter / RN）无法或难以暴露这些系统能力；小程序与网页端则「易用和方便」，可统一适配。后端确定 Python FastAPI，并把网络安全作为一等验收项。

## 决定

- **iOS**：SwiftUI + iOS 26 SDK。系统特性：Liquid Glass `glassEffect` 材质（导航/卡片/播放控件）、灵动岛实况（进行中徒步的里程/配速/海拔）、Sign in with Apple、WeatherKit、MapKit、HealthKit（徒步记录写入）、Core Motion 触感与海拔流。
- **安卓**：Jetpack Compose + Material 3。系统特性：Material You 动态取色（跟随壁纸主题化）、Predictive back 手势、edge-to-edge、Glance 小组件（下次计划/天气卡）、WorkManager（轨迹离线同步）、Media3（背景视频）。
- **鸿蒙 NEXT**：ArkUI + ArkTS。系统特性：实况窗 Live View、**星闪投送**（轨迹/照片经 NearLink 向车机、平板秒传）、万能卡片（天气/计划服务卡片）、元服务（免安装按需拉起）、分布式跨端接续（手机规划 → 平板续看）、HarmonyOS Sans。
- **小程序 + 网页**：Taro 4（React + TS）一套代码同构微信小程序与 H5；易用优先——精简动效、接口预取、分享卡片；Canvas 特效提供轻量版（降级矩阵见下）。
- **一致性基建**：设计令牌单一来源（`protype/assets/style.css` 令牌导出 tokens.json，CI 生成 iOS Asset Catalog / Compose Theme / ArkUI resource / Web CSS variables）；API 客户端由 OpenAPI 契约生成各端；后端 API 契约见 [specification.md](../spec/specification.md) §6。

## 特效降级矩阵（同一设计，各端表达）

| 特效 | iOS | 安卓 | 鸿蒙 | 小程序 / H5 |
|---|---|---|---|---|
| 地球轮廓 + 航线 | SwiftUI Canvas（移植原型引擎） | Compose Canvas | ArkUI Canvas | canvas 2d 直接复用 |
| cinema 视频背景 | AVPlayerLayer | media3 ExoPlayer | ArkUI Video | video 组件 / H5 video |
| 玻璃材质 | Liquid Glass glassEffect | M3 表面色 + blur | 模糊材质 | backdrop-filter（H5）/ 半透明（小程序） |
| 高程/配速图表 | Swift Charts | Compose 自绘 | ArkUI Canvas | SVG / canvas |

## 放弃的替代方案与原因

- **uni-app 四端一壳**（前案）：覆盖全但系统特性表达受限——Liquid Glass、实况窗、星闪投送、万能卡片等系统级能力无法通过跨端层完整暴露，与「精致和有特点」的目标冲突。其 canvas 引擎资产（cinema、地球轮廓）按降级矩阵继续复用。
- **Flutter / RN 跨端**：同上理由，且鸿蒙侧依赖第三方适配节奏。
- 网页端单列独立工程：与小程序高度同构，合并为 Taro 一套可减少一半轻端成本。

## 代价与验证

- 代价：三套移动端 UI 代码 + 一套轻端代码；一致性依赖令牌单一来源与组件规格走查。
- 验收：三端各按「系统特性清单」逐项走查（iOS 液态玻璃/灵动岛、安卓取色/预测性返回、鸿蒙实况窗/星闪/万能卡片）；主流程四端跑通；Lighthouse/系统性能面板达标。
- 安全基线与后端强化见 [specification.md](../spec/specification.md) §8。
