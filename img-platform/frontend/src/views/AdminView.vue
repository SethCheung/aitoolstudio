<script setup lang="ts">
import { ref } from 'vue'

const stats = ref([
  { label: 'Total Users', value: '2,847', change: '+12%', up: true },
  { label: 'Active Users', value: '1,392', change: '+8%', up: true },
  { label: 'Total Generations', value: '48,291', change: '+23%', up: true },
  { label: 'Total Tokens', value: '128.5M', change: '+18%', up: true },
])

const users = ref([
  { id: 1, name: 'seth', email: 'seth@example.com', generations: 142, tokens: '2.1M', status: 'active' },
  { id: 2, name: 'alice', email: 'alice@example.com', generations: 89, tokens: '1.3M', status: 'active' },
  { id: 3, name: 'bob', email: 'bob@example.com', generations: 234, tokens: '3.8M', status: 'active' },
  { id: 4, name: 'carol', email: 'carol@example.com', generations: 67, tokens: '0.9M', status: 'inactive' },
])
</script>

<template>
  <div class="admin-page">
    <!-- 左侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-logo">AI Studio</div>
      <nav class="sidebar-nav">
        <a class="nav-item active">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
          </svg>
          概览
        </a>
        <a class="nav-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          用户管理
        </a>
        <a class="nav-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
            <path d="M4.93 4.93a10 10 0 0 0 0 14.14"/>
          </svg>
          生成记录
        </a>
        <a class="nav-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v6m0 6v10"/>
            <path d="m4.22 4.22 4.24 4.24m7.08 7.08 4.24 4.24"/>
            <path d="M1 12h6m6 0h10"/>
            <path d="m4.22 19.78 4.24-4.24m7.08-7.08 4.24-4.24"/>
          </svg>
          设置
        </a>
      </nav>
    </aside>

    <!-- 主内容 -->
    <main class="main-area">
      <!-- 顶部栏 -->
      <header class="top-bar">
        <h1 class="page-title">仪表盘</h1>
      </header>

      <!-- 统计卡片 -->
      <div class="stats-grid">
        <div v-for="stat in stats" :key="stat.label" class="stat-card">
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-value">{{ stat.value }}</span>
          <span class="stat-change" :class="stat.up ? 'up' : 'down'">
            {{ stat.change }}
          </span>
        </div>
      </div>

      <!-- 图表区 -->
      <div class="charts-grid">
        <div class="chart-card">
          <h3 class="chart-title">每日生成量</h3>
          <div class="chart-placeholder">
            <div class="bar-chart">
              <div class="bar" style="height: 40%"></div>
              <div class="bar" style="height: 65%"></div>
              <div class="bar" style="height: 45%"></div>
              <div class="bar" style="height: 80%"></div>
              <div class="bar" style="height: 55%"></div>
              <div class="bar" style="height: 70%"></div>
              <div class="bar" style="height: 90%"></div>
            </div>
          </div>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Token 消耗分布</h3>
          <div class="chart-placeholder pie-placeholder">
            <div class="pie-chart"></div>
          </div>
        </div>
      </div>

      <!-- 用户表格 -->
      <div class="table-card">
        <h3 class="table-title">用户列表</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>生成次数</th>
              <th>Token 消耗</th>
              <th>状态</th>
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
    </main>
  </div>
</template>

<style scoped>
/* ── 页面布局 ───────────────────────────────── */
.admin-page {
  display: flex;
  min-height: 100vh;
  background: #00070d;
}

/* ── 侧边栏 ────────────────────────────────── */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #0d1117;
  border-right: 1px solid #21262d;
  display: flex;
  flex-direction: column;
  padding-top: 20px;
}

.sidebar-logo {
  font-size: 14px;
  font-weight: 700;
  color: #e6edf3;
  padding: 0 20px 24px;
  letter-spacing: -0.3px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  font-size: 13px;
  font-weight: 500;
  color: #8b949e;
  text-decoration: none;
  border-radius: 8px;
  transition: all 0.15s;
  cursor: pointer;
}
.nav-item svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
.nav-item:hover {
  background: #161b22;
  color: #e6edf3;
}
.nav-item.active {
  background: rgba(0, 212, 242, 0.1);
  color: #00d4f2;
}

/* ── 主内容区 ───────────────────────────────── */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

/* ── 顶部栏 ────────────────────────────────── */
.top-bar {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid #21262d;
}

.page-title {
  font-size: 15px;
  font-weight: 600;
  color: #e6edf3;
}

/* ── 统计卡片 ───────────────────────────────── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  padding: 20px 24px;
}

.stat-card {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stat-label {
  font-size: 12px;
  color: #8b949e;
  font-weight: 500;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.5px;
}

.stat-change {
  font-size: 12px;
  font-weight: 500;
}
.stat-change.up { color: #3fb950; }
.stat-change.down { color: #f85149; }

/* ── 图表区 ────────────────────────────────── */
.charts-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  padding: 0 24px 16px;
}

.chart-card {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 12px;
  padding: 18px 20px;
}

.chart-title {
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  margin-bottom: 16px;
}

.chart-placeholder {
  height: 140px;
  display: flex;
  align-items: flex-end;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 100%;
  width: 100%;
}

.bar {
  flex: 1;
  background: linear-gradient(to top, #00d4f2, #00a8c6);
  border-radius: 4px 4px 0 0;
  opacity: 0.8;
  transition: opacity 0.15s;
}
.bar:hover { opacity: 1; }

/* ── 表格 ──────────────────────────────────── */
.table-card {
  margin: 0 24px 24px;
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 12px;
  padding: 18px 20px;
}

.table-title {
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  margin-bottom: 14px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  font-size: 11px;
  font-weight: 600;
  color: #8b949e;
  text-align: left;
  padding: 0 12px 10px;
  border-bottom: 1px solid #21262d;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.data-table td {
  font-size: 13px;
  color: #e6edf3;
  padding: 12px;
  border-bottom: 1px solid #161b22;
}

.data-table tr:last-child td {
  border-bottom: none;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #00d4f2, #00a8c6);
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
  color: #e6edf3;
  font-size: 13px;
}

.user-email {
  font-size: 11px;
  color: #484f58;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
}
.status-badge.active {
  background: rgba(63, 185, 80, 0.15);
  color: #3fb950;
}
.status-badge.inactive {
  background: rgba(139, 148, 158, 0.15);
  color: #8b949e;
}
</style>
