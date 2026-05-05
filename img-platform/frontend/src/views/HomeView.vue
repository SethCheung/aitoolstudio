<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/services/api'

const { t } = useI18n()
const router = useRouter()

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

function openProject(id: number) {
  router.push({ path: '/generate', query: { convId: String(id) } })
}

function newProject() {
  router.push('/generate')
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
    <!-- Header -->
    <header class="top-header">
      <div class="header-logo">
        <svg class="logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
        </svg>
        <span class="logo-text">{{ t('generate.brand') }}</span>
      </div>
    </header>

    <!-- Projects Grid -->
    <main class="projects-main">
      <div v-if="loading" class="loading-state">
        <span>{{ t('common.loading') }}</span>
      </div>

      <div v-else-if="projects.length === 0" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="empty-icon">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <polyline points="21 15 16 10 5 21"/>
        </svg>
        <p class="empty-title">No projects yet</p>
        <p class="empty-sub">Click the + button below to create your first project.</p>
      </div>

      <div v-else class="projects-grid">
        <div
          v-for="p in projects"
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
              <p class="card-meta">{{ timeAgo(p.created_at) }} · {{ p.type }}</p>
            </div>
          </div>

          <!-- Hover Actions -->
          <div class="card-actions">
            <button class="card-action-btn" @click="startRename(p, $event)" title="重命名">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
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

    <!-- Floating Add Button -->
    <button class="fab" @click="newProject" title="New Project">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M12 5v14M5 12h14"/>
      </svg>
    </button>

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
  background: #0a0a0f;
  color: white;
  font-family: 'Inter', -apple-system, sans-serif;
  display: flex;
  flex-direction: column;
}
.top-header {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.header-logo { display: flex; align-items: center; gap: 10px; }
.logo-icon { width: 22px; height: 22px; color: #00d2ff; }
.logo-text { font-size: 15px; font-weight: 600; color: white; }

.projects-main {
  flex: 1;
  padding: 32px 24px 100px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}
.empty-state, .loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  gap: 12px;
  color: #9ca3af;
}
.empty-icon { width: 56px; height: 56px; color: rgba(0,210,255,0.3); }
.empty-title { font-size: 18px; font-weight: 600; color: white; margin: 0; }
.empty-sub { font-size: 14px; color: #6b7280; margin: 0; text-align: center; max-width: 320px; }

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 20px;
}
.project-card {
  position: relative;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
  background: #111827;
  overflow: hidden;
  transition: all 0.2s;
}
.card-main { cursor: pointer; }
.card-main:hover { opacity: 0.85; }

.card-thumb {
  height: 160px;
  background: #1a1a2e;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.card-thumb.empty { background: #1a1a2e; }
.thumb-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.thumb-placeholder { width: 48px; height: 48px; color: rgba(255,255,255,0.15); }
.thumb-placeholder svg { width: 48px; height: 48px; }
.card-body { padding: 14px 16px; }
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: white;
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-meta { font-size: 12px; color: #6b7280; margin: 0; }

/* Hover Actions */
.card-actions {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.project-card:hover .card-actions { opacity: 1; }
.card-action-btn {
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: none;
  background: rgba(0,0,0,0.65);
  color: rgba(255,255,255,0.8);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  backdrop-filter: blur(4px);
}
.card-action-btn:hover { background: rgba(0,0,0,0.85); color: white; }
.card-action-btn.danger:hover { background: rgba(220,38,38,0.8); color: white; }

/* FAB */
.fab {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00d9ff, #0080ff);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 24px rgba(0, 130, 255, 0.45);
  transition: all 0.2s;
  z-index: 100;
}
.fab:hover {
  transform: translateX(-50%) scale(1.08);
  box-shadow: 0 6px 32px rgba(0, 130, 255, 0.6);
}
.fab svg { width: 24px; height: 24px; color: white; }

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
</style>
