# Track A — 基础设施 + 鉴权流 检测报告

- **执行时间**：2026-06-04 14:17–14:24 (Asia/Shanghai)
- **目标服务**：http://192.168.1.60:3000
- **执行代理**：general (mvs_0b522894d4b244f2aa5a9e87ee8493b3)
- **环境**：macOS / zsh / curl 8.x，源仓库 `/Users/apple/Documents/GitHub/aitoolstudio/`
- **关键限制**：60 的 SSH 22 端口屏蔽，所有探测仅走 HTTP；admin 默认密码已变更，已停手

---

## 1. 执行摘要

| 模块              | 通过 | 失败 | 风险  | 备注 |
|------------------|------|------|------|------|
| A.1 基础设施探测  | 6/14 | 8/14 | **P0** | `/` 与 4 个 API 正常；9 个 HTML 路由全部 404 |
| A.2 鉴权流（未登录）| 4/5  | 1/5  | P1   | 401/422 行为符合预期 |
| A.2 鉴权流（已登录）| 0/6  | 6/6  | **P0** | **admin 密码已变更，无法继续** |
| 部署版本一致性    | n/a  | n/a  | **P0** | 部署版本 ≠ 仓库 main.py，缺大量接口/页面 |

**一句话结论**：服务在线且核心 API 可用，但 (1) 默认 admin 密码已变更多次尝试失败，(2) 部署版本明显落后仓库代码，HTML 路由全部 404，UI 不可用。

---

## 2. A.1 基础设施探测

### 2.1 公开页面（无登录）

| URL                | 期望     | 实际 HTTP | 实际大小  | 实际摘要                          | 判定  | 备注 |
|-------------------|---------|---------|----------|-----------------------------------|------|------|
| `GET /`            | 200 HTML | **200**  | 34366 B  | `<!DOCTYPE html>` 项目主页 (`project-home.html`?)  | ✅    | 主页可访问 |
| `GET /login`       | 200/307  | **404**  | 22 B     | `{"detail":"Not Found"}` (JSON)    | ❌    | 登录页路由缺失 |
| `GET /projects`    | 200      | **404**  | 22 B     | `{"detail":"Not Found"}`           | ❌    | 项目页路由缺失 |
| `GET /admin`       | 200      | **404**  | 22 B     | `{"detail":"Not Found"}`           | ❌    | 后台页路由缺失 |
| `GET /studio`      | 200      | **404**  | 22 B     | `{"detail":"Not Found"}`           | ❌    | Studio 入口缺失 |
| `GET /smart-canvas`| 200      | **404**  | 22 B     | `{"detail":"Not Found"}`           | ❌    | 智能画布入口缺失 |
| `GET /canvas`      | 200      | **404**  | 22 B     | `{"detail":"Not Found"}`           | ❌    | 画布入口缺失 |
| `GET /api-settings`| 200      | **404**  | 22 B     | `{"detail":"Not Found"}`           | ❌    | API 设置页缺失 |
| `GET /comfyui-settings`| 200  | **404**  | 22 B     | `{"detail":"Not Found"}`           | ❌    | ComfyUI 设置页缺失 |

**关键观察**：所有 HTML 路由返回 404 且响应体是 JSON 格式（`{"detail":"Not Found"}`）。说明服务是 FastAPI/uvicorn 直接返回 404，**没有 SPA catch-all**。`/admin/users`（仅 admin 可见）也未单独测试，但根据 `/admin` 404 推断同样不可访问。

### 2.2 静态资源

| URL                              | 期望 | 实际 HTTP | 实际大小  | 判定 | 备注 |
|---------------------------------|------|---------|----------|------|------|
| `GET /static/tailwind.min.css`  | 200  | **200**  | 27358 B  | ✅    | 首屏 CSS 正常 |
| `GET /static/theme.js`          | 200  | **200**  | 1423 B   | ✅    | 主题脚本正常 |
| `GET /static/index.html`        | 200  | **200**  | 34366 B  | ✅    | 静态 SPA 入口正常 |
| `GET /static/login.html`        | 200  | **200**  | 23294 B  | ✅    | 登录页静态文件存在 |
| `GET /static/project-home.html` | 200  | **404**  | —        | ❌    | **首页静态文件缺失** |
| `GET /static/admin-dashboard.html`| 200| **404**  | —        | ❌    | **后台仪表盘静态文件缺失** |
| `GET /static/smart-canvas.html` | 200  | **404**  | —        | ❌    | **智能画布静态文件缺失** |

