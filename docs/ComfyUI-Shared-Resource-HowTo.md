# ComfyUI 共享资源路径 How-to

更新时间：2026-06-01

本文档说明 AIToolStudio / ComfyUI 共享盘现在应该从哪里找模型、工作流、输入输出素材和下载缓存。2026-06-01 已将原先散在 60 盘一级目录的 ComfyUI 内容收进统一目录，后续不要再把模型或 workflow 放回 60 盘根目录。

## 1. 统一入口

### SMB / Finder 路径

```text
smb://192.168.1.60/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
```

### 当前 Mac 挂载路径

```text
/Volumes/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
```

### ComfyUI Worker 推荐 Linux 路径

如果 worker 把 60 盘根目录挂载在 `/mnt/nas_comfyui`，统一入口就是：

```text
/mnt/nas_comfyui/AI-Tool-Studio/comfyui
```

如果某台 worker 仍使用兼容挂载 `/mnt/comfyui-models`，统一入口就是：

```text
/mnt/comfyui-models/AI-Tool-Studio/comfyui
```

优先把 worker 收敛到 `/mnt/nas_comfyui`，不要为新路径再创建转接链接。

### 60 平台侧资源根目录

60 服务器上的真实路径需以本机挂载为准。当前运维基线通常是：

```text
/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui
```

设置前先在 60 服务器上执行：

```bash
ls -lah /vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui
```

AIToolStudio 环境变量应指向这个统一入口：

```env
AITOOL_RESOURCE_ROOT=/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui
RESOURCE_ROOT=/vol3/@team/SJM-MediaFile/AI-Tool-Studio/comfyui
```

本地 Mac 调试时对应为：

```env
AITOOL_RESOURCE_ROOT=/Volumes/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
RESOURCE_ROOT=/Volumes/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
```

`COMFYUI_INSTANCES` 不因这次整理改变，仍按在线 worker 列表配置。

## 2. 目录用途

```text
AI-Tool-Studio/comfyui/
  models/             标准模型目录，后续新增模型优先放这里
  workflows/          标准 workflow JSON 目录，后续新增 workflow 放这里
  assets/input/       平台或 ComfyUI 输入素材
  assets/output/      平台或 ComfyUI 输出素材
  downloads/cache/    模型下载缓存
  Comfyui_Model/      旧目录残留，只保留兼容和排障，不再新增文件
  Comfyui_Workflows/  旧 workflow 目录副本，只保留兼容和排障，不再新增文件
```

规则：

1. 新模型放 `models/<类型>/...`。
2. 新 workflow 放 `workflows/`。
3. 新下载任务先进入 `downloads/cache/`，完成后再落到 `models/`。
4. 不要再往 60 盘一级目录创建 `models`、`workflows`、`Comfyui_Model`、`Comfyui_Workflows`。
5. 不要把 `Comfyui_Model` 当作新模型目录使用；它现在只是历史残留区。

## 3. 模型放置规则

常见模型类型对应目录：

| 类型 | 目录 |
|---|---|
| Checkpoint / SD / SDXL | `models/checkpoints/` |
| LoRA | `models/loras/` |
| VAE | `models/vae/` |
| CLIP | `models/clip/` |
| Text encoder | `models/text_encoders/` |
| UNet | `models/unet/` |
| Diffusion model | `models/diffusion_models/` |
| ControlNet | `models/controlnet/` |
| Upscale model | `models/upscale_models/` |
| Latent upscale model | `models/latent_upscale_models/` |
| CLIP vision | `models/clip_vision/` |
| Embedding | `models/embeddings/` |
| Config | `models/configs/` |

新增模型前先搜索是否已经存在：

```bash
find /mnt/nas_comfyui/AI-Tool-Studio/comfyui/models -name '模型文件名.safetensors'
```

手动下载模型时只接受可信来源的直接模型文件链接，例如 `.safetensors`、`.ckpt`、`.pt`、`.pth`、`.bin`、`.gguf`。不要把网页地址、搜索页、网盘说明页直接当作模型 URL。

