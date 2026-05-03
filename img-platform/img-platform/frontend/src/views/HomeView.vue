<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()

interface Generation {
  id: number
  prompt: string
  image_urls: string[]
  model: string
  created_at: string
}

const recentGens = ref<Generation[]>([])
const totalCount = ref(0)

async function fetchData() {
  try {
    const [statsRes, gensRes] = await Promise.all([
      axios.get('/api/generations/stats'),
      axios.get('/api/generations?limit=3'),
    ])
    totalCount.value = statsRes.data.total_generations
    recentGens.value = gensRes.data.items
  } catch (e) {
    console.error('Failed to load home data', e)
  }
}

function timeAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return diff + 's ago'
  if (diff < 3600) return Math.floor(diff / 60) + ' min ago'
  if (diff < 86400) return Math.floor(diff / 3600) + ' hour' + (Math.floor(diff / 3600) > 1 ? 's' : '') + ' ago'
  return Math.floor(diff / 86400) + ' day' + (Math.floor(diff / 86400) > 1 ? 's' : '') + ' ago'
}

function goGenerate() {
  router.push('/generate')
}

onMounted(fetchData)
</script>

<template>
  <div class="home-page">
    <!-- Header -->
    <header class="top-header">
      <div class="header-logo">
        <svg class="logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          <path d="M5 3L5.75 6L8 6.75L5.75 7.5L5 10.5L4.25 7.5L2 6.75L4.25 6L5 3Z" opacity="0.6"/>
          <path d="M19 3L19.75 6L22 6.75L19.75 7.5L19 10.5L18.25 7.5L16 6.75L18.25 6L19 3Z" opacity="0.6"/>
          <path d="M5 14L5.75 17L8 17.75L5.75 18.5L5 21.5L4.25 18.5L2 17.75L4.25 17L5 14Z" opacity="0.6"/>
          <path d="M19 14L19.75 17L22 17.75L19.75 18.5L19 21.5L18.25 18.5L16 17.75L18.25 17L19 14Z" opacity="0.6"/>
        </svg>
        <span class="logo-text">AI 工作室</span>
      </div>
      <nav class="header-nav">
        <span class="nav-item active">首页</span>
        <span class="nav-item">工作室</span>
        <span class="nav-item">工作流</span>
        <span class="nav-item">模型</span>
        <span class="nav-item">社区</span>
      </nav>
      <div class="header-right">
        <!-- Bell icon -->
        <svg class="bell-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        <div class="user-badge">
          <div class="user-avatar">AC</div>
          <span class="user-name">AC</span>
          <svg class="chevron-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>
    </header>

    <!-- Hero Section -->
    <section class="hero-section">
      <h1 class="hero-title">AI 创意工作室</h1>
      <p class="hero-sub">
  <span v-if="totalCount > 0">{{ totalCount }} 张图片已生成</span>
  <span v-else>在一个地方生成、编辑和管理 AI 图片</span>
</p>
    </section>

    <!-- Feature Cards -->
    <section class="feature-grid">
      <!-- Image Generation -->
      <div class="feature-card surface-card">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
        </div>
        <h3 class="feature-title">图像生成</h3>
        <p class="feature-desc">从文本或参考图创建精美 AI 图片。</p>
        <svg class="feature-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </div>
      <!-- Workflow Canvas -->
      <div class="feature-card surface-card">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <line x1="6" y1="3" x2="6" y2="15"/>
            <circle cx="18" cy="6" r="3"/>
            <circle cx="6" cy="18" r="3"/>
            <path d="M18 9a9 9 0 0 1-9 9"/>
          </svg>
        </div>
        <h3 class="feature-title">工作流画布</h3>
        <p class="feature-desc">可视化地构建和连接强大的 AI 工作流。</p>
        <svg class="feature-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </div>
      <!-- History & Library -->
      <div class="feature-card surface-card">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <h3 class="feature-title">历史与图库</h3>
        <p class="feature-desc">访问历史创作并管理您的素材资产。</p>
        <svg class="feature-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </div>
    </section>

    <!-- Recent Projects -->
    <section class="recent-section">
      <div class="recent-header">
        <div class="recent-title-row">
          <svg class="clock-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          <h2 class="recent-title">最近项目</h2>
          <svg class="chevron-down" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
          <span class="view-all">查看全部</span>
      </div>
      <div v-if="recentGens.length > 0" class="project-grid">
        <div
          v-for="(gen, i) in recentGens"
          :key="gen.id"
          class="project-card"
          :class="{ selected: i === 0 }"
        >
          <div
            class="project-thumb"
            :class="{ 'selected-thumb': i === 0 }"
            :style="gen.image_urls[0] ? 'background-image: url(' + gen.image_urls[0] + '); background-size: cover; background-position: center;' : 'background: #111827;'"
          ></div>
          <h3 class="project-name">{{ gen.prompt.slice(0, 30) }}{{ gen.prompt.length > 30 ? '...' : '' }}</h3>
          <div class="project-meta">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="meta-icon">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            <span>{{ timeAgo(gen.created_at) }}</span>
          </div>
        </div>
      </div>
      <div v-else class="project-grid">
        <div v-for="i in 3" :key="i" class="project-card">
          <div class="project-thumb" style="background: #111827; opacity: 0.4;"></div>
          <h3 class="project-name" style="opacity: 0.3;">暂无生成记录</h3>
          <div class="project-meta">
            <span>—</span>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="cta-section">
      <button class="btn-primary" @click="goGenerate">
        开始创作
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </button>
      <router-link to="/history" class="btn-ghost">
        查看历史
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
      </router-link>
    </section>
  </div>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  background: #05070a;
  color: white;
  font-family: 'Inter', -apple-system, sans-serif;
}

