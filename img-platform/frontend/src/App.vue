<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()

function toggleLocale() {
  const next = locale.value === 'zh' ? 'en' : 'zh'
  locale.value = next
  localStorage.setItem('locale', next)
}
</script>

<template>
  <div class="locale-switch" @click="toggleLocale">
    {{ locale === 'zh' ? 'EN' : '中文' }}
  </div>
  <RouterView />
</template>

<style>
/* Global resets (design system loaded in main.ts) */
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; background: #05070a; color: white; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }

.locale-switch {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 9999;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  color: #00d2ff;
  font-size: 13px;
  font-weight: 500;
  backdrop-filter: blur(8px);
  transition: background 0.2s;
}
.locale-switch:hover {
  background: rgba(0, 210, 255, 0.2);
}
</style>
