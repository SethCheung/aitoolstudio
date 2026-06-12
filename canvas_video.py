"""
Canvas Video Task API — Submit a ComfyUI workflow and run it to completion.

设计目标 (用户要求,2026-06-04):
  1. 前端不需要记 magic node id ("23", "144"...)。按 class_type 自动识别节点角色。
  2. 参数面板友好: prompt / negative_prompt / width / height / length / fps / steps / cfg / seed
     直接对到对应的语义节点,不需要传节点号。
  3. Inspect 端点: 传 workflow 给我,我告诉你"有 1 个 prompt encoder、1 个 video output、缺模型
     loader" — 前端拿这个决定要不要展示什么参数面板。
  4. 错误信息友好: invalid tokenizer / GPU OOM / node missing 全部中文 + 修复建议。
  5. 高级用户仍可用 params 字段做节点级覆盖 (优先级最高)。

端点:
  POST /api/canvas-video-tasks          — 提交任务
  GET  /api/canvas-video-tasks/{id}     — 查询任务
  POST /api/canvas-video-tasks/inspect  — 检查 workflow 结构 (返回给前端画参数面板)
  GET  /api/canvas-video-tasks/templates — 列出内置模板
"""

from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
import urllib.request
import urllib.error
import random
import time
import os
import re
import json
import asyncio
import uuid
import shutil
from threading import Lock
from pydantic import BaseModel, Field


# ============================================================
# 节点角色识别 — class_type → 角色
# ============================================================
NODE_ROLES: Dict[str, str] = {
    # Prompt / text encoding
    "CLIPTextEncode": "prompt_text",
    "CLIPTextEncodeAdvanced": "prompt_text",
    "BNK_CLIPTextEncodeAdvanced": "prompt_text",
    "smZ CLIPTextEncode": "prompt_text",

    # Latent video
    "EmptyLTXVLatentVideo": "latent_video",
    "EmptyHunyuanVideoLatentVideo": "latent_video",
    "EmptyMochiVideoLatentVideo": "latent_video",
    "EmptyWanVideoLatentVideo": "latent_video",
    "EmptyCosmosVideoLatentVideo": "latent_video",
    "EmptyCogVideoXLatentVideo": "latent_video",
    "EmptyLatentVideo": "latent_image",  # 静态图 workflow 兼容

    # Sampler / Scheduler / Guider / Noise
    "KSampler": "sampler",
    "KSamplerAdvanced": "sampler",
    "KSamplerSelect": "sampler_select",
    "SamplerCustom": "sampler",
    "SamplerEulerAncestral": "sampler",
    "SamplerEuler": "sampler",
    "SamplerDPMPP_2M": "sampler",
    "SamplerDPMPP_SDE": "sampler",
    "LTXVScheduler": "scheduler",
    "CFGGuider": "guider",
    "RandomNoise": "noise",
    "DisableNoise": "noise",

    # Video output
    "VHS_VideoCombine": "video_output",
    "VHS_VideoInfo": "video_info",
    "SaveVideo": "video_output",
    "SaveVideoMP4": "video_output",
    "SaveAnimatedWEBP": "video_output",
    "SaveAnimatedPNG": "video_output",
    "CreateVideo": "video_output",
    "FFMPEGVideoCombine": "video_output",

    # Image output (fallback — 静态图 workflow 也能跑)
    "SaveImage": "image_output",
    "PreviewImage": "image_output",
    "SaveImageWithMeta": "image_output",

    # Model loaders
    "CheckpointLoaderSimple": "model_loader",
    "CheckpointLoader": "model_loader",
    "UNETLoader": "model_loader",
    "UNETLoaderGGUF": "model_loader",
    "LTXVGemmaCLIPModelLoader": "text_encoder",
    "LTXAVTextEncoderLoader": "text_encoder",
    "CLIPLoader": "text_encoder",
    "CLIPLoaderGGUF": "text_encoder",
    "DualCLIPLoader": "text_encoder",
    "DualCLIPLoaderGGUF": "text_encoder",
    "TripleCLIPLoader": "text_encoder",
    "QuadrupleCLIPLoader": "text_encoder",
    "VAELoader": "vae_loader",
    "LTXVAudioVAELoader": "vae_loader",
    "LTXVAudioVAEEncode": "vae_audio_encode",
    "LTXVAudioVAEDecode": "vae_audio_decode",
    "LTXVEmptyLatentAudio": "latent_audio",
    "LatentUpscaleModelLoader": "latent_upscale",

    # Conditioning
    "LTXVConditioning": "conditioning",
    "HunyuanVideoCachingWrapper": "conditioning",
    "ModelSamplingSD3": "sampling_config",
    "ModelSamplingFlux": "sampling_config",

    # Lora
    "LoraLoader": "lora",
    "LoraLoaderModelOnly": "lora",
    "LTXVBaseSampler": "sampler",
    "STGGuiderNode": "guider",
    "GuiderParameters": "guider_params",
    "LTXVLatentUpsampler": "latent_upscale",
    "LTXVImgToVideoAdvanced": "i2v_encoder",
    "VAEDecode": "vae_decode",
    "LTXVAudioVAEEncode": "vae_audio_encode",
    "LTXVAudioVAEDecode": "vae_audio_decode",

    # I2V 输入
    "LoadImage": "image_input",
    "VHS_LoadVideo": "video_input",
    "LoadVideo": "video_input",
    "VHS_LoadImages": "image_input_seq",
}


ARTISTIC_WORKFLOWS = {
    "ltx_1080p_v5_seedvr2.json",
    "seedvr2_standalone.json",
    "seedvr2_standalone_v2.json",
}

HIDDEN_WORKFLOW_META: Dict[str, Dict[str, Any]] = {
    "seedvr2_standalone.json": {
        "hidden": True,
        "workflow_type": "v2v_unsupported",
        "style_tag": "v2v_unsupported",
        "warning": "需要视频输入，但当前视频生成节点还没有视频源注入；暂时隐藏。该流程也有明显油画/插画感。",
    },
    "seedvr2_standalone_v2.json": {
        "hidden": True,
        "workflow_type": "v2v_unsupported",
        "style_tag": "v2v_unsupported",
        "warning": "需要视频输入，但当前视频生成节点还没有视频源注入；暂时隐藏。该流程也有明显油画/插画感。",
    },
    "ltx_ltx-t2v-lora.json": {
        "hidden": True,
        "not_recommended": True,
        "style_tag": "deprecated",
        "warning": "已从推荐列表下架：该 LoRA workflow 质量不稳定，容易和用户提示词错位。",
    },
    "视频反推.json": {
        "hidden": True,
        "workflow_type": "analysis",
        "style_tag": "analysis",
        "warning": "这是视频反推/描述分析 workflow，不是视频生成 workflow。",
    },
}


