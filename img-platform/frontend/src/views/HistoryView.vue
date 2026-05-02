<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()

const navItems = [
  { icon: 'home', label: '首页' },
  { icon: 'compass', label: '探索' },
  { icon: 'image', label: '图库', active: true },
  { icon: 'gitbranch', label: '工作流' },
  { icon: 'cpu', label: '模型' },
  { icon: 'folder', label: '素材' },
  { icon: 'users', label: '成员' },
  { icon: 'settings', label: '设置' },
]

const filterItems = ['全部时间', '今天', '昨天', '本周', '本月', '自定义范围']

interface Generation {
  id: number
  prompt: string
  image_urls: string[]
  model: string
  aspect_ratio: string
  n_generated: number
  created_at: string
}

const generations = ref<Generation[]>([])
const totalCount = ref(0)
const isLoading = ref(false)

async function fetchGenerations() {
  isLoading.value = true
  try {
    const resp = await axios.get('/api/generations?limit=50')
    generations.value = resp.data.items
    totalCount.value = resp.data.total
  } catch (e) {
    console.error('Failed to load generations', e)
  } finally {
    isLoading.value = false
  }
}

function timeAgo(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return diff + 's ago'
  if (diff < 3600) return Math.floor(diff / 60) + ' min ago'
  if (diff < 86400) return Math.floor(diff / 3600) + ' hour' + (Math.floor(diff / 3600) > 1 ? 's' : '') + ' ago'
  return Math.floor(diff / 86400) + ' day' + (Math.floor(diff / 86400) > 1 ? 's' : '') + ' ago'
}

function goGenerate() {
  router.push('/generate')
}

onMounted(fetchGenerations)
</script>

