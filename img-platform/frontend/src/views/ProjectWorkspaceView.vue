<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/services/api'
import GenerateView from './GenerateView.vue'
import CanvasView from './CanvasView.vue'

const route = useRoute()
const router = useRouter()

const conversationId = computed(() => {
  const id = Number(route.params.conversationId)
  return isNaN(id) ? null : id
})

const mode = computed<'chat' | 'canvas'>(() => {
  const m = route.query.mode as string
  return m === 'canvas' ? 'canvas' : 'chat'
})

const projectTitle = ref('')

async function fetchProjectTitle() {
  if (!conversationId.value) return
  try {
    const resp = await api.get(`/api/conversations/${conversationId.value}`)
    projectTitle.value = resp.data?.title || 'New Project'
  } catch {
    projectTitle.value = 'New Project'
  }
}

function switchMode(newMode: 'chat' | 'canvas') {
  router.replace({
    path: `/project/${conversationId.value}`,
    query: { mode: newMode },
  })
}

function goHome() {
  router.push('/')
}

onMounted(() => {
  fetchProjectTitle()
})

watch(conversationId, () => {
  if (conversationId.value) fetchProjectTitle()
})
</script>

<template>
  <div class="workspace-shell">
    <header class="ws-header">
      <button class="ws-back" @click="goHome" title="Back to Home">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
      </button>

      <div class="ws-title-area">
        <h1 class="ws-title">{{ projectTitle || 'New Project' }}</h1>
      </div>

      <div class="ws-mode-tabs">
        <button
          class="ws-mode-btn"
          :class="{ active: mode === 'chat' }"
          @click="switchMode('chat')"
        >
          💬 对话
        </button>
        <button
          class="ws-mode-btn"
          :class="{ active: mode === 'canvas' }"
          @click="switchMode('canvas')"
        >
          ⬡ Canvas
        </button>
      </div>
    </header>

    <main class="ws-content">
      <GenerateView
        v-if="mode === 'chat'"
        :key="String(conversationId)"
        :embedded-conversation-id="conversationId"
        :embedded="true"
      />
      <CanvasView
        v-else
        :key="String(conversationId)"
        embedded
        :embedded-conversation-id="conversationId"
      />
    </main>
  </div>
</template>

<style scoped>
.workspace-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #03060b;
  color: #fff;
  font-family: 'Inter', -apple-system, sans-serif;
}
.ws-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 20px;
  height: 56px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  background: rgba(3, 6, 12, 0.82);
  backdrop-filter: blur(18px);
}
.ws-back {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px;
  background: transparent;
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  flex-shrink: 0;
}
.ws-back:hover { border-color: rgba(255,255,255,0.28); color: #fff; }
.ws-back svg { width: 18px; height: 18px; }

.ws-title-area { flex: 1; min-width: 0; }
.ws-title {
  margin: 0;
  font-size: 16px;
  font-weight: 680;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ws-mode-tabs {
  display: flex;
  gap: 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 8px;
  padding: 3px;
  flex-shrink: 0;
}
.ws-mode-btn {
  height: 34px;
  padding: 0 16px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(255,255,255,0.62);
  font-size: 13px;
  font-weight: 560;
  cursor: pointer;
  white-space: nowrap;
}
.ws-mode-btn.active {
  background: rgba(0, 184, 255, 0.18);
  color: #00d9ff;
}
.ws-mode-btn:hover:not(.active) { color: rgba(255,255,255,0.9); }

.ws-content {
  flex: 1;
  overflow: hidden;
}


</style>
