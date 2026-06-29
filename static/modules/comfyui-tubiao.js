/**
 * 图标细化模式
 * 全局依赖: ComfyUIRegistry, comfyNameForRef, CLIENT_ID
 */

/**
 * 图标细化模式设置
 */
function tubiaoSettings(node) {
    return `
        <div class="gen-settings-row">
            <label class="field"><div class="setting-title">目标尺寸</div><input class="setting-input" data-field="tubiaoSize" type="number" min="512" max="4096" step="64" value="${Number(node.tubiaoSize || 1536)}"></label>
        </div>
        <div class="gen-settings-row">
            <label class="field"><div class="setting-title">随机种子</div><input class="setting-input" data-field="tubiaoSeed" type="number" min="0" max="999999999999999" value="${Number(node.tubiaoSeed || 180309040720206)}"></label>
        </div>
        <div class="gen-settings-row">
            <label class="field"><div class="setting-title">模型强度</div><input class="setting-input" data-field="tubiaoStrength" type="number" min="0" max="2" step="0.1" value="${Number(node.tubiaoStrength || 1)}"></label>
        </div>
    `;
}

/**
 * 图标细化模式执行
 */
async function tubiaoExecute(node, refs, prompt, promptId) {
    const inputName = await comfyNameForRef(refs[0]);
    
    // 内嵌图标细化工作流（21个节点）
    const workflow = {
        "76": {
            "inputs": { "image": inputName },
            "class_type": "LoadImage",
            "_meta": { "title": "加载图像" }
        },
        "122": {
            "inputs": { "sampler_name": "euler" },
            "class_type": "KSamplerSelect",
            "_meta": { "title": "K采样器选择" }
        },
        "123": {
            "inputs": {
                "noise": ["125", 0],
                "guider": ["137", 0],
                "sampler": ["122", 0],
                "sigmas": ["146", 0],
                "latent_image": ["148", 0]
            },
            "class_type": "SamplerCustomAdvanced",
            "_meta": { "title": "自定义采样器(高级)" }
        },
        "124": {
            "inputs": {
                "samples": ["123", 0],
                "vae": ["127", 0]
            },
            "class_type": "VAEDecode",
            "_meta": { "title": "VAE解码" }
        },
        "125": {
            "inputs": { "noise_seed": Number(node.tubiaoSeed || 180309040720206) },
            "class_type": "RandomNoise",
            "_meta": { "title": "随机噪波" }
        },
        "126": {
            "inputs": {
                "unet_name": "Flux2-Klein-9B-True-v2-bf16.safetensors",
                "weight_dtype": "default"
            },
            "class_type": "UNETLoader",
            "_meta": { "title": "UNET加载器" }
        },
        "127": {
            "inputs": { "vae_name": "flux2-vae.safetensors" },
            "class_type": "VAELoader",
            "_meta": { "title": "加载VAE" }
        },
        "133": {
            "inputs": {
                "clip_name": "qwen_3_8b_fp8mixed.safetensors",
                "type": "flux2",
                "device": "default"
            },
            "class_type": "CLIPLoader",
            "_meta": { "title": "加载CLIP" }
        },
        "135": {
            "inputs": {
                "text": prompt || "把图像改成xy风格，最佳画质",
                "嵌入提示词": null,
                "clip": ["133", 0]
            },
            "class_type": "CLIPTextEncode",
            "_meta": { "title": "CLIP Text Encode (Positive Prompt)" }
        },
        "136": {
            "inputs": {
                "text": "",
                "嵌入提示词": null,
                "clip": ["133", 0]
            },
            "class_type": "CLIPTextEncode",
            "_meta": { "title": "CLIP Text Encode ( Negative Prompt)" }
        },
        "137": {
            "inputs": {
                "cfg": 1,
                "model": ["126", 0],
                "positive": ["141", 0],
                "negative": ["139", 0]
            },
            "class_type": "CFGGuider",
            "_meta": { "title": "CFG引导" }
        },
        "139": {
            "inputs": {
                "conditioning": ["136", 0],
                "latent": ["140", 0]
            },
            "class_type": "ReferenceLatent",
            "_meta": { "title": "参考Latent" }
        },
        "140": {
            "inputs": {
                "pixels": ["173", 0],
                "vae": ["127", 0]
            },
            "class_type": "VAEEncode",
            "_meta": { "title": "VAE编码" }
        },
        "141": {
            "inputs": {
                "conditioning": ["135", 0],
                "latent": ["140", 0]
            },
            "class_type": "ReferenceLatent",
            "_meta": { "title": "参考Latent" }
        },
        "146": {
            "inputs": {
                "steps": 6,
                "width": ["147", 0],
                "height": ["147", 1]
            },
            "class_type": "Flux2Scheduler",
            "_meta": { "title": "Flux2代 调度器" }
        },
        "147": {
            "inputs": { "image": ["173", 0] },
            "class_type": "easy imageSize",
            "_meta": { "title": "图像尺寸" }
        },
        "148": {
            "inputs": {
                "width": ["147", 0],
                "height": ["147", 1],
                "batch_size": 1
            },
            "class_type": "EmptyFlux2LatentImage",
            "_meta": { "title": "Flux2代 空Latent" }
        },
        "173": {
            "inputs": {
                "aspect_ratio": "original",
                "proportional_width": 1,
                "proportional_height": 1,
                "fit": "letterbox",
                "method": "lanczos",
                "round_to_multiple": "32",
                "scale_to_side": "longest",
                "scale_to_length": Number(node.tubiaoSize || 1536),
                "background_color": "#000000",
                "image": ["76", 0]
            },
            "class_type": "LayerUtility: ImageScaleByAspectRatio V2",
            "_meta": { "title": "调整大小并填充" }
        },
        "183": {
            "inputs": { "value": Number(node.tubiaoSize || 1536) },
            "class_type": "PrimitiveInt",
            "_meta": { "title": "整数" }
        },
        "185": {
            "inputs": {
                "filename_prefix": "comfyui",
                "images": ["124", 0]
            },
            "class_type": "SaveImage",
            "_meta": { "title": "图层工具：保存图像增强版(高级)" }
        },
    };
    
    const result = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            prompt: prompt || "图标细化，最佳画质",
            workflow_data: workflow,
            type: 'tubiao',
            client_id: CLIENT_ID,
            canvas_id: window.canvas?.id || ''
        })
    }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || '图标细化失败'); return r.json(); });
    
    if (result.error) throw new Error(`图标细化失败：${result.error}`);
    if (!result.images?.length) throw new Error('图标细化失败：未返回图片');
    return { images: result.images || [] };
}

// 注册到 ComfyUI 注册表
ComfyUIRegistry.tubiao = {
    label: '图标细化',
    requiresImage: true,
    tooltip: '将图标或标志细化增强，提升整体品质',
    settings: tubiaoSettings,
    execute: tubiaoExecute
};
