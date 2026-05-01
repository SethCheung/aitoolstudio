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
    <!-- AI 图片网格背景 -->
    <div class="bg-gallery">
      <div class="gallery-grid">
        <div v-for="i in 16" :key="i" class="gallery-item">
          <div class="gallery-img" :style="{ backgroundPosition: `${(i % 4) * 25}% ${Math.floor(i / 4) * 25}%` }"></div>
        </div>
      </div>
      <div class="bg-overlay"></div>
    </div>

    <!-- 顶部导航栏 -->
    <header class="top-nav">
      <div class="nav-left">
        <svg class="nav-logo-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          <path d="M5 3L5.75 6L8 6.75L5.75 7.5L5 10.5L4.25 7.5L2 6.75L4.25 6L5 3Z" opacity="0.6"/>
          <path d="M19 3L19.75 6L22 6.75L19.75 7.5L19 10.5L18.25 7.5L16 6.75L18.25 6L19 3Z" opacity="0.6"/>
          <path d="M5 14L5.75 17L8 17.75L5.75 18.5L5 21.5L4.25 18.5L2 17.75L4.25 17L5 14Z" opacity="0.6"/>
          <path d="M19 14L19.75 17L22 17.75L19.75 18.5L19 21.5L18.25 18.5L16 17.75L18.25 17L19 14Z" opacity="0.6"/>
        </svg>
        <span class="nav-brand">AI Image Generator</span>
      </div>
      <nav class="nav-links">
        <a href="#features" class="nav-link">Features</a>
        <a href="#pricing" class="nav-link">Pricing</a>
        <a href="#docs" class="nav-link">Docs</a>
        <a href="#gallery" class="nav-link">Gallery</a>
      </nav>
      <div class="nav-right">
        <a href="#signin" class="btn-signin">Sign In</a>
      </div>
    </header>

    <!-- 登录卡片 -->
    <div class="login-card">
      <svg class="card-logo" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
        <path d="M5 3L5.75 6L8 6.75L5.75 7.5L5 10.5L4.25 7.5L2 6.75L4.25 6L5 3Z" opacity="0.6"/>
        <path d="M19 3L19.75 6L22 6.75L19.75 7.5L19 10.5L18.25 7.5L16 6.75L18.25 6L19 3Z" opacity="0.6"/>
        <path d="M5 14L5.75 17L8 17.75L5.75 18.5L5 21.5L4.25 18.5L2 17.75L4.25 17L5 14Z" opacity="0.6"/>
        <path d="M19 14L19.75 17L22 17.75L19.75 18.5L19 21.5L18.25 18.5L16 17.75L18.25 17L19 14Z" opacity="0.6"/>
      </svg>
      <h1 class="login-title">AI Image Generator</h1>
      <p class="login-subtitle">Transform ideas into stunning visuals</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <div class="input-wrapper">
            <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <input
              v-model="username"
              type="text"
              class="form-input"
              placeholder="Enter your username"
              autocomplete="username"
            />
          </div>
        </div>

        <div class="form-group">
          <div class="input-wrapper">
            <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <input
              v-model="password"
              type="password"
              class="form-input"
              placeholder="Enter your password"
              autocomplete="current-password"
            />
          </div>
        </div>

        <div v-if="auth.error" class="error-msg">{{ auth.error }}</div>

        <button type="submit" class="login-btn" :disabled="isLoading">
          <span v-if="!isLoading">Sign In</span>
          <span v-else class="loading-dots">Signing in<span>.</span><span>.</span><span>.</span></span>
          <svg v-if="!isLoading" class="btn-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
      </form>

      <p class="signup-link">Don't have an account? <a href="#signup">Sign up</a></p>
    </div>

    <!-- 底部页脚 -->
    <footer class="footer">
      <div class="footer-left">
        <span class="copyright">© 2024 AI Image Generator</span>
        <a href="#terms" class="footer-link">Terms of Service</a>
        <a href="#privacy" class="footer-link">Privacy Policy</a>
      </div>
      <div class="footer-right">
        <div class="social-icons">
          <a href="#discord" class="social-icon" aria-label="Discord">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
            </svg>
          </a>
          <a href="#x" class="social-icon" aria-label="X">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
          </a>
          <a href="#github" class="social-icon" aria-label="GitHub">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
            </svg>
          </a>
          <a href="#globe" class="social-icon" aria-label="Language">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
          </a>
        </div>
        <select class="lang-select">
          <option value="en">English</option>
          <option value="zh">中文</option>
        </select>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* ── 页面容器 ─────────────────────────────────── */