# 角色 → 参数注入映射 (param_name → (input_field, value_type, default_if_missing))
ROLE_PARAM_MAP = {
    "prompt_text": {
        "prompt": "text",
    },
    "latent_video": {
        "width": "width",
        "height": "height",
        "length": "length",  # 大部分 node 用 length, LTX 旧版用 num_frames
        "num_frames": "num_frames",
        "batch_size": "batch_size",
    },
    "latent_image": {
        "width": "width",
        "height": "height",
        "batch_size": "batch_size",
    },
    "scheduler": {
        "steps": "steps",
        "cfg": "cfg",
        "max_shift": "max_shift",
        "base_shift": "base_shift",
        "stretch": "stretch",
        "terminal": "terminal",
    },
    "guider": {
        "cfg": "cfg",
    },
    "sampler": {
        "seed": "seed",
        "noise_seed": "noise_seed",
        "steps": "steps",
        "cfg": "cfg",
    },
    "noise": {
        "seed": "noise_seed",
        "noise_seed": "noise_seed",
    },
    "video_output": {
        "fps": "frame_rate",
        "frame_rate": "frame_rate",
    },
}


# 错误中英文翻译
FRIENDLY_ERRORS: List[tuple] = [
    (re.compile(r"ValueError: invalid tokenizer", re.I),
     "缺少 tokenizer 配置。LTX 2.3 22B 用的 gemma 文本编码器需要 spiece_model 字段, "
     "建议换为 comfy_gemma_3_12B_it.safetensors (内置 tokenizer) 或加 gemma-3-12b-it HF 目录。"),
    (re.compile(r"out of memory|CUDA out of memory", re.I),
     "GPU 显存不足,ComfyUI 端 OOM。换更小的模型 (LTX-Video 2B / Wan2.1 1.3B),或减小 width/height/length/steps,或换 fp8 版本。"),
    (re.compile(r"not in \['?(comfy_gemma|gemma|t5xxl)", re.I),
     "工作流引用的 text encoder / checkpoint 不在当前 ComfyUI 实例的 models 目录里。"
     "请确认 NAS 已经挂好 (smb/cifs 到 195/197/249) 且文件路径正确。"),
    (re.compile(r"Prompt outputs failed validation", re.I),
     "工作流参数校验失败 — 节点连线断或参数类型不对。"
     "用 POST /api/canvas-video-tasks/inspect 检查一下,看是不是缺必填连线。"),
    (re.compile(r"list index out of range", re.I),
     "工作流里有节点引用了不存在的连线 (空 link)。"
     "常见原因: 复制 workflow 时丢了源节点,或连到了 disabled 的节点。"),
    (re.compile(r"required input is missing", re.I),
     "节点必填参数没填。检查: 模型加载器的 ckpt_name / text encoder 名称是不是正确,"
     "以及该 ComfyUI 实例 (195/197/249) 的对应 model 目录里有没有这个文件。"),
    (re.compile(r"No checkpoint matched|Value not in list", re.I),
     "工作流引用的模型 (checkpoint / text encoder / VAE) 在该 ComfyUI 实例上找不到。"
     "确认文件存在 / 文件名拼写正确 / 用了 backend 的真名 (有 .safetensors 后缀)。"),
    (re.compile(r"no GPU|not available|cudaMallocAsync.*0", re.I),
     "ComfyUI 实例没有可用 GPU (可能正在跑其他任务)。可以等几秒重试,或换 backend。"),
    (re.compile(r"connection.*refused|errno 111|Connection refused", re.I),
     "选中的 ComfyUI backend 连不上。检查 195/197/249 是否在线,端口 8188 是否监听。"),
]


def _friendly_translate(err: str) -> str:
    """把 ComfyUI 的技术错误翻成人话。命中规则就翻译,否则原样返回。"""
    if not err:
        return "未知错误 (空消息)"
    for pat, friendly in FRIENDLY_ERRORS:
        if pat.search(err):
            return friendly
    return err


# ============================================================
# 节点角色识别
# ============================================================
def _detect_roles(workflow: Dict[str, Any]) -> Dict[str, List[str]]:
    """返回 {role: [node_id, ...]} 索引。"""
    by_role: Dict[str, List[str]] = {}
    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        role = NODE_ROLES.get(ct, "unknown")
        by_role.setdefault(role, []).append(str(nid))
    return by_role


def _is_video_analysis_workflow(workflow: Dict[str, Any]) -> bool:
    """视频反推这类 workflow 输入视频、输出文本，不应该当作视频生成任务。"""
    roles = _detect_roles(workflow)
    has_video_input = bool(roles.get("video_input"))
    has_llm = any(
        isinstance(node, dict) and str(node.get("class_type", "")).startswith("llama_cpp")
        for node in workflow.values()
    )
    has_text_output = any(
        isinstance(node, dict) and "ShowText" in str(node.get("class_type", ""))
        for node in workflow.values()
    )
    return has_video_input and has_llm and has_text_output and not roles.get("video_output")


def _template_meta_for_workflow(name: str, workflow: Dict[str, Any]) -> Dict[str, Any]:
    """按 workflow 名称/结构返回前端可消费的展示元数据。"""
    meta: Dict[str, Any] = {}
    if name in ARTISTIC_WORKFLOWS:
        meta.update({
            "style_tag": "artistic",
            "warning": "油画/插画感强，不适合 photorealism 场景。",
        })
    if name in HIDDEN_WORKFLOW_META:
        meta.update(HIDDEN_WORKFLOW_META[name])
    elif _is_video_analysis_workflow(workflow):
        meta.update({
            "hidden": True,
            "workflow_type": "analysis",
            "style_tag": "analysis",
            "warning": "这是视频分析 workflow，不是视频生成 workflow。",
        })
    return meta


def _detect_missing(workflow: Dict[str, Any], kind: str = "video") -> List[str]:
    """检查工作流缺哪些关键节点。kind: video | image。"""
    roles = _detect_roles(workflow)
    required: List[str] = []
    if kind == "video":
        if _is_video_analysis_workflow(workflow):
            return required
        # 例外: video-to-video 模式 (有 video_input 角色) — 不需要 model_loader / latent_video / sampler
        is_v2v = bool(roles.get("video_input"))
        if not is_v2v:
            if not roles.get("model_loader"):
                required.append("model_loader (CheckpointLoaderSimple / UNETLoader)")
            if not roles.get("latent_video") and not roles.get("latent_image"):
                # 例外: LTXVBaseSampler 可以从 noise + model 自产 latent, 不需要 EmptyLTXVLatentVideo
                if not roles.get("sampler") or "LTXVBaseSampler" not in [workflow.get(nid,{}).get("class_type","") for nid in roles["sampler"]]:
                    required.append("latent_video (EmptyLTXVLatentVideo / EmptyWanVideoLatentVideo)")
        if not roles.get("video_output"):
            required.append("video_output (VHS_VideoCombine / SaveVideo)")
        if not roles.get("sampler") and not is_v2v:
            required.append("sampler (KSampler / SamplerEulerAncestral / LTXVBaseSampler)")
    else:
        if not roles.get("model_loader"):
            required.append("model_loader (CheckpointLoaderSimple / UNETLoader)")
        if not roles.get("sampler"):
            required.append("sampler (KSampler / SamplerEuler)")
        if not roles.get("image_output"):
            required.append("image_output (SaveImage / PreviewImage)")
    return required


