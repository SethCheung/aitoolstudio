<script setup lang="ts">
import { ref } from 'vue'

const prompt = ref('')
const isGenerating = ref(false)
const generatedImages = ref<string[]>([])

async function generate() {
  if (!prompt.value.trim()) return
  isGenerating.value = true
  // TODO: 调用 ComfyUI API
  setTimeout(() => {
    generatedImages.value = []
    isGenerating.value = false
  }, 2000)
}
</script>

<template>
  <div class="generate-page">
    <!-- 顶部导航 -->
    <header class="top-nav">
      <div class="nav-left">
        <span class="logo-text">AI Studio</span>
        <span class="nav-sep">/</span>
        <span class="nav-current">生图</span>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 左侧：提示词输入 -->
      <div class="prompt-panel">
        <h2 class="panel-title">提示词</h2>
        <textarea
          v-model="prompt"
          class="prompt-input"
          placeholder="描述你想要生成的图像..."
          rows="8"
        ></textarea>
        <button class="generate-btn" @click="generate" :disabled="isGenerating || !prompt.trim()">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          {{ isGenerating ? '生成中...' : '生成图像' }}
        </button>
      </div>

      <!-- 右侧：生成结果 -->
      <div class="result-panel">
        <h2 class="panel-title">生成结果</h2>
        <div class="result-area">
          <div v-if="isGenerating" class="generating-placeholder">
            <div class="spinner"></div>
            <span>AI 正在生成...</span>
          </div>
          <div v-else-if="generatedImages.length === 0" class="empty-placeholder">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <path d="M21 15l-5-5L5 21"/>
            </svg>
            <span>生成的图像将显示在这里</span>
          </div>
          <div v-else class="images-grid">
            <img v-for="(img, i) in generatedImages" :key="i" :src="img" class="result-img" />
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* ── 页面 ─────────────────────────────────────── */
.generate-page {
  min-height: 100vh;
  background: #00070d;
}

/* ── 顶部导航 ────────────────────────────────── */
.top-nav {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid #21262d;
  background: #00070d;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-text {
  font-size: 13px;
  font-weight: 600;
  color: #8b949e;
}

.nav-sep {
  color: #484f58;
}

.nav-current {
  font-size: 13px;
  font-weight: 500;
  color: #e6edf3;
}

/* ── 主内容 ─────────────────────────────────── */
.main-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  height: calc(100vh - 52px);
  background: #21262d; /* 边框色作为分隔 */
}

.main-content > * {
  background: #00070d;
}

/* ── 面板 ───────────────────────────────────── */
.prompt-panel,
.result-panel {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

/* ── 提示词输入 ─────────────────────────────── */
.prompt-input {
  flex: 1;
  width: 100%;
  padding: 12px;
  font-size: 13px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 8px;
  color: #ffffff;
  resize: none;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.prompt-input::placeholder { color: #484f58; }
.prompt-input:focus {
  border-color: #00d4f2;
  box-shadow: 0 0 0 3px rgba(0, 212, 242, 0.12);
}

/* ── 生成按钮 ───────────────────────────────── */
.generate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'Inter', -apple-system, sans-serif;
  background: #00d4f2;
  color: #000000;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}
.generate-btn:hover:not(:disabled) {
  background: #00e6ff;
  box-shadow: 0 0 20px rgba(0, 212, 242, 0.3);
}
.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  width: 16px;
  height: 16px;
}

/* ── 结果区 ─────────────────────────────────── */
.result-area {
  flex: 1;
  border: 1px dashed #21262d;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.empty-placeholder,
.generating-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #484f58;
  font-size: 13px;
}

.empty-icon {
  width: 48px;
  height: 48px;
  opacity: 0.4;
}

/* ── Loading 动画 ───────────────────────────── */
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #21262d;
  border-top-color: #00d4f2;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 12px;
  width: 100%;
}

.result-img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #21262d;
}
</style>
