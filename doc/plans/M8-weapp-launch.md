# M8-weapp-launch · 小程序端形态修正实现计划（安卓 UI / 一键登录 / 游客模式）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** 按微信小程序真实形态修正轻端：① 后端微信一键登录端点；② 启动序列（隐私政策 → 位置授权 → 主页）+ 一键登录页（替代邮箱表单的 weapp 登录路径）；③ UI 对齐安卓原型（a-home/a-detail Material 3 语言：药丸导航/FAB/卡片层级）；④ 游客模式（未登录可浏览轨迹，受限功能点击提示去登录）。

**Architecture:** 微信登录：前端 `Taro.login()` 取 code → `POST /auth/wechat-login {code}` → 后端换 openid（配置了 GL_WECHAT_APPID/SECRET 走真实 jscode2session；未配置走 **dev mock**：openid=`wxmock_`+code 哈希，供开发/测试）→ 按 oauth_provider='wechat'+oauth_subject=openid 查/建用户（users 两列 M1 已预留，无迁移）→ 签发 TokenPair。UI 基准：protype/a-home.html、a-detail.html、platforms.html 安卓列（药丸底部导航/FAB/顶部大标题/打孔屏状态栏）。

**Tech Stack:** 后端无新依赖（httpx 已有）；前端无新依赖。

## Global Constraints

- 双目标构建全绿基线（tsc/vitest/build:h5/build:weapp）；后端 195 基线不回退
- H5 端保留邮箱登录（平台分支 TARO_ENV），weapp 走一键登录——两端口径在登录页分叉，其余页面 UI 改版双端生效
- 凭据纪律：GL_WECHAT_APPID/SECRET 只走 env；mock 模式不得在生产配置下可达（env=prod 且未配置微信 → 登录端点 503 拒绝）
- 提交前缀白名单；主会话 Mimosa 全仓拦截已知——**实现提交由子代理执行**

---

### Task 1: 后端微信一键登录

**Files:**
- Modify: `backend/app/core/config.py`（wechat_appid/wechat_secret: str = ""）
- Modify: `backend/app/domains/auth/service.py`（get_or_create_by_oauth(session, provider, subject, nickname) -> User）
- Modify: `backend/app/domains/auth/schemas.py`（WechatLoginIn: code str 长度限制; 可选 nickname）
- Modify: `backend/app/domains/auth/router.py`（POST /auth/wechat-login）
- Modify: `backend/.env.example`（GL_WECHAT_* 注释行）
- Create: `backend/tests/test_wechat_login.py`

**Interfaces:**
- `POST /auth/wechat-login` body `{code: str(1..128), nickname?: str}` → 200 TokenPair
  - 配置齐全：httpx GET `https://api.weixin.qq.com/sns/jscode2session?appid&secret&js_code&grant_type=authorization_code`（外联走 assert_safe_external_url，https 外部 host 合法）；微信返回 errcode → 401 "微信登录失败"；openid → 查/建用户
  - 未配置：env!="prod" → mock（openid = "wxmock_" + sha256(code)[:24]，确定性——同 code 同用户）；env=="prod" → 503 "微信登录未配置"
  - 查/建：oauth_provider='wechat' + oauth_subject=openid 命中 → 返回；未命中 → 建 User(nickname=参数或"徒步者"+4位随机, oauth_*)+seed_tiers；软删除用户命中 → 视为不存在（404 语义统一 401）
- 测试：mock 建新用户/同 code 复用同用户（id 相同）/TokenPair 可用（/auth/me）/prod 未配置 503/微信 errcode 路径（mock httpx）
- [ ] Commit `feat: wechat one-tap login with dev mock`

---

### Task 2: 启动序列 + 一键登录页

**Files:**
- Create: `miniapp/src/pages/wechat-login/*`
- Modify: `miniapp/src/app.ts`（或入口页：启动序列编排）
- Modify: `miniapp/src/api/auth.ts`（wechatLogin(code, nickname?)）
- Modify: login 页（weapp 显示"微信一键登录"入口 → wechat-login 页；H5 保留邮箱表单）

**要点:**
- 启动序列（app 级一次性）：① 隐私政策弹窗（首次：同意/不同意——不同意 toast 并保留可重进）→ ② `Taro.getLocation` 触发平台位置授权弹窗（拒绝可继续，首页定位功能置灰）→ 主页；已完成标记存 storage 不再重复
- 一键登录页：隐私协议+用户协议勾选框（未勾选点击 → 提示）+ 微信大按钮「一键登录」→ `Taro.login()` code → wechatLogin() → setTokenPair → reLaunch 首页；失败显 detail
- H5：wechat-login 页显示"请使用微信小程序打开"降级卡；login 页 TARO_ENV==='weapp' 时主按钮变"微信一键登录"
- [ ] Commit `feat(miniapp): privacy and location startup flow, wechat one-tap login`

---

### Task 3: 安卓 UI 改版

**Files:**
- Modify: `miniapp/src/app.scss`（安卓语言：底部导航=4 tab 药丸选中态/FAB/卡片圆角阴影层级/顶部大标题）
- Modify: 各页 scss/tsx 导航与按钮形态（index/routes/route-detail/chat/trips/profile/gear）

**要点:**
- 基准 protype/a-home.html + a-detail.html：底部导航居中 4 图标+选中药丸底、AI 对话改 **FAB**（右下悬浮圆钮）、页面顶部大标题（非居中 pill）、卡片更浅底+更明显圆角、状态栏打孔屏布局
- weapp 顶部原生导航栏保留（app.config navigationBar 配置），页内大标题
- 色彩仍走 tokens.css（安卓改版不改色板，改组件形态与布局）
- 截图对照 a-home 逐页微调
- [ ] Commit `feat(miniapp): android-flavored UI (pill nav, FAB, cards)`

---

### Task 4: 游客模式

**Files:**
- Create: `miniapp/src/api/guard.ts`（requireAuth(interaction) 工具：无 token → 半屏/toast"登录后可用"+"去登录"按钮 → weapp 跳 wechat-login / H5 跳 login）
- Modify: chat/trips/gear/profile/onboard 四类页面接入守卫；routes/route-detail 保持公开浏览（匹配度/加入计划按钮点击时守卫）

**要点:**
- guest 可用：路线库、路线详情浏览（后端 GET 本就公开）
- guest 受限（点击拦截）：AI 对话发送、生成计划、行程操作、装备保存、画像保存、引导流
- 拦截交互：Taro.showModal("登录后可用" + 确认=去登录 / 取消)——统一组件化，文案一致
- [ ] Commit `feat(miniapp): guest browsing with auth-gated actions`

---

### Task 5: 质量门 + 收尾

- [ ] 四道门禁 + 后端 pytest 全绿；H5+weapp 截图（启动序列 mock、一键登录页、安卓导航、游客拦截弹窗）
- [ ] 台账 + defer 票：真实 appid 联调、手机号授权增强、H5 一键登录（微信开放平台）、安卓动态取色
- [ ] Commit `chore: m8 quality gates`

---

## Self-Review 记录

- email 列可空（UserOut.email: any）——微信建用户 email/phone 均空，前端 me() 渲染需容错（nickname 兜底）
- dev mock 的确定性 openid 保证测试幂等；prod 拒绝 mock 防误用
- 位置授权拒绝不阻塞（微信规范：权限拒绝后引导设置页是后续票）
- 安卓改版不改色板只改形态——令牌链不破坏
