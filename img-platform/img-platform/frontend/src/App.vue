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
  top: 12px;
  right: 12px;
  z-index: 9999;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  color: #a0a8b0;
  transition: all 0.2s;
  user-select: none;
}
.locale-switch:hover {
  background: rgba(255,255,255,0.15);
  color: #fff;
}
</style>
