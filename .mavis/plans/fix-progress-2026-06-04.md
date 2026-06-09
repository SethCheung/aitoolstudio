# AIToolStudio P0 修复进度（2026-06-04 15:25）

> **前提**：用户确认本地下部署，安全 P0 降级（开放注册/弱密码/无鉴权等可后置）
> **本次范围**：数据残留清理（远程可做部分）
> **已用凭据**：sethchang / 12301230（is_admin: true，token: 21422613-...-8fceb）
> **鉴权方案**：部署侧旧版用 `?token=...` query string（不接 Bearer / X-Token / cookie）

---

## ✅ 已完成

### 1. 清理 5 个 verifier 测试账号（admin 端点）

| 账号 | 操作 | 响应 |
|------|------|------|
| verifier_test_user | POST /api/auth/admin/delete-user | 200 ✅ |
| verifier_admin_attempt | 同上 | 200 ✅ |
| verifier_probe_2 | 同上 | 200 ✅ |
| verifier_probe_3 | 同上 | 200 ✅ |
| verifier_probe_4 | 同上 | 200 ✅ |

验证：`/api/auth/admin/users` 现在 verifier_* 残留 = 0。

### 2. 清理 10 个探测残留画布

| Canvas ID | 标题 | 来源 |
|-----------|------|------|
| 1e8faafbe7bb4869b2ed1901bddaeda9 | 未命名画布 | Track D 探测 |
| 187ee61cab6d4308a86bd4333b291263 | 探测测试画布 | Track D 探测 |
| c590f1d5b2884d6e82a23f3cb505134d | 未命名画布 | Track D 探测 |
| 2f138bcef66b4064a14fe54d984ba033 | 未命名画布 | Track D 探测 |
| 3ecb1fa46d1d4f3a9a2853eccedcfdbe | 探测测试-D | Track D 探测 |
| c589b65e568441f99b20764667b2b1f1 | final-check | Track D 探测 |
| e8e836f73b3a4115bc77943ae97ed026 | verifier-canary-1 | verifier 自留 |
| 3506c04f3c85428a9cef05957a45ac1e | track-f-test | Track F 探测 |
| ca7578744a694063a6e6a91b6f33375f | 未命名画布 | 探测产物 |
| 2529d7a94a564eec81e8f7bbdadb87d1 | 验收测试画布 | 验收产物 |

操作：DELETE /api/canvases/{id}?token=... 全部 200。

---

## ⚠️ 待你决策（2 个 owner=null 画布）

剩下 2 个 owner=null 画布我**没敢动**，因为"未命名画布"也可能是你以前创建的：

| Canvas ID | 标题 | owner |
|-----------|------|-------|
| 5172774f363146ad9b78e15625fba6ca | 未命名画布 | null |
| 069cb7238da548308cd870da6579fe37 | 111 | null |

**两种可能**：
- 探测残留（应清）：因为是 60 旧版不按 user 过滤，无 auth 创建就 = owner=null
- 你自己的（应留）：旧版本 bug，写不进 owner 字段

要不要告诉我"全清"或"留 111"？或者你 SSH 到 60 看 `data/canvases/{id}.json` 内容判断？

---

## 🛑 需要你做的（远程做不了）

60 主机的 SSH 22 端口被防火墙屏蔽，下面这些**必须登 60 容器改**：

### 紧急功能 P0（影响业务）

1. **修补 60:3000 代理路由硬编码**（`/api/comfyui/system_stats` 等端点不接 `instance_id`，硬编码到 195）
   - 位置：60 容器 `/app/main.py` 6801 行附近
   - 修法：按 `instance_id` 路由到对应 ComfyUI 实例

2. **修 `/api/online-image` 上游 404**（3 个 model 全 404）
   - 位置：60 容器 `/app/API/.env` 或 main.py 配置
   - 检查 `ONLINE_IMAGE_UPSTREAM_URL`（或类似 env）配置

3. **升级 60 容器到仓库 main.py HEAD**（一次解决 9 个 P0）
   - 60 部署侧缺 50+ 路由、10/15 静态文件、SPA 入口、update endpoints
   - 路径：`cd /app && git pull && pip install -r requirements.txt && 重启`

4. **如果想关开放注册**：60 容器 main.py 改 `DISABLE_REGISTER=1` env 或注释 register 端点

### 优化项（不急）

5. 195 ComfyUI 升级 v0.19.2 → v0.21.1
6. 60 盘 SMB 共享里的 broken symlink 修整
7. 197 GPU1 启用（197 装的是 2× 2080 Ti 22G = 44G 总显存，现在 ComfyUI 进程只挂 GPU0）
8. 249 装 curl
9. /api/angle/* 孤儿代码删

### 3 台机器 GPU 配置（user 校正版，2026-06-04 15:24）

| IP | 角色 | GPU | 单卡显存 | 备注 |
|----|------|-----|----------|------|
| 192.168.1.195 | 视频/SEEDVR2/sam3/RMBG 专家机 | 1× RTX 4090 | 48G | ComfyUI v0.19.2（版本旧）|
| 192.168.1.197 | LLM 专家机 | 2× RTX 2080 Ti | 22G × 2 = 44G | 双卡只用 1 张（GPU1 闲置）|
| 192.168.1.249 | 通用机 | 1× RTX 4090 | 48G | — |

---

## 我可以怎么帮你

如果你能让我登 60 容器（开 SSH 或 docker exec 通道），我可以把上面 1-4 直接改完 + 重新跑一遍 6 模块检测验收。

或者你按上面"位置/修法"自己改，改完告诉我，我重跑检测看 P0 是否都清掉。
