<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

// ── Tab ──────────────────────────────────────────────
const sidebarItems = ['概览', '用户', '工作流', 'GPU 监控', '模型', '日志', '账单', '设置']
const activeTab = ref(0)

const users = [
  ['Alex Chen', 'alex@example.com', '管理员', '活跃'],
  ['Sarah Kim', 'sarah@example.com', '专业版', '活跃'],
  ['Mike Ross', 'mike@example.com', '用户', '停用'],
  ['Emma Watson', 'emma@example.com', '专业版', '活跃'],
  ['John Doe', 'john@example.com', '用户', '活跃'],
]
const workflows = ['文生图流程', '图片增强', '批量处理']

const totalGens = ref(0)

// ── Profiles ─────────────────────────────────────────
interface Profile {
  name: string
  api_key_masked: string
  enabled: boolean
  priority: number
  models: Record<string, string[]>
}
const profiles = ref<Profile[]>([])
const modelOptions = ['image-01', 'image-01-turbo', 'speech-02-hd', 'speech-02', 'hailuo-video-01', 'music-01']
const modelCategories: Record<string, string[]> = {
  image: ['image-01', 'image-01-turbo'],
  voice: ['speech-02-hd', 'speech-02'],
  video: ['hailuo-video-01'],
  music: ['music-01'],
}

const showAddForm = ref(false)
const editingProfile = ref<Profile | null>(null)
const form = ref({ name: '', api_key: '', enabled: true, priority: 1, models: {} as Record<string, string[]> })
const formError = ref('')

async function fetchProfiles() {
  try {
    profiles.value = (await axios.get('/api/profiles')).data
  } catch (e) {
    console.error('Failed to load profiles', e)
  }
}

function openAdd() {
  editingProfile.value = null
  form.value = { name: '', api_key: '', enabled: true, priority: 1, models: { image: ['image-01'], voice: [], video: [], music: [] } }
  formError.value = ''
  showAddForm.value = true
}

function openEdit(p: Profile) {
  editingProfile.value = p
  form.value = { name: p.name, api_key: '', enabled: p.enabled, priority: p.priority, models: { ...p.models } }
  formError.value = ''
  showAddForm.value = true
}

async function saveProfile() {
  if (!form.value.name || !form.value.api_key) {
    formError.value = '名称和 API Key 不能为空'
    return
  }
  try {
    if (editingProfile.value) {
      await axios.put(`/api/profiles/${editingProfile.value.name}`, form.value)
    } else {
      await axios.post('/api/profiles', form.value)
    }
    showAddForm.value = false
    fetchProfiles()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || '保存失败'
  }
}

async function toggleProfile(name: string, enabled: boolean) {
  const action = enabled ? 'enable' : 'disable'
  await axios.post(`/api/profiles/${name}/${action}`)
  fetchProfiles()
}

async function deleteProfile(name: string) {
  if (!confirm(`确认删除 Profile "${name}"？`)) return
  await axios.delete(`/api/profiles/${name}`)
  fetchProfiles()
}

// ── Init ─────────────────────────────────────────────
async function fetchStats() {
  try {
    const resp = await axios.get('/api/generations/stats')
    totalGens.value = resp.data.total_generations
  } catch (e) {
    console.error('Failed to load stats', e)
  }
}

onMounted(() => { fetchProfiles(); fetchStats() })
</script>

