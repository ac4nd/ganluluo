# 2026-11-13 · 前端原生多端决策 + 安全规格

## 变更

- `doc/spec/specification.md`：§4 前端架构改为**各端原生重写**（iOS SwiftUI / 安卓 Compose / 鸿蒙 ArkUI，充分表达液态玻璃、实况窗、星闪投送、万能卡片、Material You 等系统特性）+ 小程序与网页由 Taro 4 统一适配；新增 §8 安全规格（传输/认证/注入防护/SSRF/LLM 安全/上传/数据/依赖/合规九个基线）
- `doc/notes/2026-11-13-native-frontend-security.md`：新增 ADR，取代前案中 uni-app 四端一壳的前端决定；后端 Python/FastAPI 决定不变并强化安全验收
- `doc/notes/2026-11-13-tech-stack-choice.md`：标注前端部分被取代、后端部分继续有效

## 未变更

- 后端 Python FastAPI 主栈与架构模块划分（§5/§6）
- 设计令牌单一来源与原型资产复用策略（§3）
