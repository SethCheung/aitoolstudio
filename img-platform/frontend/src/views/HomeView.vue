<script setup lang="ts">
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
</script>

<template>
  <div class="home-page">
    <div class="hero-content">
      <h1 class="hero-title">
        欢迎回来，<span class="username">{{ auth.user?.username }}</span>
      </h1>
      <p class="hero-sub">开始创作 AI 图像</p>
      <div class="hero-actions">
        <router-link to="/generate" class="action-btn primary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          开始生图
        </router-link>
        <router-link to="/history" class="action-btn secondary">查看历史</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  min-height: calc(100vh - 52px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: #00070d;
  position: relative;
  overflow: hidden;
}

/* 背景网格 */
.home-page::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 212, 242, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 212, 242, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
}

.hero-content {
  position: relative;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.hero-title {
  font-size: 32px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.5px;
}

.username {
  color: #00d4f2;
}

.hero-sub {
  font-size: 15px;
  color: #8b949e;
  margin-bottom: 8px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 22px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  border-radius: 8px;
  text-decoration: none;
  transition: all 0.15s;
}

.action-btn svg {
  width: 16px;
  height: 16px;
}

.action-btn.primary {
  background: #00d4f2;
  color: #000000;
}
.action-btn.primary:hover {
  background: #00e6ff;
  box-shadow: 0 0 24px rgba(0, 212, 242, 0.3);
}

.action-btn.secondary {
  background: #0d1117;
  color: #e6edf3;
  border: 1px solid #21262d;
}
.action-btn.secondary:hover {
  background: #161b22;
  border-color: #30363d;
}
</style>
