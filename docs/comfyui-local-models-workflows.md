# 60 盘网站连接 195 ComfyUI：模型与 Workflow 放置规范

最后核对日期：2026-05-09

本文档只针对当前生产形态：AI Tool Studio 网站部署在 60 盘，后端通过 HTTP 连接 `192.168.1.195:8188` 上的本地 ComfyUI。它不是泛泛而谈的 ComfyUI 教程。

核心关系先说死，免得后面靠记忆维护生产系统：

- `192.168.1.60`：团队 SMB/存储盘，保存共享模型目录和 workflow 导入目录。
- `192.168.1.195`：真正运行 ComfyUI 的 GPU 主机，负责加载模型、执行 workflow、产出图片/视频。
- AI Tool Studio 后端：运行网站 API，默认通过 `COMFYUI_BASE_URL=http://192.168.1.195:8188` 调 ComfyUI。
- 网站容器内 `/app/workflow-imports`：只用于读取 60 盘上的 workflow JSON，然后导入到平台配置。
- ComfyUI 的模型加载：只看 195 主机上的 ComfyUI 配置和挂载路径，不看网站容器里的路径记录。

别把模型、workflow、网站容器、195 本地路径混成一锅粥。混了就会出现“后台看得到路径，ComfyUI 却找不到模型”这种低级事故。

## 1. 适用范围

适用于以下场景：

- 60 盘部署的 AI Tool Studio 网站。
- 网站后端连接 `http://192.168.1.195:8188` 的本地 ComfyUI。
- 60 盘 SMB 目录保存团队共用模型和 workflow。
- 管理员在 AI Tool Studio 后台维护模型路径记录和 API-format workflow。

不覆盖：

- 云端 ComfyUI 托管平台的私有部署规则。
- 其他机器的 ComfyUI 部署。
- 每个第三方 custom node 的专属模型目录。遇到 custom node，优先看它自己的 README。

## 2. 基本原则

1. 模型文件按类型放，不按“我今天下载得很开心”放。
2. Workflow 中引用的模型名必须和 ComfyUI 下拉框里的名称一致。
3. 给 AI Tool Studio 导入的 workflow 必须是 ComfyUI API-format，不是普通 UI 画布 JSON。
4. custom node 的代码和依赖安装在 ComfyUI 环境里，不安装在 AI Tool Studio 后端环境里。
5. 60 盘只是共享存储；195 的 ComfyUI 是否能加载模型，取决于 195 本机是否挂载并配置了对应目录。
6. 修改模型路径或新增模型后，优先刷新 ComfyUI；不识别就重启 ComfyUI。

## 3. 当前生产路径总表

| 用途 | 位置/地址 | 谁使用 | 说明 |
|---|---|---|---|
| 网站部署/容器所在存储 | `192.168.1.60` | AI Tool Studio | 网站代码、容器挂载、共享文件入口。 |
| ComfyUI 服务 | `http://192.168.1.195:8188` | AI Tool Studio 后端 | 后端通过 `/system_stats`、`/object_info`、`/prompt`、`/history`、`/view` 调用。 |
| Workflow SMB 源目录 | `smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Workflows` | 管理员/团队 | 放 API-format workflow JSON。 |
| Workflow 容器挂载点 | `/app/workflow-imports` | AI Tool Studio 后端容器 | Compose 已挂载为只读：`/vol3/@team/SJM-MediaFile/Comfyui_Workflows:/app/workflow-imports:ro`。 |
| 模型 SMB 根目录 | `smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model` | 管理员/195 主机 | 团队模型文件统一放这里。 |
| 模型路径默认示例 | `smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders` | 后台 Paths 面板 | 当前代码默认记录的快捷路径。 |
| 195 本地模型挂载路径 | 例如 `/mnt/Comfyui_Model` | 195 ComfyUI | 实际路径以 195 机器挂载为准，后台只记录，不自动挂载。 |
| SMB 登录账号 | `sjm` | 管理员/维护人员 | 密码不要写进仓库文档；从内部凭据记录获取。 |