## 4. Workflow 使用规则

标准 workflow 目录：

```text
AI-Tool-Studio/comfyui/workflows
```

建议流程：

1. 在 ComfyUI 里确认 workflow 可以运行。
2. 导出 API-format JSON，或通过 AIToolStudio 导入向导转换 UI workflow。
3. 保存到 `workflows/`。
4. 在 AIToolStudio 后台执行 workflow 导入/预检。
5. 看清缺失模型、缺失 custom nodes 和可暴露参数。
6. 验收后再启用给普通用户。

不要把 workflow JSON 放进 `models/` 或 `Comfyui_Model/`。

## 5. Worker 配置要点

每台 ComfyUI worker 都要让 ComfyUI 看到新的统一入口。核心原则是：

```text
base_path = /mnt/nas_comfyui/AI-Tool-Studio/comfyui
```

`extra_model_paths.yaml` 的具体格式以当前 worker 已有文件为准，关键是把旧的共享盘根目录更新到新的 `AI-Tool-Studio/comfyui`。示例：

```yaml
aitoolstudio:
  base_path: /mnt/nas_comfyui/AI-Tool-Studio/comfyui
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
```

更新后重启 ComfyUI，再验收：

```bash
curl -fsS http://127.0.0.1:8188/system_stats >/dev/null
curl -fsS http://127.0.0.1:8188/object_info >/dev/null
```

从平台或任意局域网机器抽检：

```bash
curl -fsS http://192.168.1.195:8188/system_stats >/dev/null
curl -fsS http://192.168.1.197:8188/system_stats >/dev/null
curl -fsS http://192.168.1.249:8188/system_stats >/dev/null
```

## 6. AIToolStudio 使用路径

本地调试配置文件：

```text
/Users/apple/Documents/GitHub/aitoolstudio/API/.env
```

当前本地配置应包含：

```env
COMFYUI_INSTANCES=192.168.1.195:8188,192.168.1.197:8188,192.168.1.249:8188
AITOOL_RESOURCE_ROOT=/Volumes/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
RESOURCE_ROOT=/Volumes/团队文件-SJM-MediaFile/AI-Tool-Studio/comfyui
```

后台页面：

```text
/static/comfyui-settings.html
```

在“60 盘资源中心”里检测目录时，应看到这些目录可用：

```text
models/checkpoints
models/loras
models/vae
models/clip
models/unet
models/controlnet
models/upscale_models
workflows
assets/input
assets/output
downloads/cache
```

## 7. 当前整理结果

2026-06-01 已完成：

1. 顶层未完成下载文件 `LTX-2.3-dual*.qkdownloading` 已清理。
2. 60 盘一级目录不再保留 `assets`、`downloads`、`models`、`workflows`、`Comfyui_Model`、`Comfyui_Workflows`。
3. ComfyUI 相关内容已收进 `AI-Tool-Studio/comfyui/`。
4. 当前统一入口下没有 symlink。
5. `models/` 为标准模型目录，约 666G，197 个文件。
6. `workflows/` 为标准 workflow 目录，59 个文件。
7. `Comfyui_Model/` 和 `Comfyui_Workflows/` 只作历史兼容和排障，不作为新增入口。

## 8. 排障

### Worker 找不到模型

先查 worker 是否能看到统一入口：

```bash
ls -lah /mnt/nas_comfyui/AI-Tool-Studio/comfyui/models
```

再查 `extra_model_paths.yaml` 是否仍指向旧根目录。如果还是 `/mnt/nas_comfyui`，需要改成 `/mnt/nas_comfyui/AI-Tool-Studio/comfyui` 并重启 ComfyUI。

### 平台预检显示缺模型

确认平台 `AITOOL_RESOURCE_ROOT` 指向统一入口，而不是 60 盘根目录。

### 旧路径里还有文件

不要手工新建旧路径。若看到旧路径残留，先确认是不是 Finder 缓存或 SMB 占用，再安排维护窗口处理。新增内容只放统一入口。
