<script setup lang="ts">
import { ref } from 'vue'

const stats = ref([
  { label: 'Total Creations', value: '48,291', change: '+23%', up: true },
  { label: 'Active Users', value: '1,392', change: '+8%', up: true },
  { label: 'API Calls Today', value: '8,547', change: '+15%', up: true },
  { label: 'Avg Generation Time', value: '8.2s', change: '-12%', up: true },
])

const users = ref([
  { id: 1, name: 'seth', email: 'seth@studio.ai', generations: 142, tokens: '2.1M', status: 'active' },
  { id: 2, name: 'alice', email: 'alice@studio.ai', generations: 89, tokens: '1.3M', status: 'active' },
  { id: 3, name: 'bob', email: 'bob@studio.ai', generations: 234, tokens: '3.8M', status: 'active' },
  { id: 4, name: 'carol', email: 'carol@studio.ai', generations: 67, tokens: '0.9M', status: 'inactive' },
  { id: 5, name: 'dave', email: 'dave@studio.ai', generations: 198, tokens: '2.9M', status: 'active' },
  { id: 6, name: 'eve', email: 'eve@studio.ai', generations: 45, tokens: '0.6M', status: 'active' },
])

const activeTab = ref('overview')
</script>

<template>
  <div class="admin-page">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <svg class="sidebar-logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          <path d="M5 3L5.75 6L8 6.75L5.75 7.5L5 10.5L4.25 7.5L2 6.75L4.25 6L5 3Z" opacity="0.6"/>
          <path d="M19 3L19.75 6L22 6.75L19.75 7.5L19 10.5L18.25 7.5L16 6.75L18.25 6L19 3Z" opacity="0.6"/>
          <path d="M5 14L5.75 17L8 17.75L5.75 18.5L5 21.5L4.25 18.5L2 17.75L4.25 17L5 14Z" opacity="0.6"/>
          <path d="M19 14L19.75 17L22 17.75L19.75 18.5L19 21.5L18.25 18.5L16 17.75L18.25 17L19 14Z" opacity="0.6"/>
        </svg>
        <span class="sidebar-brand">AI Studio</span>
      </div>

      <nav class="sidebar-nav">
        <button class="nav-item" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
          </svg>
          Overview
        </button>
        <button class="nav-item" :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          Users
        </button>
        <button class="nav-item" :class="{ active: activeTab === 'creations' }" @click="activeTab = 'creations'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <path d="M21 15l-5-5L5 21"/>
          </svg>
          Creations
        </button>
        <button class="nav-item" :class="{ active: activeTab === 'settings' }" @click="activeTab = 'settings'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
            <path d="M12 1v6m0 6v10M1 12h6m6 0h10"/>
          </svg>
          Settings
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="user-info">
          <div class="user-avatar">S</div>
          <div class="user-details">
            <span class="user-name">seth</span>
            <span class="user-role">Admin</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Area -->
    <main class="main-area">
      <!-- Top Bar -->
      <header class="top-bar">
        <div class="page-title-area">
          <h1 class="page-title">Dashboard</h1>
          <span class="page-sub">Overview of your AI Image Generator</span>
        </div>
        <div class="top-actions">
          <button class="action-btn secondary">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
            </svg>
            Export
          </button>
          <button class="action-btn primary">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
            New Generation
          </button>
        </div>
      </header>

      <!-- Content -->
      <div class="content-area">
        <!-- Stats Grid -->
        <div class="stats-grid">
          <div v-for="stat in stats" :key="stat.label" class="stat-card">
            <div class="stat-top">
              <span class="stat-label">{{ stat.label }}</span>
              <span class="stat-change" :class="stat.up ? 'up' : 'down'">
                <svg v-if="stat.up" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <path d="M18 15l-6-6-6 6"/>
                </svg>
                {{ stat.change }}
              </span>
            </div>
            <span class="stat-value">{{ stat.value }}</span>
            <div class="stat-bar">
              <div class="stat-bar-fill" :style="{ width: Math.random() * 60 + 40 + '%' }"></div>
            </div>
          </div>
        </div>

        <!-- Charts Row -->
        <div class="charts-grid">
          <div class="chart-card">
            <div class="chart-header">
              <h3 class="chart-title">Daily Generations</h3>
              <div class="chart-tabs">
                <button class="chart-tab active">7D</button>
                <button class="chart-tab">30D</button>
                <button class="chart-tab">90D</button>
              </div>
            </div>
            <div class="bar-chart">
              <div v-for="i in 7" :key="i" class="bar-col">
                <div class="bar-fill" :style="{ height: [45, 65, 40, 80, 55, 70, 90][i-1] + '%' }"></div>
                <span class="bar-label">{{ ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][i-1] }}</span>
              </div>
            </div>
          </div>

          <div class="chart-card">
            <div class="chart-header">
              <h3 class="chart-title">Model Usage</h3>
            </div>
            <div class="model-list">
              <div class="model-item">
                <div class="model-info">
                  <span class="model-name">SDXL Turbo</span>
                  <span class="model-pct">42%</span>
                </div>
                <div class="model-bar">
                  <div class="model-bar-fill" style="width: 42%; background: #667eea;"></div>
                </div>
              </div>
              <div class="model-item">
                <div class="model-info">
                  <span class="model-name">DALL-E 3</span>
                  <span class="model-pct">28%</span>
                </div>
                <div class="model-bar">
                  <div class="model-bar-fill" style="width: 28%; background: #f093fb;"></div>
                </div>
              </div>
              <div class="model-item">
                <div class="model-info">
                  <span class="model-name">Stable Diffusion</span>
                  <span class="model-pct">19%</span>
                </div>
                <div class="model-bar">
                  <div class="model-bar-fill" style="width: 19%; background: #4facfe;"></div>
                </div>
              </div>
              <div class="model-item">
                <div class="model-info">
                  <span class="model-name">Midjourney v6</span>
                  <span class="model-pct">11%</span>
                </div>
                <div class="model-bar">
                  <div class="model-bar-fill" style="width: 11%; background: #43e97b;"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Users Table -->
        <div class="table-card">
          <div class="table-header">
            <h3 class="table-title">Recent Users</h3>
            <button class="view-all-btn">View all</button>
          </div>
          <table class="data-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Generations</th>
                <th>Token Usage</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in users" :key="user.id">
                <td>
                  <div class="user-cell">
                    <div class="user-avatar">{{ user.name[0].toUpperCase() }}</div>
                    <div>
                      <div class="user-name">{{ user.name }}</div>
                      <div class="user-email">{{ user.email }}</div>
                    </div>
                  </div>
                </td>
                <td>{{ user.generations }}</td>
                <td>{{ user.tokens }}</td>
                <td>
                  <span class="status-badge" :class="user.status">{{ user.status }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* ── Layout ───────────────────────────────── */
.admin-page {
  display: flex;
  min-height: 100vh;
  background: #0a0a0f;
}

/* ── Sidebar ──────────────────────────────── */
.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: rgba(15, 15, 20, 0.95);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(20px);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-logo-icon {
  width: 26px;
  height: 26px;
  color: #00d9ff;
  filter: drop-shadow(0 0 6px rgba(0, 217, 255, 0.5));
}

.sidebar-brand {
  font-size: 15px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.3px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 16px 12px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.5);
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  width: 100%;
}