/* Header */
.top-header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.header-logo {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-icon {
  width: 24px;
  height: 24px;
  color: #00d2ff;
}
.logo-text {
  font-size: 15px;
  font-weight: 600;
  color: white;
}
.header-nav {
  display: flex;
  gap: 32px;
  font-size: 14px;
  color: #9ca3af;
}
.nav-item {
  cursor: pointer;
  transition: color 0.15s;
}
.nav-item:hover { color: white; }
.nav-item.active { color: #00d2ff; }
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.bell-icon {
  width: 20px;
  height: 20px;
  color: #9ca3af;
}
.user-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #00d2ff;
  color: #05070a;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.user-name {
  font-size: 14px;
  font-weight: 600;
  color: white;
}
.chevron-icon {
  width: 16px;
  height: 16px;
  color: #9ca3af;
}

/* Hero */
.hero-section {
  text-align: center;
  padding: 80px 20px 0;
}
.hero-title {
  font-size: 48px;
  font-weight: 700;
  color: white;
  letter-spacing: -0.5px;
  margin: 0;
}
.hero-sub {
  margin: 16px 0 0;
  font-size: 18px;
  color: #9ca3af;
}

/* Feature Grid */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  max-width: 1250px;
  margin: 40px auto 0;
  padding: 0 40px;
}
.feature-card {
  height: 220px;
  padding: 24px;
  border-radius: 12px;
  border: 1px solid #1f2937;
  background: #0d1117;
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: all 0.15s;
}
.feature-card:hover {
  border-color: rgba(0, 210, 255, 0.3);
}
.feature-icon {
  width: 24px;
  height: 24px;
  color: #00d2ff;
  margin-bottom: 16px;
}
.feature-icon svg { width: 24px; height: 24px; }
.feature-title {
  font-size: 16px;
  font-weight: 700;
  color: white;
  margin: 0 0 12px;
}
.feature-desc {
  font-size: 14px;
  color: #9ca3af;
  margin: 0;
  flex: 1;
}
.feature-arrow {
  width: 16px;
  height: 16px;
  color: rgba(0,0,0,0.4);
  margin-top: 16px;
}

/* Recent Projects */
.recent-section {
  max-width: 1250px;
  margin: 40px auto 0;
  padding: 0 40px;
}
.recent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.recent-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.clock-icon {
  width: 16px;
  height: 16px;
  color: #00d2ff;
}
.recent-title {
  font-size: 16px;
  font-weight: 700;
  color: white;
  margin: 0;
}
.chevron-down {
  width: 16px;
  height: 16px;
  color: #9ca3af;
  transform: rotate(180deg);
}
.view-all {
  font-size: 14px;
  color: #9ca3af;
  cursor: pointer;
}
.project-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.project-card { cursor: pointer; }
.project-thumb {
  height: 200px;
  border-radius: 12px;
  border: 1px solid transparent;
  transition: border-color 0.15s;
}
.selected-thumb { border: 2px solid #00d2ff; }
.project-name {
  font-size: 14px;
  font-weight: 700;
  color: white;
  margin: 8px 0 4px;
}
.project-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #6b7280;
}
.meta-icon {
  width: 12px;
  height: 12px;
}

/* CTA */
.cta-section {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px 60px;
}
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 13px 24px;
  font-size: 14px;
  font-weight: 700;
  font-family: 'Inter', sans-serif;
  background: #00d2ff;
  color: #05070a;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.15s;
}
.btn-primary:hover {
  box-shadow: 0 0 28px rgba(0, 210, 255, 0.5);
  transform: translateY(-2px);
}
.btn-icon { width: 18px; height: 18px; }
.btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 13px 24px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  background: rgba(255, 255, 255, 0.05);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-ghost:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.25);
}
</style>
