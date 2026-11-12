# 2026-11-13 · RAG 知识库、记忆系统与澄清引导

## 新增

- `doc/notes/2026-11-13-rag-memory-clarification.md`：ADR——pgvector 混合检索（bge-m3 + FTS + RRF + 重排）、三层记忆系统（会话短期/滚动摘要/长期事实，用户可见可删）、澄清状态机（逐项追问、上限 3 轮）
- `doc/spec/system-design.md`：§2 assistant 职责扩展（RAG/记忆/澄清）；§3 新增 RAG 检索与澄清时序；§5 新增 5.5 知识库/记忆/澄清 DDL（kb_docs、kb_chunks + pgvector HNSW、user_memory）与 ClarifyState/MemoryFact/RetrievedChunk Pydantic 契约、SSE 事件类型

## 决策

- 向量存储选 pgvector（放弃独立向量库）；混合检索放弃纯向量；记忆改为用户可见可删（放弃全自动不可见记忆）；澄清放弃一次性全槽位追问
