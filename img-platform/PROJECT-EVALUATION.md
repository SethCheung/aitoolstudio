# img-platform 项目评估报告

> 评估时间：2026-05-04 · 评估人：废才（资深产品经理 / 全栈教练视角）
> 评估对象：`/img-platform`（FastAPI 后端 + Vue 3 前端 + 文件 Profiles 配置）
> 代码量：前端视图 ~3.3k 行 / 后端 API+Services ~2k 行

> **状态说明（2026-05-05）**：本报告是历史评估快照，部分结论已过期。Admin/Profile 鉴权、前端构建错误、`DATABASE_URL` 环境化、项目缩略图、Generate 原图预览等已在后续迭代中处理。仍有效的高优先级风险包括：`/minimax-output` 静态目录公开、Profile 配置文件可能承载 API Key、缺少测试和迁移体系。最新安全清单见仓库根目录 `SECURITY.md`。

---

## 一、总评（TL;DR）

**分数：62 / 100 · 等级：C+（可跑、不能放心上生产）**

这是一个**内网协作工具级别**的实现：功能闭环是通的（登录、生图/语音/视频/音乐、历史、Admin UI、Profile 路由），但在**安全、架构清晰度、可维护性**上有若干**必须修复**的红线问题。现在部署到公网或多人共用场景，会翻车。

**三件最紧急的事（按优先级）：**
1. 🔴 **Admin API 完全没有鉴权** —— `/api/admin/users` 任何人都能增删用户、提权
2. 🔴 **前端依赖版本是幻觉/超前版本** —— `vite@^8`、`typescript@~6`、`vue-router@^5`、`@types/node@^24` 都不存在或高度可疑，安装/构建会出问题
3. 🟠 **Profile 配置（含 API Key 明文）直接写 JSON 文件** —— 无加密、无审计、无版本控制隔离

---

## 二、亮点（做对的事）

- ✅ JWT Secret **强制从 env 读**，没有硬编码兜底 —— `core/security.py` 直接 raise，这点赞一个
- ✅ 登录接口有 **slowapi 速率限制**（5/min/IP），防暴力
- ✅ 密码 **bcrypt** 哈希，不是 MD5/SHA1
- ✅ CORS 用 **白名单 + regex**，没有 `allow_origins=['*']` + `credentials=True` 的致命组合
- ✅ Profile 抽象合理，支持 HTTP / CLI 双模式，`get_profile_for_model` 按 priority 路由的思路是对的
- ✅ 前端用 **Pinia + Vue Router + axios 拦截器**，401 自动跳登录，结构标准
- ✅ 错误日志用 `logger.exception`，不向前端泄漏 traceback（image.py 的做法是对的）
- ✅ Profile 列表接口 **脱敏 api_key**（只返回 `****xxxx`）

---

## 三、严重问题（必须修）

### 🔴 P0-1：Admin API 无鉴权
**位置**：`backend/api/admin.py`

```python
@router.get("/api/admin/users")
async def list_users(db: Session = Depends(get_db)):   # ← 没 get_current_user
@router.post("/api/admin/users")
async def create_user(req, db):                         # ← 没 get_current_user
@router.put("/api/admin/users/{user_id}")               # ← 没 get_current_user
@router.delete("/api/admin/users/{user_id}")            # ← 没 get_current_user
```
同样的问题也出现在 `api/profiles.py`（创建/更新/删除 profile 的接口，基于 `admin.py` 引用的 fetch 路径推断）—— 这是一个**任何拿到 URL 的人都能把自己提权为 admin、甚至删除 api key** 的设施。

**另外**：`GET /admin` 直接返回的 HTML 管理页也是**完全无鉴权**的静态页，虽然 HTML 本身不敏感，但它把所有后台 API 路径暴露给爬虫。

**修法**（最小改动）：
```python
from api.auth import get_current_user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user

@router.get("/api/admin/users")
async def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    ...
```
所有 `/api/admin/*` 和 `/api/profiles/*`（除了只读的 models 列表）都必须挂 `require_admin`。

---

### 🔴 P0-2：前端依赖版本有幻觉
**位置**：`frontend/package.json`

| 包 | 声明版本 | 现实 |
|---|---|---|
| `vite` | `^8.0.10` | Vite 最新是 5.x/6.x，**没有 8** |
| `typescript` | `~6.0.2` | TypeScript 最新是 5.x，**没有 6** |
| `vue-router` | `^5.0.6` | Vue 3 用 **vue-router@4**，5.x 是 Vue 2 Router Next 时代的遗留号段，不兼容 |
| `@types/node` | `^24.12.2` | Node 类型随 Node LTS 走，24 超前 |
| `@vue/tsconfig` | `^0.9.1` | 实际在 0.5.x |
| `vue-tsc` | `^3.2.7` | 最新是 2.x |
| `pinia` | `^3.0.4` | 最新是 2.x |

