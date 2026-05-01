<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const prompt = ref('')
const isGenerating = ref(false)
const generatedImages = ref<string[]>([])

async function generate() {
  if (!prompt.value.trim()) return
  isGenerating.value = true
  // TODO: call ComfyUI API
  setTimeout(() => {
    generatedImages.value = []
    isGenerating.value = false
  }, 2000)
}

function goBack() {
  router.push('/')
}
</script>

<template>
  <div class="generate-page">
    <!-- AI Gallery Background -->
    <div class="bg-gallery">
      <div class="gallery-grid">
        <div v-for="i in 16" :key="i" class="gallery-item">
          <div class="gallery-img"></div>
        </div>
      </div>
      <div class="bg-overlay"></div>
    </div>

    <!-- Top Nav -->
    <header class="top-nav">
      <div class="nav-left">
        <button class="back-btn" @click="goBack">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <svg class="nav-logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          <path d="M5 3L5.75 6L8 6.75L5.75 7.5L5 10.5L4.25 7.5L2 6.75L4.25 6L5 3Z" opacity="0.6"/>
          <path d="M19 3L19.75 6L22 6.75L19.75 7.5L19 10.5L18.25 7.5L16 6.75L18.25 6L19 3Z" opacity="0.6"/>
          <path d="M5 14L5.75 17L8 17.75L5.75 18.5L5 21.5L4.25 18.5L2 17.75L4.25 17L5 14Z" opacity="0.6"/>
          <path d="M19 14L19.75 17L22 17.75L19.75 18.5L19 21.5L18.25 18.5L16 17.75L18.25 17L19 14Z" opacity="0.6"/>
        </svg>
        <span class="nav-brand">AI Image Generator</span>
        <span class="nav-sep">/</span>
        <span class="nav-current">Create</span>
      </div>
      <nav class="nav-links">
        <a href="#features" class="nav-link">Features</a>
        <a href="#pricing" class="nav-link">Pricing</a>
        <a href="#gallery" class="nav-link">Gallery</a>
      </nav>
    </header>

    <!-- Main Content -->
    <main class="main-content">
      <!-- Left: Prompt Panel -->
      <div class="prompt-panel">
        <div class="panel-header">
          <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
          <h2 class="panel-title">Describe Your Vision</h2>
        </div>
        <p class="panel-desc">Be specific about style, mood, lighting, and details for best results</p>
        
        <textarea
          v-model="prompt"
          class="prompt-input"
          placeholder="A cyberpunk city at night with neon lights reflecting on wet streets, cinematic lighting, highly detailed..."
          rows="10"
        ></textarea>

        <div class="prompt-tips">
          <span class="tip-label">Quick prompts</span>
          <div class="tip-chips">
            <button class="chip" @click="prompt = 'Cyberpunk portrait, neon lighting, ultra detailed'">Cyberpunk</button>
            <button class="chip" @click="prompt = 'Studio product photography, soft lighting, 4K'">Product</button>
            <button class="chip" @click="prompt = 'Abstract art, vibrant colors, geometric patterns'">Abstract</button>
            <button class="chip" @click="prompt = 'Fantasy landscape, golden hour, volumetric lighting'">Fantasy</button>
          </div>
        </div>

        <button class="generate-btn" @click="generate" :disabled="isGenerating || !prompt.trim()">
          <svg v-if="!isGenerating" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
          <div v-else class="spinner"></div>
          {{ isGenerating ? 'Generating...' : 'Generate Image' }}
          <svg v-if="!isGenerating" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </button>
      </div>

      <!-- Right: Result Panel -->
      <div class="result-panel">
        <div class="panel-header">
          <svg class="panel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <path d="M21 15l-5-5L5 21"/>
          </svg>
          <h2 class="panel-title">Generated Result</h2>
        </div>

        <div class="result-area">
          <!-- Generating State -->
          <div v-if="isGenerating" class="generating-state">
            <div class="gen-animation">
              <div class="gen-orb"></div>
              <div class="gen-orb ring-2"></div>
              <div class="gen-orb ring-3"></div>
            </div>
            <p class="gen-text">AI is crafting your image<span class="dots"><span>.</span><span>.</span><span>.</span></span></p>
            <p class="gen-sub">This usually takes 5-15 seconds</p>
          </div>

          <!-- Empty State -->
          <div v-else-if="generatedImages.length === 0" class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="56" height="56">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <path d="M21 15l-5-5L5 21"/>
            </svg>
            <p class="empty-title">Your creations will appear here</p>
            <p class="empty-sub">Describe your vision and click Generate</p>
          </div>

          <!-- Generated Images -->
          <div v-else class="images-grid">
            <img v-for="(img, i) in generatedImages" :key="i" :src="img" class="result-img" />
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.generate-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0a0a0f;
  position: relative;
  overflow: hidden;
}

/* ── Background ────────────────────────────── */
.bg-gallery {
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0.2;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: repeat(4, 1fr);
  gap: 4px;
  padding: 4px;
  height: 100%;
}

.gallery-item { overflow: hidden; border-radius: 4px; }

.gallery-img {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 25%, #0f3460 50%, #1a1a2e 75%, #16213e 100%);
  background-size: 400% 400%;
  animation: galleryShift 20s ease infinite;
}

