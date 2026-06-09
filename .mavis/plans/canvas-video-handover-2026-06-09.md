# 视频生成 E2E 验证 + 修复 — 交接文档（v2 含基础信息）

> 日期：2026-06-09
> 作者：Mavis (mvs_11691dee977444eb808dfc2f3d927aea)
> 给谁：接手 agent（修复未完成项 / 推进视频生成质量）
> 状态：**A 项（web UI 痛点）已修复并 playwright 复测通过 ✅**，B/C/D/E/F 项待办 ⏳
> v2 增量：补全 4 台机器登录信息 + docker 部署步骤 + 端口表 + NAS 挂载信息

## 文档版本

| 版本 | 日期 | 增量 |
|---|---|---|
| v1 | 2026-06-09 13:27 | 初版：10 个 workflow 评估 + 4 条待办 |
| **v2** | **2026-06-09 13:45** | **补 §1.5 登录凭据 / §1.6 端口表 / §1.7 部署步骤 / §1.8 NAS 挂载 / §12 cheat sheet** |

---

## 0. TL;DR（5 分钟看完）

用户在 xy-canvas web UI 上加 ComfyUI 视频生成节点，搭了 10+ 个 video workflow，希望"用户画布上点几下就能出图生视频/T2V/I2V 视频"。

**已修复 ✅**：web UI 上 video node 自己的 prompt textarea 缺漏（用户痛点），Playwright headless Chromium 复测全通过。

**关键发现 ⚠️**：**LTX 22B distilled 模型本身 photorealism 评分只有 3/10**（偏概念艺术/数字插画），不是 SeedVR2 的锅。所有 v4/v5/i2v/t2v-lora/studio_quality 风格都偏插画。要真正出 photorealism 得换模型（见 §5 选项 B）。

**待办 ⏳（4 条）**：
1. seedvr2_standalone / ltx_1080p_v5_seedvr2 加 "⚠️ 艺术化" 警告标签
2. 音视频 workflow（`ltx_音视频-ltx-av.json`）节点 16 连线修
3. 视频反推 workflow（`视频反推.json`）缺 video_output 节点
4. t2v-lora workflow 决定保留/下架

**接手第一步**：
```bash
# 1. 拿本机一台
# 2. ssh 进 60
sshpass -p '12301230' ssh sethchang@192.168.1.60
# 3. 看 xy-canvas 状态
echo "12301230" | sudo -S docker ps --filter name=xy-canvas
# 4. 改代码
ls /opt/xy-canvas/  # 改这里！
# 5. 重启
echo "12301230" | sudo -S docker restart xy-canvas
```

完整凭据见 §1.5，端口见 §1.6，部署细节见 §1.7。

---

## 1. 项目背景

### 1.1 xy-canvas 是什么

- 自研 web AI 工具台，FastAPI + 静态前端，端口 **3000**
- 通过"无限画布"提供节点式工作流编辑器（comfyui-registry.js 管理所有节点类型）
- 前端 iframe 加载 `canvas.html`，里面挂载所有 `static/modules/*-node.js` 节点模块
- 后端在 docker 容器 `xy-canvas`（`python:3.11-slim` 镜像）跑，挂在 host 3000 端口

### 1.2 算力拓扑

| 机器 | IP | 角色 | 显存 |
|---|---|---|---|
| sjm-mac (本机) | 192.168.x.x | 开发机 | - |
| 60 | 192.168.1.60 | xy-canvas web + NAS 网关 | - |
| 195 | 192.168.1.195 | RTX 4090 48G | 49140 MiB |
| 249 | 192.168.1.249 | RTX 4090 48G | 49140 MiB |
| 197 | 192.168.1.197 | 2× RTX 2080 Ti | 22G 总量 |

- **NAS**：`//192.168.1.60/团队文件-SJM-MediaFile` 191T 已用，190T 可用
- 各机挂载：60→`/home/sethchang/smb/`，195/249→`/mnt/nas_comfyui/`
- **nvidia-smi 是真实显存来源**（不要信 ComfyUI `/system_stats` 接口的 `mem_total`）

### 1.3 关键路径（**别 ssh 错地方**）

| 用途 | 路径 | 说明 |
|---|---|---|
| **服务在跑的代码** | `/opt/xy-canvas/` (60 机器) | **Docker 容器 `xy-canvas` 挂这个目录**。改这个才生效。 |
| main.py | `/opt/xy-canvas/main.py` (173KB, 6月8日改) | FastAPI 后端，注册 `/api/canvas-video-tasks/*` 路由 |
| 视频 API 实现 | `/opt/xy-canvas/canvas_video.py` (48KB) | canvas-video-tasks 的 handler 全部在这 |
| canvas.html | `/opt/xy-canvas/static/canvas.html` (6月8日 19:38 改) | v=20260603005 |
| video-node.js | `/opt/xy-canvas/static/modules/video-node.js` (25KB, 6月8日 19:37 改) | v=20260608001 |
| Workflow 目录 | `/opt/xy-canvas/workflows/` | canvas_video.py 的 WORKFLOW_DIR 指向这里 |
| **同步源（不是服务源）** | `/fs/1001/ftp/团队文件-SJM-MediaFile/AI-Tool-Studio/xy-canvas-source/` | **不要改这里**！这是另外一份同步副本，跟服务无关。改这个会以为生效了但实际没生效 — 之前 Mavis 就在这踩过坑。 |
| Mac 本地副本 | `/Users/apple/Documents/GitHub/xy-canvas/` | git 仓库，Mac 上的 dev 副本 |
| Web UI 入口 | `http://192.168.1.60:3000/` | 登录 `sethchang` / `12301230` |