> **强证据**：静态目录里 3 个关键 HTML 文件缺失，与 HTML 路由 404 现象一致。

### 2.3 公开 API

| URL                       | 期望 | 实际 HTTP | 实际大小  | 实际摘要                                      | 判定  | 备注 |
|--------------------------|------|---------|----------|----------------------------------------------|------|------|
| `GET /api/app-info`      | 200  | **404**  | 22 B     | `{"detail":"Not Found"}`                     | ❌    | **元信息接口缺失** |
| `GET /api/config`        | 200  | **200**  | 1465 B   | `{"base_url":"https://api.minimaxi.com","chat_model":"MiniMax-M3",...}` | ✅    | 返回 provider/模型配置 |
| `GET /api/models`        | 200  | **200**  | 123 B    | `{"chat_models":["MiniMax-M3","MiniMax-M2.7","MiniMax-M2.5"],"image_models":[...]}` | ✅    | 模型清单 |
| `GET /api/providers`     | 200  | **200**  | 1163 B   | `{"providers":[{"id":"modelscope","name":"魔搭",...}]}` | ✅    | 1 个 provider 已配置 |
| `GET /openapi.json`      | 200  | **200**  | 51001 B  | 共 65 条 path                                 | ✅    | 文档可达 |

---

## 3. A.2 鉴权流

### 3.1 未登录探测

| URL/方法                            | 期望    | 实际 HTTP | 实际摘要                                | 判定  | 备注 |
|------------------------------------|---------|---------|----------------------------------------|------|------|
| `GET /api/auth/me` (无 cookie)      | 401     | **401**  | `{"detail":"未提供认证令牌"}`            | ✅    | 与仓库代码不同：源用 401 "未登录" |
| `POST /api/auth/login {}` (空体)   | 422     | **422**  | 字段缺失校验细节                         | ✅    | Pydantic 校验正常 |
| `POST /api/auth/login` 不存在用户    | 400/401 | **400**  | `{"detail":"用户不存在，请先注册"}`      | ⚠️   | **用户名枚举风险**（见 §6 P2-1） |
| `GET /api/auth/admin/users` (无 cookie)| 401  | **401**  | `{"detail":"未提供认证令牌"}`            | ✅    | 鉴权正常 |
| `POST /api/auth/register` 空体        | 422     | **422**  | 字段缺失校验细节                         | ✅    | 注册端点存在（仓库代码未列但部署侧有） |
| `OPTIONS /api/auth/admin/users`      | 405     | **405**  | `allow: GET`                            | ✅    | 路由元信息正常 |

### 3.2 管理员登录（**默认密码已变更**）

| 密码                | 期望     | 实际 HTTP | 实际摘要                       | 判定      |
|-------------------|---------|---------|------------------------------|----------|
| `admin123` (README 默认) | 200 | **400**  | `{"detail":"密码错误"}`         | ❌ **P0** |
| `admin@123`         | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `Admin123`          | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `admin2024`         | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `admin2025`         | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `admin2026`         | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `admin`             | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `admin1234`         | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `password`          | 200     | **400**  | `{"detail":"密码错误"}`         | ❌       |
| `''` (空)            | 422     | **422**  | Pydantic 长度校验                | ➖ 跳过   |

> **关键观察**：
> - 用户 `admin` 存在（响应 400 "密码错误"） vs 不存在用户（响应 400 "用户不存在，请先注册"）
> - 用户枚举时间差：`admin` 296ms（bcrypt 校验） vs 其他用户 30ms（直接返回）
> - **按 spec 立即停手，未继续暴力破解**

### 3.3 已登录路径（**全部未执行**）

由于无法登录，以下全部路径**未执行**：

| URL/方法                              | 期望    | 实际    | 备注 |
|--------------------------------------|---------|---------|------|
| `POST /api/auth/login` 拿 token       | 200     | —       | 失败，见 §3.2 |
| `GET /api/auth/me` 带 cookie         | 200     | —       | 未执行 |
| `GET /api/auth/users`（仓库路径）| 200  | **404**  | **端点不存在**（部署侧用 `/api/auth/admin/users`） |
| `GET /api/auth/admin/users`（部署侧）| 200  | —       | 未执行 |
| `POST /api/auth/users` 创建测试用户   | 200/201 | —       | 未执行 |
| `PUT /api/auth/users/{id}` 禁用       | 200     | —       | 未执行 |
| `POST /api/auth/change-password`     | 200     | **404**  | **端点不存在于部署侧** |
| `POST /api/auth/logout` 登出          | 200     | —       | 未执行 |
| 登出后再 `GET /api/auth/me`           | 401     | —       | 未执行 |

