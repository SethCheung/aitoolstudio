<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

interface ProjectItem {
  id: number
  title: string
  type: string
  thumb: string
  prompt: string
  created_at: string
}

const projects = ref<ProjectItem[]>([])
const loading = ref(false)
const searchQuery = ref('')
const sortMode = ref<'recent' | 'oldest' | 'name'>('recent')
const viewMode = ref<'grid' | 'list'>('grid')

// Rename modal
const renameVisible = ref(false)
const renameId = ref<number | null>(null)
const renameTitle = ref('')

async function fetchProjects() {
  loading.value = true
  try {
    const resp = await api.get('/api/conversations')
    projects.value = (Array.isArray(resp.data) ? resp.data : []).map((c: any) => ({
      id: c.id,
      title: c.title || 'New Project',
      type: c.type || 'image',
      thumb: c.thumb || '',
      prompt: c.prompt || '',
      created_at: c.created_at,
    }))
  } catch (e) {
    console.error('Failed to load projects', e)
  } finally {
    loading.value = false
  }
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return diff + 's ago'
  if (diff < 3600) return Math.floor(diff / 60) + ' min ago'
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago'
  return Math.floor(diff / 86400) + 'd ago'
}

const filteredProjects = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  const list = projects.value.filter((project) => {
    if (!query) return true
    return [project.title, project.prompt, project.type]
      .some((value) => value.toLowerCase().includes(query))
  })

  return [...list].sort((a, b) => {
    if (sortMode.value === 'name') return a.title.localeCompare(b.title)
    const aTime = new Date(a.created_at).getTime()
    const bTime = new Date(b.created_at).getTime()
    return sortMode.value === 'oldest' ? aTime - bTime : bTime - aTime
  })
})

function openProject(id: number) {
  router.push({ path: '/generate', query: { convId: String(id) } })
}

function canvasUrl() {
  // Force port 5173 for canvas — avoid fnOS (5666) or port 80 misrouting
  const proto = window.location.protocol
  const host = window.location.hostname
  return `${proto}//${host}:5173/canvas`
}

function newPipeline() {
  window.location.href = canvasUrl()
}

function openCanvas(_id: number, e: Event) {
  e.stopPropagation()
  localStorage.setItem('api-provider', 'comfyui')
  localStorage.setItem('token', auth.token || '')
  localStorage.setItem('api-keys-by-provider', JSON.stringify({ comfyui: 'fire-canvas-intranet' }))
  localStorage.setItem('base-urls-by-provider', JSON.stringify({ comfyui: '' }))
  window.location.href = canvasUrl()
}

function newProject() {
  router.push('/generate')
}

async function logout() {
  auth.logout()
  await router.replace('/login')
}

// Rename
function startRename(p: ProjectItem, e: Event) {
  e.stopPropagation()
  renameId.value = p.id
  renameTitle.value = p.title
  renameVisible.value = true
}

async function confirmRename() {
  if (!renameId.value || !renameTitle.value.trim()) return
  try {
    await api.patch(`/api/conversations/${renameId.value}`, {
      title: renameTitle.value.trim()
    })
    const p = projects.value.find(x => x.id === renameId.value)
    if (p) p.title = renameTitle.value.trim()
    renameVisible.value = false
    ElMessage.success('已重命名')
  } catch {
    ElMessage.error('重命名失败')
  }
}