关键区别：

- Workflow 导入路径是给“网站后端容器”读的。
- 模型目录是给“195 上的 ComfyUI”读的。
- 后台 Paths 面板只是登记簿，不是魔法挂载器。别指望填了 SMB 地址，ComfyUI 就突然懂了。

## 4. 60 盘目录规范

60 盘团队目录建议保持下面这个结构：

```text
团队文件-SJM-MediaFile/
├── Comfyui_Workflows/
│   ├── image/
│   ├── video/
│   ├── disabled/
│   └── README.md
└── Comfyui_Model/
    ├── checkpoints/
    ├── diffusion_models/
    ├── text_encoders/
    ├── clip/
    ├── clip_vision/
    ├── vae/
    ├── loras/
    ├── controlnet/
    ├── upscale_models/
    ├── embeddings/
    ├── audio_encoders/
    └── custom_nodes_models/
```

服务器本地路径当前 Compose 已使用：

```text
/vol3/@team/SJM-MediaFile/Comfyui_Workflows
```

也就是说，网站容器里看到的是：

```text
/app/workflow-imports
```

这两个路径指向同一个 workflow 目录，只是一个是 60 主机路径，一个是容器路径。

## 5. 登录 60 盘 SMB

SMB 地址：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile
```

登录账号：

```text
sjm
```

密码：从内部凭据记录获取。不要把明文密码写进 Git 仓库、README、Markdown、截图或聊天记录转存里。你要是把密码写进仓库，后面排查泄漏比排查 ComfyUI 节点还烦。

### 5.1 macOS Finder 登录

1. 打开 Finder。
2. 按 `Command + K`。
3. 输入：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile
```

4. 用户名填写 `sjm`。
5. 密码填写内部凭据记录中的 SMB 密码。
6. 登录后进入：

```text
Comfyui_Workflows/
Comfyui_Model/
```

### 5.2 Windows 登录

在资源管理器地址栏输入：

```text
\\192.168.1.60\团队文件-SJM-MediaFile
```

用户名填写：

```text
sjm
```

密码填写内部凭据记录中的 SMB 密码。

### 5.3 Linux / 195 主机挂载示例

195 如果需要把 60 盘模型目录挂载为 `/mnt/Comfyui_Model`，示例命令如下。把密码放进 root-only 凭据文件，别直接写在命令行历史里。

创建凭据文件：

```bash
sudo install -m 600 /dev/null /etc/samba/credentials-sjm
sudo sh -c 'cat > /etc/samba/credentials-sjm <<EOF
username=sjm
password=填写内部凭据记录中的SMB密码
EOF'
```

创建挂载目录：

```bash
sudo mkdir -p /mnt/Comfyui_Model
```

临时挂载：

```bash
sudo mount -t cifs "//192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model" \
  /mnt/Comfyui_Model \
  -o credentials=/etc/samba/credentials-sjm,iocharset=utf8,vers=3.0,uid=$(id -u),gid=$(id -g)
```

验证：

```bash
ls /mnt/Comfyui_Model
```

如果需要开机自动挂载，把下面这一行加入 `/etc/fstab`：

```fstab
//192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model /mnt/Comfyui_Model cifs credentials=/etc/samba/credentials-sjm,iocharset=utf8,vers=3.0,nofail 0 0
```

然后执行：

```bash
sudo mount -a
ls /mnt/Comfyui_Model
```

## 6. 195 ComfyUI 推荐目录结构

标准 ComfyUI 根目录建议如下：

```text
ComfyUI/
├── custom_nodes/
├── input/
├── output/
├── temp/
├── models/
│   ├── checkpoints/
│   ├── diffusion_models/
│   ├── text_encoders/
│   ├── clip/                 # 旧版 CLIP 路径，仍常见；优先使用 text_encoders
│   ├── clip_vision/
│   ├── vae/
│   ├── loras/
│   ├── controlnet/
│   ├── upscale_models/
│   ├── embeddings/
│   ├── configs/
│   ├── diffusers/
│   ├── vae_approx/
│   ├── style_models/
│   ├── audio_encoders/
│   ├── model_patches/
│   ├── gligen/
│   ├── hypernetworks/
│   ├── photomaker/
│   └── classifiers/
├── extra_model_paths.yaml.example
└── extra_model_paths.yaml     # 手动创建，不提交敏感路径
```