def _detect_warnings(workflow: Dict[str, Any]) -> List[str]:
    """检查工作流兼容性警告 (不影响跑通但可能效果差)。"""
    warnings: List[str] = []
    roles = _detect_roles(workflow)

    # 有多个 prompt encoder 时,默认第一个是 positive 第二个是 negative
    pcount = len(roles.get("prompt_text", []))
    if pcount == 1:
        warnings.append("工作流只有 1 个 prompt encoder,没有 negative prompt — 可能需要补一个。")
    if pcount >= 3:
        warnings.append(f"工作流有 {pcount} 个 prompt encoder,默认会取前两个 (positive+negative),其余会被忽略。")

    # 用 gemma 但没有 gemma_configs (老 ComfyUI)
    if any("LTXAV" in n.get("class_type", "") for n in workflow.values() if isinstance(n, dict)):
        warnings.append("用了 LTXAV text encoder,确保 ComfyUI-LTXVideo 节点已安装到 custom_nodes/。")

    # VHS_VideoCombine 但前面是图片 latent 不是视频 latent
    has_video_source = (
        roles.get("latent_video") or roles.get("video_input") or roles.get("i2v_encoder") or
        roles.get("sampler") or roles.get("latent_audio")
    )
    if roles.get("video_output") and not has_video_source:
        warnings.append("有视频输出节点但没有视频 latent / 视频输入节点,视频可能是空。")

    if _is_video_analysis_workflow(workflow):
        warnings.append("这是视频反推/文本分析 workflow，不适合放在视频生成节点里直接运行。")

    return warnings


