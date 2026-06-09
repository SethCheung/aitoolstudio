# AIToolStudio P0 修复进度 v2（2026-06-04 15:35）

> **前提**：用户确认本地下部署，安全 P0 降级
> **本次范围**：远程可做的功能 P0 修复（不重启服务，只改代码+起备用实例）
> **当前状态**：✅ P0-1 路由硬编码已修并验证；⏳ 60:3000 需 user 重启让修复生效；❓ 剩 3 个 P0 等 user 决策

---

## ✅ 已完成

### P0-1：60:3000 代理路由硬编码（已修+已验证）

**Root cause**：`main.py` 第 856 行的 `requested_comfyui_addr` 函数只识别 `server_url` / `server` / `X-ComfyUI-Server-Url` header，不识别 `instance_id` query param。verifier 测的 `?instance_id=197:8188` 永远 fallback 到 `COMFYUI_ADDRESS`（列表第一个 = 195）。

**修改**：在 `requested_comfyui_addr` 末尾加 `or request.query_params.get("instance_id")`。

**改动文件**：
- `/opt/xy-canvas/main.py`（已备份 `main.py.bak.20260604-1528`）
- 改动：+1 行（行数 4261 → 4262）

**验证**（3001 备用实例跑的是改后的代码，3000 还是旧代码）：

| 实例 | 3000 (旧) system_stats md5 | 3001 (新) system_stats md5 | 3000 (旧) object_info md5 | 3001 (新) object_info md5 |
|------|------------------------|------------------------|------------------------|------------------------|
| 195  | b9ea0203… (0.19.2)     | b9ea0203… (0.19.2) ✓     | 83b9085b… (3797676 B)   | 83b9085b… (3797676 B) ✓  |
| 197  | **b9ea0203… (错!)**     | **dd1dc0dc… (0.21.1) ✓** | **83b9085b… (错!)**     | **6444dda6… (3305979 B) ✓** |
| 249  | **b9ea0203… (错!)**     | **60e44409… (0.21.1) ✓** | **83b9085b… (错!)**     | **2fc6e671… (3264031 B) ✓** |

3001 上 3 个实例路由正确，返回各自真实的 system_stats 版本和 object_info 字节数。

---

## ⏳ 60:3000 需要你重启

sethchang 没有 sudo，**杀不掉 root 跑的 uvicorn 进程（PID 2624686）**。修复已就绪但 60:3000 仍是旧代码。

**你 SSH 进 60 跑下面任一命令**：

```bash
# 选项 A（最简单，依赖 systemd 自动拉起）
sudo kill 2624686
# trim_main.service 检测到进程死了会自动 restart（如果 service 配的是 Restart=always）

# 选项 B（明确重启）
sudo systemctl restart trim_main.service

# 选项 C（手动启动，参考 60 现有 uvicorn 启动方式）
sudo kill 2624686
cd /opt/xy-canvas && nohup /usr/local/bin/python3.11 -m uvicorn main:app --host 0.0.0.0 --port 3000 > /var/log/xy-canvas.log 2>&1 &
```

**验证 3000 修好**：
```bash
curl -s 'http://192.168.1.60:3000/api/comfyui/system_stats?instance_id=197:8188' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['system']['comfyui_version'])"
# 期望：0.21.1（旧代码会返回 0.19.2）
```

**3001 备用实例还在跑**（PID 2631443），user 可以随时 curl `http://192.168.1.60:3001/...` 验证修复效果。重启 3000 后我可以 kill 3001。

---

## ❓ 剩 3 个 P0，等你决定要不要继续

| P0 | 我能修？ | 风险 | 建议 |
|----|---------|------|------|
| **P0-6**：online-image 上游 404 | ⚠️ 需改 base_url 配置 | 中（你可能就是要用 `api.minimaxi.com`）| 你确认切到哪个上游？默认 `ai.comfly.chat` 有 `/v1/images/generations` |
| **P0-2**：60 容器升级到仓库 HEAD | ⚠️ 改 .env + restart + 可能引新 bug | 中-高 | 你登 60 跑 `bash scripts/replace_60_3000_with_xy_canvas.sh --apply`，会先备份当前 data/auth.db 和 API/.env |
| **P0-4**：关开放注册 `/api/auth/register` | ✅ 改 main.py line 1649 注释掉 | 低 | 本地部署用不到，关了无害 |

**没修的安全 P0**（按你"安全等级不高"已降级）：
- admin 弱密码（test123）
- 用户枚举时序漏洞
- 大部分 API 未鉴权

---

## 我建议的优先级

如果你只想再做一件事：**关开放注册**（一行注释 + restart 3000 即可生效）。

如果你想彻底：**升级 60 容器**（一次解决 9 个 P0：路由 / SPA / 鉴权 / update endpoints / register 关闭 / workflow-install 等），但要你登 60 跑部署脚本。

要不要继续？告诉我做哪个，我直接动手。
