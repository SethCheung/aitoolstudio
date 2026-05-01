<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const isLoggedIn = computed(() => auth.isLoggedIn)
const isLoginPage = computed(() => route.name === 'login')

const navItems = [
  { name: 'home', label: '首页', path: '/' },
  { name: 'generate', label: '生图', path: '/generate' },
  { name: 'history', label: '历史', path: '/history' },
]

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-root">
    <!-- 登录页不需要导航栏 -->
    <template v-if="!isLoginPage && isLoggedIn">
      <!-- 顶部导航栏 -->
      <nav class="top-nav">
        <div class="nav-brand">
          <span class="brand-text">AI Studio</span>
        </div>

        <div class="nav-links">
          <router-link
            v-for="item in navItems"
            :key="item.name"
            :to="item.path"
            class="nav-link"
            :class="{ active: route.name === item.name }"
          >
            {{ item.label }}
          </router-link>
        </div>

        <div class="nav-right">
          <router-link to="/admin" class="nav-link" :class="{ active: route.name === 'admin' }">
            后台
          </router-link>
          <div class="nav-user">
            <span class="user-name">{{ auth.user?.username }}</span>
            <button class="logout-btn" @click="logout">退出</button>
          </div>
        </div>
      </nav>

      <!-- 顶部装饰条 -->
      <div class="top-accent-bar"></div>
    </template>

    <!-- 页面内容 -->
    <RouterView />
  </div>
</template>

<style scoped>
.app-root {
  min-height: 100vh;
  background: #00070d;
}

/* ── 顶部导航栏 ─────────────────────────────── */
.top-nav {
  height: 52px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  background: #00070d;
  border-bottom: 1px solid #21262d;
  gap: 8px;
}

.nav-brand {
  margin-right: 12px;
}

.brand-text {
  font-size: 14px;
  font-weight: 700;
  color: #e6edf3;
  letter-spacing: -0.3px;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
}

.nav-link {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 500;
  color: #8b949e;
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.15s;
}
.nav-link:hover {
  background: #161b22;
  color: #e6edf3;
}
.nav-link.active {
  background: rgba(0, 212, 242, 0.1);
  color: #00d4f2;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-left: 12px;
  border-left: 1px solid #21262d;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: #e6edf3;
}

.logout-btn {
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  font-family: 'Inter', sans-serif;
  background: transparent;
  color: #8b949e;
  border: 1px solid #21262d;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
}
.logout-btn:hover {
  background: #161b22;
  color: #e6edf3;
  border-color: #30363d;
}

/* ── 顶部强调条 ─────────────────────────────── */
.top-accent-bar {
  height: 2px;
  background: linear-gradient(90deg, #00d4f2 0%, transparent 100%);
}
</style>