<template>
  <div class="admin-page">
    <!-- Top Header -->
    <header class="top-header">
      <div class="header-logo">
        <svg class="logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          <path d="M5 3L5.75 6L8 6.75L5.75 7.5L5 10.5L4.25 7.5L2 6.75L4.25 6L5 3Z" opacity="0.6"/>
          <path d="M19 3L19.75 6L22 6.75L19.75 7.5L19 10.5L18.25 7.5L16 6.75L18.25 6L19 3Z" opacity="0.6"/>
          <path d="M5 14L5.75 17L8 17.75L5.75 18.5L5 21.5L4.25 18.5L2 17.75L4.25 17L5 14Z" opacity="0.6"/>
          <path d="M19 14L19.75 17L22 17.75L19.75 18.5L19 21.5L18.25 18.5L16 17.75L18.25 17L19 14Z" opacity="0.6"/>
        </svg>
        <span class="logo-text">AI 图片生成器</span>
      </div>
      <div class="header-right">
        <div class="search-box">
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          搜索...
        </div>
        <svg class="bell-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        <div class="user-avatar">AC</div>
      </div>
    </header>

    <!-- Body: Sidebar + Main -->
    <div class="admin-body">
      <!-- Left Sidebar -->
      <aside class="sidebar">
        <div class="sidebar-nav">
          <div
            v-for="(item, i) in sidebarItems"
            :key="item"
            class="sidebar-item"
            :class="{ active: i === 0 }"
          >
            <!-- Grid3x3 for first item -->
            <svg v-if="i === 0" class="item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
              <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
            <!-- Settings for others -->
            <svg v-else class="item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            {{ item }}
          </div>
        </div>

        <!-- System Status -->
        <div class="system-status surface-card">
          <div class="status-row">
            <div class="status-dot"></div>
            <span class="status-text">所有系统运行正常</span>
          </div>
          <p class="status-meta">上次检查：2 分钟前</p>
        </div>

        <!-- User -->
        <div class="sidebar-user">
          <div class="user-avatar-lg">AC</div>
          <div class="user-info">
            <div class="user-name">Alex Chen</div>
            <div class="user-role">Super Admin</div>
          </div>
        </div>
      </aside>

      <!-- Main -->
      <main class="admin-main">
        <!-- Page Header -->
        <div class="page-header">
          <div>
            <h1 class="page-title">概览</h1>
            <p class="page-sub">AI 图片生成器 管理面板</p>
          </div>
          <div class="header-pills">
            <div class="toolbar-pill">2026年5月1日</div>
            <div class="toolbar-pill">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="pill-icon">
                <polyline points="23 4 23 10 17 10"/>
                <polyline points="1 20 1 14 7 14"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
              </svg>
              刷新
            </div>
          </div>
        </div>

        <!-- KPI Cards -->
        <div class="kpi-grid">
          <div class="kpi-card surface-card">
            <div class="kpi-label">用户总数</div>
            <div class="kpi-value">1,248</div>
            <div class="kpi-meta">+12.5%</div>
          </div>
          <div class="kpi-card surface-card">
            <div class="kpi-label">生成图片数</div>
            <div class="kpi-value">{{ totalGens > 0 ? totalGens.toLocaleString() : "—" }}</div>
            <div class="kpi-meta">+18.7%</div>
          </div>
          <div class="kpi-card surface-card">
            <div class="kpi-label">活跃 GPU</div>
            <div class="kpi-value">12/16</div>
            <div class="kpi-bar"><div class="kpi-bar-fill"></div></div>
          </div>
          <div class="kpi-card surface-card green-kpi">
            <div class="kpi-label">运行时间</div>
            <div class="kpi-value green-val">99.9%</div>
          </div>
        </div>

        <!-- Charts -->
        <div class="charts-grid">
          <div class="chart-card surface-card">
            <h2 class="chart-title">GPU 温度</h2>
            <div class="chart-area">
              <div class="chart-line cyan-line"></div>
              <div class="chart-line purple-line"></div>
              <div class="chart-line green-line"></div>
              <div class="chart-line amber-line"></div>
            </div>
          </div>
          <div class="chart-card surface-card">
            <h2 class="chart-title">GPU 显存</h2>
            <div class="chart-area">
              <div class="chart-line cyan-line"></div>
              <div class="chart-line purple-line"></div>
              <div class="chart-line green-line"></div>
              <div class="chart-line amber-line"></div>
            </div>
          </div>
        </div>

        <!-- Bottom Section -->
        <div class="bottom-grid">
          <!-- Users Table -->
          <div class="table-card surface-card">
            <div class="table-header">
              <div class="col">用户</div>
              <div class="col">邮箱</div>
              <div class="col">角色</div>
              <div class="col">状态</div>
            </div>
            <div v-for="row in users" :key="row[0]" class="table-row">
              <div class="cell">{{ row[0] }}</div>
              <div class="cell">{{ row[1] }}</div>
              <div class="cell">{{ row[2] }}</div>
              <div class="cell">
                <span class="status-badge" :class="row[3] === 'Active' ? 'badge-green' : 'badge-gray'">{{ row[3] }}</span>
              </div>
            </div>
            <div class="pagination">
              <button class="page-btn">上一页</button>
              <button class="page-btn active-page">1 / 10</button>
              <button class="page-btn">下一页</button>
            </div>
          </div>

          <!-- Workflow Configs -->
          <div class="workflow-card surface-card">
            <h2 class="wf-title">工作流配置</h2>
            <div v-for="(wf, i) in workflows" :key="wf" class="wf-item">
              <div class="wf-name">
                <svg class="wf-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <line x1="6" y1="3" x2="6" y2="15"/>
                  <circle cx="18" cy="6" r="3"/>
                  <circle cx="6" cy="18" r="3"/>
                  <path d="M18 9a9 9 0 0 1-9 9"/>
                </svg>
                {{ wf }}
              </div>
              <span class="wf-status" :class="i === 2 ? 'status-amber' : 'status-green'">
                {{ i === 2 ? '已暂停' : '运行中' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Profile Management (设置 tab) -->
        <div class="section-card surface-card" style="margin-top:24px">
          <div class="section-header">
            <h2 class="section-title">API Profile 配置</h2>
            <button class="btn-primary" @click="openAdd">+ 新增 Profile</button>
          </div>

          <!-- Profile List -->
          <div class="profile-list">
            <div v-for="p in profiles" :key="p.name" class="profile-row">
              <div class="profile-info">
                <div class="profile-name">{{ p.name }}</div>
                <div class="profile-meta">
                  <span class="badge" :class="p.enabled ? 'badge-green' : 'badge-gray'">{{ p.enabled ? '已启用' : '已禁用' }}</span>
                  <span class="meta-tag">优先级 {{ p.priority }}</span>
                  <span class="meta-tag">{{ p.api_key_masked }}</span>
                </div>
                <div class="profile-models">
                  <template v-for="(models, cat) in (p.models || {})" :key="cat">
                    <span v-if="models && models.length" class="model-chip">
                      {{ cat }}: {{ models.join(', ') }}
                    </span>
                  </template>
                </div>
              </div>
              <div class="profile-actions">
                <button class="btn-sm" @click="toggleProfile(p.name, !p.enabled)">{{ p.enabled ? '禁用' : '启用' }}</button>
                <button class="btn-sm" @click="openEdit(p)">编辑</button>
                <button class="btn-sm btn-danger" @click="deleteProfile(p.name)">删除</button>
              </div>
            </div>
            <div v-if="profiles.length === 0" class="empty-state">暂无 Profile，点击上方按钮添加</div>
          </div>
        </div>
      </main>
    </div>
  </div>

  <!-- Add/Edit Profile Modal -->
  <div v-if="showAddForm" class="modal-overlay" @click.self="showAddForm = false">
    <div class="modal-box surface-card">
      <div class="modal-header">
        <h3>{{ editingProfile ? '编辑' : '新增' }} Profile</h3>
        <button class="modal-close" @click="showAddForm = false">✕</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label>名称</label>
          <input v-model="form.name" placeholder="如: MiniMax-Pro" :disabled="!!editingProfile" />
        </div>
        <div class="form-group">
          <label>API Key <span style="color:#888;font-weight:400">({{ editingProfile ? '留空则不修改' : '必填' }})</span></label>
          <input v-model="form.api_key" type="password" placeholder="sk-..." />
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>优先级</label>
            <input v-model.number="form.priority" type="number" min="1" />
          </div>
          <div class="form-group">
            <label>状态</label>
            <select v-model="form.enabled">
              <option :value="true">启用</option>
              <option :value="false">禁用</option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label>支持的模型</label>
          <div class="model-grid">
            <div v-for="(models, cat) in modelCategories" :key="cat" class="model-cat">
              <div class="cat-label">{{ cat }}</div>
              <label v-for="m in models" :key="m" class="model-check">
                <input type="checkbox" :value="m" v-model="form.models[cat]" />
                {{ m }}
              </label>
            </div>
          </div>
        </div>
        <div v-if="formError" class="form-error">{{ formError }}</div>
      </div>
      <div class="modal-footer">
        <button class="btn-ghost" @click="showAddForm = false">取消</button>
        <button class="btn-primary" @click="saveProfile">保存</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-page {
  min-height: 100vh;
  background: #05070a;
  color: white;
  font-family: 'Inter', -apple-system, sans-serif;
}

/* Top Header */
.top-header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: #0d1117;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.header-logo {
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
  font-size: 15px;
  font-weight: 600;
  color: white;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}
.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 200px;
  height: 40px;
  padding: 0 12px;
  background: #151821;
  border-radius: 8px;
  font-size: 14px;
  color: #484f58;
}
.search-icon { width: 16px; height: 16px; }
.bell-icon {
  width: 20px;
  height: 20px;
  color: #9ca3af;
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
  cursor: pointer;
}