def _suggest_params(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """给前端画参数面板的 schema: 每个语义参数的可调范围 / 默认值。"""
    roles = _detect_roles(workflow)
    has_video = bool(roles.get("latent_video")) or bool(roles.get("video_output"))
    has_scheduler = bool(roles.get("scheduler"))
    has_guider = bool(roles.get("guider"))

    p: Dict[str, Any] = {
        "prompt": {
            "type": "textarea", "label": "正向提示词",
            "default": "", "required": True,
            "description": "想生成什么视频",
        },
        "negative_prompt": {
            "type": "textarea", "label": "反向提示词",
            "default": "blurry, low quality, distorted, watermark",
            "required": False, "description": "不想出现什么",
            "show_if": lambda r: len(r.get("prompt_text", [])) >= 2,
        },
    }
    if has_video:
        p["width"] = {"type": "int", "label": "宽度", "default": 480, "min": 64, "max": 1920, "step": 8}
        p["height"] = {"type": "int", "label": "高度", "default": 270, "min": 64, "max": 1920, "step": 8}
        p["length"] = {"type": "int", "label": "帧数", "default": 25, "min": 1, "max": 257, "step": 1,
                       "description": "总帧数,典型 25 (1秒@24fps) / 49 (2秒) / 97 (4秒)"}
        p["fps"] = {"type": "int", "label": "帧率", "default": 24, "min": 1, "max": 60, "step": 1}
    else:
        p["width"] = {"type": "int", "label": "宽度", "default": 512, "min": 64, "max": 2048, "step": 8}
        p["height"] = {"type": "int", "label": "高度", "default": 512, "min": 64, "max": 2048, "step": 8}
    p["steps"] = {"type": "int", "label": "采样步数", "default": 20, "min": 1, "max": 100, "step": 1,
                  "description": "越高质量越好但越慢"}
    p["cfg"] = {"type": "float", "label": "CFG 引导强度", "default": 3.0, "min": 0.0, "max": 20.0, "step": 0.1}
    p["seed"] = {"type": "int", "label": "随机种子 (-1=随机)", "default": -1, "min": -1, "max": 2**31 - 1, "step": 1}
    p["timeout"] = {"type": "int", "label": "超时(秒)", "default": 900, "min": 60, "max": 7200, "step": 60,
                    "advanced": True}

    return p




def _autowire_sampler(workflow):
    """给 sampler / guider / noise 自动补缺连线的输入 (smb 团队配的 workflow 经常漏连).

    LTXVBaseSampler 接受: model, vae, width, height, num_frames, guider, sampler, sigmas, noise
    STGGuiderNode / CFGGuider 接受: model, positive, negative
    """
    # 找 sources
    vae_src = None
    model_src = None
    for nid, n in workflow.items():
        if isinstance(n, dict) and n.get("class_type") == "CheckpointLoaderSimple":
            vae_src = [nid, 2]
            model_src = [nid, 0]
            break
    # model 也可以来自 UNETLoader
    if model_src is None:
        for nid, n in workflow.items():
            if isinstance(n, dict) and n.get("class_type") in ("UNETLoader", "UNETLoaderGGUF"):
                model_src = [nid, 0]
                break
    # model 还可以来自 LoraLoaderModelOnly 链
    if model_src is not None:
        for nid, n in workflow.items():
            if isinstance(n, dict) and n.get("class_type") == "LoraLoaderModelOnly":
                ins = n.get("inputs", {})
                if ins.get("model") == model_src:
                    model_src = [nid, 0]  # 跟 lora 后的
                    break
    # 找 conditioning (positive/negative) — 优先取第一个/第二个 CLIPTextEncode
    pos_src = neg_src = None
    text_nodes = [nid for nid, n in workflow.items() if isinstance(n, dict) and n.get("class_type") == "CLIPTextEncode"]
    if text_nodes:
        pos_src = [text_nodes[0], 0]
        if len(text_nodes) >= 2:
            neg_src = [text_nodes[1], 0]
        else:
            # 1 个 prompt 时, neg 复用 pos (空 negative)
            neg_src = pos_src
    # 找 guider
    guider_src = None
    for nid, n in workflow.items():
        if isinstance(n, dict) and n.get("class_type") in ("STGGuiderNode", "CFGGuider"):
            guider_src = [nid, 0]
            break
    # 找 LTXVApplySTG 输出 (如果存在, STGGuiderNode 要用 STG 后的 model, 这样 skip_block_list 才生效)
    stg_model_src = None
    for nid, n in workflow.items():
        if isinstance(n, dict) and n.get("class_type") == "LTXVApplySTG":
            stg_model_src = [nid, 0]
            break
    # STGGuiderNode 用 STG model; CFGGuider 不用 STG
    # 给 STGGuiderNode / CFGGuider 补
    for nid, n in workflow.items():
        if not isinstance(n, dict) or n.get("class_type") not in ("STGGuiderNode", "CFGGuider"):
            continue
        ins = n.setdefault("inputs", {})
        if not isinstance(ins, dict):
            continue
        # STGGuiderNode: 优先用 stg_model_src (有 skip_block_list), 没有再用 model_src
        src_for_guider = (stg_model_src if n["class_type"] == "STGGuiderNode" else None) or model_src
        if "model" not in ins and src_for_guider:
            ins["model"] = src_for_guider
        if "positive" not in ins and pos_src:
            ins["positive"] = pos_src
        if "negative" not in ins and neg_src:
            ins["negative"] = neg_src
    # 给 LTXVBaseSampler 补
    for nid, n in workflow.items():
        if not isinstance(n, dict) or n.get("class_type") != "LTXVBaseSampler":
            continue
        ins = n.setdefault("inputs", {})
        if not isinstance(ins, dict):
            continue
        if "vae" not in ins and vae_src:
            ins["vae"] = vae_src
        if "guider" not in ins and guider_src:
            ins["guider"] = guider_src
# ============================================================
# 自动参数注入
# ============================================================
def _auto_inject(workflow: Dict[str, Any], payload: "OnlineVideoRequest") -> Dict[str, Any]:
    """按角色注入参数,返回 {'injected': [...], 'skipped': [...]} 调试信息。"""
    roles = _detect_roles(workflow)
    injected: List[str] = []
    skipped: List[str] = []

    # 1. prompt: 第一个 prompt_text 节点的 text
    if payload.prompt:
        nodes = roles.get("prompt_text", [])
        if nodes:
            _set_input(workflow, nodes[0], "text", payload.prompt)
            injected.append(f"prompt_text[{nodes[0]}].text")
        else:
            skipped.append("prompt: 没找到 CLIPTextEncode 节点")

    # 2. negative_prompt: 第二个 prompt_text 节点的 text
    if payload.negative_prompt:
        nodes = roles.get("prompt_text", [])
        if len(nodes) >= 2:
            _set_input(workflow, nodes[1], "text", payload.negative_prompt)
            injected.append(f"negative_prompt -> prompt_text[{nodes[1]}].text")
        else:
            skipped.append("negative_prompt: 只有 1 个 CLIPTextEncode 节点,没有 negative 槽位")

    # 3. width/height/length: latent_video / i2v_encoder / sampler
    # LTX 22B 模型对齐要求 (2026-06-09 实测):
    #   - width  / height 必须能被 32 整除 (不然 ComfyUI 内部截断)
    #   - length (num_frames) 必须满足 (8n+1) — 比如 9/17/25/33/41/49/57/65/73/81/89/97
    #     不满足的话 ComfyUI 静默 round 到最近的 8n+1, 用户填 96 实际只跑 89 帧。
    # 我们在注入前做对齐, 避免静默裁剪。

    def _align_dim(v: int, mod: int = 32) -> int:
        """向下取最近 mod 整数倍 (LTX 必须 32 整除, 不能上取否则超显存)。"""
        return (v // mod) * mod

    def _align_frames(v: int) -> int:
        """向上取最近 (8n+1) — 比如 96→97, 100→105, 200→201。"""
        # 8n+1 范围内最大 257
        n = (v - 1 + 7) // 8  # ceil((v-1)/8)
        aligned = 8 * n + 1
        return min(aligned, 257)

    aligned_log: List[str] = []
    payload_length_aligned = _align_frames(payload.length) if payload.length and payload.length > 0 else None
    if payload_length_aligned is not None and payload_length_aligned != payload.length:
        aligned_log.append(f"length {payload.length} → {payload_length_aligned} (8n+1 对齐, LTX 硬要求)")

    payload_width_aligned = _align_dim(payload.width, 32) if payload.width and payload.width > 0 else None
    if payload_width_aligned is not None and payload_width_aligned != payload.width:
        aligned_log.append(f"width {payload.width} → {payload_width_aligned} (32 整除对齐)")

    payload_height_aligned = _align_dim(payload.height, 32) if payload.height and payload.height > 0 else None
    if payload_height_aligned is not None and payload_height_aligned != payload.height:
        aligned_log.append(f"height {payload.height} → {payload_height_aligned} (32 整除对齐)")

    # 收集所有可能接管 length/width/height 的节点角色
    # 修复前: 只走 latent_video 角色 — 导致 i2v_encoder (LTXVImgToVideoAdvanced) 和 sampler (LTXVBaseSampler) 不被注入
    #          只靠 {{num_frames}} 模板替换 — 但用户在 UI 填 96 走 ComfyUI 后被 round 到 89 (8n+1)
    for nodelist_key, payload_key in [("latent_video", "width"), ("latent_video", "height"),
                                       ("latent_video", "length"), ("latent_image", "width"),
                                       ("latent_image", "height"),
                                       ("i2v_encoder", "width"), ("i2v_encoder", "height"),
                                       ("i2v_encoder", "length"),
                                       ("sampler", "length")]:
        val = getattr(payload, payload_key, None)
        if not val or val <= 0:
            continue
        # 决定实际写入值 (length 用对齐后, width/height 用对齐后)
        if payload_key == "length" and payload_length_aligned is not None:
            actual = payload_length_aligned
        elif payload_key == "width" and payload_width_aligned is not None:
            actual = payload_width_aligned
        elif payload_key == "height" and payload_height_aligned is not None:
            actual = payload_height_aligned
        else:
            actual = val

        for nid in roles.get(nodelist_key, []):
            ins = _get_inputs(workflow, nid)
            if not ins:
                continue
            if payload_key in ins:
                ins[payload_key] = actual
                injected.append(f"{nodelist_key}[{nid}].{payload_key}={actual}")
            elif payload_key == "length" and "num_frames" in ins:
                ins["num_frames"] = actual
                injected.append(f"{nodelist_key}[{nid}].num_frames={actual}")
            elif payload_key == "length" and "frames" in ins:
                ins["frames"] = actual
                injected.append(f"{nodelist_key}[{nid}].frames={actual}")
            else:
                skipped.append(f"{nodelist_key}[{nid}] 缺 {payload_key} 字段")

    # 4. fps: video_output
    if payload.fps and payload.fps > 0:
        for nid in roles.get("video_output", []):
            ins = _get_inputs(workflow, nid)
            if ins and "frame_rate" in ins:
                ins["frame_rate"] = payload.fps
                injected.append(f"video_output[{nid}].frame_rate={payload.fps}")

    # 5. steps: scheduler > sampler (scheduler 优先)
    if payload.steps and payload.steps > 0:
        done = False
        for nid in roles.get("scheduler", []):
            ins = _get_inputs(workflow, nid)
            if ins and "steps" in ins:
                ins["steps"] = payload.steps
                injected.append(f"scheduler[{nid}].steps={payload.steps}")
                done = True
        if not done:
            for nid in roles.get("sampler", []):
                ins = _get_inputs(workflow, nid)
                if ins and "steps" in ins:
                    ins["steps"] = payload.steps
                    injected.append(f"sampler[{nid}].steps={payload.steps}")
                    done = True
        if not done:
            skipped.append("steps: 没找到 scheduler/sampler 节点含 steps 字段")

    # 6. cfg: guider > scheduler > sampler
    if payload.cfg is not None and payload.cfg >= 0:
        done = False
        for nid in roles.get("guider", []):
            ins = _get_inputs(workflow, nid)
            if ins and "cfg" in ins:
                ins["cfg"] = payload.cfg
                injected.append(f"guider[{nid}].cfg={payload.cfg}")
                done = True
        if not done:
            for nid in roles.get("scheduler", []):
                ins = _get_inputs(workflow, nid)
                if ins and "cfg" in ins:
                    ins["cfg"] = payload.cfg
                    injected.append(f"scheduler[{nid}].cfg={payload.cfg}")
                    done = True
        if not done:
            for nid in roles.get("sampler", []):
                ins = _get_inputs(workflow, nid)
                if ins and "cfg" in ins:
                    ins["cfg"] = payload.cfg
                    injected.append(f"sampler[{nid}].cfg={payload.cfg}")
                    done = True
        if not done:
            skipped.append("cfg: 没找到 guider/scheduler/sampler 节点含 cfg 字段")

    # 7. seed: noise > sampler > guider
    if payload.seed and payload.seed > 0:
        seed_val = payload.seed
    else:
        seed_val = random.randint(1, 10 ** 15)
    injected.append(f"resolved seed={seed_val}")
    for nid in roles.get("noise", []):
        ins = _get_inputs(workflow, nid)
        if not ins:
            continue
        for k in ("noise_seed", "seed"):
            if k in ins and isinstance(ins[k], (int, float)):
                ins[k] = seed_val
                injected.append(f"noise[{nid}].{k}={seed_val}")
                break
    for nid in roles.get("sampler", []):
        ins = _get_inputs(workflow, nid)
        if not ins:
            continue
        for k in ("noise_seed", "seed"):
            if k in ins and isinstance(ins[k], (int, float)):
                ins[k] = seed_val
                injected.append(f"sampler[{nid}].{k}={seed_val}")
                break
    for nid in roles.get("guider", []):
        ins = _get_inputs(workflow, nid)
        if not ins:
            continue
        for k in ("noise_seed", "seed"):
            if k in ins and isinstance(ins[k], (int, float)):
                ins[k] = seed_val
                injected.append(f"guider[{nid}].{k}={seed_val}")
                break

    return {"injected": injected, "skipped": skipped, "seed": seed_val, "aligned": aligned_log}


def _set_input(workflow, nid, field, value):
    node = workflow.get(nid) or workflow.get(int(nid))
    if node and isinstance(node, dict):
        node.setdefault("inputs", {})[field] = value


def _get_inputs(workflow, nid):
    node = workflow.get(nid) or workflow.get(int(nid))
    if node and isinstance(node, dict):
        return node.setdefault("inputs", {})
    return None


# ============================================================
# Pydantic models
# ============================================================
class OnlineVideoRequest(BaseModel):
    prompt: str = Field(default="", max_length=8000)
    negative_prompt: str = Field(default="", max_length=4000)
    workflow_data: Optional[Dict[str, Any]] = None
    workflow_json: str = ""
    # 通用语义参数 (按角色自动注入)
    seed: int = -1
    width: int = 480
    height: int = 270
    length: int = 25
    fps: int = 24
    steps: int = 0            # 0 = 用 workflow 自带
    cfg: float = -1.0         # <0 = 用 workflow 自带
    canvas_id: str = ""
    client_id: str = ""
    preferred_backend: str = ""
    timeout: int = 900
    input_image: str = ""  # I2V: 上传到 ComfyUI 后的文件名 (替代 {{image}} 模板)
    # 高级: 节点级参数覆盖 (优先级最高)
    params: Dict[str, Dict[str, Any]] = {}


class WorkflowInspectRequest(BaseModel):
    workflow_data: Optional[Dict[str, Any]] = None
    workflow_json: str = ""


# ============================================================
# 视频输出提取
# ============================================================
def _extract_video_outputs(history_data: Dict[str, Any]) -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []
    if not isinstance(history_data, dict):
        return files
    outputs = history_data.get("outputs") or {}
    for _node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        for key in ("gifs", "videos", "images"):
            items = node_output.get(key) or []
            if isinstance(items, list) and items:
                for it in items:
                    if isinstance(it, dict) and it.get("filename"):
                        files.append({
                            "filename": it["filename"],
                            "subfolder": it.get("subfolder", ""),
                            "type": it.get("type", "output"),
                            "format": it.get("format", ""),
                        })
                if files:
                    return files
    return files


# ============================================================
# 视频下载
# ============================================================
def _download_video_to_local(ctx, comfy_address, comfy_url_path, src_filename, prefix, canvas=None, username=None):
    src_ext = os.path.splitext(src_filename)[1].lower() or ".mp4"
    if not src_ext.startswith("."):
        src_ext = "." + src_ext
    if src_ext not in {".mp4", ".webm", ".mov", ".avi", ".mkv", ".gif", ".png", ".jpg", ".jpeg", ".webp"}:
        src_ext = ".mp4"
    if canvas is not None:
        canvas_output_dir = ctx["get_canvas_output_dir"](canvas)
    elif username:
        canvas_output_dir, _ = ctx["get_user_output_dir"](username)
    else:
        canvas_output_dir = ctx["OUTPUT_DIR"]
    os.makedirs(canvas_output_dir, exist_ok=True)
    base = f"{prefix}{uuid.uuid4().hex[:10]}"
    local_path = os.path.join(canvas_output_dir, base + src_ext)
    full_url = f"http://{comfy_address}{comfy_url_path}"
    try:
        with urllib.request.urlopen(full_url, timeout=120) as resp, open(local_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        return ctx["build_output_url"](canvas, base + src_ext, username)
    except Exception as e:
        print(f"[CanvasVideo] download failed {full_url}: {e}")
        return None


# ============================================================
# 主任务执行
# ============================================================
def run_canvas_video_task(task_id: str, payload: OnlineVideoRequest, ctx: Dict[str, Any]):
    with ctx["CANVAS_TASK_LOCK"]:
        if task_id in ctx["CANVAS_TASKS"]:
            ctx["CANVAS_TASKS"][task_id]["status"] = "running"
            ctx["CANVAS_TASKS"][task_id]["updated_at"] = ctx["time"].time()

    try:
        canvas = None
        if payload.canvas_id:
            try:
                canvas = ctx["load_canvas"](payload.canvas_id)
            except Exception:
                canvas = None
        username = ctx["get_username_by_token"](None)

        # 加载 workflow
        if payload.workflow_data:
            workflow = json.loads(json.dumps(payload.workflow_data))
        elif payload.workflow_json:
            workflow_path = os.path.join(ctx["WORKFLOW_DIR"], payload.workflow_json)
            if not os.path.exists(workflow_path):
                raise Exception(f"Workflow 文件没找到: {payload.workflow_json}\n请检查 /opt/xy-canvas/workflows/ 目录,或用 GET /api/canvas-video-tasks/templates 看内置模板名。")
            with open(workflow_path, "r", encoding="utf-8") as f:
                workflow = json.load(f)
        else:
            raise Exception("缺少工作流数据。请提供 workflow_data (前端编辑的 JSON) 或 workflow_json (服务器上的文件名)。")

        # 移除 wrapper 字段 (我们的 _meta / workflow 嵌套包装, 不属于 ComfyUI workflow)
        for k in ("_meta", "workflow"):
            if k in workflow and not isinstance(workflow.get(k, None), dict) or (k in workflow and "class_type" not in workflow[k]):
                # 顶层 k 是 meta wrapper, 删掉
                if k in workflow and "class_type" not in workflow[k]:
                    workflow.pop(k, None)
            elif k in workflow and isinstance(workflow[k], dict):
                # k 是嵌套的 workflow_json (canvas 格式)
                workflow = workflow[k]
        # 最后兜底: 任何没 class_type 的顶层 key 都不是 ComfyUI 节点
        for k in list(workflow.keys()):
            v = workflow.get(k)
            if isinstance(v, dict) and "class_type" not in v:
                workflow.pop(k, None)

        # 检查关键节点
        if _is_video_analysis_workflow(workflow):
            raise Exception(
                "这个 workflow 是视频反推/文本分析流程，不是视频生成流程。"
                "请不要在视频生成节点里直接运行它。"
            )

        missing = _detect_missing(workflow, kind="video")
        if missing:
            raise Exception(
                "工作流缺关键节点:\n  - " + "\n  - ".join(missing) +
                "\n\n用 POST /api/canvas-video-tasks/inspect 可以看到完整结构分析 + 修复建议。"
            )

        # 给缺 advanced default 的节点填默认值 (smb 团队配的 workflow 经常漏 advanced 字段)
        # 已知必填默认:
        _defaults_map = {
            "VHS_VideoCombine": {
                "loop_count": 0,
                "save_output": True,
                "pingpong": False,
                "crf": 19,
            },
            "SaveVideo": {
                "format": "auto",
                "codec": "auto",
            },
            "LTXVScheduler": {
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1,
            },
            "STGGuiderNode": {
                "stg": 0.0,
                "rescale": 0.5,
            },
            "KSamplerSelect": {
                "sampler_name": "euler",
            },
            "LTXVBaseSampler": {
                "cfg_scale": 3.0,
                "stg_scale": 1.0,
                "rescale_scale": 0.0,
                "denoise": 1.0,
            },
            "CFGGuider": {
                "cfg": 3.0,
            },
            "LTXAVTextEncoderLoader": {
                "device": "default",
            },
            "LTXVGemmaCLIPModelLoader": {
                "device": "default",
            },
        }
        for nid, node in workflow.items():
            if not isinstance(node, dict) or "inputs" not in node:
                continue
            ins = node["inputs"]
            if not isinstance(ins, dict):
                continue
            ct = node.get("class_type", "")
            defaults = _defaults_map.get(ct, {})
            for k, default_val in defaults.items():
                if k not in ins:
                    ins[k] = default_val

        # 字段名兼容映射 (老 workflow 字段名跟新 ComfyUI 节点 schema 不一致)
        # 比如 LTXVBaseSampler 老版本用 "frames", 新版本要 "num_frames"
        _field_aliases = {
            "LTXVBaseSampler": {"frames": "num_frames", "positive": None, "negative": None},
            "LTXVImgToVideoAdvanced": {"num_frames": "frames"},
            "EmptyLTXVLatentVideo": {"num_frames": "length"},
            "STGGuiderNode": {"conditioning": "positive"},
            "LTXVScheduler": {"model": None},
        }
        for nid, node in workflow.items():
            if not isinstance(node, dict) or "inputs" not in node:
                continue
            ins = node["inputs"]
            if not isinstance(ins, dict):
                continue
            ct = node.get("class_type", "")
            aliases = _field_aliases.get(ct, {})
            for old_key, new_key in aliases.items():
                if old_key in ins:
                    if new_key is None:
                        # 显式删除
                        ins.pop(old_key, None)
                    else:
                        if new_key not in ins:
                            ins[new_key] = ins[old_key]
                        if old_key != new_key:
                            ins.pop(old_key, None)
            # 额外: text encoder / audio vae loader 字段名兼容
            if ct in ("LTXAVTextEncoderLoader", "LTXVGemmaCLIPModelLoader", "CLIPLoader", "DualCLIPLoader", "QuadrupleCLIPLoader"):
                if "text_encoder_name" in ins and "text_encoder" not in ins:
                    ins["text_encoder"] = ins["text_encoder_name"]
                if "ckpt_name" not in ins:
                    # 找主模型 loader
                    for nnid, nn in workflow.items():
                        if isinstance(nn, dict) and nn.get("class_type") == "CheckpointLoaderSimple":
                            ck = nn.get("inputs", {}).get("ckpt_name")
                            if ck:
                                ins["ckpt_name"] = ck
                            break
            if ct == "LTXVAudioVAELoader":
                # 字段名 ckpt_name 兼容 (smb workflow 用 vae_name)
                if "vae_name" in ins and "ckpt_name" not in ins:
                    ins["ckpt_name"] = ins["vae_name"]
                if "ckpt_name" not in ins:
                    for nnid, nn in workflow.items():
                        if isinstance(nn, dict) and nn.get("class_type") == "CheckpointLoaderSimple":
                            ck = nn.get("inputs", {}).get("ckpt_name")
                            if ck:
                                ins["ckpt_name"] = ck
                            break

        # 自动补全 LTXVBaseSampler 缺连线的输入 (smb workflow bug 兜底)
        _autowire_sampler(workflow)

        # 模板占位符替换 ({{seed}} {{width}} ...)
        template_subs = {
            "{{seed}}": payload.seed if payload.seed > 0 else random.randint(1, 10 ** 15),
            "{{width}}": payload.width,
            "{{height}}": payload.height,
            "{{length}}": payload.length,
            "{{num_frames}}": payload.length,
            "{{fps}}": payload.fps,
            "{{frame_rate}}": payload.fps,
            "{{steps}}": payload.steps if payload.steps > 0 else None,
            "{{cfg}}": payload.cfg if payload.cfg >= 0 else None,
            "{{prompt}}": payload.prompt,
            "{{negative_prompt}}": payload.negative_prompt,
            "{{image}}": payload.input_image or None,
            "{{input_image}}": payload.input_image or None,
        }
        tpl_count = 0
        for nid, node in workflow.items():
            if not isinstance(node, dict) or "inputs" not in node:
                continue
            ins = node["inputs"]
            if not isinstance(ins, dict):
                continue
            for k, v in list(ins.items()):
                if isinstance(v, str) and v in template_subs and template_subs[v] is not None:
                    ins[k] = template_subs[v]
                    tpl_count += 1

        image_injected: List[str] = []
        image_placeholders = {"{{image}}", "{{input_image}}", "{{source_image}}"}
        if payload.input_image:
            for nid in _detect_roles(workflow).get("image_input", []):
                ins = _get_inputs(workflow, nid)
                if not ins:
                    continue
                for field in ("image", "images"):
                    current = ins.get(field)
                    if field in ins and (not current or current in image_placeholders):
                        ins[field] = payload.input_image
                        image_injected.append(f"image_input[{nid}].{field}={payload.input_image}")
        else:
            pending_images: List[str] = []
            for nid in _detect_roles(workflow).get("image_input", []):
                ins = _get_inputs(workflow, nid)
                if not ins:
                    continue
                for field in ("image", "images"):
                    if ins.get(field) in image_placeholders:
                        pending_images.append(f"{nid}.{field}")
            if pending_images:
                raise Exception("I2V 图生视频 workflow 需要先上传输入图片。缺少: " + ", ".join(pending_images))

        # 自动参数注入
        inject_log = _auto_inject(workflow, payload)
        inject_log["template_replaced"] = tpl_count
        inject_log["injected"].extend(image_injected)
        # 把对齐信息也写到 inject_log — 前端能展示给用户"你填的 96 实际跑 97"
        if inject_log.get("aligned"):
            inject_log.setdefault("warnings", []).extend(inject_log["aligned"])

        # 高级 params 覆盖
        for nid, overrides in (payload.params or {}).items():
            if nid in workflow and isinstance(workflow[nid], dict):
                ins = workflow[nid].setdefault("inputs", {})
                for k, v in overrides.items():
                    ins[k] = v
                inject_log["injected"].append(f"params override: {nid}.{k}")

        # 选 backend
        required_images = []
        for n, w in workflow.items():
            if not isinstance(w, dict):
                continue
            ins = w.get("inputs", {})
            if not isinstance(ins, dict):
                continue
            for k in ("image", "images"):
                v = ins.get(k)
                if isinstance(v, str) and v:
                    required_images.append(v)
        target_backend = payload.preferred_backend or ctx["get_best_backend"](required_images)
        with ctx["LOAD_LOCK"]:
            ctx["BACKEND_LOCAL_LOAD"][target_backend] = ctx["BACKEND_LOCAL_LOAD"].get(target_backend, 0) + 1
        try:
            ctx["ensure_images_on_backend"](target_backend, required_images)
        except Exception:
            pass

        # 提交
        client_id = payload.client_id or ctx["CLIENT_ID"]
        data = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"http://{target_backend}/prompt", data=data, headers={"Content-Type": "application/json"}
            )
            prompt_id = json.loads(urllib.request.urlopen(req, timeout=30).read())["prompt_id"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            friendly = _friendly_translate(body)
            raise Exception(f"ComfyUI 提交失败 HTTP {e.code} (backend={target_backend}):\n{friendly}")
        except Exception as e:
            friendly = _friendly_translate(str(e))
            raise Exception(f"ComfyUI 提交异常: {friendly}")

        # 轮询
        deadline = time.time() + payload.timeout
        history = None
        while time.time() < deadline:
            try:
                res = ctx["get_comfy_history"](target_backend, prompt_id)
                if prompt_id in res:
                    history = res[prompt_id]
                    break
            except Exception:
                pass
            time.sleep(1.0)
        if not history:
            raise Exception(f"ComfyUI 渲染超时 (>{payload.timeout}s, prompt_id={prompt_id})。可能 GPU 太慢 / 队列堵 / workflow 卡住。")

        # 检查执行状态
        status = history.get("status", {})
        if status.get("status_str") == "error":
            err_node = err_msg = err_trace = ""
            for m in status.get("messages", []):
                if isinstance(m, list) and m and m[0] == "execution_error":
                    err_node = m[1].get("node_type", "?")
                    err_msg = m[1].get("exception_message", "")
                    err_trace = m[1].get("traceback", "")
                    break
            friendly = _friendly_translate(err_msg)
            raise Exception(
                f"ComfyUI 执行失败 (节点: {err_node}):\n{friendly}\n\n"
                f"原始错误: {err_msg[:300]}"
            )

        # 抽视频
        video_files = _extract_video_outputs(history)
        if not video_files:
            raise Exception(
                "ComfyUI 跑完了但没产出视频。\n"
                "可能原因: workflow 缺 VHS_VideoCombine / SaveVideo 节点,或连线断了。"
                "用 POST /api/canvas-video-tasks/inspect 检查结构。"
            )

        # 下载
        local_urls: List[str] = []
        ts = int(time.time())
        for vf in video_files:
            qs = urlencode({"filename": vf["filename"], "subfolder": vf["subfolder"], "type": vf["type"]})
            comfy_url_path = f"/view?{qs}"
            try:
                local_path = _download_video_to_local(
                    ctx, target_backend, comfy_url_path,
                    src_filename=vf["filename"],
                    prefix=f"canvas_video_{ts}_", canvas=canvas, username=username,
                )
            except Exception as e:
                print(f"[CanvasVideo] download failed {vf['filename']}: {e}")
                continue
            if local_path:
                local_urls.append(local_path)

        if not local_urls:
            raise Exception("下载视频文件全部失败 (ComfyUI 端 /view 端点 404 或权限问题)。")

        result = {
            "prompt": payload.prompt,
            "negative_prompt": payload.negative_prompt,
            "videos": local_urls,
            "timestamp": time.time(),
            "type": "canvas-video",
            "model": "comfyui",
            "backend": target_backend,
            "prompt_id": prompt_id,
            "params": {
                "width": payload.width,
                "height": payload.height,
                "length": payload.length,
                "fps": payload.fps,
                "steps": payload.steps,
                "cfg": payload.cfg,
                "seed": inject_log.get("seed"),
            },
            "inject_log": inject_log,
        }
        with ctx["CANVAS_TASK_LOCK"]:
            ctx["CANVAS_TASKS"][task_id].update({
                "status": "succeeded",
                "result": result,
                "error": "",
                "updated_at": time.time(),
            })
    except Exception as exc:
        with ctx["CANVAS_TASK_LOCK"]:
            ctx["CANVAS_TASKS"][task_id].update({
                "status": "failed",
                "error": str(exc),
                "updated_at": time.time(),
            })


# ============================================================
# 路由注册
# ============================================================
def register_canvas_video_routes(app, ctx: Dict[str, Any]):
    from fastapi import HTTPException, Request

    def _load_workflow_from_request(payload) -> Dict[str, Any]:
        if payload.workflow_data:
            return json.loads(json.dumps(payload.workflow_data))
        if payload.workflow_json:
            workflow_path = os.path.join(ctx["WORKFLOW_DIR"], payload.workflow_json)
            if not os.path.exists(workflow_path):
                raise HTTPException(status_code=404, detail=f"Workflow 文件没找到: {payload.workflow_json}")
            with open(workflow_path, "r", encoding="utf-8") as f:
                return json.load(f)
        raise HTTPException(status_code=400, detail="缺少 workflow_data 或 workflow_json")

    @app.post("/api/canvas-video-tasks/upload-image")
    async def upload_image_for_video(request: Request, filename: str = "image.png", preferred_backend: str = ""):
        """上传图片到 ComfyUI (I2V workflow 需要).

        Query: filename=...&preferred_backend=192.168.1.195:8188
        Body: 原始图片 bytes (Content-Type: image/png 等)

        返回: {"name": "image.png", "subfolder": "", "type": "input", "backend": "..."}
        """
        image = await request.body()
        if not image:
            raise HTTPException(status_code=400, detail="未提供图片数据")
        target = preferred_backend or ctx.get("COMFYUI_ADDRESS") or "127.0.0.1:8188"
        # 用 multipart 转发到 ComfyUI /upload/image
        try:
            # 构造 multipart body
            import io
            boundary = "----MavisBoundary" + uuid.uuid4().hex
            body = (
                f"--{boundary}\r\n"
                f"Content-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
                f"Content-Type: application/octet-stream\r\n"
                f"\r\n"
            ).encode("utf-8") + image + (f"\r\n--{boundary}--\r\n").encode("utf-8")
            req = urllib.request.Request(
                f"http://{target}/upload/image",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                result["backend"] = target
                return result
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"上传到 ComfyUI 失败: {e}")

    @app.post("/api/canvas-video-tasks/inspect")
    async def inspect_workflow(payload: WorkflowInspectRequest):
        """
        检查工作流结构,返回给前端用于画参数面板。

        返回:
          - roles: {node_id: class_type}
          - nodes_by_role: {role: [node_id, ...]}
          - missing: [缺的节点类型]
          - warnings: [兼容性警告]
          - param_schema: {param_name: {type, label, default, min, max, ...}}
          - node_count: int
        """
        workflow = _load_workflow_from_request(payload)
        roles_raw = {}
        for nid, node in workflow.items():
            if isinstance(node, dict):
                roles_raw[str(nid)] = node.get("class_type", "unknown")
        nodes_by_role = _detect_roles(workflow)
        missing = _detect_missing(workflow, kind="video")
        warnings = _detect_warnings(workflow)
        if payload.workflow_json:
            meta = _template_meta_for_workflow(os.path.basename(payload.workflow_json), workflow)
            if meta.get("warning"):
                warnings.append(meta["warning"])
        param_schema = _suggest_params(workflow)
        return {
            "node_count": sum(1 for n in workflow.values() if isinstance(n, dict)),
            "roles": roles_raw,
            "nodes_by_role": nodes_by_role,
            "missing": missing,
            "warnings": warnings,
            "param_schema": param_schema,
        }

    @app.get("/api/canvas-video-tasks/templates")
    async def list_templates():
        """列出服务器上可用的 workflow 模板 (.json)。"""
        wf_dir = ctx["WORKFLOW_DIR"]
        out: List[Dict[str, Any]] = []
        if os.path.isdir(wf_dir):
            for fn in sorted(os.listdir(wf_dir)):
                if not fn.endswith(".json"):
                    continue
                p = os.path.join(wf_dir, fn)
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        wf = json.load(f)
                except Exception:
                    continue
                roles = _detect_roles(wf)
                # 判断是图还是视频
                kind = "video" if roles.get("video_output") or roles.get("latent_video") or roles.get("video_input") else "image"
                # 看用了什么模型
                model = ""
                for nid in roles.get("model_loader", []):
                    ck = _get_inputs(wf, nid)
                    if ck and "ckpt_name" in ck:
                        model = ck["ckpt_name"]
                        break
                    if ck and "unet_name" in ck:
                        model = ck["unet_name"]
                        break
                te = ""
                for nid in roles.get("text_encoder", []):
                    te_in = _get_inputs(wf, nid)
                    if te_in:
                        te = te_in.get("text_encoder", "") or te_in.get("clip_name1", "") or te_in.get("clip_name", "")
                        if te:
                            break
                out.append({
                    "name": fn,
                    "kind": kind,
                    "model": model,
                    "text_encoder": te,
                    "node_count": sum(1 for n in wf.values() if isinstance(n, dict)),
                    **_template_meta_for_workflow(fn, wf),
                })
        return {"workflows": out, "workflow_dir": wf_dir}

    @app.post("/api/canvas-video-tasks")
    async def create_canvas_video_task(payload: OnlineVideoRequest):
        task_id = f"canvas_vid_{uuid.uuid4().hex}"
        with ctx["CANVAS_TASK_LOCK"]:
            ctx["CANVAS_TASKS"][task_id] = {
                "id": task_id,
                "type": "canvas-video",
                "status": "queued",
                "created_at": time.time(),
                "updated_at": time.time(),
                "result": None,
                "error": "",
            }
        asyncio.get_event_loop().run_in_executor(
            None, run_canvas_video_task, task_id, payload, ctx
        )
        return {"task_id": task_id, "status": "queued"}

    @app.get("/api/canvas-video-tasks/{task_id}")
    async def get_canvas_video_task(task_id: str):
        with ctx["CANVAS_TASK_LOCK"]:
            task = dict(ctx["CANVAS_TASKS"].get(task_id) or {})
        if not task:
            raise HTTPException(status_code=404, detail="画布视频任务不存在,可能服务已重启或任务已过期")
        return task