### 1.4 SSH / 提权

- `sshpass -p '12301230' ssh sethchang@192.168.1.60` 直接进
- 提权：`echo '12301230' | sudo -S <cmd>`（sethchang sudo 全开）
- `docker ps` 不行的话：`echo '12301230' | sudo -S docker ps`

### 1.5 完整登录凭据速查（**换电脑必备**）

| 机器 | IP | 用户 | 密码 | sudo | 备注 |
|---|---|---|---|---|---|
| 60 (SJM-MediaFile) | 192.168.1.60 | sethchang | `12301230` | ✅ NOPASSWD 实测 sudo 全开 | **xy-canvas web + NAS 网关** |
| 195 (sjm-ubuntu) | 192.168.1.195 | sjm | `Sjm744546` | ✅ NOPASSWD（需密码 sudo） | RTX 4090 48G + ComfyUI 8188 |
| 249 (sjm-B550-VISION-D-P) | 192.168.1.249 | sjm | `Sjm744546` | ✅ NOPASSWD（需密码 sudo） | RTX 4090 48G + ComfyUI 8188 |
| 197 (sjm-To-Be-Filled-By-O-E-M) | 192.168.1.197 | sjm | `Sjm744546` | ✅ NOPASSWD（需密码 sudo） | 2× RTX 2080 Ti 22G + ComfyUI 8188 |
| Mac 本机 | sjm-mac | apple | 用户自己的 | - | 开发机 |

> ⚠️ 之前的 user_profile 写的是 "60 = sethchang:12301230, sudo 全开" — 准确。197 写的是 "sjm:Sjm744546" — 实际是 `Sjm744546` 大写 S 开头，没有冒号。

**Mac 本地凭据存放**：
- `~/.ssh/config` 里通常有 `Host sjm-60/195/197/249` 别名（如有就直接用 `ssh sjm-60`）
- 没配就用 `sshpass -p '<密码>' ssh <user>@<ip>`（**注意 sshpass 的 -p 只接密码，不接 user:pass**）

**60 系统的 hostname** = `SJM-MediaFile`（不是 `sjm-60`），网络接口 `enp59s0d1`。

**Linux 发行版**：
- 60：Linux 6.18.18-trim（裁剪版内核，**不是 Ubuntu**）
- 195/197/249：Linux 6.17.0-xx-generic（**Ubuntu 24.04**）

**GPU 验证脚本**（任何机器都能跑）：
```bash
sshpass -p 'Sjm744546' ssh sjm@192.168.1.195 'nvidia-smi --query-gpu=name,memory.total --format=csv'
# 输出: NVIDIA GeForce RTX 4090, 49140 MiB
```

### 1.6 完整端口表

#### 60 (xy-canvas web + NAS 网关) — Linux NAS
| 端口 | 服务 | 用途 |
|---|---|---|
| **3000** | **xy-canvas (uvicorn in docker)** | **xy-canvas web UI — 主要工作目标** |
| 80 | nginx | 反向代理（备用） |
| 443 | nginx | HTTPS（备用） |
| 22 | sshd | SSH |
| 21 | smbftpd | FTP |
| 139/445 | smbd | SMB/CIFS（NAS 共享） |
| 2049 | nfsd | NFS（NAS 共享） |
| 9024 | rpc.mountd | NFS mountd |
| 5666/5667 | nginx | 监控？ |
| 3702 | wsdd2 | Windows Service Discovery |

**60 还挂着 docker 服务**：`/var/run/docker.sock`，sethchang 在 `Users` 组可直接 `sudo docker` 访问。

#### 195/197/249 (ComfyUI) — Linux Ubuntu
| 端口 | 服务 | 用途 |
|---|---|---|
| **8188** | **ComfyUI main.py** | **视频生成 worker 端**（xy-canvas 提交任务到这里） |
| 8080 | python3 (AiHelper) | 195 上有，249/197 没有 — ComfyUI-zhenzhen 自定义节点辅助端口 |
| 22 | sshd | SSH |
| 631 | CUPS | 打印服务（可忽略） |
| 3389/3390 | gnome-remote-de | 远程桌面（195） |

