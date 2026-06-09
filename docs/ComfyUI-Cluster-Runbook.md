# ComfyUI 集群运行维护手册（Aitoolstudio）

更新时间：2026-06-01

相关文档：

- `docs/comfyui-worker-ops.md`：偏长期标准化方案，描述 `systemd/fstab` 托管目标。
- 本文档：偏当前真实运行状态，记录现有三节点池、非 sudo 启动策略、验收命令与下一步收口项。

## 1. 目标与边界

当前目标：Aitoolstudio 的 ComfyUI 后端计算池采用“集中模型盘 + 分布式计算”模式。  
所有模型/文件以 `192.168.1.60` 的共享盘为源头；ComfyUI 机器只负责执行任务，不做模型源数据分叉管理。

## 2. 60 服务器（平台入口与池配置基线）

| 项目 | 当前状态 |
|---|---|
| 平台入口（唯一） | `http://192.168.1.60:3000/` |
| ComfyUI pool（后端配置） | `192.168.1.195:8188`、`192.168.1.197:8188`、`192.168.1.249:8188` |
| 连通性验证 | 2026-05-27 `/api/comfyui/status` 曾验证 `3/3` 可用；2026-06-01 从本机抽检为 `192.168.1.195` 在线、`192.168.1.197/249` 未连通 |
| 上传同步验证 | `/api/upload` 已验证可同步上传到三台 |
| ComfyUI 共享资源统一入口 | `AI-Tool-Studio/comfyui` |

统一入口路径：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
```

Worker 如将 60 盘根目录挂载到 `/mnt/nas_comfyui`，则 ComfyUI 资源根目录为：

```text
/mnt/nas_comfyui/AI-Tool-Studio/comfyui
```

60 平台侧通常对应：

```text
/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui
```

本地 Mac 调试对应：

```text
/Volumes/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
```

## 3. Worker 当前状态

| Worker | 启动方式 | Python | 模型挂载 | extra_model_paths.yaml | Z-Image-Enhance missing | 备注 |
|---|---|---|---|---|---|---|
| `192.168.1.195` | `crontab @reboot -> /home/sjm/start_comfyui.sh` | `/usr/bin/python3` | `/mnt/nas_comfyui` | 应指向 `/mnt/nas_comfyui/AI-Tool-Studio/comfyui` | `0` | 2026-06-01 从本机可访问 `/system_stats` |
| `192.168.1.197` | `crontab @reboot -> /home/sjm/start_comfyui.sh` | `/usr/bin/python3` | `/mnt/nas_comfyui` | 应指向 `/mnt/nas_comfyui/AI-Tool-Studio/comfyui` | `0` | ComfyUI-Manager 依赖安装受 PEP668 拦截；2026-06-01 从本机访问 `8188` 未连通 |
| `192.168.1.249` | `crontab @reboot -> /home/sjm/start_comfyui.sh` | `/home/sjm/ComfyUI/venv/bin/python` | `/mnt/comfyui-models`（ro） | 应指向 `/mnt/comfyui-models/AI-Tool-Studio/comfyui` 或统一 `/mnt/nas_comfyui/AI-Tool-Studio/comfyui` | `0` | `/mnt/nas_comfyui -> /mnt/comfyui-models` 兼容链接曾存在；2026-06-01 从本机访问 `8188` 未连通 |

## 4. 已完成工作（里程碑）

1. `192.168.1.249` 加入池。  
2. 三台安装缺失 `custom_nodes`。  
3. 三台配置 `extra_model_paths.yaml` 指向共享模型路径。  
4. 安装/确认 Z-Image 所需模型 patch 在 `192.168.1.60` 盘可用。  
5. 平台后端 API 更新为三实例。  
6. 浏览器页面确认池状态 `3/3` 可用。  
7. 三台已创建/确认 `start_comfyui.sh` 与 `@reboot` 启动项。

## 5. 当前运维策略（低风险、非 sudo）

当前策略为低风险非 sudo 模式：  
`@reboot` 脚本负责等待挂载、幂等启动、日志落盘、`nohup` 后台启动。

执行原则：

1. 不依赖 root/systemd 才能恢复服务。  
2. 重启后由用户级 `crontab` 自动拉起。  
3. 同机重复执行启动脚本不应产生多实例冲突。  
4. 启动日志可追踪（便于排障和审计）。

## 6. 限制与风险

1. 尚未完成 `systemd/fstab` 级规范化（原因：sudo/root 权限未打通）。  
2. 当前方案“可用”，但不等同标准 `systemd` 托管方案。  
3. `192.168.1.197` 的 ComfyUI-Manager 依赖问题需后续单独收口。

## 7. 标准新增 Worker 流程

1. 安装/准备 ComfyUI 运行环境（Python、依赖、启动脚本）。  
2. 挂载 `192.168.1.60` 共享盘到本机统一路径。  
3. 配置 `extra_model_paths.yaml` 指向 `挂载根目录/AI-Tool-Studio/comfyui`。  
4. 安装业务所需 `custom_nodes`。  
5. 调 `object_info` 校验关键节点是否可见。  
6. 调 `queue` 接口校验实例可响应。  
7. 在 `192.168.1.60` 后端配置加入 `COMFYUI_INSTANCES`。  
8. 平台页面确认新节点已纳入池并可用。

## 8. 验收命令清单（无明文密码）

### 8.1 在各 Worker 本机执行

```bash
crontab -l
```

```bash
pgrep -af main.py
```

```bash
curl -fsS http://127.0.0.1:8188/object_info | head -c 300
```

```bash
curl -fsS http://127.0.0.1:8188/queue
```

```bash
ls -lah /mnt/nas_comfyui/AI-Tool-Studio/comfyui
```

### 8.2 在 60 平台侧执行

```bash
curl -fsS http://192.168.1.60:3000/api/comfyui/status
```

```bash
curl -fsSI http://192.168.1.60:3000/comfyui-settings
```

> 说明：`5173/8000` 视为历史端口，仅用于排障核对，不作为当前平台入口。

### 8.3 按节点逐台抽检（可选）

```bash
curl -fsS http://192.168.1.195:8188/object_info | head -c 300
curl -fsS http://192.168.1.197:8188/object_info | head -c 300
curl -fsS http://192.168.1.249:8188/object_info | head -c 300
```

```bash
curl -fsS http://192.168.1.195:8188/queue
curl -fsS http://192.168.1.197:8188/queue
curl -fsS http://192.168.1.249:8188/queue
```

## 9. 安全要求

1. 严禁将 SSH/SMB 密码写入仓库文档、脚本、配置文件。  
2. 凭据统一由主控/运维侧保管。  
3. 文档中仅允许记录无敏感信息的命令与地址。

## 10. 下一步建议

A. 继续接受当前 `@reboot` 方案（保持服务可用优先）。  
B. 获取 sudo/root 后，落地 `systemd + mount units + fstab` 规范化。  
C. 收口 `192.168.1.197` Manager Python 环境（PEP668/`git` 模块问题）。  
D. 执行一次真实工作流回归：`Z-Image-Enhance`、Topaz 类工作流、上传输入图到三节点并核对结果一致性。
