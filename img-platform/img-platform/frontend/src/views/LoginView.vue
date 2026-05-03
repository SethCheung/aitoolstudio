<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const isLoading = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) return
  isLoading.value = true
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <!-- Header -->
    <header class="login-header">
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
      <nav class="header-nav">
        <span>功能</span>
        <span>定价</span>
        <span>文档</span>
        <span>图库</span>
      </nav>
      <button class="btn-signin">登录</button>
    </header>

    <!-- Login Card -->
    <div class="login-body">
      <div class="login-card">
        <!-- Star icon in cyan box -->
        <div class="card-logo-box">
          <svg class="card-star-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          </svg>
        </div>

        <!-- Title -->
        <div class="card-title-group">
          <div class="card-ai-label">AI</div>
          <h1 class="card-title">图片生成器。</h1>
          <p class="card-subtitle">将创意转化为精美视觉作品</p>
        </div>

        <!-- Form -->
        <form @submit.prevent="handleLogin" class="login-form">
          <label class="field-label">用户名</label>
          <div class="field-input">
            <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <input
              v-model="username"
              type="text"
              placeholder="输入用户名"
              autocomplete="username"
            />
          </div>

          <label class="field-label">密码</label>
          <div class="field-input">
            <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <input
              v-model="password"
              type="password"
              placeholder="输入密码"
              autocomplete="current-password"
            />
          </div>

          <div v-if="auth.error" class="error-msg">{{ auth.error }}</div>

          <button type="submit" class="btn-submit" :disabled="isLoading">
            <span v-if="!isLoading">登录</span>
            <span v-else class="loading-dots">正在登录<span>.</span><span>.</span><span>.</span></span>
            <svg v-if="!isLoading" class="btn-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </form>

        <p class="signup-link">
          <span class="text-muted">还没有账号？</span>
          <span class="text-cyan">注册</span>
        </p>
      </div>
    </div>

    <!-- Footer -->
    <footer class="login-footer">
      <span class="copyright">&copy; 2024 AI 图片生成器</span>
      <div class="footer-icons">
        <!-- MessageCircle -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="footer-icon">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        <!-- Zap -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="footer-icon">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
        <!-- GitBranch -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="footer-icon">
          <line x1="6" y1="3" x2="6" y2="15"/>
          <circle cx="18" cy="6" r="3"/>
          <circle cx="6" cy="18" r="3"/>
          <path d="M18 9a9 9 0 0 1-9 9"/>
        </svg>
        <!-- Compass -->
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="footer-icon">
          <circle cx="12" cy="12" r="10"/>
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
        </svg>
      </div>
      <div class="footer-lang">
        English
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron-icon">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070a;
  color: white;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Header */
.login-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
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
  filter: drop-shadow(0 0 8px rgba(0, 210, 255, 0.5));
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
.btn-signin {
  height: 36px;
  padding: 0 24px;
  font-size: 14px;
  font-weight: 500;
  background: transparent;
  color: white;
  border: 1px solid #00d2ff;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-signin:hover {
  background: rgba(0, 210, 255, 0.1);
}

/* Body */
.login-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}
.login-card {
  width: 400px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  padding: 40px;
  border-radius: 12px;
  border: 1px solid #00d2ff;
  background: #0d1117;
}
.card-logo-box {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #00d2ff;
  border-radius: 8px;
}
.card-star-icon {
  width: 24px;
  height: 24px;
  color: #05070a;
}
.card-title-group {
  text-align: center;
}
.card-ai-label {
  font-size: 28px;
  font-weight: 700;
  color: #00d2ff;
}
.card-title {
  margin: 12px 0 0;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  color: white;
}
.card-subtitle {
  margin: 20px 0 0;
  font-size: 14px;
  color: #9ca3af;
}
.login-form {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}
.field-input {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 48px;
  padding: 0 16px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
}
.field-icon {
  width: 18px;
  height: 18px;
  color: #00d2ff;
  flex-shrink: 0;
}
.field-input input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-size: 14px;
  color: #484f58;
  font-family: inherit;
}
.field-input input::placeholder {
  color: #484f58;
}
.error-msg {
  font-size: 12px;
  color: #ff6b6b;
  padding: 10px 14px;
  background: rgba(255, 107, 107, 0.1);
  border-radius: 8px;
  border: 1px solid rgba(255, 107, 107, 0.2);
}
.btn-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 48px;
  margin-top: 8px;
  font-size: 14px;
  font-weight: 700;
  font-family: 'Inter', -apple-system, sans-serif;
  background: #00d2ff;
  color: #05070a;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-submit:hover:not(:disabled) {
  box-shadow: 0 0 24px rgba(0, 210, 255, 0.4);
  transform: translateY(-1px);
}
.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-arrow {
  width: 16px;
  height: 16px;
}
.loading-dots span {
  animation: blink 1.4s infinite both;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 80%, 100% { opacity: 0; }
  40% { opacity: 1; }
}
.signup-link {
  font-size: 13px;
}
.text-muted { color: #9ca3af; }
.text-cyan { color: #00d2ff; cursor: pointer; }

/* Footer */
.login-footer {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 12px;
  color: #6b7280;
}
.copyright { color: #6b7280; }
.footer-icons {
  display: flex;
  gap: 12px;
}
.footer-icon {
  width: 16px;
  height: 16px;
}
.footer-lang {
  display: flex;
  align-items: center;
  gap: 4px;
}
.chevron-icon {
  width: 12px;
  height: 12px;
}
</style>