**ComfyUI 三台版本**：
- 195: ComfyUI v0.19.2（git `c033bbf5`, 2026-04-17）
- 197: ComfyUI v0.21.1（git `d3607a8e`, 2026-05-16）
- 249: ComfyUI v0.21.1（git `72e3f608`, 2026-05-19）

**vram_total 从 /system_stats 看**（注意：**60 通过 xy-canvas 中转，所以看到的 mem_total 经常返 0.0G，别信！**）：
- 195: 50863603712 bytes = 47.4 GB（实际 49140 MiB，差几 MB 是单位换算）
- 197: 23059824640 bytes = 21.5 GB（**两个 GPU 都一样**）
- 249: 50864390144 bytes = 47.4 GB

#### 跨机器通信
- **xy-canvas (60) → ComfyUI (195/197/249)**：从 60 看 `API/.env`：
  ```
  COMFYUI_INSTANCES=192.168.1.195:8188,192.168.1.197:8188,192.168.1.249:8188
  ```
  提交时 60 端 canvas_video.py 轮询 3 个实例，挑空闲的提交（代码逻辑见 canvas_video.py）。
- **Web 端 → xy-canvas**：`http://192.168.1.60:3000/`
- **Web 端 → ComfyUI 直连**：也能直接 `http://192.168.1.195:8188/` 看 ComfyUI 自带 UI（但 xy-canvas workflow 不走这个）

### 1.7 xy-canvas 部署到 3000 端口（**完整步骤**）

#### 当前部署（docker 容器，60 机器）

**前提**：60 机器的 `/opt/xy-canvas/` 目录已经存在，docker + python:3.11-slim 镜像可用。

**一键启停**：
```bash
# 重启
sshpass -p '12301230' ssh sethchang@192.168.1.60 'echo "12301230" | sudo -S docker restart xy-canvas'
# 看日志
sshpass -p '12301230' ssh sethchang@192.168.1.60 'echo "12301230" | sudo -S docker logs xy-canvas --tail 30'
# 看状态
sshpass -p '12301230' ssh sethchang@192.168.1.60 'echo "12301230" | sudo -S docker ps --filter name=xy-canvas'
```

**冷启动（首次或重建）**：
```bash
sshpass -p '12301230' ssh sethchang@192.168.1.60
cd /opt/xy-canvas
echo "12301230" | sudo -S docker compose -f docker-compose.60.yml up -d
# 或者用旧版 docker-compose
echo "12301230" | sudo -S docker-compose -f docker-compose.60.yml up -d
```

**完整 docker-compose.60.yml**（实测在 `/opt/xy-canvas/docker-compose.60.yml`）：
```yaml
services:
  xy-canvas:
    image: python:3.11-slim
    container_name: xy-canvas
    working_dir: /app
    command: >
      sh -c "pip install --no-cache-dir -r requirements.txt &&
             uvicorn main:app --host 0.0.0.0 --port 3000"
    ports:
      - "3000:3000"
    volumes:
      - ./:/app
      - ./API/.env:/app/API/.env
      - ./data:/app/data
      - /vol3/@team/SJM-MediaFile/AI-Tool-Studio/xy-canvas/input:/app/input
      - /vol3/@team/SJM-MediaFile/AI-Tool-Studio/xy-canvas/output:/app/output
      - /vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui/workflows:/app/workflows/shared:ro
    restart: unless-stopped
```

**重要 volume 挂载点**（`/app` 内是容器视角）：
| 容器内路径 | 宿主机路径 | 用途 |
|---|---|---|
| `/app` | `/opt/xy-canvas/` | **代码**（main.py / canvas_video.py / static/ / workflows/） |
| `/app/API/.env` | `/opt/xy-canvas/API/.env` | 环境变量（含 COMFYUI_INSTANCES / API keys） |
| `/app/data` | `/opt/xy-canvas/data` | 用户数据库 + 上传数据 |
| `/app/input` | `/vol3/@team/SJM-MediaFile/AI-Tool-Studio/xy-canvas/input` | 用户上传图（在 NAS 上） |
| `/app/output` | `/vol3/@team/SJM-MediaFile/AI-Tool-Studio/xy-canvas/output` | 生成结果（在 NAS 上） |
| `/app/workflows/shared` | `/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui/workflows` | **共享 workflow 目录**（ro 只读） |