**后果**：`npm install` 要么失败，要么装到不兼容版本导致运行时/构建时炸。如果你现在能跑，说明 `package-lock.json` 锁到了别的版本，但 `package.json` 的 range 是谎言。

**修法**：按实际能跑的版本回写 `package.json`，或者执行：
```bash
cd frontend && rm -rf node_modules package-lock.json
npm install vue@^3.4 vue-router@^4.3 pinia@^2.1 \
  element-plus@^2.7 @element-plus/icons-vue@^2.3 \
  vue-i18n@^9.13 axios@^1.7
npm install -D vite@^5.3 @vitejs/plugin-vue@^5.0 \
  typescript@^5.4 vue-tsc@^2.0 @vue/tsconfig@^0.5 \
  @types/node@^20 tailwindcss@^3.4 autoprefixer@^10.4 postcss@^8.4
```

---

### 🔴 P0-3：API Key 明文落盘
**位置**：`backend/config/profiles.json` + `services/profile_manager.py`

MiniMax 的 API Key（真金白银额度）**明文**写在 JSON 里，跟代码一起。`.gitignore` 里是否排除了 `config/profiles.json`？需要确认 —— 我看到 `/config/profiles.json` 和 `/backend/config/profiles.json` **两份都存在**，风险翻倍。

**修法（三选一，从弱到强）**：
- 🪫 最低：确保 `config/profiles.json` 在 `.gitignore` 且从 git 历史清除（`git log --all -- config/profiles.json`）
- 🔋 中等：把 api_key 移到 `.env` / 环境变量，JSON 里只存 `api_key_env: "MINIMAX_KEY_1"`
- 🔌 推荐：专门建 `ApiProfile` 数据表 + 应用层加密（Fernet），admin 界面写入即加密

---

## 四、重要问题（应该修）

### 🟠 P1-1：Token 策略自相矛盾
`stores/auth.ts` 注释写：
> "Token stored in memory only — more secure than localStorage (XSS risk)"

但代码**每次 setToken 都写 localStorage**，并且初始化时 rehydrate。**注释在撒谎**。要么去掉误导注释、接受 localStorage 的 XSS 风险（内网可接受），要么真正切到 HttpOnly Cookie + CSRF token 方案。当前状态是「声称安全、实际没做」，最糟。

### 🟠 P1-2：Router 守卫只检查 token 存在、不校验有效性
`router/index.ts` 只看 `localStorage.getItem('token')` 是否非空。Token 过期时仍然会让你进页面，要等到第一个 API 401 才跳出。可接受但不优雅。改成检查 `authStore.isLoggedIn` 并在 `App.vue` 挂载时调一次 `fetchMe` 校验。

### 🟠 P1-3：数据库硬编码 SQLite + 没有 Migration
`DATABASE_URL = "sqlite:///./img_platform.db"` 写死在代码里。多人并发写、切换到 PostgreSQL/MySQL 都要改源码。而且用 `Base.metadata.create_all()` 裸建表，没有 Alembic —— 以后改字段就是手动 ALTER 或数据丢失。

**修法**：
- `DATABASE_URL` 移到 env
- 上 Alembic（`alembic init` + 一条 baseline migration）

### 🟠 P1-4：`/minimax-output` 静态目录暴露全量文件
```python
MINIMAX_OUTPUT_DIR = str(Path.home() / "minimax-output")
app.mount("/minimax-output", StaticFiles(directory=..., html=True))
```
- **无鉴权**：任何登录/未登录用户都能遍历 CLI 用户的本机目录
- `html=True` 允许目录索引，泄漏文件名
- 挂载的是 `Path.home()` 下的真实目录，有被路径遍历绕过的历史前例

**修法**：要么做一个带鉴权的 `/api/files/{id}` 代理端点，要么至少把 `html=False` 并套个中间件查 JWT。

### 🟠 P1-5：Image 返回值里混用 URL 和 base64
```python
image_urls = data.get("image_urls", []) if req.response_format == "url" else data.get("image_base64", [])
```
字段名叫 `image_urls` 但内容可能是 base64 字符串 —— 命名撒谎，前端类型分辨靠约定而非类型。建议拆两个字段 `image_urls` 和 `image_base64`，或者统一返回 URL（base64 太大不适合入库）。

### 🟠 P1-6：没有任何测试
`find` 结果里 0 个 `test_*.py` 或 `*.spec.ts`。关键路径（登录、JWT 解码、profile 路由、admin 增删）**零回归保护**。后续一改全崩的概率极高。

**最低门槛**：
- `backend/tests/test_auth.py` —— 登录成功/失败/限流
- `backend/tests/test_profile_manager.py` —— get_profile_for_model priority 排序
- `backend/tests/test_admin_authz.py` —— 非 admin 调 admin 接口应得 403（修完 P0-1 后）

---

