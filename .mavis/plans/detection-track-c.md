# Track C — ComfyUI 工作流（导入 / 校验 / 缺失模型）

> 范围：本地 `workflows/` 目录 12 个 JSON（7 个主流程 + 5 个 config），服务端 `GET /api/workflows` 列表、详情拉取，跨 60 盘 3 个 ComfyUI 实例（195 / 197 / 249）做模型与节点可用性核对，workflow-install API 行为记录。
>
> 时间：2026-06-04 14:17–14:35 (UTC+8)  
> 主机：192.168.1.60:3000（aitoolstudio-canvas）  
> 服务端 openapi 路径下未部署的端点已在「API 行为记录」标注。

---

## 0. 关键结论

| 项 | 结果 |
| --- | --- |
| 工作流 JSON 数量 | **7 个**主流程（`workflows/*.json` + `custom/*.json`） |
| 服务端注册工作流 | **5 个**（均为 `custom/...` 形式；其余 2 个仅在仓库内） |
| 模型引用总数 | **26**（去重后 23 个不同文件） |
| 缺失模型（MISSING） | **0** |
| 错放目录（WRONG_DIR） | **0**（修正 ComfyUI 现代 loader 的目录映射后） |
| 缺失自定义节点（MISSING class） | **0**（所用 28 个 class_type 全部存在于 3 个 ComfyUI 实例） |
| 阻断性工作流 | **无** — 所有已注册工作流在 60 盘就绪 |
| workflow-install 端点状态 | **未部署到 live server**（全部 404，需先升级服务） |

---

## 1. 工作流清单表

### 1.1 仓库内全部 7 个工作流 + 跨实例就绪状态

| workflow_id（注册名 / 文件） | 中文标题 | 节点数 | 模型引用数 | 缺失 | 错放目录 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| `custom/local-view-2511.json` (≡ `2511.json`) | 3D 视角变换（本地 2511） | 17 | 5 | 0 | 0 | **就绪** |
| `custom/黑白线稿.json` | custom/黑白线稿 | — | — | — | — | **未在仓库**（仅服务端注册） |
| `custom/local-edit-flux2-klein.json` (≡ `Flux2-Klein.json`) | 图片编辑（本地 Flux2-Klein） | 35 | 3 | 0 | 0 | **就绪** |
| `custom/local-detail-zimage.json` (≡ `Z-Image-Enhance.json`) | 细节增强（本地 Z-Image） | 23 | 4 | 0 | 0 | **就绪** |
| `custom/local-highres-seedvr2.json` (≡ `upscale.json`) | 高清修复（本地 SeedVR2） | 5 | 2 | 0 | 0 | **就绪** |
| `LTXDirectorv2-API.json`（仓库根，未注册） | LTX Director v2 (API) | 33 | 8 | 0 | 0 | **就绪**（需手动上传注册） |
| `Z-Image.json`（仓库根，未注册） | Z-Image | 11 | 3 | 0 | 0 | **就绪**（需手动上传注册） |
| `custom/aitool-smoke-sd15.json`（仓库内，仅 smoke-test） | 本地 ComfyUI 连通测试 SD15 | 7 | 1 | 0 | 0 | **就绪**（未在 GET /api/workflows 公开列表中暴露） |

详细数据落在 `static-analysis/per-workflow-analysis.json`。

### 1.2 服务端 `GET /api/workflows` 返回

```json
{"workflows":[
  {"name":"custom/local-view-2511.json","title":"3D视角变换（本地 2511）","builtin":false,"field_count":3},
  {"name":"custom/黑白线稿.json","title":"custom/黑白线稿","builtin":false,"field_count":2},
  {"name":"custom/local-edit-flux2-klein.json","title":"图片编辑（本地 Flux2-Klein）","builtin":false,"field_count":5},
  {"name":"custom/local-detail-zimage.json","title":"细节增强(本地 Z-Image)","builtin":false,"field_count":3},
  {"name":"custom/local-highres-seedvr2.json","title":"高清修复（本地 SeedVR2）","builtin":false,"field_count":2}
]}
```