**代码生效规则**：
- **静态文件**（canvas.html / static/modules/*-node.js）改了立即生效，但前端有 `?v=2026XXXXXXX` 缓存戳，**用户必须硬刷（Ctrl+Shift+R）**
- **Python 文件**（main.py / canvas_video.py）改了**需要重启容器**才生效

**requirements.txt**（在 `/opt/xy-canvas/requirements.txt`）：
```
fastapi
uvicorn[standard]
requests
pydantic
python-multipart
httpx
pillow
websockets
```

**启动时间**：约 30-60s（pip install 在容器启动时跑一次，第二次有缓存就快了）。

#### 如果要从零部署到新电脑 / 重建（**完整步骤**）

**A. 在 60 机器上**：
```bash
# 1. 准备目录
sshpass -p '12301230' ssh sethchang@192.168.1.60
sudo mkdir -p /opt/xy-canvas
sudo chown sethchang:Users /opt/xy-canvas

# 2. 拉代码（从 git 或 Mac 同步）
cd /opt/xy-canvas
git clone <repo> .  # 或者从 Mac 用 rsync 同步
# 重要: API/.env 单独有,别覆盖!
ls API/  # 应该有 .env

# 3. 准备 NAS 挂载点（如果没挂）
sudo mkdir -p /vol3/@team/SJM-MediaFile/AI-Tool-Studio/xy-canvas/{input,output}
sudo mount -t cifs -o username=sethchang,password=12301230 //192.168.1.60/团队文件-SJM-MediaFile /vol3/@team/SJM-MediaFile

# 4. 起容器
cd /opt/xy-canvas
echo "12301230" | sudo -S docker compose -f docker-compose.60.yml up -d

# 5. 验证
sleep 30
curl http://192.168.1.60:3000/  # 应该返回 HTML
```

**B. 在 ComfyUI 机器（195/197/249 任一台）上**：
```bash
# 1. 登录
sshpass -p 'Sjm744546' ssh sjm@192.168.1.195

# 2. 装 ComfyUI（如果没装）
git clone https://github.com/comfyanonymous/ComfyUI.git /home/sjm/ComfyUI
cd /home/sjm/ComfyUI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 挂载 NAS（如果没挂）
sudo mkdir -p /mnt/nas_comfyui
sudo mount -t cifs -o username=sjm,password=Sjm744546,uid=1000,gid=1000 \
  //192.168.1.60/团队文件-SJM-MediaFile /mnt/nas_comfyui

# 4. 创建 models symlink 链 NAS（已部署的机器就这么做的）
cd /home/sjm/ComfyUI/models
ln -s /mnt/nas_comfyui/checkpoints checkpoints
ln -s /mnt/nas_comfyui/loras loras
ln -s /mnt/nas_comfyui/vae vae
# ... 其他 12 个目录（见 §1.8）

# 5. 写 extra_model_paths.yaml
cat > /home/sjm/ComfyUI/extra_model_paths.yaml << 'EOF'
aitoolstudio:
  base_path: /mnt/nas_comfyui/AI-Tool-Studio/comfyui
  is_default: true
  checkpoints: models/checkpoints
  loras: models/loras
  vae: models/vae
  clip: models/clip
  text_encoders: models/text_encoders
  unet: models/unet
  diffusion_models: models/diffusion_models
  controlnet: models/controlnet
  upscale_models: models/upscale_models
  clip_vision: models/clip_vision
  embeddings: models/embeddings
  latent_upscale_models: models/latent_upscale_models
  audio_encoders: models/audio_encoders
  audio_vae: models/audio_vae
  model_patches: models/model_patches
  configs: models/configs
  sams: models/sams
EOF

# 6. 启动 ComfyUI
cd /home/sjm/ComfyUI
nohup python3 main.py --listen 0.0.0.0 --port 8188 > /tmp/comfyui.log 2>&1 &

# 7. 验证
sleep 30
curl http://localhost:8188/system_stats  # 应该返回 JSON
```

**C. 验证整条链路**：
```bash
# 从 Mac 跑
/usr/bin/python3 /tmp/v6_check/re_play.py  # Playwright 完整 web UI 验证
```

### 1.8 NAS 挂载信息

**NAS 自身**：60 机器就是 NAS 服务器（hostname `SJM-MediaFile`），`/vol3` 是个 191T 的 Btrfs 卷（`df -h /vol3` 看：`trim_67568013-c543-47f7-bd47-84d152c77c49  191T  1.8T  190T  1%`）。

**NAS 共享名**：`//192.168.1.60/团队文件-SJM-MediaFile`

**挂载方式**（cifs/smb 凭据）：

| 机器 | 挂载点 | 挂载选项 | 用户 | 用途 |
|---|---|---|---|---|
| 60 | `/home/sethchang/smb` | `username=sethchang,uid=0,noforceuid` | sethchang (root) | 60 自己访问 NAS（self-mount） |
| 60 | `/vol3/@team/SJM-MediaFile` | **btrfs native** | - | 60 自身 NAS 卷根 |
| 195 | `/mnt/nas_comfyui` | `username=sjm,uid=1000,forceuid,gid=1000,forcegid` | sjm | ComfyUI 模型/工作流 |
| 249 | `/mnt/nas_comfyui` | 同 195 | sjm | 同 195 |
| 197 | `/mnt/nas_comfyui` | 同 195 | sjm | 同 195 |
| Mac 本机 | finder 里 `smb://192.168.1.60/团队文件-SJM-MediaFile` | 用户登录态 | apple | dev 副本同步 |

**从 Mac 访问 NAS**：
```
Finder → 前往 → 连接服务器 (⌘K) → smb://192.168.1.60 → 
用户名: apple (或 sjm 看权限) → 浏览 "团队文件-SJM-MediaFile"
```

**NAS 关键子目录**：
```
/vol3/@team/SJM-MediaFile/
├── AI-Tool-Studio/
│   ├── xy-canvas/                 # xy-canvas input/output
│   ├── xy-canvas-source/          # 同步源副本（不要改这里！）
│   └── comfyui/
│       ├── workflows/             # ComfyUI 共享工作流
│       │   ├── video/             # 11 个 video workflow
│       │   ├── image/             # 图片工作流
│       │   └── *.json             # 散落工作流
│       ├── models/                # **所有模型都在这里**（150+ GB）
│       │   ├── checkpoints/       # 基础模型（SDXL, Flux 等）
│       │   ├── loras/             # LoRA
│       │   ├── text_encoders/     # text encoder
│       │   ├── diffusion_models/  # LTX 22B, Wan2.1 等
│       │   ├── vae/
│       │   ├── controlnet/
│       │   ├── upscale_models/    # SeedVR2 等
│       │   ├── audio_encoders/    # LTX-AV
│       │   ├── audio_vae/         # LTX-AV
│       │   └── ... 12+ 子目录
│       ├── outputs/               # ComfyUI 输出
│       └── scripts/               # 杂项脚本
```

**LTX 22B distilled 模型位置**（在 NAS）：
```
/mnt/nas_comfyui/AI-Tool-Studio/comfyui/models/diffusion_models/ltx-2.3-22b-distilled-fp8.safetensors
/mnt/nas_comfyui/AI-Tool-Studio/comfyui/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors
```

**ComfyUI models 目录的 symlink 链**（在 195 实测，其他两台应该一样）：
```bash
ls -la /home/sjm/ComfyUI/models
# audio_encoders -> /mnt/nas_comfyui/audio_encoders
# checkpoints -> /mnt/nas_comfyui/checkpoints
# clip -> /mnt/nas_comfyui/clip
# clip_vision -> /mnt/nas_comfyui/clip_vision
# configs -> /mnt/nas_comfyui/configs
# controlnet -> /mnt/nas_comfyui/controlnet
# diffusers -> /mnt/nas_comfyui/diffusers
# diffusion_models -> /mnt/nas_comfyui/diffusion_models
# embeddings -> /mnt/nas_comfyui/embeddings
# gligen -> /mnt/nas_comfyui/gligen
# hypernetworks -> /mnt/nas_comfyui/hypernetworks
# latent_upscale_models -> /mnt/nas_comfyui/latent_upscale_models
# loras -> /mnt/nas_comfyui/loras
# model_patches -> /mnt/nas_comfyui/model_patches
# photomaker -> /mnt/nas_comfyui/photomaker
# sams -> /mnt/nas_comfyui/sams
# style_models -> /mnt/nas_comfyui/style_models
# text_encoders -> /mnt/nas_comfyui/text_encoders
# unet -> /mnt/nas_comfyui/unet
# upscale_models -> /mnt/nas_comfyui/upscale_models
# vae -> /mnt/nas_comfyui/vae
# vae_approx -> /mnt/nas_comfyui/vae_approx
```

---

## 2. 视频生成是怎么串起来的

```
Web UI (canvas.html iframe)
  ↓ 点菜单 "视频生成" → addVideoNode()
video-node.js 渲染节点 UI
  ↓ 选 provider="comfyui" → 出现 .comfyui-prompt textarea + 8 字段 + workflow 下拉
  ↓ 用户填 prompt/width/height/.../workflow
  ↓ 点 "生成视频" → POST /api/canvas-video-tasks
canvas_video.py 接收请求
  ↓ workflow_json 加载 /opt/xy-canvas/workflows/<name>.json
  ↓ 按 NODE_ROLES 字典（class_type → 角色）识别节点
  ↓ 把语义参数 (prompt/negative/w/h/length/fps/steps/cfg/seed) 注入对应节点
  ↓ params 字段允许节点级覆盖
  ↓ 提交到 ComfyUI (195/197/249 任一台)
  ↓ 轮询任务状态
  ↓ 完成 → 视频文件 + 元数据
返回前端
```

**关键代码位置**（在 `/opt/xy-canvas/canvas_video.py`）：
- `NODE_ROLES` 字典 (line 40-200) — class_type → 角色映射
- 端点 `/api/canvas-video-tasks/templates` (line 1051) — 列出所有 workflow
- 端点 `/api/canvas-video-tasks/inspect` (line 920) — 检查 workflow 结构
- 端点 `/api/canvas-video-tasks` (line 654) — 提交任务
- 端点 `/api/canvas-video-tasks/{id}` (line 975) — 查询任务

**前端 video-node.js 关键 class**：
- `.video-provider` — provider 下拉（comfly/modelscope/comfyui）
- `.video-model` — 旧模型下拉（comfly 用）
- `.comfyui-workflow` — workflow 下拉（**ComfyUI 模式才出现**）
- `.comfyui-prompt` — **video node 自己的 prompt textarea**（**6月8日新加的**，痛点修了）
- `.comfyui-image-section` — I2V 图片上传区（**按 workflow 名字自动显隐**）
- 8 字段：`.video-w / .video-h / .video-length / .video-fps / .video-steps / .video-cfg / .video-negative / .video-seed`

---

## 3. 10 个 video workflow 跑通情况（2026-06-08 测）

| # | workflow 文件名 | 跑通 | photorealism 评分 | 结论 |
|---|---|---|---|---|
| 1 | `ltx_1080p_v4.json` | ✅ | **3/10** | 概念艺术, 当前最佳基线 |
| 2 | `ltx_1080p_v5_seedvr2.json` | ✅ | 2/10 | SeedVR2 让它退步（3→2） |
| 3 | `ltx_ltx-i2v.json` (空 prompt / 重跑) | ✅ / ✅ | 2/10 / 3/10 | prompt 注入对就 ok |
| 4 | `ltx_ltx-t2v-lora.json` | ✅ | <2/10 | **内容完全错位**（没 hummingbird）+ 严重质量低 |
| 5 | `ltx_studio_quality.json` | ✅ | 3/10 | v4 副本，跟 v4 同 |
| 6 | `ltx_图生视频-ltx2.3.json` (smb) | ✅/❌ | - | 看 subagent 注入 |
| 7 | `ltx_视频超分-ltx-twostage.json` | ✅ | <2/10 | 风格 melted, 内容不对 |
| 8 | `ltx_音视频-ltx-av.json` | ❌ | - | **节点 16 连线错**（已知 bug） |
| 9 | `seedvr2_standalone.json` | ✅ | 2/10 | **油画感**（用户痛点） |
| 10 | `seedvr2_standalone_v2.json` | - | - | （v2 跟 v1 类似，单独 v2v 流程） |
| 11 | `视频反推.json` | ❌ | - | **缺 video_output 节点**（vhs_videocombine 没接） |

**参考截图**（在 `/tmp/v6_check/runs/`）：
- `v4_f8.png` — v4 LTX 22B distilled：3/10 photorealism
- `v5_seedvr2_f8.png` — v5 + SeedVR2：2/10（退步）
- `i2v_v2_f8.png` — I2V（正确注入 prompt 后）：3/10

---

## 4. 关键发现 — 油画感不怪 SeedVR2

我之前给"v4 9.4/10 studio quality"评分是**误导**——那评分是"概念艺术质量 + 细节 + temporal 稳"，**不是** photorealism。

**LTX 22B distilled 本身只有 3/10 photorealism**（偏概念艺术 / digital illustration 风格）：
- v4 = 3/10（v3/v4 调优的"9.4"是概念艺术 9.4，**不**是 photorealism）
- v5 + SeedVR2 = 2/10（退步）
- standalone v2v + SeedVR2 = 2/10（油画感）

**用户对"油画感"的不满** = LTX 22B 本来就偏插画，SeedVR2 又加重了。不是 SeedVR2 单独的问题。

---

## 5. 建议方向（决策表）

| 选项 | 投入 | 收益 | 风险 |
|---|---|---|---|
| **A. 接受 v4，删 SeedVR2 workflow** | 0 | 回到 v4 基线 3/10（概念艺术最佳） | 无 |
| B. 换 Wan2.1 14B（photorealistic 强） | 2-3h | 预期 6-7/10 photorealism | 大量重做 |
| C. 加 LatentUpscale 节点（不重画） | 30min | 1.1x 分辨率提升, 不破坏 | 边际小 |
| D. 接受现状 + 用户改 prompt 用 v4 | 0 | 0 | 0 |

**Mavis 建议 A** — LTX 22B distilled 已经是它能给的最好，把 seedvr2_standalone.json 跟 v5_seedvr2.json 标 "⚠️ 艺术化" 警告，**不让它**挡在主推荐。后续如果用户要 photorealism，再上 Wan2.1 14B（选项 B）。

---

## 6. 修复清单

### ✅ A. web UI prompt textarea 痛点 — **已完成**

**问题**：video-node.js 的 render 里漏了 `.comfyui-prompt` textarea，导致用户切到 ComfyUI 模式时只能复用 `.prompt-list`（空 div，没法编辑）。

**修复**：在 `/opt/xy-canvas/static/modules/video-node.js` 加 `.comfyui-prompt` textarea + 缓存戳 bump 到 `v=20260608001`（6月8日 19:37）。

**验证**：2026-06-09 13:25 playwright 复测全通过（见 §7）。

### ⏳ B. seedvr2 standalone / v5 加 "⚠️ 艺术化" 警告 — 待办

**目标**：在 `canvas_video.py` 的 `/api/canvas-video-tasks/templates` 端点（line 1051）返回的 workflow 列表里，给 seedvr2_standalone.json / seedvr2_standalone_v2.json / ltx_1080p_v5_seedvr2.json 加 `style_tag: "artistic"` 字段（或 `warning: "⚠️ 油画/插画感强，不适合 photorealism 场景"`），前端在 workflow 下拉里展示警告。

**实现**：
1. `canvas_video.py` line 1051-1091：返回每个 workflow 元数据时加 `style_tag` / `warning`
2. `video-node.js` workflow `<option>` 渲染时读 `style_tag`，警告的 workflow option 文字后加 `⚠️`

**预计投入**：30min-1h。

### ⏳ C. 音视频 workflow 节点 16 连线修 — 待办

**问题**：`ltx_音视频-ltx-av.json` 节点 16 连线错（具体哪个连错需要看 workflow JSON）。

**位置**：`/opt/xy-canvas/workflows/ltx_音视频-ltx-av.json`

**实现**：
1. 读 workflow JSON，定位节点 16 的 input 引用
2. 对照其他能跑通的 workflow（如 `ltx_1080p_v4.json`）的同位置连线
3. 修完跑一次端到端验证

**预计投入**：1-2h（要看具体错在哪）。

### ⏳ D. 视频反推 workflow 缺 video_output 节点 — 待办

**问题**：`视频反推.json` workflow 跑完没视频输出，缺 video_output 节点（vhs_videocombine 没接上）。

**位置**：`/opt/xy-canvas/workflows/视频反推.json`

**实现**：
1. 读 workflow JSON，找到最后一个输出节点
2. 末尾加一个 `VHS_VideoCombine` 节点（或现有 video_output 接好）
3. 检查输入边对不对
4. 跑通验证

**预计投入**：1-2h。

### ⏳ E. t2v-lora workflow 质量差决定 — 待办

**问题**：`ltx_ltx-t2v-lora.json` 跑出来内容完全错位（用户 prompt 提到 hummingbird，输出根本没），photorealism <2/10。

**选项**：
- F1. 修 LoRA 加载或 prompt 注入路径，重跑
- F2. 下架这个 workflow，从 templates 里移除
- F3. 保留但加 "⚠️ 实验性" 警告

**建议**：先 F1（投入 30min），不行就 F2。

### ⏳ F. 图生视频 smb 注入 — 待办

**问题**：`ltx_图生视频-ltx2.3.json` 注入是否正确需要 subagent 验证。

**位置**：`/opt/xy-canvas/workflows/ltx_图生视频-ltx2.3.json`

**建议**：跟 A 项 playwright 验证脚本扩展一下，覆盖 I2V workflow 的图片上传 → inspect → 提交 → 看输出。

---

## 7. 验证脚本（已跑通）

`/tmp/v6_check/re_play.py` — 2026-06-09 13:25 重跑 Playwright headless Chromium 验证 web UI。

**复现步骤**：
```bash
# Mac 本地 (用户机器)
/usr/bin/python3 /tmp/v6_check/re_play.py 2>&1 | tail -100
```

**输出**（节选）：
```json
{
  "iframe_src": "/static/canvas.html?v=20260603005",
  "scripts_video_node": [
    "http://192.168.1.60:3000/static/modules/video-node.js?v=20260608001"
  ],
  "v20260608001": true,
  "addVideoNode": {"ok": true},
  "comfyui_selected": true,
  "comfyui_prompt_visible": true,
  "comfyui_prompt_value": "a photorealistic portrait of an elderly fisherman...",
  "comfyui_prompt_match": true,
  "workflow_count": 11,
  "fields_present": {
    "宽度": true, "高度": true, "帧数": true, "帧率": true,
    "步数": true, "CFG": true, "反向": true
  },
  "i2v_picked": "ltx_ltx-i2v.json",
  "image_section_i2v": {"display": "block", "classes": "comfyui-image-section mb-2"},
  "t2v_picked": "ltx_ltx-t2v-lora.json",
  "image_section_t2v": {"display": "none", "classes": "comfyui-image-section mb-2"},
  "e5_alert": ["请输入提示词"],
  "e6_alert": ["请先选择一个 ComfyUI 工作流"]
}
```

**截图**（在 `/tmp/v6_check_re/`）：
- `02_comfyui_selected.png` — ComfyUI 模式已选
- `03_prompt_filled.png` — .comfyui-prompt textarea 可填充
- `04_i2v.png` — I2V workflow 选中后图片上传区自动显示
- `05_t2v.png` — 切回 T2V 后图片区自动隐藏

---

## 8. 用户对话历史（完整时间线）

### Round 1 (2026-06-08 19:00-20:30)
- 用户："你自己用 computer use 验证一下" — 让 Mavis 自己跑真实浏览器
- Mavis 完成 web UI E2E 验证，发现痛点：video node 没有自己的 prompt textarea
- 写了报告 `/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/E2E-verify-2026-06-08.md`
- 跑通 10 个 workflow 视觉评估（v4=3/10 photorealism, v5=2/10, i2v=3/10, ...）
- **关键发现**：LTX 22B distilled 本身 photorealism 3/10，SeedVR2 不是元凶

### Round 2 (2026-06-08 20:30-21:00)
- 用户追问
- Mavis 修复 video-node.js 加 `.comfyui-prompt` textarea
- 部署到 60 机器 `/opt/xy-canvas/`
- bump 缓存戳到 v=20260608001
- 用 Playwright 验证全通过

### Round 3 (2026-06-09 13:19)
- daemon 重启，session 修复
- Mavis 重新跑 Playwright 复测 — **全通过**（web UI 痛点真修好了）

### Round 4 (2026-06-09 13:27) — **当前**
- 用户要交接文档
- Mavis 写这份 doc

---

## 9. 接手 agent 行动清单

按优先级排序：

1. **【高】B. seedvr2 加艺术化警告**（30min）— 用户痛点最直接
2. **【高】C. 音视频 workflow 连线修**（1-2h）— 让一个 workflow 从 ❌ 变 ✅
3. **【高】D. 视频反推加 video_output 节点**（1-2h）— 让一个 workflow 从 ❌ 变 ✅
4. **【中】E. t2v-lora 决定**（30min-1h）— 决定保留/下架
5. **【低】F. 图生视频 smb 注入验证**（1-2h）— 扩展 playwright 脚本
6. **【决策】5 选项 B：换 Wan2.1 14B**（2-3h）— **如果用户要 photorealism 才做**

**复测验证**：每修一项，扩展 `/tmp/v6_check/re_play.py` 跑一次 playwright 验证，把截图存到 `/tmp/v6_check_re/`，加 timestamp。

---

## 10. 风险 / 注意事项

1. **不要改 `/fs/1001/.../xy-canvas-source/`** — 那是同步源不是服务源。Mavis 之前 ssh 错地方误判"修复没生效"。
2. **改 `/opt/xy-canvas/` 不用 docker restart** — 容器挂载的是 host 目录，Python 进程 reload 才会生效；静态文件 (canvas.html / video-node.js) 用户硬刷 (Ctrl+Shift+R) 即可；Python 文件改完需要重启 uvicorn / docker restart。
3. **缓存戳记得 bump** — `video-node.js?v=20260608001` 这种。用户没硬刷就看不到新代码。
4. **GPU 调度**：195/249 是 4090 48G，197 是 2080Ti 22G。LTX 22B 必须 195 或 249，**别往 197 提交**（会 OOM）。
5. **ComfyUI /system_stats 的 mem_total 经常返 0.0G** — 显存以 nvidia-smi 为准。
6. **prompt 注入错 workflow 就崩** — 之前 i2v_v1（空 prompt）跑出来 2/10，注入对就 3/10。修 workflow 时一定先 inspect 再提交。

---

## 11. 参考资料

- 完整 E2E 报告：`/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/E2E-verify-2026-06-08.md`
- v5 seedvr2 测试：`/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/v5-seedvr2-test-report.md`
- 视频任务 E2E 报告：`/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/video-task-e2e-report.md`
- 之前的决策 JSON：`/Users/apple/Documents/GitHub/aitoolstudio/.mavis/plans/decision-*.json`
- 6月8日 playwright 脚本（原始）：`/tmp/v6_check/a_playwright.py`
- 6月9日 playwright 复测脚本：`/tmp/v6_check/re_play.py`
- 截图（6月8日）：`/tmp/v6_check/*.png`
- 截图（6月9日复测）：`/tmp/v6_check_re/*.png`
- 视频帧（v4/v5/i2v/standalone）：`/tmp/v6_check/runs/`

---

## 12. 一页 Cheat Sheet（贴在桌面上看）

```
┌─────────────────────────────────────────────────────────────┐
│  4 台机器 + 关键端口（记住这个就够）                            │
│                                                              │
│  60  sethchang/12301230  →  3000 (xy-canvas web)              │
│  195 sjm/Sjm744546       →  8188 (ComfyUI, RTX 4090 48G)     │
│  249 sjm/Sjm744546       →  8188 (ComfyUI, RTX 4090 48G)     │
│  197 sjm/Sjm744546       →  8188 (ComfyUI, 2× RTX 2080Ti 22G)│
│                                                              │
│  改代码路径: 60 机器 /opt/xy-canvas/  (不要改 xy-canvas-source)│
│  重启: echo "12301230"|sudo -S docker restart xy-canvas      │
│  静态文件改完用户硬刷 (Ctrl+Shift+R)                            │
│                                                              │
│  NAS: //192.168.1.60/团队文件-SJM-MediaFile (191T)            │
│  60 端: /vol3/@team/...  其他机: /mnt/nas_comfyui/            │
└─────────────────────────────────────────────────────────────┘
```

---

**祝顺利！有问题直接 ping Mavis 续命。** 🚀
