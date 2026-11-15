# M6-media · 媒体域实现计划（UGC 上传 / 审核 / 对象存储）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** 新建 media 域（`app/domains/media/`）：MinIO 预签名直传 + 登记 + **先审后发**状态机（pending/approved/rejected，合规硬要求见 specification §7/§8）+ 签名下载 URL + admin 审核 API。

**Architecture:** 媒体域持有 `media_items` 表与对象存取层；预签名直传（服务端不碰文件流，仅签 URL 与登记元数据）；`MediaStore` 协议抽象（`MinioMediaStore` 生产 / `FakeMediaStore` 测试，与 track_store/Provider 模式一致）。审核状态机：登记 → pending → approved（可分发签名 URL）/ rejected。magic number 校验在登记时由服务端读对象头部执行。

**Tech Stack:** 新依赖 `minio`（Python SDK）。远程 MinIO：47.107.160.31:9000（minioadmin/minioadmin），自建 bucket `ganluluo`（不动共享 godlikeagents）。

## Global Constraints

- 全部测试保持绿色（159 基线）；覆盖率 ≥ 93% 不回退
- 迁移只增不改：从 **0014** 起（当前 head 0013）
- 上传白名单：`.mp4/.mov/.webm`（video/mp4, video/quicktime, video/webm）≤ 200MB；登记时 magic number 复核（ftyp box），不符 → 422 并删除对象
- 签名下载 URL 仅 approved 可取（pending/rejected → 403）；全部端点鉴权；admin 端点走 get_current_admin
- MinIO 连接只走环境变量（GL_MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET，.env.example 记录）；凭据纪律照旧
- 提交前缀白名单

---

### Task 1: MediaItem 数据层 + MediaStore 抽象

**Files:**
- Create: `backend/app/models/media.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0014_media_items.py`
- Create: `backend/app/domains/media/media_store.py`
- Create: `backend/tests/test_media_store.py`
- Modify: `backend/pyproject.toml`（dependencies 加 `minio>=7.2`）
- Modify: `backend/app/core/config.py` + `backend/.env.example`（GL_MINIO_* 四项）

**Interfaces:**
- 模型 `MediaItem(id, user_id FK users CASCADE index, kind: str(8) 'video' MVP 常量, object_key str(256) unique, status str(8) 'pending'/'approved'/'rejected' default 'pending', size_bytes int, mime str(64), created_at server_default now())`
- `MediaStore` 协议：`presign_put(key, content_type) -> str`；`presign_get(key, expires_s) -> str`；`remove(key) -> None`；`head_bytes(key, n) -> bytes`
- `MinioMediaStore(endpoint, access_key, secret_key, bucket)` 实现（presign_* 用 SDK 的 presigned_put_object/get_object，bucket 不存在时 ensure_bucket() 幂等创建）
- `FakeMediaStore(dict-backed)`：同接口，内存 dict + 可注入 presign 前缀——测试用

- [ ] **Step 1: 失败测试**（Fake roundtrip presign 字符串包含 key；head_bytes 读回写入内容前缀）→ **Step 2-4: 红→实现→绿**（全量 159→163±） → **Step 5: Commit** `feat: media item model and media store abstraction`

---

### Task 2: 用户 API（presign / 登记 / 列表 / 下载 URL）

**Files:**
- Create: `backend/app/domains/media/media_router.py`
- Modify: `backend/app/main.py`（include，prefix="/media"，tags=["media"]）
- Create: `backend/app/domains/media/media_service.py`（登记校验/状态机/URL 发放）
- Create: `backend/tests/test_media_api.py`

**Interfaces:**
- `POST /media/presign` body `{filename: str, content_type: str, size: int}`：白名单（扩展名+content_type+size≤200MB）→ 422；通过 → `{upload_url, object_key, expires_in}`（object_key `media/{uuid4hex}{ext}`）
- `POST /media` body `{object_key, filename, size}`：object_key 必须匹配我们签发的格式（正则白名单，防任意 key 注入）→ `head_bytes` 读 16 字节 magic number 校验（mp4: bytes 4-8 == b'ftyp'；webm: b'\x1aE\xdf\xa3'；quicktime 同 mp4 ftyp）→ 不符 422 并 `remove` 对象；通过 → MediaItem(pending) → 201 `{id, status}`
- `GET /media/my` → 本人列表 [{id, kind, status, size_bytes, created_at}]（id desc）
- `GET /media/{id}/url`：本人 + status=='approved' → `{url, expires_in}`；pending/rejected → 403 "未通过审核"；他人 404
- store 依赖注入：`get_media_store()` 依赖（app.dependency_overrides 注入 FakeMediaStore，与 agent_provider 模式一致）

- [ ] **Step 1: 失败测试**（presign 白名单三拒两过；登记 magic number 两态含不符删对象；列表；URL 三态 approved/pending 403/他人 404；未登录 401） → **Step 2-4: 红→实现→绿**（全量 163→172±） → **Step 5: Commit** `feat: media upload pipeline with presigned direct upload`

---

### Task 3: admin 审核 API

**Files:**
- Modify: `backend/app/domains/admin/admin_router.py`
- Create: `backend/tests/test_media_admin.py`

**Interfaces:**
- `GET /admin/media?status=&page=&size=`：分页列表（默认 pending），item [{id, user_id, kind, status, size_bytes, created_at}]
- `POST /admin/media/{id}/review` body `{action: 'approve'|'reject'}`：pending → 对应状态（非 pending 400 "已审核过"）；404；返回 {id, status}
- rejected 不删对象（留证）；登记白名单与审核流复用 media_service

- [ ] **Step 1: 失败测试**（403 链路；pending 列表过滤；approve/reject 两态；重复审核 400；404） → **Step 2-4: 红→实现→绿**（全量 172→179±） → **Step 5: Commit** `feat: admin media review API`

---

### Task 4: 质量门 + 收尾

- [ ] openapi.json 重新生成（/media/*、/admin/media*）；全量 pytest / ruff / mypy / 覆盖率 ≥93%
- [ ] 台账 + defer 票：机审（转码/元数据剥离/视频抽帧检测）、CDN 独立域名分发、photo kind 扩展、远程 MinIO 集成冒烟（integration_pg.py 加 minio 检查）
- [ ] Commit `chore: m6-media quality gates`

---

## Self-Review 记录

- 先审后发是合规硬要求：approved 之前任何签名 URL 不可得（download 端点 403），presign_put URL 只能上传不能读
- object_key 正则白名单防"签发他人 key/穿越 key"（presign 端点自己生成 key，登记端点校验格式）
- magic number 失败即删对象：不给未通过校验的残留文件占用存储
- MinIO 不在单测环境：FakeMediaStore 注入 + 远程集成冒烟留票，与 track_store/Provider 先例同构
- users 无 FK 变更：media_items 独立表，不影响既有迁移链
