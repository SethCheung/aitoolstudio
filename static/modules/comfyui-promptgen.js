/**
 * 图像反推模式
 * 全局依赖: ComfyUIRegistry, comfyNameForRef, CLIENT_ID
 */

/**
 * Promptgen 模式设置
 */
function promptgenSettings(node) {
    return `
        <div class="gen-settings-row">
            <label class="field"><div class="setting-title">预设提示词风格</div>
                <select class="setting-input" data-field="pgPreset">
                    <option value="提示词风格 - 详细"${normalizePromptgenPreset(node.pgPreset) === '提示词风格 - 详细' ? ' selected' : ''}>详细</option>
                    <option value="提示词风格 - 简单"${normalizePromptgenPreset(node.pgPreset) === '提示词风格 - 简单' ? ' selected' : ''}>简单</option>
                    <option value="提示词风格 - 电影质感"${normalizePromptgenPreset(node.pgPreset) === '提示词风格 - 电影质感' ? ' selected' : ''}>电影质感</option>
                    <option value="提示词风格 - 标签"${normalizePromptgenPreset(node.pgPreset) === '提示词风格 - 标签' ? ' selected' : ''}>标签</option>
                    <option value="提示词风格 - JSON"${normalizePromptgenPreset(node.pgPreset) === '提示词风格 - JSON' ? ' selected' : ''}>JSON</option>
                </select>
            </label>
        </div>
        <div class="gen-settings-row">
            <label class="field"><div class="setting-title">提示词</div><input class="setting-input" data-field="pgPrompt" type="text" value="${node.pgPrompt || '使用中文描述这张图片'}" placeholder="自定义提示词"></label>
        </div>
        <div class="gen-settings-row">
            <label class="field"><div class="setting-title">随机种子</div><input class="setting-input" data-field="pgSeed" type="number" min="0" max="999999999999999" value="${Number(node.pgSeed || 498061195854013)}"></label>
        </div>
    `;
}

function normalizePromptgenPreset(value) {
    const mapping = {
        'Prompt Style - Extreme Detailed': '提示词风格 - 详细',
        'Prompt Style - Simple': '提示词风格 - 简单',
        'Prompt Style - Artistic': '提示词风格 - 电影质感',
        'Prompt Style - Technical': '提示词风格 - 标签'
    };
    return mapping[value] || value || '提示词风格 - 详细';
}

/**
 * Promptgen 模式执行
 */
async function promptgenExecute(node, refs, prompt, promptId) {
    const inputName = await comfyNameForRef(refs[0]);
    const promptText = node.pgPrompt || prompt || "使用中文描述这张图片";
    const seed = Number(node.pgSeed || 498061195854013) % 4294967295;
    const preset = normalizePromptgenPreset(node.pgPreset);

    // 内嵌图像反推工作流（Dapao_LlamaCaption 本地路线）
    const workflow = {
        "6": {
            "inputs": { "image": inputName },
            "class_type": "LoadImage",
            "_meta": { "title": "加载图像" }
        },
        "8": {
            "inputs": {
                "🤖模型文件": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
                "🔌对话处理器": "Qwen2.5-VL",
                "🖼️mmproj文件": "mmproj-BF16.gguf",
                "📐上下文长度": 8192,
                "💾显存限制(GB)": -1,
                "🔢图像最小token": 256,
                "🔢图像最大token": 1344,
                "🎨提示词风格": preset,
                "💬附加指令": promptText,
                "📏图像最大边长": 768,
                "🎲随机种子": seed,
                "🎰随机化": "固定种子",
                "📊最大输出token": 1024,
                "🌡️温度": 0.3,
                "🎯top_p": 0.9,
                "🔝top_k": 40,
                "🔁重复惩罚": 1.1,
                "🧠思考模式": false,
                "⚡推理后卸载模型": false,
                "🖼️图像1": ["6", 0]
            },
            "class_type": "Dapao_LlamaCaption",
            "_meta": { "title": "大炮图像反推" }
        },
        "15": {
            "inputs": {
                "text_undefined": "",
                "text": ["8", 0]
            },
            "class_type": "ShowText|pysssss",
            "_meta": { "title": "展示文本🐍" }
        }
    };

    const result = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            prompt: promptText,
            workflow_data: workflow,
            type: 'promptgen',
            client_id: CLIENT_ID,
            canvas_id: window.canvas?.id || ''
        })
    }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || '图像反推失败'); return r.json(); });
    
    if (result.error) throw new Error(`图像反推失败：${result.error}`);
    if (!result.text) throw new Error('图像反推失败：未返回文本');
    return { images: result.images || [], text: result.text };
}

// 注册到 ComfyUI 注册表
ComfyUIRegistry.promptgen = {
    label: '图像反推',
    requiresImage: true,
    returnsText: true,
    tooltip: '根据图像自动生成描述性提示词',
    settings: promptgenSettings,
    execute: promptgenExecute
};
