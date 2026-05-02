<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const sidebarItems = ['概览', '用户', '工作流', 'GPU 监控', '模型', '日志', '账单', '设置']
const users = [
  ['Alex Chen', 'alex@example.com', '管理员', '活跃'],
  ['Sarah Kim', 'sarah@example.com', '专业版', '活跃'],
  ['Mike Ross', 'mike@example.com', '用户', '停用'],
  ['Emma Watson', 'emma@example.com', '专业版', '活跃'],
  ['John Doe', 'john@example.com', '用户', '活跃'],
]
const workflows = ['文生图流程', '图片增强', '批量处理']

const totalGens = ref(0)

async function fetchStats() {
  try {
    const resp = await axios.get('/api/generations/stats')
    totalGens.value = resp.data.total_generations
  } catch (e) {
    console.error('Failed to load stats', e)
  }
}

onMounted(fetchStats)
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
      </main>
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
</style>