如果 195 直接把 60 盘模型目录挂到本地，推荐挂载为：

```text
/mnt/Comfyui_Model
```

然后 ComfyUI 的额外模型路径配置指向这个本地路径。注意，是 195 本机路径，不是 `smb://...` 地址。

## 7. 模型放置规则

| 模型类型 | 推荐目录 | 常见加载节点/用途 | 备注 |
|---|---|---|---|
| SD 1.5 / SDXL / Pony 等整合 checkpoint | `Comfyui_Model/checkpoints/` | `CheckpointLoaderSimple` | 常见后缀为 `.safetensors`、`.ckpt`、`.pt` 等。 |
| FLUX / UNet / diffusion-only 权重 | `Comfyui_Model/diffusion_models/` 或 `Comfyui_Model/unet/` | `Load Diffusion Model` 等 | 不要看到 `.safetensors` 就扔进 `checkpoints`。看 workflow 用什么 loader。 |
| VAE | `Comfyui_Model/vae/` | `VAELoader` | 如果 checkpoint 已内置 VAE，workflow 未必需要单独 VAE。 |
| LoRA / LyCORIS | `Comfyui_Model/loras/` | `LoraLoader` | Workflow 中 LoRA 文件名必须匹配。 |
| Text Encoder / CLIP / T5 | `Comfyui_Model/text_encoders/`，旧版也可能用 `Comfyui_Model/clip/` | Dual CLIP、CLIP loader 等 | 新项目优先 `text_encoders`。 |
| CLIP Vision | `Comfyui_Model/clip_vision/` | `CLIPVisionLoader` | IP-Adapter、图像理解类流程常用。 |
| ControlNet / T2I Adapter | `Comfyui_Model/controlnet/` | ControlNet loader | 有些节点也会找 `t2i_adapter`，以节点文档为准。 |
| Upscaler / ESRGAN / RealESRGAN | `Comfyui_Model/upscale_models/` | Upscale model loader | 模型超分和普通 resize 不是一回事。 |
| Textual Inversion / Embedding | `Comfyui_Model/embeddings/` | Prompt embedding | 文件名会影响 prompt 调用方式。 |
| Diffusers 目录模型 | `Comfyui_Model/diffusers/` | Diffusers loader | 通常是一个模型文件夹，不是单文件。 |
| Audio encoder | `Comfyui_Model/audio_encoders/` | 音频/视频相关 custom workflow | 本项目已有 SJM audio encoder 路径记录。 |
| custom node 专用模型 | 按该节点 README | 该节点自带 loader | 例如 GGUF、IPAdapter、InstantID、ERNIE Image 等，别硬套核心目录。 |

命名建议：

- 文件名尽量使用英文、数字、短横线、下划线。
- 不建议使用中文、emoji、过长空格名。不是不能用，是出问题时你很难判断到底谁在搞事。
- 如果重命名模型，必须同步修改所有 workflow JSON 中引用的模型名。

## 8. 195 上的外部模型路径规范

195 的 ComfyUI 应通过本地挂载路径读取 60 盘模型。不要在 `extra_model_paths.yaml` 里直接写 `smb://...`，ComfyUI 需要的是 195 本机能访问的文件系统路径。

### 8.1 Portable / 手动安装版

在 ComfyUI 根目录复制：

```text
ComfyUI/extra_model_paths.yaml.example
```

重命名为：

```text
ComfyUI/extra_model_paths.yaml
```

示例：

```yaml
sjm_60_models:
  base_path: /mnt/Comfyui_Model
  checkpoints: checkpoints
  diffusion_models: |
    diffusion_models
    unet
  text_encoders: text_encoders
  clip: clip
  clip_vision: clip_vision
  vae: vae
  loras: loras
  controlnet: controlnet
  upscale_models: upscale_models
  embeddings: embeddings
  audio_encoders: audio_encoders
```

