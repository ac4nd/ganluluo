# 2026-11-13 · 系统设计文档

## 新增

- `doc/spec/system-design.md`：架构总览（模块化单体拓扑）、7 模块职责与禁区、关键时序（AI 对话 SSE 流式 + 工具调用、轨迹 Celery 管线）、匹配度评分公式、技术选型明细（后端组件与版本底线、四端仓库结构）、数据结构（9 张核心表 DDL + Pydantic 契约 + Redis 键设计）、部署拓扑与测试策略

## 决策

- `doc/notes/2026-11-13-monolith-first.md`：后端采用模块化单体优先，域边界即未来微服务边界，演进触发条件已定义

## 变更

- `doc/spec/specification.md` §6 增加对 system-design.md 的引用