// Delete
async function deleteProject(p: ProjectItem, e: Event) {
  e.stopPropagation()
  try {
    await ElMessageBox.confirm(`删除项目「${p.title}」？此操作不可恢复。`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await api.delete(`/api/conversations/${p.id}`)
    projects.value = projects.value.filter(x => x.id !== p.id)
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

onMounted(fetchProjects)
</script>

<template>
  <div class="home-page">
    <header class="top-header">
      <div class="header-logo">
        <svg class="logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
        </svg>
        <span class="logo-text">{{ t('generate.brand') }}</span>
      </div>

      <label class="search-box">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <circle cx="11" cy="11" r="7"/>
          <path d="M20 20l-3.5-3.5"/>
        </svg>
        <input v-model="searchQuery" type="search" placeholder="搜索项目、提示词或标签..." />
        <span>⌘ K</span>
      </label>

      <div class="header-actions">
        <button class="logout-top-btn" type="button" @click="logout">
          退出登录
        </button>
        <button class="new-top-btn" type="button" @click="newProject">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          新建项目
        </button>
      </div>
    </header>

    <main class="projects-main">
      <section class="projects-toolbar">
        <div>
          <h1>Recent Projects</h1>
          <p>共 {{ filteredProjects.length }} 个项目</p>
        </div>

        <div class="toolbar-actions">
          <select v-model="sortMode" class="toolbar-select">
            <option value="recent">最近更新</option>
            <option value="oldest">最早创建</option>
            <option value="name">项目名称</option>
          </select>
          <button class="filter-btn" type="button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
              <path d="M4 5h16l-6 7v5l-4 2v-7L4 5z"/>
            </svg>
            筛选
          </button>
          <div class="view-toggle">
            <button type="button" :class="{ active: viewMode === 'grid' }" title="网格视图" @click="viewMode = 'grid'">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="4" y="4" width="6" height="6"/>
                <rect x="14" y="4" width="6" height="6"/>
                <rect x="4" y="14" width="6" height="6"/>
                <rect x="14" y="14" width="6" height="6"/>
              </svg>
            </button>
            <button type="button" :class="{ active: viewMode === 'list' }" title="列表视图" @click="viewMode = 'list'">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>
              </svg>
            </button>
          </div>
        </div>
      </section>

      <div v-if="loading" class="loading-state">
        <span>{{ t('common.loading') }}</span>
      </div>

      <div v-else class="projects-grid" :class="{ list: viewMode === 'list' }">
        <div class="create-card" @click="newPipeline()">
          <div class="create-plus">+</div>
          <strong>新建流水线</strong>
          <small>用画布节点、工作流和素材开始</small>
        </div>
        <div
          v-for="p in filteredProjects"
          :key="p.id"
          class="project-card"
        >
          <!-- Click area -->
          <div class="card-main" @click="openProject(p.id)">
            <div class="card-thumb" :class="{ empty: !p.thumb }">
              <img v-if="p.thumb" :src="p.thumb" :alt="p.title" class="thumb-image" loading="lazy" />
              <div v-if="!p.thumb" class="thumb-placeholder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="8.5" cy="8.5" r="1.5"/>
                  <polyline points="21 15 16 10 5 21"/>
                </svg>
              </div>
            </div>
            <div class="card-body">
              <p class="card-title">{{ p.title }}</p>
              <p class="card-meta">{{ timeAgo(p.created_at) }}</p>
            </div>
          </div>

          <div class="card-actions">
            <button class="card-action-btn canvas-btn" @click="openCanvas(p.id, $event)" title="画布编辑">
              ⬡
            </button>
            <button class="card-action-btn" @click="startRename(p, $event)" title="重命名">
              ···
            </button>
            <button class="card-action-btn danger" @click="deleteProject(p, $event)" title="删除">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- Rename Modal -->
    <Teleport to="body">
      <div v-if="renameVisible" class="modal-overlay" @click.self="renameVisible = false">
        <div class="modal">
          <h3 class="modal-title">重命名项目</h3>
          <input
            v-model="renameTitle"
            class="modal-input"
            placeholder="输入项目名称..."
            @keydown.enter="confirmRename"
            autofocus
          />
          <div class="modal-actions">
            <button class="modal-btn cancel" @click="renameVisible = false">取消</button>
            <button class="modal-btn confirm" @click="confirmRename">保存</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at 50% -12%, rgba(0, 217, 255, 0.12), transparent 34%),
    linear-gradient(180deg, #03060b 0%, #050912 45%, #03060b 100%);
  color: white;
  font-family: 'Inter', -apple-system, sans-serif;
  display: flex;
  flex-direction: column;
}
.top-header {
  min-height: 66px;
  display: grid;
  grid-template-columns: minmax(190px, 1fr) minmax(320px, 520px) minmax(300px, 1fr);
  gap: 20px;
  align-items: center;
  padding: 0 28px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  background: rgba(3, 6, 12, 0.74);
  backdrop-filter: blur(18px);
  flex-shrink: 0;
}
.header-logo { display: flex; align-items: center; gap: 10px; min-width: 0; }
.logo-icon { width: 21px; height: 21px; color: #00cfff; filter: drop-shadow(0 0 9px rgba(0,207,255,.46)); }
.logo-text { font-size: 16px; font-weight: 730; color: white; white-space: nowrap; }
.search-box {
  height: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 10px;
  background: rgba(5, 8, 14, 0.86);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
}
.search-box svg { width: 18px; height: 18px; color: rgba(255,255,255,0.58); flex-shrink: 0; }
.search-box input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: #fff;
  font-size: 13px;
}
.search-box input::placeholder { color: rgba(255,255,255,0.46); }
.search-box span { color: rgba(255,255,255,0.56); font-size: 12px; white-space: nowrap; }
.header-actions {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 11px;
}

.logout-top-btn {
  height: 40px;
  display: inline-flex;
  align-items: center;
  padding: 0 14px;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 9px;
  background: rgba(255,255,255,0.07);
  color: rgba(255,255,255,0.82);
  font-size: 13px;
  font-weight: 720;
  cursor: pointer;
}
.logout-top-btn:hover {
  border-color: rgba(255,255,255,0.28);
  background: rgba(255,255,255,0.12);
  color: #fff;
}
.new-top-btn {
  height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 17px;
  border: 0;
  border-radius: 9px;
  background: linear-gradient(180deg, #05c8ff, #00a9ef);
  color: #00131c;
  font-size: 13px;
  font-weight: 760;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(0, 178, 255, 0.24);
}
.new-top-btn svg { width: 16px; height: 16px; }
.projects-main {
  flex: 1;
  padding: 28px 28px 34px;
  max-width: 1420px;
  margin: 0 auto;
  width: 100%;
}
.projects-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}
.projects-toolbar h1 {
  margin: 0 0 7px;
  font-size: 24px;
  line-height: 1.1;
  font-weight: 760;
}
.projects-toolbar p {
  margin: 0;
  color: rgba(255,255,255,0.62);
  font-size: 13px;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar-select,
.filter-btn,
.view-toggle {
  height: 42px;
  border: 1px solid rgba(255,255,255,0.13);
  border-radius: 9px;
  background: rgba(5,8,14,0.72);
  color: rgba(255,255,255,0.88);
}
.toolbar-select {
  padding: 0 14px;
  font-size: 13px;
  outline: 0;
}
.toolbar-select option { background: #08101a; color: #fff; }
.filter-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  font-size: 13px;
  cursor: pointer;
}
.filter-btn svg { width: 17px; height: 17px; }
.view-toggle {
  display: inline-flex;
  overflow: hidden;
}
.view-toggle button {
  width: 52px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  color: rgba(255,255,255,0.68);
  cursor: pointer;
}
.view-toggle button.active {
  background: rgba(0,184,255,0.14);
  color: #00d9ff;
}
.view-toggle svg { width: 19px; height: 19px; }
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  gap: 12px;
  color: #9ca3af;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(238px, 1fr));
  gap: 22px;
}
.projects-grid.list {
  grid-template-columns: 1fr;
  gap: 14px;
}
.create-card {
  min-height: 190px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px dashed rgba(255,255,255,0.22);
  border-radius: 10px;
  background: rgba(5,8,14,0.36);
  color: #fff;
  cursor: pointer;
}
.create-card:hover {
  border-color: rgba(0,217,255,0.52);
  background: rgba(0,217,255,0.05);
}
.create-plus {
  color: #00d9ff;
  font-size: 32px;
  line-height: 1;
  font-weight: 300;
}
.create-card strong { font-size: 14px; }
.create-card small {
  max-width: 136px;
  color: rgba(255,255,255,0.56);
  font-size: 12px;
  line-height: 1.5;
}
.project-card {
  position: relative;
  min-height: 190px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(9,15,25,0.82);
  overflow: hidden;
  transition: all 0.2s;
}
.project-card:hover {
  transform: translateY(-2px);
  border-color: rgba(0,217,255,0.34);
  box-shadow: 0 18px 52px rgba(0,0,0,0.34);
}
.card-main { height: 100%; cursor: pointer; }

.card-thumb {
  height: 132px;
  background: #0b1220;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.card-thumb.empty { background: linear-gradient(135deg, #0f172a, #111827); }
.thumb-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumb-placeholder { width: 40px; height: 40px; color: rgba(255,255,255,0.15); }
.thumb-placeholder svg { width: 40px; height: 40px; }
.card-body {
  min-height: 58px;
  padding: 10px 14px 12px;
  background: linear-gradient(180deg, rgba(8,12,20,0.82), rgba(8,12,20,0.96));
}
.card-title {
  font-size: 13px;
  font-weight: 720;
  color: white;
  margin: 0 0 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-meta { font-size: 12px; color: rgba(255,255,255,0.56); margin: 0; }
.projects-grid.list .create-card,
.projects-grid.list .project-card {
  min-height: 96px;
}
.projects-grid.list .project-card .card-main {
  display: grid;
  grid-template-columns: 140px 1fr;
}
.projects-grid.list .card-thumb { height: 96px; }
.projects-grid.list .card-body {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 96px;
}

.card-actions {
  position: absolute;
  right: 11px;
  bottom: 13px;
  display: flex;
  gap: 6px;
  opacity: 1;
}
.card-action-btn {
  width: 26px;
  height: 22px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.88);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  font-size: 18px;
  line-height: 1;
}
.card-action-btn.canvas-btn {
  color: #72ff9c;
  font-size: 16px;
  line-height: 1;
}
.card-action-btn:hover { background: rgba(255,255,255,0.08); color: white; }
.card-action-btn.danger:hover { background: rgba(220,38,38,0.8); color: white; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}
.modal {
  background: #1a1a2e;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 16px;
  padding: 28px 32px;
  width: min(420px, 90vw);
}
.modal-title { font-size: 18px; font-weight: 700; color: white; margin: 0 0 20px; }
.modal-input {
  width: 100%;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 10px;
  color: white;
  font-size: 15px;
  font-family: 'Inter', sans-serif;
  padding: 12px 14px;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}
.modal-input:focus { border-color: rgba(0,210,255,0.5); }
.modal-input::placeholder { color: rgba(255,255,255,0.3); }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
.modal-btn {
  padding: 9px 22px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}
.modal-btn.cancel { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.6); }
.modal-btn.cancel:hover { background: rgba(255,255,255,0.12); color: white; }
.modal-btn.confirm { background: #00d2ff; color: #05070a; }
.modal-btn.confirm:hover { background: #00b4d8; }

@media (max-width: 980px) {
  .top-header {
    grid-template-columns: 1fr;
    gap: 14px;
    padding: 18px;
  }

  .header-actions,
  .search-box {
    width: 100%;
  }

  .header-actions {
    justify-self: stretch;
    justify-content: space-between;
  }

  .projects-main {
    padding: 24px 18px 32px;
  }

  .projects-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    width: 100%;
    flex-wrap: wrap;
  }
}

@media (max-width: 640px) {
  .projects-grid {
    grid-template-columns: 1fr;
    gap: 18px;
  }

  .new-top-btn {
    flex: 1;
    justify-content: center;
  }

  .toolbar-select,
  .filter-btn,
  .view-toggle {
    flex: 1;
  }
}
</style>