这里假设 195 已经把 60 盘的：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model
```

挂载到了：

```text
/mnt/Comfyui_Model
```

如果 195 实际挂载路径不是这个，照实际路径改 `base_path`。别脑补，去 195 上 `ls` 一下。

保存后重启 ComfyUI，并打开 `http://192.168.1.195:8188` 检查各 loader 下拉框是否能看到模型。

### 8.2 ComfyUI Desktop

ComfyUI Desktop 使用的配置文件位置不同：

```text
Windows: C:\Users\YourUsername\AppData\Roaming\ComfyUI\extra_models_config.yaml
macOS:   ~/Library/Application Support/ComfyUI/extra_models_config.yaml
```

不要把 Desktop 的配置文件挪到 ComfyUI 根目录。要在原文件里追加配置，修改前先备份。

## 9. Workflow 文件规范

ComfyUI 有两种常见 workflow JSON：

| 类型 | 用途 | 是否适合 AI Tool Studio |
|---|---|---|
| UI 画布 workflow | 保存节点位置、连线、界面状态 | 不适合直接导入 |
| API-format workflow | 提交给 ComfyUI `/prompt` 执行 | 必须使用 |

AI Tool Studio 的导入器只接受 API-format workflow。结构必须类似这样：

```json
{
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "seed": 123456,
      "steps": 28,
      "cfg": 7,
      "model": ["4", 0],
      "positive": ["6", 0],
      "negative": ["7", 0],
      "latent_image": ["5", 0]
    }
  },
  "4": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": {
      "ckpt_name": "dreamshaperXL_lightningDPMSDE.safetensors"
    }
  }
}
```

也可以使用带元信息的包装格式：

```json
{
  "id": "sdxl-basic-txt2img",
  "name": "SDXL Basic Txt2Img",
  "description": "基础 SDXL 文生图工作流",
  "category": "image",
  "enabled": true,
  "workflow_json": {
    "4": {
      "class_type": "CheckpointLoaderSimple",
      "inputs": {
        "ckpt_name": "sd_xl_base_1.0.safetensors"
      }
    }
  },
  "notes": "需要 SDXL checkpoint"
}
```

## 10. AI Tool Studio Workflow 接入规则

当前项目相关代码：

- `img-platform/backend/services/comfyui.py`
- `img-platform/backend/services/comfyui_workflows.py`
- `img-platform/backend/services/model_paths.py`
- `img-platform/backend/api/comfyui.py`

### 10.1 服务地址

后端通过环境变量连接 ComfyUI：

```env
COMFYUI_BASE_URL=http://192.168.1.195:8188
COMFYUI_GENERATION_TIMEOUT=900
```

如果 ComfyUI 在另一台机器或 Docker 外部，启动时需要监听局域网地址：

```bash
python main.py --listen 0.0.0.0 --port 8188
```

验证：

```bash
curl http://192.168.1.195:8188/system_stats
curl http://192.168.1.195:8188/object_info
```

### 10.2 模型路径管理

后台的 `model-paths` 是路径记录和管理清单，不会自动帮你修改 ComfyUI 的 `extra_model_paths.yaml`，也不会自动搬模型。

换句话说：

- ComfyUI 能不能识别模型，看 ComfyUI 本机配置。
- AI Tool Studio 只是记录 `label`、`category`、`uri`、`mount_path`、`notes`。
- 管理员仍要保证 ComfyUI 主机能访问真实模型路径。

推荐在后台 Paths 面板这样填：

| 字段 | 示例 |
|---|---|
| Label | `SJM checkpoints` |
| Category | `checkpoints` |
| SMB / Storage URI | `smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/checkpoints` |
| 195 Mount Path | `/mnt/Comfyui_Model/checkpoints` |
| Notes | `195 ComfyUI extra_model_paths.yaml: sjm_60_models.checkpoints` |