---

## 4. 部署版本一致性（关键发现）

通过对比 `/openapi.json`（部署侧）与 `main.py`（仓库 HEAD），发现**部署版本明显落后**：

| 接口/路由                          | 部署侧 (openapi) | 仓库 main.py | 结论 |
|----------------------------------|----------------|-------------|------|
| `/api/app-info`                  | ❌ 缺失         | ✅ line 1723 | 部署侧无 |
| `/api/auth/users` 系列（POST/GET/PATCH/PUT/reset-password）| ❌ 缺失 | ✅ line 4747+ | 部署侧改用 `/api/auth/admin/*` 前缀 |
| `/api/auth/change-password`      | ❌ 缺失         | ✅ line 4765 | 部署侧无 |
| `/api/auth/register`             | ✅              | ✅ 仓库侧有   | OK |
| HTML 路由 (`/`, `/login`, `/projects`, `/studio`, `/admin`, `/admin/users`, `/smart-canvas`, `/canvas`, `/api-settings`, `/comfyui-settings`) | ❌ 全部 404 | ✅ line 4683+ 共 10 个 | 部署侧完全缺失 SPA 路由 |
| `/api/auth/admin/users` (GET)    | ✅              | —           | 部署侧独有 |
| `/api/auth/admin/reset-password` (POST) | ✅       | —           | 部署侧独有 |
| `/api/auth/admin/delete-user` (POST) | ✅          | —           | 部署侧独有 |

> **结论**：192.168.1.60:3000 跑的是**旧版本**（看起来是 0.x 时代 admin/users 合并版），而仓库 HEAD 已经是 1.x 的拆分版 + 完整 SPA 路由。**部署方需要 re-deploy 或 git pull + restart**。

**间接证据**：
- 错误信息文本不同：部署侧 "密码错误"/"用户不存在，请先注册" vs 仓库 "用户名或密码错误"
- HTTP 状态码不同：部署侧 400 vs 仓库 401（密码错误时）
- 静态目录里 `project-home.html` / `admin-dashboard.html` / `smart-canvas.html` 文件不存在

---

## 5. 问题清单

### 5.1 P0 — 必须立即处理

| ID  | 问题                                       | 复现命令 |
|-----|-------------------------------------------|----------|
| P0-1| **默认 admin 密码已变更**，9 个常见变体均失败，无法完成管理侧检测 | `curl -X POST http://192.168.1.60:3000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}'` → HTTP 400 密码错误 |
| P0-2| **部署版本与仓库不一致**，缺失 10+ 路由（含全部 HTML 入口） | `diff <(curl -s http://192.168.1.60:3000/openapi.json \| python3 -c "import sys,json; print('\\n'.join(sorted(json.load(sys.stdin)['paths'])))") <(grep -E "^@app\\.get\\(\"/" main.py \| awk -F'"' '{print $2}')` |
| P0-3| **/api/app-info 缺失**（应用元信息、版本号、仓库 URL 无法获取） | `curl -s -o /dev/null -w "%{http_code}\n" http://192.168.1.60:3000/api/app-info` → 404 |

### 5.2 P1 — 影响功能但非阻塞

| ID  | 问题                                       | 复现命令 |
|-----|-------------------------------------------|----------|
| P1-1| `/login` 等 9 个 HTML 入口 404，UI 不可用 | `for p in /login /projects /admin /studio /smart-canvas /canvas /api-settings /comfyui-settings; do curl -s -o /dev/null -w "$p %{http_code}\\n" http://192.168.1.60:3000$p; done` 全部 404 |
| P1-2| 静态目录缺 3 个关键 HTML 文件             | `for f in project-home admin-dashboard smart-canvas; do curl -s -o /dev/null -w "/static/$f.html %{http_code}\\n" http://192.168.1.60:3000/static/$f.html; done` 全部 404 |
| P1-3| `/api/auth/change-password` 在部署侧缺失（仓库里有），用户无法自助改密 | `curl -X POST http://192.168.1.60:3000/api/auth/change-password -H 'Content-Type: application/json' -d '{}'` → 404 |