- 全部 `builtin:false`（即都是 custom，没有 builtin 槽位暴露给用户）
- `custom/黑白线稿.json` 仓库里没有对应 JSON — 服务端的 custom 目录里多了一个未同步的 `黑白线稿.json`，仓库里只有 config 之外的 6 个 JSON

### 1.3 涉及模型 / 缺失模型（按工作流列）

> 全部 26 个 model reference 的 `expected_dir` 已在 60 盘 3 个 ComfyUI 实例的对应目录下找到匹配项。详情见 `static-analysis/per-workflow-analysis.json`。

| workflow | class_type.field | filename | expected_dir | 60 盘就绪 |
| --- | --- | --- | --- | --- |
| 2511 | LoraLoaderModelOnly.lora_name | Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors | loras | ✓ |
| 2511 | VAELoader.vae_name | qwen_image_vae.safetensors | vae | ✓ |
| 2511 | LoraLoaderModelOnly.lora_name | qwen-image-edit-2511-multiple-angles-lora.safetensors | loras | ✓ |
| 2511 | UNETLoader.unet_name | qwen_image_edit_2511_fp8_e4m3fn.safetensors | diffusion_models | ✓ |
| 2511 | CLIPLoader.clip_name | qwen_2.5_vl_7b_fp8_scaled.safetensors | text_encoders | ✓ |
| Flux2-Klein | VAELoader.vae_name | flux2-vae.safetensors | vae | ✓ |
| Flux2-Klein | LoadTextEncoderShared //Inspire.model_name1 | qwen_3_8b_fp8mixed.safetensors | text_encoders | ✓ |
| Flux2-Klein | LoadDiffusionModelShared //Inspire.model_name | flux-2-klein-9b-fp8/flux-2-klein-9b-fp8.safetensors | diffusion_models | ✓ |
| LTXDirectorv2-API | CheckpointLoaderSimple.ckpt_name | ltx-2.3-22b-dev-fp8.safetensors | checkpoints | ✓ |
| LTXDirectorv2-API | VAELoaderKJ.vae_name | taeltx2_3.safetensors | vae | ✓ |
| LTXDirectorv2-API | LoraLoaderModelOnly.lora_name | ltx-2.3-22b-distilled-1.1_lora-dynamic_fro09_avg_rank_111_bf16.safetensors | loras | ✓ |
| LTXDirectorv2-API | DualCLIPLoader.clip_name1 | gemma_3_12B_it_fp4_mixed.safetensors | text_encoders | ✓ |
| LTXDirectorv2-API | DualCLIPLoader.clip_name2 | ltx-2.3_text_projection_bf16.safetensors | text_encoders | ✓ |
| LTXDirectorv2-API | LTXVAudioVAELoader.ckpt_name | ltx-2.3-22b-distilled-fp8.safetensors | checkpoints | ✓ |
| LTXDirectorv2-API | VAELoaderKJ.vae_name | LTX23_video_vae_bf16.safetensors | vae | ✓ |
| LTXDirectorv2-API | LatentUpscaleModelLoader.model_name | ltx-2.3-spatial-upscaler-x2-1.1.safetensors | latent_upscale_models | ✓ |
| Z-Image-Enhance | VAELoader.vae_name | ae.safetensors | vae | ✓ |
| Z-Image-Enhance | LoadDiffusionModelShared //Inspire.model_name | z_image_turbo_bf16.safetensors | diffusion_models | ✓ |
| Z-Image-Enhance | LoadTextEncoderShared //Inspire.model_name1 | qwen_3_4b.safetensors | text_encoders | ✓ |
| Z-Image-Enhance | ModelPatchLoader.name | Z-Image-Turbo-Fun-Controlnet-Union.safetensors | model_patches | ✓ |
| Z-Image | VAELoader.vae_name | ae.safetensors | vae | ✓ |
| Z-Image | LoadDiffusionModelShared //Inspire.model_name | z_image_turbo_bf16.safetensors | diffusion_models | ✓ |
| Z-Image | LoadTextEncoderShared //Inspire.model_name1 | qwen_3_4b.safetensors | text_encoders | ✓ |
| upscale | SeedVR2LoadDiTModel.model | seedvr2_ema_3b_fp16.safetensors | seedvr2 | ✓ |
| upscale | SeedVR2LoadVAEModel.model | ema_vae_fp16.safetensors | seedvr2 | ✓ |
| custom/aitool-smoke-sd15 | CheckpointLoaderSimple.ckpt_name | v1-5-pruned-emaonly-fp16.safetensors | checkpoints | ✓ |

