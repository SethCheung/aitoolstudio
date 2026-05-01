<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// TODO: load from API
const records = ref([
  { id: 1, prompt: 'Cyberpunk city at night, neon lights reflecting on wet streets', time: '2 minutes ago', thumb: '' },
  { id: 2, prompt: 'Studio product photography, minimalist white background, soft lighting', time: '15 minutes ago', thumb: '' },
  { id: 3, prompt: 'Fantasy landscape, ancient temple on floating islands, golden hour', time: '1 hour ago', thumb: '' },
  { id: 4, prompt: 'Abstract art, vibrant geometric patterns, fluid shapes', time: '2 hours ago', thumb: '' },
  { id: 5, prompt: 'Portrait photography, cinematic lighting, moody atmosphere', time: '3 hours ago', thumb: '' },
  { id: 6, prompt: 'Sci-fi spaceship concept art, highly detailed, 4K', time: '5 hours ago', thumb: '' },
])

function regenerate(record: typeof records.value[0]) {
  // TODO: re-generate with same prompt
  console.log('regenerate', record.prompt)
}

function viewDetail(record: typeof records.value[0]) {
  // TODO: navigate to detail
  console.log('view detail', record.id)
}
</script>

<template>
  <div class="history-page">
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
        <button class="back-btn" @click="router.push('/')">
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
        <span class="nav-current">History</span>
      </div>
      <nav class="nav-links">
        <a href="#features" class="nav-link">Features</a>
        <a href="#pricing" class="nav-link">Pricing</a>
        <a href="#gallery" class="nav-link">Gallery</a>
      </nav>
    </header>

    <!-- Main Content -->
    <main class="main-content">
      <div class="history-header">
        <div class="header-left">
          <h1 class="page-title">Creation History</h1>
          <p class="page-sub">{{ records.length }} creations this session</p>
        </div>
        <div class="header-right">
          <div class="filter-tabs">
            <button class="tab active">All</button>
            <button class="tab">Recent</button>
            <button class="tab">Favorites</button>
          </div>
        </div>
      </div>

      <!-- Gallery Grid -->
      <div class="gallery-grid-view">
        <div v-for="record in records" :key="record.id" class="gallery-card" @click="viewDetail(record)">
          <div class="card-thumb">
            <div v-if="!record.thumb" class="thumb-placeholder">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="32" height="32">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <path d="M21 15l-5-5L5 21"/>
              </svg>
            </div>
            <img v-else :src="record.thumb" />
          </div>
          <div class="card-overlay">
            <button class="overlay-btn" @click.stop="regenerate(record)" title="Regenerate">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M1 4v6h6M23 20v-6h-6"/>
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
              </svg>
            </button>
            <button class="overlay-btn" title="Download">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
            </button>
          </div>
          <div class="card-info">
            <p class="card-prompt">{{ record.prompt }}</p>
            <span class="card-time">{{ record.time }}</span>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.history-page {
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
  padding: 32px;
  overflow-y: auto;
}

.history-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 28px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 4px;
}

.page-sub {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.4);
}

.filter-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
}

.tab {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.5);
  background: transparent;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab:hover { color: #ffffff; }

.tab.active {
  background: rgba(0, 217, 255, 0.15);
  color: #00d9ff;
}

/* ── Gallery Grid ──────────────────────────── */
.gallery-grid-view {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.gallery-card {
  position: relative;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
}

.gallery-card:hover {
  border-color: rgba(0, 217, 255, 0.3);
  transform: translateY(-3px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);
}

.card-thumb {
  position: relative;
  aspect-ratio: 4/3;
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb-placeholder {
  color: rgba(255, 255, 255, 0.1);
}

.card-overlay {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}

.gallery-card:hover .card-overlay { opacity: 1; }

.overlay-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  transition: all 0.2s;
}

.overlay-btn:hover {
  background: rgba(0, 217, 255, 0.2);
  border-color: rgba(0, 217, 255, 0.4);
  color: #00d9ff;
}

.card-info {
  padding: 14px 16px;
}

.card-prompt {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-time {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
}

/* ── Responsive ────────────────────────────── */
@media (max-width: 768px) {
  .main-content { padding: 20px; }
  .history-header { flex-direction: column; gap: 16px; }
  .gallery-grid-view { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
  .nav-links { display: none; }
}
</style>
