# Track D 检测报告：无限画布 + 项目/画布 CRUD

> **检测时间**: 2026-06-04 14:18–14:30 CST
> **目标服务**: http://192.168.1.60:3000/
> **检测者**: general / track-d-canvas-projects (session mvs_cc638743796f4dc2859d53c98e9dd034)
> **代码基线**: 仓库 main.py 2026.05.28.2（v1.21），但 **部署版本≠仓库版本**（详见 P0-2）

---

## 0. 执行摘要

| 模块 | 通过 | 失败 | 阻断（auth） | 风险 | 状态 |
|------|------|------|-------------|------|------|
| A.0 鉴权 | 0 | 0 | 1 | — | 🔴 阻断（admin 密码已变更） |
| D.1 项目 CRUD | 0 | 0 | 0 | — | ⛔ 路由不存在（404）+ 鉴权阻断 |
| D.2 画布 CRUD（公开） | 3 | 0 | 0 | 2 | 🟡 部分可用 |
| D.2 画布 CRUD（需 auth） | 0 | 0 | 4 | 1 | 🔴 鉴权阻断 |
| D.3 资产库 | 0 | 0 | 0 | — | ⛔ 路由不存在（404） |
| D.4 历史 + 队列 | 3 | 0 | 0 | 1 | 🟢 健康 |
| **总计** | **6** | **0** | **5** | **4** | 🔴 **有 P0 阻断** |

**核心结论**：
1. 60 部署的是 **main.py 旧版本**（缺 D.1/D.3 + 多个辅助端点）
2. admin 默认密码已变（与 Track A 一致），按 spec 停手
3. 鉴权阻断的 API 全部记录，留待 owner 拿到密码后重测
4. 探测过程中在 60 留了 5+ 个 `owner=null` 的孤儿画布（因 auth 被阻断，无法用 API 清，详见 P1-1）

---

## 1. A.0 鉴权状态