> **重要修正**：ComfyUI 现代 loader（≥ 2024）实际查找目录如下（旧版新手常误读）：
> - `UNETLoader` → `models/diffusion_models/`（**不是** `models/unet/`）
> - `CLIPLoader` / `DualCLIPLoader` → `models/text_encoders/`（**不是** `models/clip/`）
> - `VAELoaderKJ`、`BasicScheduler`、`LTXVAudioVAELoader`、`LatentUpscaleModelLoader` 等均为 ComfyUI-LTXV / ComfyUI-KJ / latent-list 扩展提供。
>
> 60 盘上 `models/unet/` 与 `models/clip/` 目录为空（未挂载别名），但 `models/diffusion_models/` 和 `models/text_encoders/` 完备。**因此本次 0 MISSING / 0 WRONG_DIR**。

---

## 2. 常见模型需求 Top 10（在 60 盘是否就绪）

| # | 引用次数 | filename | 60 盘位置 | 就绪 |
| --- | --- | --- | --- | --- |
| 1 | 2 | ae.safetensors | models/vae | ✓ |
| 2 | 2 | z_image_turbo_bf16.safetensors | models/diffusion_models | ✓ |
| 3 | 2 | qwen_3_4b.safetensors | models/text_encoders | ✓ |
| 4 | 1 | Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors | models/loras | ✓ |
| 5 | 1 | qwen_image_vae.safetensors | models/vae | ✓ |
| 6 | 1 | qwen-image-edit-2511-multiple-angles-lora.safetensors | models/loras | ✓ |
| 7 | 1 | qwen_image_edit_2511_fp8_e4m3fn.safetensors | models/diffusion_models | ✓ |
| 8 | 1 | qwen_2.5_vl_7b_fp8_scaled.safetensors | models/text_encoders | ✓ |
| 9 | 1 | flux2-vae.safetensors | models/vae | ✓ |
| 10 | 1 | qwen_3_8b_fp8mixed.safetensors | models/text_encoders | ✓ |

**Top 10 全部就绪。** 完整 23 个模型在 `static-analysis/per-workflow-analysis.json` 与 API 响应 `api-responses/install-task-*.json`（live 端点不可用导致空响应，见第 4 节）。

---

## 3. 问题工作流（阻断性缺失）

**无**。所有已注册工作流在 60 盘 3 个 ComfyUI 实例下均模型齐备、自定义节点齐全。

> 仅一处**轻量提示**（不阻断）：
> - `custom/黑白线稿.json` 在仓库 `workflows/custom/` 下没有对应 JSON，源仅来自服务端 `custom/` 目录的 live 注册。如需审计 / 重生成，需要在 60 主机上查看 `/opt/aitoolstudio-canvas/workflows/custom/黑白线稿.json` 是否存在。

### 自定义节点 / class_type 兼容性

- 3 个 ComfyUI 实例的 `object_info` 总节点数：195=2347 / 197=2129 / 249=2083
- 仓库工作流用到的 28 个 class_type（含 custom 包名 `//Inspire` / `|pysssss` / `(rgthree)`）：
  - 全部 present
- 唯一 `MISSING` 的 `ModelPatchTorchCompileSettings` 未被任何仓库工作流引用

---

## 4. workflow-install API 行为记录

### 4.1 本地 main.py 里的端点（已实现）