<template>
  <div class="history-layout">
    <!-- Left Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-logo">
        <svg class="logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          <path d="M5 3L5.75 6L8 6.75L5.75 7.5L5 10.5L4.25 7.5L2 6.75L4.25 6L5 3Z" opacity="0.6"/>
          <path d="M19 3L19.75 6L22 6.75L19.75 7.5L19 10.5L18.25 7.5L16 6.75L18.25 6L19 3Z" opacity="0.6"/>
          <path d="M5 14L5.75 17L8 17.75L5.75 18.5L5 21.5L4.25 18.5L2 17.75L4.25 17L5 14Z" opacity="0.6"/>
          <path d="M19 14L19.75 17L22 17.75L19.75 18.5L19 21.5L18.25 18.5L16 17.75L18.25 17L19 14Z" opacity="0.6"/>
        </svg>
        <span class="logo-text">AI Collaboration Platform</span>
      </div>

      <!-- Nav -->
      <nav class="sidebar-nav">
        <div
          v-for="item in navItems"
          :key="item.label"
          class="nav-item"
          :class="{ active: item.active }"
        >
          <!-- Home -->
          <svg v-if="item.icon === 'home'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          <!-- Compass -->
          <svg v-else-if="item.icon === 'compass'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
          </svg>
          <!-- Image -->
          <svg v-else-if="item.icon === 'image'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
          <!-- GitBranch -->
          <svg v-else-if="item.icon === 'gitbranch'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <line x1="6" y1="3" x2="6" y2="15"/>
            <circle cx="18" cy="6" r="3"/>
            <circle cx="6" cy="18" r="3"/>
            <path d="M18 9a9 9 0 0 1-9 9"/>
          </svg>
          <!-- Cpu -->
          <svg v-else-if="item.icon === 'cpu'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="4" y="4" width="16" height="16" rx="2" ry="2"/>
            <rect x="9" y="9" width="6" height="6"/>
            <line x1="9" y1="1" x2="9" y2="4"/>
            <line x1="15" y1="1" x2="15" y2="4"/>
            <line x1="9" y1="20" x2="9" y2="23"/>
            <line x1="15" y1="20" x2="15" y2="23"/>
            <line x1="20" y1="9" x2="23" y2="9"/>
            <line x1="20" y1="14" x2="23" y2="14"/>
            <line x1="1" y1="9" x2="4" y2="9"/>
            <line x1="1" y1="14" x2="4" y2="14"/>
          </svg>
          <!-- Folder -->
          <svg v-else-if="item.icon === 'folder'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <!-- Users -->
          <svg v-else-if="item.icon === 'users'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          <!-- Settings -->
          <svg v-else-if="item.icon === 'settings'" class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          {{ item.label }}
        </div>
      </nav>

      <!-- Filters -->
      <div class="sidebar-filters">
        <div class="filter-label">筛选</div>
        <div class="filter-clear">清除全部</div>
        <div class="filter-group">
          <div class="filter-heading">按日期</div>
          <div class="filter-dot active-dot"></div>
          <div v-for="f in filterItems" :key="f" class="filter-item" :class="{ active: f === 'All Time' }">{{ f }}</div>
        </div>
      </div>

      <!-- Storage -->
      <div class="sidebar-storage">
        <div class="storage-visual"></div>
        <div class="storage-label">存储</div>
        <div class="storage-amount">102.4 GB / 500 GB</div>
        <div class="storage-bar"><div class="storage-fill"></div></div>
        <div class="storage-pct">20%</div>
        <div class="storage-user">
          <div class="user-avatar">AC</div>
          <div class="user-info">
            <div class="user-name">Alex Chen</div>
            <div class="user-plan">专业版</div>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content">
      <!-- Content Header -->
      <div class="content-header">
        <div class="header-left">
          <h1 class="page-title">图库</h1>
          <div class="result-count">
            <div class="count-box"></div>
            <span>{{ totalCount.toLocaleString() }}</span>
          </div>
        </div>
        <div class="header-right">
          <div class="search-box">
            <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            搜索图片、工作流...
          </div>
          <button class="btn-primary" @click="goGenerate">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            新建生成
          </button>
        </div>
      </div>

      <!-- Sort Bar -->
      <div class="sort-bar">
        <span class="sort-label">排序：</span>
        <span class="sort-value">最新</span>
        <svg class="sort-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
        <div class="view-toggles">
          <div class="view-toggle active-toggle"></div>
          <div class="view-toggle"></div>
        </div>
      </div>

      <!-- Gallery Grid -->
      <div v-if="isLoading" class="gallery-grid">
        <div v-for="i in 4" :key="i" class="gallery-card">
          <div class="card-thumb" style="background: #111827; opacity: 0.5;"></div>
          <h3 class="card-title" style="opacity: 0.3;">加载中...</h3>
          <p class="card-meta">—</p>
        </div>
      </div>
      <div v-else-if="generations.length === 0" class="gallery-grid" style="grid-column: 1/-1; text-align: center; padding: 60px 0;">
        <p style="color: #9ca3af; font-size: 16px;">暂无生成记录， 开始创作吧！</p>
        <button class="btn-primary" style="margin-top: 16px; display: inline-flex;" @click="goGenerate">新建生成</button>
      </div>
      <div v-else class="gallery-grid">
        <div
          v-for="gen in generations"
          :key="gen.id"
          class="gallery-card"
        >
          <div
            class="card-thumb"
            :style="gen.image_urls[0] ? 'background-image: url(' + gen.image_urls[0] + '); background-size: cover; background-position: center;' : 'background: #111827;'"
          ></div>
          <h3 class="card-title">{{ gen.prompt.slice(0, 40) }}{{ gen.prompt.length > 40 ? '...' : '' }}</h3>
          <p class="card-meta">{{ gen.model }} - {{ timeAgo(gen.created_at) }}</p>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.history-layout {
  min-height: 100vh;
  display: flex;
  background: #0a0a0b;
  color: white;
  font-family: 'Inter', -apple-system, sans-serif;
}

