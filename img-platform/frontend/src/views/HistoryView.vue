<script setup lang="ts">
import { ref } from 'vue'

// TODO: 从 API 加载历史记录
const records = ref([
  { id: 1, prompt: '一只赛博朋克风格的猫', time: '2 分钟前', thumb: '' },
  { id: 2, prompt: '未来城市街景，赛博朋克', time: '15 分钟前', thumb: '' },
  { id: 3, prompt: '机械手臂特写', time: '1 小时前', thumb: '' },
])
</script>

<template>
  <div class="history-page">
    <!-- 顶部导航 -->
    <header class="top-nav">
      <div class="nav-left">
        <span class="logo-text">AI Studio</span>
        <span class="nav-sep">/</span>
        <span class="nav-current">历史记录</span>
      </div>
    </header>

    <!-- 主内容 -->
    <main class="main-content">
      <div class="history-header">
        <h1 class="page-title">历史记录</h1>
      </div>

      <div class="records-list">
        <div v-for="record in records" :key="record.id" class="record-item">
          <div class="record-thumb">
            <div v-if="!record.thumb" class="thumb-placeholder">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <path d="M21 15l-5-5L5 21"/>
              </svg>
            </div>
            <img v-else :src="record.thumb" />
          </div>
          <div class="record-info">
            <p class="record-prompt">{{ record.prompt }}</p>
            <span class="record-time">{{ record.time }}</span>
          </div>
          <button class="re生成-btn">重新生成</button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.history-page {
  min-height: 100vh;
  background: #00070d;
}

.top-nav {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid #21262d;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-text {
  font-size: 13px;
  font-weight: 600;
  color: #8b949e;
}

.nav-sep { color: #484f58; }
.nav-current { font-size: 13px; font-weight: 500; color: #e6edf3; }

.main-content {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 24px;
}

.history-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #ffffff;
}

.records-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.record-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 10px;
  transition: border-color 0.15s;
}
.record-item:hover {
  border-color: #30363d;
}

.record-thumb {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  background: #161b22;
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb-placeholder {
  color: #484f58;
  width: 24px;
  height: 24px;
}

.thumb-placeholder svg {
  width: 100%;
  height: 100%;
}

.record-info {
  flex: 1;
  min-width: 0;
}

.record-prompt {
  font-size: 13px;
  color: #e6edf3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.record-time {
  font-size: 12px;
  color: #484f58;
}

.re生成-btn {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  font-family: 'Inter', sans-serif;
  background: #0d1117;
  color: #8b949e;
  border: 1px solid #21262d;
  border-radius: 6px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}
.re生成-btn:hover {
  background: #161b22;
  color: #e6edf3;
  border-color: #30363d;
}
</style>