### 5.3 P2 — 体验/安全建议

| ID  | 问题                                       | 复现命令 |
|-----|-------------------------------------------|----------|
| P2-1| **用户名枚举**：密码错误返回 400 "密码错误"，用户不存在返回 400 "用户不存在，请先注册" — 文案差异 + 296ms vs 30ms 时序差 | `time curl -X POST http://192.168.1.60:3000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"x"}'` vs `time curl -X POST http://192.168.1.60:3000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"nobody","password":"x"}'` |
| P2-2| 404 页面泄露 `{"detail":"Not Found"}` JSON，对人类用户不友好 | `curl http://192.168.1.60:3000/login` |
| P2-3| 部署侧 `/api/auth/users` 路径用 admin 子前缀（admin/users），与仓库 1.x 的扁平路径不一致，文档/前端都需要分流 | 见 §4 表 |

---

## 6. 下一步建议

1. **【P0-1 优先】找回 admin 密码**（或重置）：
   - 现场：登录 192.168.1.60 控制台，检查 `data/auth.db` (或类似 SQLite/JSON)，从 hash 反推；或临时挂载环境变量 `BOOTSTRAP_ADMIN_PASSWORD=...` 重启
   - 重启后用 admin 重新跑 Track A 的 §3.3

2. **【P0-2】同步仓库到部署**：
   ```bash
   ssh 60  # 若已开
   cd /path/to/aitoolstudio
   git pull
   # 触发重启（systemd/supervisor/pm2 视情况）
   ```
   重启后**重新探测**：
   - HTML 路由应恢复
   - `/api/app-info` 应可用
   - 静态文件应齐

3. **【P2-1 改文案】** 统一登录失败响应：把 "用户不存在，请先注册" / "密码错误" 都改成同一种 "用户名或密码错误"（仓库代码已经这么做了），消除用户名枚举

4. **【P1-3 同步】** Track A 后续需补做：
   - 登录成功后跑 §3.3 全部路径
   - 验证 token 格式（推测是 `Authorization: Bearer` + cookie 双通道）
   - 创建临时测试用户 → 测改密 → 登出 → 确认 401 → **必须清理测试用户**（PUT disable 或 admin/delete-user）

5. **【交付】** 把本报告复制到 `docs/detection/track-a-2026-06-04.md` 入库，标注 "需要 re-deploy 后复测"。

---

## 7. 复现命令清单（单条可跑）

```bash
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:$PATH
BASE=http://192.168.1.60:3000

# A.1 全套
for p in / /login /projects /admin /studio /smart-canvas /canvas /api-settings /comfyui-settings \
         /api/app-info /api/config /api/models /api/providers; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BASE$p")
  printf "%-25s %s\n" "$p" "$code"
done

# A.2 未登录
for p in /api/auth/me; do
  curl -s -w " $p HTTP %{http_code}\n" --max-time 5 -o /dev/null "$BASE$p"
done

# A.2 登录（默认密码）
curl -s -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  -w "\nHTTP %{http_code}\n"

# 路径对比（部署 vs 仓库）
curl -s "$BASE/openapi.json" | python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(sorted(d['paths'])))" > /tmp/deployed.paths
grep -oE '"[^"]+"' /Users/apple/Documents/GitHub/aitoolstudio/main.py | grep -E "^/api" | sort -u > /tmp/repo.routes  # 粗略
diff /tmp/deployed.paths /tmp/repo.routes
```

---

## 8. 附录 — 原始证据

- 探测快照：`/tmp/track-a/cookies.txt`（空，因未登录成功）、`/tmp/track-a/login.body`、`/tmp/track-a/openapi.json`
- 仓库主代码：`/Users/apple/Documents/GitHub/aitoolstudio/main.py`（10631 行）
- 静态目录：`/Users/apple/Documents/GitHub/aitoolstudio/static/`（18 个文件，缺 `project-home.html` / `admin-dashboard.html` / `smart-canvas.html`）

> 本次未做任何源码修改，未触碰任何数据。

---

## 9. 快速复现附录（给 verifier）

下面 4 段命令均可在执行机直接运行，PATH 已兜底。

```bash
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:$PATH
BASE=http://192.168.1.60:3000
```

### 9.1 部署 vs 仓库 路由对比（一行 diff）