.login-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0a0a0f;
  position: relative;
  overflow: hidden;
}

/* ── AI 图片网格背景 ────────────────────────────── */
.bg-gallery {
  position: absolute;
  inset: 0;
  z-index: 0;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: repeat(4, 1fr);
  gap: 4px;
  padding: 4px;
  height: 100%;
  opacity: 0.4;
}

.gallery-item {
  overflow: hidden;
  border-radius: 4px;
}

.gallery-img {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, 
    #1a1a2e 0%, 
    #16213e 25%, 
    #0f3460 50%, 
    #1a1a2e 75%, 
    #16213e 100%
  );
  background-size: 400% 400%;
  animation: galleryShift 20s ease infinite;
}

.gallery-item:nth-child(1) .gallery-img { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.gallery-item:nth-child(2) .gallery-img { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.gallery-item:nth-child(3) .gallery-img { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
.gallery-item:nth-child(4) .gallery-img { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); }
.gallery-item:nth-child(5) .gallery-img { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
.gallery-item:nth-child(6) .gallery-img { background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); }
.gallery-item:nth-child(7) .gallery-img { background: linear-gradient(135deg, #d299c2 0%, #fef9d7 100%); }
.gallery-item:nth-child(8) .gallery-img { background: linear-gradient(135deg, #89f7fe 0%, #66a6ff 100%); }
.gallery-item:nth-child(9) .gallery-img { background: linear-gradient(135deg, #fddb92 0%, #d1fdff 100%); }
.gallery-item:nth-child(10) .gallery-img { background: linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%); }
.gallery-item:nth-child(11) .gallery-img { background: linear-gradient(135deg, #f68084 0%, #a60b68 100%); }
.gallery-item:nth-child(12) .gallery-img { background: linear-gradient(135deg, #96e6a1 0%, #d4fc79 100%); }
.gallery-item:nth-child(13) .gallery-img { background: linear-gradient(135deg, #ee9ca7 0%, #ffdde1 100%); }
.gallery-item:nth-child(14) .gallery-img { background: linear-gradient(135deg, #bdc3c7 0%, #2c3e50 100%); }
.gallery-item:nth-child(15) .gallery-img { background: linear-gradient(135deg, #0ba360 0%, #3cba92 100%); }
.gallery-item:nth-child(16) .gallery-img { background: linear-gradient(135deg, #00d2ff 0%, #3a7bd5 100%); }

@keyframes galleryShift {
  0%, 100% { filter: hue-rotate(0deg) brightness(0.7); }
  50% { filter: hue-rotate(30deg) brightness(0.9); }
}

.bg-overlay {
  position: absolute;
  inset: 0;
  background: rgba(10, 10, 15, 0.75);
  backdrop-filter: blur(2px);
}

/* ── 顶部导航栏 ────────────────────────────────── */
.top-nav {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 32px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-logo-icon {
  width: 28px;
  height: 28px;
  color: #00d9ff;
  filter: drop-shadow(0 0 8px rgba(0, 217, 255, 0.5));
}

.nav-brand {
  font-size: 15px;
  font-weight: 600;
  color: #ffffff;
  letter-spacing: -0.3px;
}

.nav-links {
  display: flex;
  gap: 32px;
}

.nav-link {
  font-size: 13px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.6);
  text-decoration: none;
  transition: color 0.2s;
}

.nav-link:hover {
  color: #ffffff;
}

.nav-right {
  display: flex;
  align-items: center;
}

.btn-signin {
  font-size: 13px;
  font-weight: 500;
  color: #00d9ff;
  text-decoration: none;
  padding: 8px 16px;
  border: 1px solid rgba(0, 217, 255, 0.4);
  border-radius: 8px;
  transition: all 0.2s;
}

.btn-signin:hover {
  background: rgba(0, 217, 255, 0.1);
  border-color: #00d9ff;
}

/* ── 登录卡片 ──────────────────────────────────── */
.login-card {
  position: relative;
  z-index: 10;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

.card-logo {
  width: 48px;
  height: 48px;
  color: #00d9ff;
  margin-bottom: 16px;
  filter: drop-shadow(0 0 12px rgba(0, 217, 255, 0.6));
}

.login-title {
  font-size: 26px;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 8px;
  letter-spacing: -0.5px;
}

.login-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.5);
  margin-bottom: 32px;
}

.login-card-inner {
  width: 100%;
  max-width: 380px;
  padding: 32px;
  background: rgba(15, 15, 20, 0.85);
  border: 1px solid rgba(0, 217, 255, 0.3);
  border-radius: 16px;
  box-shadow: 
    0 0 40px rgba(0, 217, 255, 0.15),
    0 8px 32px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(20px);
}

/* ── 表单 ─────────────────────────────────────── */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
}

.input-wrapper {
  position: relative;
}

.input-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: rgba(255, 255, 255, 0.3);
  pointer-events: none;
}

.form-input {
  width: 100%;
  padding: 12px 14px 12px 42px;
  font-size: 14px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #ffffff;
  outline: none;
  transition: all 0.2s;
}

.form-input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.form-input:focus {
  border-color: rgba(0, 217, 255, 0.6);
  background: rgba(0, 217, 255, 0.05);
  box-shadow: 0 0 0 3px rgba(0, 217, 255, 0.1);
}

/* ── 错误提示 ─────────────────────────────────── */
.error-msg {
  font-size: 12px;
  color: #ff6b6b;
  padding: 10px 14px;
  background: rgba(255, 107, 107, 0.1);
  border-radius: 8px;
  border: 1px solid rgba(255, 107, 107, 0.2);
}

/* ── 登录按钮 ─────────────────────────────────── */
.login-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 13px;
  margin-top: 8px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: linear-gradient(135deg, #00d9ff 0%, #00b4d8 100%);
  color: #000000;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.login-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #00e6ff 0%, #00c4e8 100%);
  box-shadow: 0 0 24px rgba(0, 217, 255, 0.4);
  transform: translateY(-1px);
}

.login-btn:active:not(:disabled) {
  transform: translateY(0);
}

.login-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-arrow {
  width: 18px;
  height: 18px;
  transition: transform 0.2s;
}

.login-btn:hover .btn-arrow {
  transform: translateX(3px);
}

/* ── Loading 动画 ─────────────────────────────── */
.loading-dots span {
  animation: blink 1.4s infinite both;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0; }
  40% { opacity: 1; }
}

/* ── 注册链接 ─────────────────────────────────── */
.signup-link {
  margin-top: 24px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.5);
  text-align: center;
}

.signup-link a {
  color: #00d9ff;
  text-decoration: none;
  font-weight: 500;
  transition: color 0.2s;
}

.signup-link a:hover {
  color: #00e6ff;
  text-decoration: underline;
}

/* ── 底部页脚 ─────────────────────────────────── */
.footer {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 32px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.copyright {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
}

.footer-link {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  text-decoration: none;
  transition: color 0.2s;
}

.footer-link:hover {
  color: rgba(255, 255, 255, 0.7);
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.social-icons {
  display: flex;
  gap: 12px;
}

.social-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: rgba(255, 255, 255, 0.4);
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  transition: all 0.2s;
}

.social-icon svg {
  width: 16px;
  height: 16px;
}

.social-icon:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.1);
}

.lang-select {
  padding: 6px 10px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  outline: none;
  cursor: pointer;
  transition: all 0.2s;
}

.lang-select:hover {
  border-color: rgba(255, 255, 255, 0.2);
}

.lang-select option {
  background: #1a1a2e;
  color: #ffffff;
}

/* ── 响应式 ───────────────────────────────────── */
@media (max-width: 768px) {
  .nav-links {
    display: none;
  }
  
  .top-nav {
    padding: 12px 20px;
  }
  
  .footer {
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  
  .footer-left {
    flex-wrap: wrap;
    justify-content: center;
    gap: 12px;
  }
}
</style>