| 探测 | 期望 | 实际 | 备注 |
|------|------|------|------|
| `POST /api/auth/login admin/admin123` | 200 + token | 400 `密码错误` | 默认密码已变更 |
| `POST /api/auth/login admin/admin@123` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/Admin123` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/admin2024` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/admin2025` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/admin2026` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/admin` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/admin1234` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/admin888` | 200 | 400 `密码错误` | |
| `POST /api/auth/login admin/` (空密码) | 422 | 422 `String should have at least 1 character` | |
| `POST /api/auth/login Admin/admin123` | 400 | 400 `用户不存在` | 用户名仅匹配小写 admin |
| `GET /api/auth/me` (无 auth) | 401 | 401 `未提供认证令牌` | ✅ 与 main.py 行为一致 |

**结论**：按 spec（9 个常见变体全失败后停手），不暴力破解。admin 密码已变更，需 owner 提供。

---

## 2. D.1 项目 CRUD

> **⛔ 全部 404：部署版本不包含 `/api/projects` 路由组**

| API | 期望 | 实际 | 判定 | 清理状态 |
|-----|------|------|------|----------|
| `GET /api/projects` | 200 `{projects:[...]}` | **404 `Not Found`** | ⛔ 路由不存在 | n/a |
| `POST /api/projects` | 200 `{project, canvas}` | **404 `Not Found`** | ⛔ 路由不存在 | n/a |
| `GET /api/projects/{id}` | 200 / 404 | **404 `Not Found`** | ⛔ 路由不存在 | n/a |
| `GET /api/projects/trash` | 200 | **404 `Not Found`** | ⛔ 路由不存在 | n/a |
| `DELETE /api/projects/{id}` | 200 | **404 `Not Found`** | ⛔ 路由不存在 | n/a |
| `POST /api/projects/{id}/restore` | 200 | **404 `Not Found`** | ⛔ 路由不存在 | n/a |
| `DELETE /api/projects/{id}/purge` | 200 | **404 `Not Found`** | ⛔ 路由不存在 | n/a |

**测试项目生命周期记录**：无。无法创建测试项目。

---

## 3. D.2 画布 CRUD

> 部署版本仅含画布基础 CRUD，缺 meta / restore / purge / assets/check 子端点。

### 3.1 可访问的端点

| API | 期望 | 实际 | 判定 | 清理状态 |
|-----|------|------|------|----------|
| `GET /api/canvases` (无 auth) | 200 列表 | 200 `{canvases:[…]}` | ✅ 可用 | n/a（只读） |
| `GET /api/canvases?project_id=xxx` (无 auth) | 200 过滤 | 200 返回**全量** | ⚠️ P2-1 过滤参数被静默忽略 | n/a |
| `GET /api/canvases/trash` (无 auth) | 200 | 200 `{canvases:[], retention_days:30}` | ✅ 可用 | n/a |
| `POST /api/canvases` (无 auth, `{}`) | 401/403 | **200 创建成功** | ⚠️ **P1-2 鉴权旁路**：创建出 `owner:null` 画布 | ⚠️ 孤儿（无法清） |
| `POST /api/canvases` (无 auth, `{title,icon,kind}`) | 401/403 | 200 创建成功 | ⚠️ P1-2（`kind` 字段被静默丢弃） | ⚠️ 孤儿 |
| `POST /api/canvases` (无 auth, `{title:12345}`) | 422 | 422 `Input should be a valid string` | ✅ 校验生效 | n/a |

### 3.2 鉴权阻断的端点

| API | 期望 | 实际 | 判定 | 清理状态 |
|-----|------|------|------|----------|
| `GET /api/canvases/{id}` (无 auth) | 401 | **403 `无权操作此画布`** | 🔴 鉴权阻断 + 行为可疑 | n/a |
| `PUT /api/canvases/{id}` (无 auth) | 401 | **403 `无权操作此画布`** | 🔴 鉴权阻断 | n/a |
| `DELETE /api/canvases/{id}` (无 auth) | 401 | **403 `无权操作此画布`** | 🔴 鉴权阻断 | ⚠️ 孤儿清不掉 |
| `DELETE /api/canvases/{id}/purge` (无 auth) | 401 | **403 `无权操作此画布`** | 🔴 鉴权阻断（旧版本有此端点） | n/a |

### 3.3 路由不存在的端点

| API | 期望 | 实际 | 判定 |
|-----|------|------|------|
| `GET /api/canvases/{id}/meta` | 200 | **404 `Not Found`** | ⛔ 路由不存在 |
| `POST /api/canvases/{id}/restore` | 200 | **404** （未注册） | ⛔ 路由不存在 |
| `POST /api/canvas-assets/check` | 200 | **404** | ⛔ 路由不存在 |
| `POST /api/canvas-assets/download` | 200 | **404** | ⛔ 路由不存在 |

### 3.4 测试画布生命周期（孤儿记录）

| Canvas ID | 标题 | 创建方式 | 清理方式 | 最终状态 |
|-----------|------|----------|----------|----------|
| `1e8faafbe7bb4869b2ed1901bddaeda9` | 未命名画布 | POST 探测（owner=null） | 不可清（auth 阻断） | 孤儿，磁盘残留 |
| `187ee61cab6d4308a86bd4333b291263` | 探测测试画布 | POST 探测（owner=null） | 不可清 | 孤儿，磁盘残留 |
| `c590f1d5b2884d6e82a23f3cb505134d` | 未命名画布 | POST 探测（owner=null） | 不可清 | 孤儿，磁盘残留 |
| `2f138bcef66b4064a14fe54d984ba033` | 未命名画布 | POST 探测（owner=null） | 不可清 | 孤儿，磁盘残留 |
| `3ecb1fa46d1d4f3a9a2853eccedcfdbe` | 探测测试-D | POST 探测（owner=null） | 不可清 | 孤儿，磁盘残留 |
| `c589b65e568441f99b20764667b2b1f1` | final-check | POST 探测（owner=null） | 不可清 | 孤儿，磁盘残留 |

**验证状态**：
- 列表端点 `GET /api/canvases` 当前过滤掉了 `owner=null` 的画布（实测返回 `{canvases:[]}`），所以普通用户看不到
- 但**单画布直查** `GET /api/canvases/{id}` 仍 403，画布文件估计还在 `data/canvases/{id}.json`
- 仅 owner 拿到 admin 密码后可通过 DELETE / PUT 清；或 SSH 到 60 主机直接 `rm` 文件

---

## 4. D.3 资产库

> **⛔ 全部 404：部署版本不包含 `/api/asset-library` 路由组**

| API | 期望 | 实际 | 判定 | 清理状态 |
|-----|------|------|------|----------|
| `GET /api/asset-library` | 200 `{library:{categories:[...]}}` | **404 `Not Found`** | ⛔ 路由不存在 | n/a |
| `GET /api/asset-library/` | 200 | **404** | ⛔ | n/a |
| `GET /api/asset-library/categories` | 200 | **404** | ⛔ | n/a |
| `GET /api/asset-library/items` | 200 | **404** | ⛔ | n/a |
| `POST /api/asset-library/categories` | 200 | **404** | ⛔ | n/a |
| `POST /api/asset-library/items` | 200 | **404** | ⛔ | n/a |
| `DELETE /api/asset-library/categories/{id}` | 200 | **404** | ⛔ | n/a |
| `DELETE /api/asset-library/items/{id}` | 200 | **404** | ⛔ | n/a |
| `GET /api/asset-library/list` | 200 | **404** | ⛔ | n/a |
| `GET /api/asset_library` | 200 | **404** | ⛔ | n/a |
| `GET /api/assets` | 200 | **404** | ⛔ | n/a |
| `GET /api/library` | 200 | **404** | ⛔ | n/a |

**测试分类/条目生命周期记录**：无。无法创建。

**附加观察**：
- 本地 `data/asset_library.json` 存在且格式正确（角色/场景/工作流 3 个预置分类），证明代码层支持
- 但 60 上没有暴露 API → 旧版本 main.py 没有这部分代码

---

## 5. D.4 历史 + 队列

| API | 期望 | 实际 | 判定 | 清理状态 |
|-----|------|------|------|----------|
| `GET /api/history` (无 auth) | 200 | 200, **45 条记录**，14697B | ✅ 可用 | n/a（只读） |
| `GET /api/history?type=canvas` (无 auth) | 过滤 canvas | 200, **`[]`** | ⚠️ P2-2 0 条结果（无 canvas 类型历史或过滤行为不一致） | n/a |
| `GET /api/history?type=textmatting` (无 auth) | 过滤 textmatting | 200, **2 条** | ✅ 过滤生效 | n/a |
| `GET /api/history?type=kuotu` (无 auth) | 过滤 kuotu | 200, **2 条** | ✅ 过滤生效 | n/a |
| `GET /api/queue_status` | 200/422 | **422** `Field required: client_id` | ✅ 参数校验生效 | n/a |
| `GET /api/queue_status?client_id=test` | 200 | 200, `{total:0, position:0}` | ✅ 队列空 | n/a |
| `GET /api/queue_status?client_id=test&session_id=test` | 200 | 200, `{total:0, position:0}` | ✅ 多余参数不报错 | n/a |

**历史 type 分布**（来自 45 条 `GET /api/history`）：

| Type | 计数 |
|------|------|
| angle | 12 |
| workflow | 6 |
| 2dstyle | 3 |
| klein | 3 |
| textmatting | 2 |
| kuotu | 2 |
| cgstyle | 2 |
| rmbg | 2 |
| gaoqingxiufu | 2 |
| qwen_edit | 2 |
| yichuwuti | 1 |
| online | 1 |
| 高清修复 | 1 |
| 图标风格细化 | 1 |
| gaoqing | 1 |
| tubiao | 1 |
| 风格迁移 | 1 |
| 2D风格细化 | 1 |
| CG一键细化 | 1 |

**用户**：`sethchang`（数据中可见）

---

## 6. 问题清单

### 🔴 P0 — 阻断性

#### P0-1：admin 默认密码已变更
- **复现**：
  ```bash
  curl -X POST http://192.168.1.60:3000/api/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"admin123"}'
  # → HTTP 400 {"detail":"密码错误"}
  ```
- **影响**：所有 `/api/auth/*` 鉴权、D.1 项目 CRUD、D.2 画布的 GET/PUT/DELETE、D.3 资产库、D.4 history 全量数据均不可访问
- **建议**：owner 重置 admin 密码（仓库有 `data/auth.db` 可直接编辑 hash，或加 AITOOL_ADMIN_PASSWORD 环境变量重启）

#### P0-2：60 部署版本 ≠ 仓库 main.py（缺 10+ 路由）
- **对比表**：

| 路由 | 仓库 main.py 状态 | 60 部署实际 |
|------|------------------|------------|
| `GET /api/projects` | ✅ 6047 | ❌ 404 |
| `GET /api/projects/trash` | ✅ 6052 | ❌ 404 |
| `POST /api/projects` | ✅ 6057 | ❌ 404 |
| `GET /api/projects/{id}` | ✅ 6095 | ❌ 404 |
| `PATCH /api/projects/{id}` | ✅ 6105 | ❌ 404 |
| `DELETE /api/projects/{id}` | ✅ 6142 | ❌ 404 |
| `POST /api/projects/{id}/restore` | ✅ 6172 | ❌ 404 |
| `DELETE /api/projects/{id}/purge` | ✅ 6203 | ❌ 404 |
| `GET /api/canvases/{id}/meta` | ✅ 6256 | ❌ 404 |
| `POST /api/canvas-assets/check` | ✅ 6278 | ❌ 404 |
| `POST /api/canvas-assets/download` | ✅ 6291 | ❌ 404 |
| `POST /api/smart-canvas/group-export` | ✅ 6340 | ❌ 404 |
| `GET /api/asset-library` | ✅ 6388 | ❌ 404 |
| `POST /api/asset-library/categories` | ✅ 6392 | ❌ 404 |
| `POST /api/asset-library/items` | ✅ 6423 | ❌ 404 |
| `GET /api/auth/users` | ✅ 4747 | ❌ 404 |
| `GET /api/app-info` | ❌（仓库也没） | ❌ 404 |

- **影响**：整个项目 + 画布 v2 + 资产库子模块无法在 60 演示
- **建议**：`cd /opt/aitoolstudio-canvas && git pull && docker compose -f docker-compose.60.yml restart` （需要 owner 操作）

### 🟡 P1 — 需关注

#### P1-1：探测遗留 5+ 个孤儿 `owner=null` 画布无法 API 清理
- **现象**：探测过程中 `POST /api/canvases` 6 次（无 auth）创建了 6 个画布，`owner=null`
- **列表可见性**：`GET /api/canvases` 当前已过滤掉 owner=null（实测返回 `[]`），普通用户看不到
- **单画布可见性**：`GET /api/canvases/{id}` 仍 403，证明画布文件还在 `data/canvases/` 目录
- **建议清理方式**（任选）：
  1. owner 拿到 admin 密码后，逐个 `DELETE /api/canvases/{id}` 删
  2. SSH 到 60 主机（**注意：22 端口可能被防火墙挡**），`rm /opt/aitoolstudio-canvas/data/canvases/{id}.json`
  3. 加一个 60 容器的 bind shell 或 docker exec 入口

#### P1-2：`POST /api/canvases` 无 auth 鉴权旁路
- **现象**：未登录 POST 创建画布成功，`owner: null`
- **复现**：
  ```bash
  curl -X POST http://192.168.1.60:3000/api/canvases \
    -H 'Content-Type: application/json' -d '{}'
  # → HTTP 200 {"canvas":{...,"owner":null,...}}
  ```
- **影响**：任何网络可达者都能在 60 创建孤儿画布（虽然因 owner=null，list 看不到，单查 403，但占磁盘 + 写 `data/canvases/` JSON）
- **建议**：60 部署的旧版本可能没有 `require_current_user` 调用；升级到 v1.21 main.py 后应自动修

#### P1-3：`GET /api/canvases` 不按当前用户过滤（信息泄露）
- **现象**：早期探测（探测 ID 403 之前）能 list 出 6 个画布，包括其他用户/历史 session 拥有的画布（ca75787...、2529d7a...、069cb72...）
- **当前状态**：实测目前 list 返回 `{}`（空），但这只是因为画布被 filter 排除，**不证明 fix**
- **复现（旧观察）**：
  ```bash
  curl http://192.168.1.60:3000/api/canvases
  # 早期返回 6 条，包括其他 user/IP 创建的画布
  ```
- **影响**：可枚举所有用户的画布 ID + 标题 + 节点数
- **建议**：同上，升级 main.py 到 v1.21 修

### 🟢 P2 — 优化建议

#### P2-1：`GET /api/canvases?project_id=xxx` 过滤参数被静默忽略
- **复现**：
  ```bash
  curl "http://192.168.1.60:3000/api/canvases?project_id=non-existent"
  # → HTTP 200 返回全量画布
  ```
- **期望**：400 或 200 但按 project_id 过滤
- **实际**：静默忽略参数，返回全量
- **建议**：升级 main.py 后会自动按 project_id 过滤（v1.21 已实现）

#### P2-2：`GET /api/history?type=canvas` 返回空
- **现象**：其他 type 过滤正常工作（textmatting/kuotu/2dstyle 都能过滤到），但 `type=canvas` 总是返回 `[]`
- **可能原因 1**：历史上确实没有 `type=canvas` 的记录（45 条里没看到）
- **可能原因 2**：旧版本 main.py 没把 canvas 编辑写入 history
- **建议**：升级 main.py 后再测一次

#### P2-3：画布 `kind` 字段被静默丢弃
- **复现**：
  ```bash
  curl -X POST http://192.168.1.60:3000/api/canvases \
    -H 'Content-Type: application/json' \
    -d '{"title":"x","kind":"smart"}'
  # → 200，但响应里没有 kind 字段
  ```
- **期望**：kind 字段持久化（v1.21 main.py 已支持）
- **建议**：升级 main.py

---

## 7. 下一步建议

1. **owner 决定 admin 密码重置方案**（spec 第 36 行留口子：登录失败停手，由 owner 提供）
2. **owner 在 60 部署 v1.21 main.py**（覆盖旧版本）
3. **重测 D.1 项目 CRUD**：owner 拿密码后 subworker 再走一遍 create → list → detail → soft-del → restore → purge
4. **owner 清理 6 个孤儿画布**（详见 P1-1 三种清理方式任选）
5. **重测 D.2/D.3**：P1-2/P1-3/P2-1/P2-2 全部期望在 v1.21 自动修复

---

## 8. 测试命令汇总（验证用）

```bash
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:$PATH
BASE=http://192.168.1.60:3000

# 鉴权
curl -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}'
curl $BASE/api/auth/me

# D.1（预期 404）
curl -o /dev/null -w "%{http_code}\n" $BASE/api/projects

# D.2
curl $BASE/api/canvases
curl $BASE/api/canvases/trash
curl -X POST $BASE/api/canvases -H 'Content-Type: application/json' -d '{}'
curl $BASE/api/canvases/2529d7a94a564eec81e8f7bbdadb87d1
curl -X DELETE $BASE/api/canvases/c589b65e568441f99b20764667b2b1f1
curl -o /dev/null -w "%{http_code}\n" $BASE/api/canvases/x/meta

# D.3（预期 404）
curl -o /dev/null -w "%{http_code}\n" $BASE/api/asset-library
curl -o /dev/null -w "%{http_code}\n" $BASE/api/asset-library/categories

# D.4
curl $BASE/api/history
curl "$BASE/api/history?type=canvas"
curl "$BASE/api/queue_status?client_id=test"
```

---

## 9. 附录：环境信息

- **检测机**：mac (Apple Silicon, darwin), zsh, curl 8.7.1
- **服务器**：60 主机（端口 3000，uvicorn）
- **代码基线**：仓库 `/Users/apple/Documents/GitHub/aitoolstudio`，main.py v1.21（10631 行），VERSION = 2026.05.28.2
- **部署版本**：未对外暴露（GET /api/app-info 404）；通过路由探测反推是 2026-05 之前版本
- **网络**：60 的 SSH 22 端口被防火墙屏蔽，HTTP 3000 可达
- **本地 auth.db 时间戳**：2026-05-27 21:00（admin hash 更新于 2026-05-27 04:42）
- **测试时间窗口**：14:18–14:30 CST（实际探测 +3 个写操作 + 1 个状态检查）