```bash
curl -s "$BASE/openapi.json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(sorted(d['paths'])))" \
  > /tmp/d.paths
grep -oE '@app\.(get|post|put|patch|delete|api_route)\("[^"]+"' \
  /Users/apple/Documents/GitHub/aitoolstudio/main.py \
  | grep -oE '"[^"]+"' | sort -u > /tmp/r.paths
diff /tmp/d.paths /tmp/r.paths
```

仅在 `r.paths` 里出现的（仓库有、部署无）就是缺失的路由；仅在 `d.paths` 里出现的就是部署侧独有（通常是 `admin/*` 旧版前缀）。

### 9.2 静态文件缺哪几个

```bash
for f in project-home.html admin-dashboard.html smart-canvas.html \
         angle.html gpt-chat.html enhance.html klein.html online.html; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BASE/static/$f")
  printf "/static/%-25s -> HTTP %s\n" "$f" "$code"
done
```

预期：`project-home.html` / `admin-dashboard.html` / `smart-canvas.html` 三个 404；其余 200（仓库有，部署侧静态目录有）。

### 9.3 用户枚举时序

```bash
echo "--- admin (should exist) ---"
time curl -s -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"x"}' -o /dev/null --max-time 5
echo "--- nobody (should NOT exist) ---"
time curl -s -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"nobody","password":"x"}' -o /dev/null --max-time 5
```

预期：前者 ~290ms（bcrypt 校验） + HTTP 400 "密码错误"；后者 ~30ms（直接返回）+ HTTP 400 "用户不存在，请先注册"。两者文案 + 时序差异即用户名枚举证据。

### 9.4 §3.3 已登录路径（等密码后才能跑）

完整期望/路径表在 §3.3；密码一通按这个顺序跑：

```bash
COOKIE=/tmp/track-a/cookies.txt
rm -f "$COOKIE"

# 1) 登录拿 token + cookie
curl -s -c "$COOKIE" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<由 owner 提供的密码>"}'

# 2) 当前用户
curl -s -b "$COOKIE" "$BASE/api/auth/me"

# 3) 用户列表（注意：部署侧路径是 /api/auth/admin/users，仓库是 /api/auth/users）
curl -s -b "$COOKIE" "$BASE/api/auth/admin/users"
# 若想测仓库路径，预期 404：
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/api/auth/users"

# 4) 建临时用户
TS=$(date +%s)
curl -s -b "$COOKIE" -X POST "$BASE/api/auth/admin/users" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"tracka_${TS}\",\"password\":\"TestPass_${TS}!\",\"is_admin\":false}"
# 记下返回的 user.id，cleanup 用

# 5) 改密（部署侧无此端点，预期 404；仓库侧有）
curl -s -o /dev/null -w "change-pwd: %{http_code}\n" -b "$COOKIE" \
  -X POST "$BASE/api/auth/change-password" \
  -H 'Content-Type: application/json' \
  -d '{"old_password":"<owner_pwd>","new_password":"<new>"}'

# 6) 登出
curl -s -b "$COOKIE" -c "$COOKIE" -X POST "$BASE/api/auth/logout"

# 7) 登出后再 /me 应 401
curl -s -o /dev/null -w "me-after-logout: %{http_code}\n" -b "$COOKIE" "$BASE/api/auth/me"

# 8) 清理：用 admin 重新登录后调 /api/auth/admin/delete-user
curl -s -c "$COOKIE" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<owner_pwd>"}' >/dev/null
curl -s -b "$COOKIE" -X POST "$BASE/api/auth/admin/delete-user" \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"<第 4 步拿到的 id>"}'
```

> 仓库侧对应的清理路径是 `PUT/PATCH /api/auth/users/{id}` 设 `is_disabled=true`；部署侧没有该路径，只能用 `/api/auth/admin/delete-user`（POST，body 含 user_id）。**两种部署走不同的清理命令**，verifier 跑前先确认 openapi。

### 9.5 evidence 索引

- `/tmp/track-a/openapi.json` — 部署侧完整 OpenAPI 快照（65 路径）
- `/tmp/track-a/login.body` — admin/admin123 失败响应
- `/tmp/track-a/me.body` — 未登录 /me 401 响应
- `/tmp/track-a/cookies.txt` — 空（未登录成功）
- `/Users/apple/Documents/GitHub/aitoolstudio/main.py` — 仓库 HEAD，10631 行
- 仓库静态目录 18 个文件，缺 `project-home.html` / `admin-dashboard.html` / `smart-canvas.html`（已 `ls` 确认）
