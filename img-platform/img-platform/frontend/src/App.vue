<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <RouterView />
</template>

<style>
/* Global resets (design system loaded in main.ts) */
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; background: #05070a; color: white; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
</style>