/* Admin Body */
.admin-body {
  display: flex;
  height: calc(100vh - 64px);
}

/* Sidebar */
.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #0a0d12;
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sidebar-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 44px;
  padding: 0 12px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 8px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.15s;
}
.sidebar-item:hover {
  background: #151821;
  color: white;
}
.sidebar-item.active {
  background: #00d2ff;
  color: #05070a;
}
.sidebar-item.active .item-icon { stroke: #05070a; }
.item-icon {
  width: 16px;
  height: 16px;
}

/* System Status */
.system-status {
  padding: 16px;
  border-radius: 12px;
  border: 1px solid #1f2937;
  background: #0d1117;
}
.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #22c55e;
}
.status-text { color: white; }
.status-meta {
  font-size: 12px;
  color: #6b7280;
  margin: 16px 0 0;
}

/* Sidebar User */
.sidebar-user {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #151821;
  border-radius: 12px;
}
.user-avatar-lg {
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
.user-role {
  font-size: 12px;
  color: #6b7280;
}

/* Main */
.admin-main {
  flex: 1;
  padding: 32px;
  overflow-y: auto;
}

/* Page Header */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.page-title {
  font-size: 24px;
  font-weight: 700;
  color: white;
  margin: 0;
}
.page-sub {
  font-size: 14px;
  color: #9ca3af;
  margin: 4px 0 0;
}
.header-pills {
  display: flex;
  gap: 12px;
}
.toolbar-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  background: #151821;
  border-radius: 8px;
  font-size: 14px;
  color: #d1d5db;
  cursor: pointer;
}
.pill-icon { width: 14px; height: 14px; }