| Method | Path | 代码位置 | 行为 |
| --- | --- | --- | --- |
| POST | `/api/workflow-install/tasks` | main.py:10373 | 入参 `WorkflowInstallTaskRequest{actions:List[dict]}`，admin 鉴权；调 `start_workflow_install_task(actions)` 启动下载/克隆 task |
| POST | `/api/workflow-install/model-candidates` | main.py:10379 | 入参 `WorkflowModelCandidatesRequest{action,model_name,value,category}`；依次 ModelScope → Hugging Face → AI 三家找候选，最多 8 条；URL 必须 http(s) + 命中 `MODEL_DEPENDENCY_FILE_EXTS` |
| POST | `/api/workflow-install/auto-model-downloads` | main.py:10385 | 入参 `WorkflowAutoModelDownloadsRequest{actions:List[dict]}`；仅对 model download 类型 action + 高置信度同基名候选启动 task，**忽略 custom node clone** |
| GET | `/api/workflow-install/tasks/{task_id}` | main.py:10390 | 拉取 task 快照（含 per-action `downloaded_bytes` / `total_bytes` / `percent` / `speed_bytes_per_sec` / `phase` / `target_relative_path`） |
| POST | `/api/workflows/import/plan` | main.py:10438 | workflow_json 预检：识别 class_type、模型依赖、模型在 resource_root 是否就绪；`save_workflow=true` 时直接落盘 |

### 4.2 live server (192.168.1.60:3000) 实测

| Method | Path | live 实测返回 | 结论 |
| --- | --- | --- | --- |
| GET `/openapi.json` | — | 65 paths，**未包含** `workflow-install/*` 任何端点 | live 端不包含 |
| POST `/api/workflow-install/tasks` | 404 `{"detail":"Not Found"}` | 路由不存在 |
| POST `/api/workflow-install/model-candidates` | 404 `{"detail":"Not Found"}` | 路由不存在 |
| POST `/api/workflow-install/auto-model-downloads` | 404 `{"detail":"Not Found"}` | 路由不存在 |
| GET `/api/workflow-install/tasks/{id}` | 404 | 路由不存在 |
| POST `/api/workflows/import/plan` | 405 Method Not Allowed, `allow: GET` | 路由**已被** `GET /api/workflows/{name:path}` 吞掉；当前后端实现不支持 import/plan |
| GET `/api/workflows` | 200，5 条 custom 列表 | 正常 |
| GET `/api/workflows/{name}` | 200，完整 workflow 节点 | 正常 |
| GET `/api/comfyui/instances` | 200，`["192.168.1.195:8188","192.168.1.197:8188","192.168.1.249:8188"]` | 正常 |
| GET `/api/comfyui/object_info` | 200，转发至 195 | 正常 |

### 4.3 结论与建议

- **Track C 的核心 import/预检/download API 全部未部署到 60 盘 live 容器**。本地 `main.py` 有完整实现，差异在 60 主机当前是旧 build（无 `WorkflowInstallTaskRequest` 等 Pydantic 类）。  
- 验收前需要先升级 60 主机部署（重建 `aitoolstudio-canvas` 容器 → 拷贝新版 `main.py` → 重启），否则用户侧触发「导入工作流」「一键下载缺失模型」会全部 404。  
- 我**没有**在 60 主机上跑任何 model-candidates / auto-model-downloads / install task（live 端点不存在 + 任务约束也禁止触发实际下载）。  
- 已知服务端 `ADMIN_API_PREFIXES = ("/api/providers", "/api/workflow-install")` 已配置（main.py:419），升级后鉴权 + 路径应一次到位。  
- 模型候选逻辑本身（`workflow_install_find_model_candidates_for_action`）已确认支持 ModelScope → HF → AI fallback，且 URL 白名单 `MODEL_DEPENDENCY_FILE_EXTS` 与 `validate_model_candidate_download_url` 已就绪。

---

## 5. 附：检测脚本与缓存

- `static-analysis/per-workflow-analysis.json` — 7 个工作流 × 26 个 model reference × status（OK / WRONG_DIR / MISSING）逐条结果
- `api-responses/workflows-list.json` — 服务端列表
- `api-responses/detail-*.json` — 5 个工作流的服务端详情
- `api-responses/install-task-*.json` — 5 次 workflow-install/tasks 调用（全部 404，已落盘便于回溯）
- 检测脚本可由 main.py:7496 / 8709 / 9549 / 9608 附近的 `workflow_install_*` 系列函数直接复用