## 五、次要问题（建议优化）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| P2-1 | `main.py` | `@app.on_event("startup")` 在 FastAPI ≥0.93 已 deprecated | 改 `lifespan` context manager |
| P2-2 | `api/*.py` | 每个文件都 `sys.path.insert(0, ...)` hack | 用 `python -m` 或包结构，去掉脏路径修改 |
| P2-3 | `api/admin.py` | 561 行 Python 里塞了 **469 行内联 HTML/JS/CSS** | 拆成 `backend/templates/admin.html`，改用 Jinja2 渲染；或彻底砍掉、让 Vue 的 AdminView 承担 |
| P2-4 | `models/database.py` | 没有连接池参数、SQLite `check_same_thread=False` 多线程写不安全 | 切 PostgreSQL 或加 WAL 模式 + serialized writes |
| P2-5 | `profile_manager.py` | `@lru_cache` + `_save` 里 `cache_clear` —— 但**多进程**部署会各持一份缓存，不同步 | 生产多 worker 场景下会见到幽灵配置；改 Redis 或每次读 |
| P2-6 | `frontend/views/GenerateView.vue` | 单文件 **1106 行** | 拆成 PromptForm / ModelPicker / ResultGallery / HistoryPanel |
| P2-7 | `frontend/views/AdminView.vue` | 同样 772 行，且和 `backend/api/admin.py` 里的内联 HTML 功能**重复** | 统一到 Vue 端，删后端 HTML |
| P2-8 | `backend/.env` 存在仓内 | 真实 secret 可能已入库 | 确认 `.env` 是否被 gitignore；`git log -- backend/.env` 检查历史 |
| P2-9 | `image_001.jpg` / `img_platform.db` 在 backend/ | 构件物入仓 | 加 gitignore |
| P2-10 | `designs/*.pen` 在根目录 | 设计稿和代码同仓可接受，但注意仓库体积 | — |

---

## 六、架构评估

### 后端
- **分层合理**：`api / services / models / schemas / core` 职责清晰
- **路由自动注册缺失**：9 个 router 一条条 `include_router`，加新模块要改 `main.py`；可以用目录扫描或 `apps/` pattern
- **缺少中间层**：image/voice/video/music 四个 API 的路由代码**高度重复**（profile 路由 → http/cli 分支 → 存库 → 返回），应抽 `services/dispatcher.py`

### 前端
- **标准 Vue 3 SPA**，技术栈选型合理（Element Plus + Pinia + axios）
- **没有 TypeScript 严格模式**（没看到 `strict: true` 配置细节，建议开）
- **没有组件级拆分纪律** —— 单个 View 动辄 500-1100 行

### 部署
- 有 `backend/Dockerfile` 和 `frontend/Dockerfile`，但**没有 `docker-compose.yml`** 把它们串起来
- 没看到 Nginx 反向代理配置，生产怎么跑说不清

---

## 七、修复优先级路线图

### Sprint 1（本周必须）
- [ ] **P0-1** 给 admin / profiles 管理接口加 `require_admin` 依赖
- [ ] **P0-2** 修 `package.json` 依赖版本到真实可用版
- [ ] **P0-3** 确认 `config/profiles.json` 和 `backend/.env` 不在 git 历史，api_key 最低先挪到 env

### Sprint 2（两周内）
- [ ] **P1-4** `/minimax-output` 加鉴权或代理
- [ ] **P1-3** 引入 Alembic，`DATABASE_URL` 环境化
- [ ] **P1-6** 补 3 组最关键的 pytest（登录/authz/profile 路由）
- [ ] **P2-3** 拆 `admin.py` 内联 HTML
- [ ] **P2-6 / P2-7** 拆大组件

### Sprint 3（长期）
- [ ] 切 PostgreSQL + 迁移 bootstrap 脚本
- [ ] 统一 API 调度层，消除 image/voice/video/music 重复
- [ ] 加 CI：lint（ruff + eslint）+ typecheck + pytest
- [ ] 写 `docker-compose.yml` + Nginx 配置

---

## 八、评分拆解

| 维度 | 分 | 备注 |
|---|---|---|
| 功能完整度 | 8/10 | 闭环通顺，四类生成 + 历史 + admin 都有 |
| 代码质量 | 6/10 | 结构 OK，但大文件和重复路由拖分 |
| **安全性** | **3/10** | **admin 无鉴权 + api_key 明文，红线问题** |
| 可维护性 | 5/10 | 没测试 + 没迁移 + 依赖版本虚假 |
| 性能 | 7/10 | SQLite 单机够用，异步调用外部 API 到位 |
| 文档 | 6/10 | README 基础齐，缺部署/运维/安全说明 |
| 工程化 | 5/10 | 有 Dockerfile，缺 compose / CI / lint |
| **加权总分** | **62/100** | — |

---

## 九、给开发者的一句话

> 功能做到这一步已经比 80% 的「我有个 idea」型选手好得多。但**把 admin API 裸奔、api key 明文、package.json 版本号乱写**这三件事留着，哪天公司内网爬虫扫到、或者某个实习生删库，你会后悔今天没花两小时修。**先解决这三个，再谈别的。**
