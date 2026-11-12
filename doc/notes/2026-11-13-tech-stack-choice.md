# ADR 2026-11-13 · 前端四端方案与后端语言选型

> 状态（2026-11-13 更新）：本文的**前端部分（uni-app 四端一壳）已被 [原生多端方案](2026-11-13-native-frontend-security.md) 取代**——移动端三系统各端原生重写、小程序+网页由 Taro 统一适配。本文的**后端部分（Python/FastAPI）继续有效**，权衡分析仍是后端选型的依据。

## 背景

V2 进入工程化准备阶段。前端需同时覆盖 iOS、安卓、鸿蒙 NEXT、微信小程序四端；后端在 Python（FastAPI）与 Java（Spring Boot）之间二选一。项目差异化的两个技术重心：AI 规划助手（LLM 编排/检索/工具调用）与轨迹地理处理；原型已完成的核心交互资产是两个平台无关的 Canvas2D 引擎（Hero Cinema 视频背景层、地球轮廓+探险航线层，见 [specification.md](../spec/specification.md) §2/§4）。

## 决定

- 前端主壳：**uni-app（Vue3 + TypeScript + Pinia）**，一套工程覆盖 iOS / Android / 鸿蒙 NEXT / 微信小程序 / H5。
- 重特效模块（cinema 视频背景层、地球轮廓层）以**平台无关 Canvas2D 模块**迁移，为小程序 `canvas type="2d"` 接口差异封装适配器；地图/轨迹按端接原生 SDK，收敛为 `MapService` 接口。
- 后端主栈：**Python + FastAPI**，配套 PostgreSQL(PostGIS)、Redis、Celery、对象存储、WebSocket 流式、LLM 网关。

## 放弃的替代方案与原因

- **Flutter 全端**：iOS/Android/鸿蒙表现强、CustomPainter 与原型 Canvas2D 同构，但小程序无法运行 Flutter 运行时——四端覆盖出现缺口，需额外维护第五套小程序 UI 栈。若小程序降级为 H5 嵌入，Flutter 升为备选。
- **React Native + RNOH + Taro**：TS 单语言统一且 RNOH 已可用，但 App（RN 组件）与小程序（Taro 组件）是两套 UI 表达，特效层需桥接两套图形 API，成本高于 uni-app 的 canvas 直用。
- **全原生四端**：体验上限最高，但四套团队与四倍维护成本，与当前团队规模和迭代节奏不匹配。
- **后端 Java（Spring Boot）**：强事务与大规模并发是长项，但本项目核心负载（LLM 编排、geopandas 轨迹计算、sklearn 匹配实验）均为 Python 生态强项，且当前无强事务交易场景。保留演进路径：未来装备电商/报名付费等强事务模块可按需引入 Java 微服务与 Python 服务共存。

## 代价与验证

- uni-app 依赖 HBuilderX 的鸿蒙 App 能力与小程序 canvas 2d 差异适配：验收标准为四端各跑通「登录 → 画像三步 → 首页视频背景 → 路线详情」主流程，且 cinema 层帧率 ≥ 24fps（中端真机）。
- Python 后端需 pydantic + mypy 严格模式约束类型，规避动态类型在多人协作下的腐化。
- 相关规格：[specification.md](../spec/specification.md) §4/§5/§6。