.nav-item svg { flex-shrink: 0; }

.nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.8);
}

.nav-item.active {
  background: rgba(0, 217, 255, 0.1);
  color: #00d9ff;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00d9ff, #00b4d8);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #000000;
  flex-shrink: 0;
}

.user-details {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: #ffffff;
}

.user-role {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
}

/* ── Main Area ─────────────────────────────── */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

/* ── Top Bar ──────────────────────────────── */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 28px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(10, 10, 15, 0.8);
  backdrop-filter: blur(10px);
}

.page-title-area {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  color: #ffffff;
}

.page-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
}

.top-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
  font-family: 'Inter', -apple-system, sans-serif;
}

.action-btn.secondary {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.action-btn.secondary:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
}

.action-btn.primary {
  background: linear-gradient(135deg, #00d9ff 0%, #00b4d8 100%);
  color: #000000;
  font-weight: 600;
}

.action-btn.primary:hover {
  box-shadow: 0 0 16px rgba(0, 217, 255, 0.3);
}

/* ── Content ──────────────────────────────── */
.content-area {
  flex: 1;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── Stats Grid ────────────────────────────── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s;
}

.stat-card:hover {
  border-color: rgba(0, 217, 255, 0.2);
  background: rgba(0, 217, 255, 0.02);
}

.stat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-label {
  font-size: 12px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.5);
}

.stat-change {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  font-weight: 600;
}

.stat-change.up { color: #3fb950; }
.stat-change.down { color: #f85149; }

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.5px;
}

.stat-bar {
  height: 3px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}

.stat-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #00d9ff, #00b4d8);
  border-radius: 2px;
  transition: width 0.6s ease;
}

/* ── Charts Grid ───────────────────────────── */
.charts-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}

.chart-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 20px;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #ffffff;
}

.chart-tabs {
  display: flex;
  gap: 4px;
}

.chart-tab {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.4);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.chart-tab:hover { color: rgba(255, 255, 255, 0.7); }

.chart-tab.active {
  color: #00d9ff;
  background: rgba(0, 217, 255, 0.1);
  border-color: rgba(0, 217, 255, 0.2);
}

/* ── Bar Chart ────────────────────────────── */
.bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  height: 120px;
}

.bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  height: 100%;
  justify-content: flex-end;
}

.bar-fill {
  width: 100%;
  background: linear-gradient(to top, #00d9ff, rgba(0, 217, 255, 0.5));
  border-radius: 4px 4px 0 0;
  transition: height 0.5s ease;
  min-height: 4px;
}

.bar-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

/* ── Model List ────────────────────────────── */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.model-item { display: flex; flex-direction: column; gap: 6px; }

.model-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.model-name {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 500;
}

.model-pct {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.5);
}

.model-bar {
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
}

.model-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}

/* ── Table Card ────────────────────────────── */
.table-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 20px;
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.table-title {
  font-size: 14px;
  font-weight: 600;
  color: #ffffff;
}

.view-all-btn {
  font-size: 12px;
  font-weight: 500;
  color: #00d9ff;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 0.15s;
}

.view-all-btn:hover { color: #00e6ff; }

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.4);
  text-align: left;
  padding: 0 12px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.data-table td {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
  padding: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.data-table tr:last-child td { border-bottom: none; }

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00d9ff, #00b4d8);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #000000;
  flex-shrink: 0;
}

.user-name {
  font-weight: 500;
  color: #ffffff;
  font-size: 13px;
}

.user-email {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
}

.status-badge {
  display: inline-block;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
}

.status-badge.active {
  background: rgba(63, 185, 80, 0.12);
  color: #3fb950;
}

.status-badge.inactive {
  background: rgba(139, 148, 158, 0.12);
  color: #8b949e;
}

/* ── Responsive ────────────────────────────── */
@media (max-width: 1100px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .charts-grid { grid-template-columns: 1fr; }
}
</style>