/* KPI Grid */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-top: 56px;
}
.kpi-card {
  height: 120px;
  padding: 20px;
  border-radius: 12px;
  border: 1px solid #1f2937;
  background: #0d1117;
}
.kpi-label {
  font-size: 14px;
  color: #9ca3af;
}
.kpi-value {
  font-size: 30px;
  font-weight: 700;
  color: white;
  margin-top: 8px;
}
.kpi-meta {
  font-size: 14px;
  color: #22c55e;
  margin-top: 8px;
}
.kpi-bar {
  height: 4px;
  background: #243044;
  border-radius: 99px;
  margin-top: 16px;
  overflow: hidden;
}
.kpi-bar-fill {
  height: 100%;
  width: 75%;
  background: #00d2ff;
  border-radius: 99px;
}
.green-kpi .kpi-value { color: #22c55e; }

/* Charts */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-top: 16px;
}
.chart-card {
  height: 240px;
  padding: 20px;
  border-radius: 12px;
  border: 1px solid #1f2937;
  background: #0d1117;
}
.chart-title {
  font-size: 14px;
  font-weight: 700;
  color: white;
  margin: 0;
}
.chart-area {
  height: 150px;
  background: #080b10;
  border-radius: 8px;
  margin-top: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.chart-line {
  height: 2px;
  border-radius: 99px;
}
.cyan-line { background: #00d2ff; }
.purple-line { background: #7c3aed; }
.green-line { background: #22c55e; }
.amber-line { background: #f59e0b; }

/* Bottom Grid */
.bottom-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
  margin-top: 16px;
}

/* Table */
.table-card {
  padding: 20px;
  border-radius: 12px;
  border: 1px solid #1f2937;
  background: #0d1117;
}
.table-header {
  display: grid;
  grid-template-columns: 1.1fr 1.4fr 0.8fr 0.8fr;
  gap: 12px;
  font-size: 12px;
  color: #9ca3af;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.table-row {
  display: grid;
  grid-template-columns: 1.1fr 1.4fr 0.8fr 0.8fr;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.cell {
  font-size: 14px;
  color: #d1d5db;
}
.status-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
.badge-green {
  background: #22c55e;
  color: white;
}
.badge-gray {
  background: #6b7280;
  color: white;
}
.pagination {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
  font-size: 12px;
}
.page-btn {
  padding: 8px 16px;
  background: #151821;
  border: none;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
}
.page-btn:hover { color: white; }
.active-page {
  background: #00d2ff;
  color: #05070a;
  font-weight: 600;
}

/* Workflows */
.workflow-card {
  padding: 20px;
  border-radius: 12px;
  border: 1px solid #1f2937;
  background: #0d1117;
}
.wf-title {
  font-size: 14px;
  font-weight: 700;
  color: white;
  margin: 0 0 16px;
}
.wf-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 16px;
  background: #151821;
  border-radius: 8px;
  margin-bottom: 12px;
}
.wf-name {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: white;
}
.wf-icon {
  width: 20px;
  height: 20px;
}
.wf-name .wf-icon { color: #00d2ff; }
.wf-status {
  font-size: 12px;
}
.status-green { color: #22c55e; }
.status-amber { color: #f59e0b; }

/* Profile Management */
.section-card { padding: 24px; border-radius: 12px; border: 1px solid #1f2937; background: #0d1117; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.section-title { font-size: 16px; font-weight: 600; color: white; margin: 0; }
.profile-list { display: flex; flex-direction: column; gap: 12px; }
.profile-row { display: flex; align-items: center; justify-content: space-between; padding: 16px; background: #151821; border-radius: 8px; gap: 16px; }
.profile-info { flex: 1; min-width: 0; }
.profile-name { font-weight: 600; color: white; margin-bottom: 4px; }
.profile-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.meta-tag { font-size: 12px; color: #9ca3af; background: #1f2937; padding: 2px 8px; border-radius: 4px; }
.profile-models { display: flex; flex-wrap: wrap; gap: 6px; }
.model-chip { font-size: 11px; background: #1a2a3a; color: #60a5fa; padding: 2px 8px; border-radius: 4px; }
.profile-actions { display: flex; gap: 8px; flex-shrink: 0; }
.empty-state { text-align: center; color: #6b7280; padding: 32px; font-size: 14px; }

/* Buttons */
.btn-primary { background: #00d2ff; color: #05070a; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-primary:hover { opacity: 0.85; }
.btn-ghost { background: transparent; color: #9ca3af; border: 1px solid #374151; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-ghost:hover { color: white; border-color: #6b7280; }
.btn-sm { background: #1f2937; color: #d1d5db; border: none; padding: 5px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; }
.btn-sm:hover { background: #374151; color: white; }
.btn-danger { color: #f87171 !important; border: 1px solid #7f1d1d !important; }
.btn-danger:hover { background: #7f1d1d !important; }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { width: 520px; max-width: 95vw; border-radius: 12px; border: 1px solid #374151; overflow: hidden; }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid #1f2937; }
.modal-header h3 { margin: 0; font-size: 15px; color: white; }
.modal-close { background: none; border: none; color: #6b7280; cursor: pointer; font-size: 16px; padding: 4px; }
.modal-close:hover { color: white; }
.modal-body { padding: 20px; max-height: 70vh; overflow-y: auto; }
.modal-footer { padding: 16px 20px; border-top: 1px solid #1f2937; display: flex; justify-content: flex-end; gap: 10px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; color: #9ca3af; margin-bottom: 6px; font-weight: 500; }
.form-group input, .form-group select { width: 100%; background: #151821; border: 1px solid #374151; color: white; padding: 8px 12px; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.form-group input:focus, .form-group select:focus { outline: none; border-color: #00d2ff; }
.form-group input:disabled { opacity: 0.5; cursor: not-allowed; }
.form-row { display: flex; gap: 12px; }
.form-row .form-group { flex: 1; }
.form-error { color: #f87171; font-size: 13px; margin-top: 8px; }
.model-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.model-cat { background: #151821; border-radius: 8px; padding: 10px; }
.cat-label { font-size: 12px; color: #60a5fa; text-transform: uppercase; font-weight: 600; margin-bottom: 8px; }
.model-check { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #d1d5db; cursor: pointer; margin-bottom: 4px; }
.model-check input { accent-color: #00d2ff; }
</style>