当前代码默认已有一个 `audio_encoders` 示例：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders
```

它的 195 mount path 应填写为类似：

```text
/mnt/Comfyui_Model/audio_encoders
```

### 10.3 Workflow 导入目录

默认导入目录：

```text
/app/workflow-imports
```

可通过环境变量覆盖：

```env
COMFYUI_WORKFLOW_IMPORT_DIR=/app/workflow-imports
```

如果团队 workflow 放在 SMB，例如：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Workflows
```

当前 `docker-compose.yml` 已经把 60 盘本机路径挂载到后端容器：

```yaml
volumes:
  - /vol3/@team/SJM-MediaFile/Comfyui_Workflows:/app/workflow-imports:ro
```

所以网站后端导入 workflow 时读取的是：

```text
/app/workflow-imports
```

团队成员实际放文件时使用的是 SMB 目录：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Workflows
```

推荐结构：

```text
Comfyui_Workflows/
├── image/
│   ├── sdxl-basic.api.json
│   ├── flux-basic.api.json
│   └── ernie-image.api.json
├── video/
│   ├── wan-t2v.api.json
│   └── ltx-i2v.api.json
└── disabled/
    └── old-test.api.json
```

### 10.4 Runtime 参数替换

为了让平台能动态注入用户参数，workflow 应遵守以下约定：

| 参数 | 推荐写法 | 后端替换逻辑 |
|---|---|---|
| 正向提示词 | 文本输入中写 `{{prompt}}` | 替换为用户 prompt |
| 宽度 | `width` 或 `w`，值为整数 | 替换为用户选择尺寸 |
| 高度 | `height` 或 `h`，值为整数 | 替换为用户选择尺寸 |
| 批量数 | `batch_size` | 替换为用户选择数量 |
| 随机种子 | `seed` 或 `noise_seed` | 替换为用户 seed |
| checkpoint | `ckpt_name` | 用户选择 checkpoint 时替换 |
| 帧率 | `fps` | 视频 workflow 可替换 |
| 时长 | `duration` | 视频 workflow 可替换 |
| 帧数 | `num_frames`、`frames`、`frame_count`、`length`、`video_length` | 根据时长和 fps 计算 |

强制建议：在 prompt 节点里明确写 `{{prompt}}`。不要依赖后端“猜第一个 text 字段”，能跑但脆。

## 11. 更新 Workflow 到 AI Tool Studio

这部分是日常维护流程。目标很简单：195 ComfyUI 跑通的 workflow，放到 60 盘，然后同步进 AI Tool Studio 后台。

### 11.1 在 195 ComfyUI 中准备 workflow

1. 打开：

```text
http://192.168.1.195:8188
```

2. 在 ComfyUI 里加载或搭建 workflow。
3. 确认所有模型、LoRA、VAE、ControlNet、custom node 都能在 195 上正常加载。
4. 用真实 prompt 手动跑通一次。
5. 确认输出节点能写入结果：
   - 图片 workflow：使用 `SaveImage` 或等价输出。
   - 视频 workflow：history 中需要能读到 `videos` 或 `gifs` 输出。

### 11.2 导出 API-format JSON

AI Tool Studio 导入的是 ComfyUI API-format，不是普通 UI workflow JSON。

推荐做法：

1. 在 ComfyUI 设置里开启开发者/Dev 模式。
2. 使用 `Save (API Format)` 或等价导出方式。
3. 文件名使用：

```text
用途-模型-版本.api.json
```

示例：

```text
sdxl-basic-txt2img-v1.api.json
wan-t2v-720p-v1.api.json
ernie-image-v1.api.json
```

导出后打开 JSON 快速看一眼：每个节点应该有 `class_type` 和 `inputs`。如果里面主要是节点坐标、画布位置、UI 状态，那就是普通画布 JSON，别导入，导了也是浪费时间。

### 11.3 修改 workflow 参数占位

至少检查这些字段：

- 正向 prompt 文本建议写成 `{{prompt}}`。
- checkpoint 节点的 `ckpt_name` 必须是 195 ComfyUI 下拉框里真实存在的文件名。
- 图片 workflow 要有 `width`、`height`、`batch_size`、`seed` 或 `noise_seed`，这样平台才能替换用户参数。
- 视频 workflow 如果要吃时长/帧数，要使用 `duration`、`fps`、`num_frames`、`frames`、`frame_count`、`length` 或 `video_length` 这类字段。

### 11.4 放入 60 盘 workflow 目录

通过 SMB 登录 60 盘：

```text
smb://192.168.1.60/团队文件-SJM-MediaFile
```

账号：

```text
sjm
```

密码从内部凭据记录获取。

把 API-format JSON 放入：

```text
Comfyui_Workflows/image/
Comfyui_Workflows/video/
```

不要把测试废稿直接丢根目录。没启用但要保留的 workflow 放：

```text
Comfyui_Workflows/disabled/
```

### 11.5 在 AI Tool Studio 后台同步

1. 打开 AI Tool Studio。
2. 使用管理员账号登录。
3. 进入 `/admin`。
4. 打开 `Workflows` 面板。
5. 点击 `Sync Folder`。
6. 检查导入结果：
   - `imported`：成功导入的文件。
   - `skipped`：跳过或失败的文件，需要看 reason。
7. 确认 workflow 的：
   - Name
   - Category：图片填 `image`，视频填 `video`
   - Enabled
   - Notes

后端实际读取目录是：

```text
/app/workflow-imports
```

它来自 Compose 挂载：

```yaml
/vol3/@team/SJM-MediaFile/Comfyui_Workflows:/app/workflow-imports:ro
```

所以如果后台同步不到文件，先查容器挂载，不要先怀疑 ComfyUI。ComfyUI 还没轮到背锅。

### 11.6 生成页验证

图片 workflow：

1. 进入生成页。
2. Category 选择 `image`。
3. Model 选择 `comfyui-local`。
4. 选择刚同步的 workflow。
5. 输入简单 prompt。
6. 点击生成。
7. 确认结果进入平台历史，并保存到 `/uploads/comfyui`。

视频 workflow：

1. 进入生成页。
2. Category 选择 `video`。
3. Model 选择 `comfyui-local-video`。
4. 选择 `video` 类型 workflow。
5. 输入 prompt 并生成。
6. 如果超时，先看 195 ComfyUI 队列和显存，不要只盯前端报错。

### 11.7 更新已有 workflow

同名文件更新后，再点 `Sync Folder`。导入器会按 workflow id 或文件名 slug 更新已有记录。

建议：

- 小改动：沿用原 id，更新 notes 写清楚变化。
- 大改动：新建版本文件，例如 `sdxl-basic-txt2img-v2.api.json`。
- 不要把旧文件直接删除，先放 `disabled/` 观察一段时间。

## 12. Workflow 交付清单

交付一个 workflow 前，按这个清单检查：

- [ ] 在 ComfyUI 里手动跑通一次。
- [ ] 使用 API-format 导出，而不是普通 UI workflow JSON。
- [ ] 所有节点都有 `class_type` 和 `inputs`。
- [ ] prompt 输入包含 `{{prompt}}`。
- [ ] 图片 workflow 有可被 ComfyUI history 记录的图片输出，例如 `SaveImage`。
- [ ] 视频 workflow 有可被 history 记录的 `videos` 或 `gifs` 输出。
- [ ] 所有模型文件已经放在 60 盘 `Comfyui_Model` 正确分类目录，或 195 本地 ComfyUI 可识别的位置。
- [ ] 195 已挂载 60 盘模型目录，并且 `extra_model_paths.yaml` 指向 195 本地挂载路径。
- [ ] 所有 custom nodes 已安装在 195 的 ComfyUI 环境里，并且依赖装在 ComfyUI 的 Python 环境里。
- [ ] `category` 正确：图片为 `image`，视频为 `video`。
- [ ] 文件名包含用途和格式，例如 `sdxl-basic-txt2img.api.json`。
- [ ] JSON 已放入 60 盘 `Comfyui_Workflows`，网站容器能从 `/app/workflow-imports` 读到。

## 13. 常见问题排查

### 13.1 模型在 ComfyUI 里找不到

按顺序查：

1. 放错目录。checkpoint、LoRA、VAE、ControlNet 不是一个东西。
2. 用错 loader。FLUX/diffusion-only 模型通常不是 `CheckpointLoaderSimple`。
3. ComfyUI 没刷新。按 `r` 或重启。
4. `extra_model_paths.yaml` 缩进错误。YAML 缩进错一个空格就够你浪费半小时。
5. Desktop 版配置文件放错位置。
6. 195 没有挂载 60 盘模型目录，或挂载路径和 `extra_model_paths.yaml` 不一致。
7. custom node 要求的专属路径没有按 README 配。
8. 你只在 AI Tool Studio 后台 Paths 面板填了 SMB 地址，但没有配置 195 的 ComfyUI。这个填了也白填，后台不会替你改 195。

### 13.2 Workflow 导入失败

常见原因：

- 导入的是 UI 画布 JSON，不是 API-format。
- 根对象不是 node id 映射。
- node 缺少 `class_type`。
- `inputs` 不是对象。
- 使用了包装格式但 `workflow_json` 不是对象。
- JSON 文件有注释或尾逗号。JSON 没有注释，别把它当 JS。
- 文件没有放进 60 盘 `Comfyui_Workflows`，或者网站容器没有挂载到 `/app/workflow-imports`。
- Docker Compose 没带上 `/vol3/@team/SJM-MediaFile/Comfyui_Workflows:/app/workflow-imports:ro`。

### 13.3 Workflow 能导入但生成失败

常见原因：

- workflow 引用了本机不存在的模型名。
- custom node 没安装或版本不匹配。
- 输出节点没有写入 ComfyUI history 可读取的 `images`、`videos` 或 `gifs`。
- prompt 字段没被替换，或者被替换到了 negative prompt。
- 视频 workflow 的帧数、分辨率、显存需求超出机器能力。
- AI Tool Studio 能访问后端，但后端访问不到 ComfyUI 地址。
- Workflow JSON 在网站里导入成功，只代表网站读到了 JSON，不代表 195 有对应模型和 custom node。

## 14. 最小可用 Workflow 示例

```json
{
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "seed": 123456,
      "steps": 28,
      "cfg": 7,
      "sampler_name": "euler",
      "scheduler": "normal",
      "denoise": 1,
      "model": ["4", 0],
      "positive": ["6", 0],
      "negative": ["7", 0],
      "latent_image": ["5", 0]
    }
  },
  "4": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": {
      "ckpt_name": "sd_xl_base_1.0.safetensors"
    }
  },
  "5": {
    "class_type": "EmptyLatentImage",
    "inputs": {
      "width": 1216,
      "height": 704,
      "batch_size": 1
    }
  },
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "{{prompt}}",
      "clip": ["4", 1]
    }
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "low quality, blurry, watermark, text, logo",
      "clip": ["4", 1]
    }
  },
  "8": {
    "class_type": "VAEDecode",
    "inputs": {
      "samples": ["3", 0],
      "vae": ["4", 2]
    }
  },
  "9": {
    "class_type": "SaveImage",
    "inputs": {
      "filename_prefix": "aitoolstudio",
      "images": ["8", 0]
    }
  }
}
```

导入前把 `ckpt_name` 改成 ComfyUI 里真实存在的 checkpoint 名称。

## 15. 参考来源

- ComfyUI 官方 Models 文档：<https://docs.comfy.org/development/core-concepts/models>
- ComfyUI 官方 Workflow 概念：<https://docs.comfy.org/development/core-concepts/workflow>
- ComfyUI 官方 Workflow JSON 规范：<https://docs.comfy.org/specs/workflow_json>
- ComfyUI 官方 Cloud API workflow 说明：<https://docs.comfy.org/development/cloud/overview>
- ComfyUI `extra_model_paths.yaml.example`：<https://github.com/Comfy-Org/ComfyUI/blob/master/extra_model_paths.yaml.example>