/* Sidebar */
.sidebar {
  width: 280px;
  flex-shrink: 0;
  background: #0f1115;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100vh;
  overflow-y: auto;
}
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-icon {
  width: 24px;
  height: 24px;
  color: #00d2ff;
}
.logo-text {
  font-size: 14px;
  font-weight: 600;
  color: white;
}
.sidebar-nav {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 40px;
  padding: 0 12px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 8px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.15s;
}
.nav-item:hover {
  background: rgba(255,255,255,0.05);
  color: white;
}
.nav-item.active {
  background: #1f2937;
  color: white;
}
.nav-item.active .nav-icon { color: #00d2ff; }
.nav-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* Filters */
.sidebar-filters {
  margin-top: 8px;
  font-size: 12px;
}
.filter-label {
  font-weight: 700;
  color: white;
  margin-bottom: 4px;
}
.filter-clear {
  color: #00d2ff;
  cursor: pointer;
  margin-top: 8px;
}
.filter-group {
  margin-top: 12px;
}
.filter-heading {
  color: #9ca3af;
  margin-bottom: 8px;
}
.active-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #00d2ff;
  margin: 8px 0;
}
.filter-item {
  color: #6b7280;
  margin-top: 8px;
  cursor: pointer;
}
.filter-item:first-of-type { color: white; }

/* Storage */
.sidebar-storage {
  margin-top: auto;
  padding-top: 16px;
}
.storage-visual {
  height: 100px;
  border-radius: 8px;
  background: #151821;
  margin-bottom: 12px;
}
.storage-label {
  font-size: 12px;
  color: #9ca3af;
}
.storage-amount {
  font-size: 12px;
  color: white;
  margin-top: 4px;
}
.storage-bar {
  height: 4px;
  background: #233044;
  border-radius: 99px;
  margin-top: 12px;
  overflow: hidden;
}
.storage-fill {
  height: 100%;
  width: 20%;
  background: #00d2ff;
  border-radius: 99px;
}
.storage-pct {
  font-size: 12px;
  color: #00d2ff;
  margin-top: 8px;
}
.storage-user {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 28px;
}
.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #00d2ff;
  color: #05070a;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.user-name {
  font-size: 14px;
  font-weight: 700;
  color: white;
}
.user-plan {
  font-size: 12px;
  color: #6b7280;
}

/* Main Content */
.main-content {
  flex: 1;
  padding: 24px;
  overflow: hidden;
}
.content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 48px;
}
.page-title {
  font-size: 24px;
  font-weight: 700;
  color: white;
  margin: 0;
}
.result-count {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #9ca3af;
}
.count-box {
  width: 40px;
  height: 24px;
  background: #1f2937;
  border-radius: 4px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 24px;
}
.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 320px;
  height: 40px;
  padding: 0 12px;
  background: #0d1117;
  border: 1px solid #1f2937;
  border-radius: 8px;
  font-size: 14px;
  color: #484f58;
}
.search-icon {
  width: 16px;
  height: 16px;
  color: #6b7280;
}
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 0 20px;
  font-size: 14px;
  font-weight: 700;
  background: #00d2ff;
  color: #05070a;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.btn-primary:hover {
  box-shadow: 0 0 24px rgba(0,210,255,0.4);
}
.btn-icon { width: 16px; height: 16px; }

/* Sort Bar */
.sort-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 40px;
  margin-top: 16px;
  font-size: 14px;
}
.sort-label { color: #9ca3af; }
.sort-value { font-weight: 700; color: white; }
.sort-chevron {
  width: 16px;
  height: 16px;
  color: #9ca3af;
}
.view-toggles {
  display: flex;
  gap: 8px;
  margin-left: 8px;
}
.view-toggle {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  background: #1f2937;
}
.active-toggle {
  background: #00d2ff;
}

/* Gallery Grid */
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-top: 16px;
}
.gallery-card { cursor: pointer; }
.card-thumb {
  height: 180px;
  border-radius: 8px;
}
.card-title {
  font-size: 12px;
  font-weight: 700;
  color: white;
  margin: 16px 0 12px;
}
.card-meta {
  font-size: 10px;
  color: #6b7280;
  margin: 0;
}
</style>