.gallery-item:nth-child(1) .gallery-img { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.gallery-item:nth-child(2) .gallery-img { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.gallery-item:nth-child(3) .gallery-img { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
.gallery-item:nth-child(4) .gallery-img { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); }
.gallery-item:nth-child(5) .gallery-img { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
.gallery-item:nth-child(6) .gallery-img { background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); }
.gallery-item:nth-child(7) .gallery-img { background: linear-gradient(135deg, #d299c2 0%, #fef9d7 100%); }
.gallery-item:nth-child(8) .gallery-img { background: linear-gradient(135deg, #89f7fe 0%, #66a6ff 100%); }
.gallery-item:nth-child(9) .gallery-img { background: linear-gradient(135deg, #fddb92 0%, #d1fdff 100%); }
.gallery-item:nth-child(10) .gallery-img { background: linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%); }
.gallery-item:nth-child(11) .gallery-img { background: linear-gradient(135deg, #f68084 0%, #a60b68 100%); }
.gallery-item:nth-child(12) .gallery-img { background: linear-gradient(135deg, #96e6a1 0%, #d4fc79 100%); }
.gallery-item:nth-child(13) .gallery-img { background: linear-gradient(135deg, #ee9ca7 0%, #ffdde1 100%); }
.gallery-item:nth-child(14) .gallery-img { background: linear-gradient(135deg, #bdc3c7 0%, #2c3e50 100%); }
.gallery-item:nth-child(15) .gallery-img { background: linear-gradient(135deg, #0ba360 0%, #3cba92 100%); }
.gallery-item:nth-child(16) .gallery-img { background: linear-gradient(135deg, #00d2ff 0%, #3a7bd5 100%); }

@keyframes galleryShift {
  0%, 100% { filter: hue-rotate(0deg) brightness(0.7); }
  50% { filter: hue-rotate(30deg) brightness(0.9); }
}

.bg-overlay {
  position: absolute;
  inset: 0;
  background: rgba(10, 10, 15, 0.85);
  backdrop-filter: blur(1px);
}

/* ── Top Nav ───────────────────────────────── */
.top-nav {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
}

.nav-logo-icon {
  width: 24px;
  height: 24px;
  color: #00d9ff;
  filter: drop-shadow(0 0 6px rgba(0, 217, 255, 0.5));
}

.nav-brand {
  font-size: 14px;
  font-weight: 600;
  color: #ffffff;
}

.nav-sep { color: rgba(255, 255, 255, 0.2); }

.nav-current {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.5);
}

.nav-links {
  display: flex;
  gap: 24px;
}

.nav-link {
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.5);
  text-decoration: none;
  transition: color 0.2s;
}

.nav-link:hover { color: #ffffff; }

/* ── Main Content ──────────────────────────── */
.main-content {
  position: relative;
  z-index: 10;
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 0;
}

/* ── Panels ───────────────────────────────── */
.prompt-panel,
.result-panel {
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.prompt-panel {
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-icon {
  color: #00d9ff;
  filter: drop-shadow(0 0 6px rgba(0, 217, 255, 0.4));
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #ffffff;
}

.panel-desc {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  margin-top: -8px;
}

/* ── Prompt Input ──────────────────────────── */
.prompt-input {
  flex: 1;
  width: 100%;
  min-height: 200px;
  padding: 14px;
  font-size: 13px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  color: #ffffff;
  resize: none;
  outline: none;
  transition: all 0.2s;
  line-height: 1.6;
}

.prompt-input::placeholder { color: rgba(255, 255, 255, 0.25); }

.prompt-input:focus {
  border-color: rgba(0, 217, 255, 0.5);
  background: rgba(0, 217, 255, 0.03);
  box-shadow: 0 0 0 3px rgba(0, 217, 255, 0.08);
}

/* ── Quick Prompts ─────────────────────────── */
.prompt-tips {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tip-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.tip-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.5);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s;
}

.chip:hover {
  color: #00d9ff;
  border-color: rgba(0, 217, 255, 0.3);
  background: rgba(0, 217, 255, 0.05);
}

/* ── Generate Button ────────────────────────── */
.generate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 13px 20px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: linear-gradient(135deg, #00d9ff 0%, #00b4d8 100%);
  color: #000000;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.generate-btn:hover:not(:disabled) {
  box-shadow: 0 0 24px rgba(0, 217, 255, 0.4);
  transform: translateY(-1px);
}

.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Result Area ────────────────────────────── */
.result-area {
  flex: 1;
  min-height: 300px;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.01);
}

/* ── Empty State ────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
  padding: 40px;
}

.empty-icon {
  color: rgba(255, 255, 255, 0.12);
  margin-bottom: 8px;
}

.empty-title {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.3);
}

.empty-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.2);
}

/* ── Generating State ──────────────────────── */
.generating-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px;
}

.gen-animation {
  position: relative;
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gen-orb {
  position: absolute;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00d9ff, #00b4d8);
  animation: orbPulse 2s ease-in-out infinite;
}

.gen-orb.ring-2 {
  width: 60px;
  height: 60px;
  animation-delay: 0.3s;
  opacity: 0.5;
}

.gen-orb.ring-3 {
  width: 80px;
  height: 80px;
  animation-delay: 0.6s;
  opacity: 0.25;
}

@keyframes orbPulse {
  0%, 100% { transform: scale(0.8); opacity: 0.8; }
  50% { transform: scale(1.2); opacity: 0.4; }
}

.gen-text {
  font-size: 15px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.7);
}

.gen-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.3);
}

.dots span {
  animation: blink 1.4s infinite both;
}
.dots span:nth-child(2) { animation-delay: 0.2s; }
.dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0; }
  40% { opacity: 1; }
}

/* ── Spinner ──────────────────────────────── */
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(0, 0, 0, 0.3);
  border-top-color: #000000;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Images Grid ───────────────────────────── */
.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  padding: 12px;
  width: 100%;
}

.result-img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

/* ── Responsive ────────────────────────────── */
@media (max-width: 900px) {
  .main-content { grid-template-columns: 1fr; }
  .prompt-panel { border-right: none; border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
  .nav-links { display: none; }
}
</style>
