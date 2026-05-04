<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// ── Types ───────────────────────────────────────────────
interface Message {
  id: string
  role: 'user' | 'assistant' | 'error'
  type: 'text' | 'image' | 'voice' | 'video' | 'music'
  content: string
  results?: string[]
  model?: string
  loading?: boolean
  taskId?: string
  createdAt: Date
}

interface HistoryItem {
  id: number
  title: string
  type: string
  thumb?: string
  prompt?: string
  createdAt: Date
}

// ── State ──────────────────────────────────────────────
const selectedCategory = ref<'image' | 'voice' | 'video' | 'music'>('image')
const selectedModel = ref('image-01')
const selectedStyle = ref('Cinematic')
const selectedAspect = ref('16:9')

const messages = ref<Message[]>([])
const inputText = ref('')
const messagesContainer = ref<HTMLDivElement | null>(null)
const isGenerating = ref(false)
const convId = ref<number | null>(null)

const styles = ['Cinematic', 'Photorealistic', 'Anime', 'Abstract', 'Minimalist']
const aspects = ['1:1', '16:9', '9:16', '4:3', '3:4']

// ── Models ─────────────────────────────────────────────
interface AvailableModels {
  image?: string[] | Record<string, string[]>
  voice?: string[] | Record<string, string[]>
  video?: string[] | Record<string, string[]>
  music?: string[] | Record<string, string[]>
}
const availableModels = ref<AvailableModels>({})

function modelNamesFor(category: keyof AvailableModels): string[] {
  const models = availableModels.value[category]
  if (!models) return []
  return Array.isArray(models) ? models : Object.keys(models)
}

const currentModelList = computed(() => {
  return modelNamesFor(selectedCategory.value as keyof AvailableModels)
})

watch(selectedCategory, () => {
  const models = currentModelList.value
  if (models.length && !models.includes(selectedModel.value)) {
    selectedModel.value = models[0]
  }
})

// ── History ─────────────────────────────────────────────
const history = ref<HistoryItem[]>([])

async function loadHistory() {
  try {
    const resp = await api.get('/api/conversations')
    const data = Array.isArray(resp.data) ? resp.data : []
    history.value = data.map((item: any) => ({
      id: item.id,
      title: item.title || 'New Conversation',
      type: item.type || 'image',
      thumb: item.thumb || '',
      prompt: item.prompt || '',
      createdAt: new Date(item.created_at),
    }))
  } catch (e) {
    console.warn('Failed to load history', e)
  }
}

// ── State ────────────────────────────────────────────────
const conversationTitle = ref('')
const isEditingTitle = ref(false)

function startEditTitle() {
  isEditingTitle.value = true
}

async function saveTitleOnBlur() {
  isEditingTitle.value = false
  if (!conversationTitle.value.trim()) {
    conversationTitle.value = '未命名项目'
    return
  }
  try {
    await ensureConversation()
    await api.patch(`/api/conversations/${convId.value}`, {
      title: conversationTitle.value.trim()
    })
  } catch (e) {
    console.error('Title save failed', e)
  }
}

// ── Send ───────────────────────────────────────────────
async function ensureConversation() {
  if (!convId.value) {
    const resp = await api.post('/api/conversations', { title: 'New Conversation' })
    convId.value = resp.data.id
    conversationTitle.value = 'New Conversation'
  }
  return convId.value
}

async function saveMessages() {
  if (!convId.value) return
  const payload = {
    role: messages.value[messages.value.length - 1].role,
    type: messages.value[messages.value.length - 1].type,
    content: messages.value[messages.value.length - 1].content,
    results: JSON.stringify(messages.value[messages.value.length - 1].results || []),
    model: messages.value[messages.value.length - 1].model,
  }
  try {
    await api.post(`/api/conversations/${convId.value}/messages`, payload)
    await api.patch(`/api/conversations/${convId.value}`, { title: messages.value[0]?.content.slice(0, 50) || 'New Conversation' })
  } catch (e) {
    console.warn('Failed to save messages', e)
  }
}

async function sendMessage() {
  if (!inputText.value.trim() || isGenerating.value) return
  const text = inputText.value.trim()
  inputText.value = ''

  await ensureConversation()

  const userMsg: Message = {
    id: `user-${Date.now()}`,
    role: 'user',
    type: 'text',
    content: text,
    createdAt: new Date(),
  }
  messages.value.push(userMsg)
  await saveMessages()
  scrollToBottom()

  if (selectedCategory.value === 'image') {
    await sendImage(text)
  } else if (selectedCategory.value === 'voice') {
    await sendVoice(text)
  } else if (selectedCategory.value === 'music') {
    await sendMusic(text)
  } else if (selectedCategory.value === 'video') {
    await sendVideo(text)
  }
}

async function sendImage(prompt: string) {
  const placeholders = createPlaceholder('image')
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/image/generate', {
      prompt,
      model: selectedModel.value,
      aspect_ratio: selectedAspect.value,
      n: 4,
      response_format: 'url',
    })
    const data = resp.data as { image_urls: string[] }
    placeholders.msg.loading = false
    console.log('[sendImage] image_urls:', JSON.stringify(data.image_urls))
    console.log('[sendImage] results count:', (data.image_urls || []).length)
    placeholders.msg.results = data.image_urls || []
    placeholders.msg.type = 'image'
    placeholders.msg.model = selectedModel.value
    await saveAssistantResponse(placeholders.msg)
  } catch (err: any) {
    placeholders.msg.role = 'error'
    placeholders.msg.content = err?.response?.data?.detail || err.message || 'Generation failed'
    placeholders.msg.loading = false
  } finally {
    isGenerating.value = false
    scrollToBottom()
  }
}

async function sendVoice(text: string) {
  const placeholders = createPlaceholder('voice')
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/voice/generate', {
      text,
      voice_id: 'male-qn-qingse',
      model: selectedModel.value,
    })
    const data = resp.data as { audio_url: string }
    placeholders.msg.loading = false
    placeholders.msg.results = [data.audio_url]
    placeholders.msg.type = 'voice'
    placeholders.msg.model = selectedModel.value
    await saveAssistantResponse(placeholders.msg)
  } catch (err: any) {
    placeholders.msg.role = 'error'
    placeholders.msg.content = err?.response?.data?.detail || err.message || 'Voice generation failed'
    placeholders.msg.loading = false
  } finally {
    isGenerating.value = false
    scrollToBottom()
  }
}

async function sendMusic(text: string) {
  const placeholders = createPlaceholder('music')
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/music/generate', {
      prompt: text,
      model: selectedModel.value,
    })
    const data = resp.data as { audio_url: string }
    placeholders.msg.loading = false
    placeholders.msg.results = [data.audio_url]
    placeholders.msg.type = 'music'
    placeholders.msg.model = selectedModel.value
    await saveAssistantResponse(placeholders.msg)
  } catch (err: any) {
    placeholders.msg.role = 'error'
    placeholders.msg.content = err?.response?.data?.detail || err.message || 'Music generation failed'
    placeholders.msg.loading = false
  } finally {
    isGenerating.value = false
    scrollToBottom()
  }
}

async function sendVideo(text: string) {
  const placeholders = createPlaceholder('video')
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/video/generate', {
      prompt: text,
      model: selectedModel.value,
    })
    const data = resp.data as { task_id: string }
    placeholders.msg.taskId = data.task_id
    placeholders.msg.loading = true

    // Poll for video completion
    await pollVideoStatus(placeholders.msg, data.task_id)
  } catch (err: any) {
    placeholders.msg.role = 'error'
    placeholders.msg.content = err?.response?.data?.detail || err.message || 'Video generation failed'
    placeholders.msg.loading = false
  } finally {
    isGenerating.value = false
    scrollToBottom()
  }
}

async function pollVideoStatus(msg: Message, taskId: string) {
  const maxAttempts = 30
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 3000))
    try {
      const resp = await api.get(`/api/video/status/${taskId}`)
      const data = resp.data as { status: string; video_url?: string }
      if (data.video_url) {
        msg.loading = false
        msg.results = [data.video_url]
        msg.type = 'video'
        await saveAssistantResponse(msg)
        return
      }
    } catch (e) {
      // Continue polling
    }
  }
  msg.role = 'error'
  msg.loading = false
  msg.content = 'Video generation timed out'
}

function createPlaceholder(type: Message['type']): { msg: Message } {
  return {
    msg: {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      type,
      content: '',
      loading: true,
      createdAt: new Date(),
    },
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// ── History click ──────────────────────────────────────
async function loadFromHistory(item: HistoryItem) {
  try {
    const resp = await api.get(`/api/conversations/${item.id}`)
    const data = resp.data
    convId.value = data.id
    conversationTitle.value = data.title || ''
    isEditingTitle.value = false
    messages.value = data.messages.map((m: any) => ({
      id: String(m.id),
      role: m.role,
      type: m.type,
      content: m.content,
      results: m.results || [],
      model: m.model,
      loading: false,
      createdAt: new Date(m.created_at),
    }))
  } catch (e) {
    ElMessage.error('Failed to load conversation')
  }
}

async function newConversation() {
  messages.value = []
  convId.value = null
  conversationTitle.value = ''
  isEditingTitle.value = false
}

async function goHome() {
  await router.push('/')
}

async function saveAssistantResponse(msg: Message) {
  if (!convId.value) return
  const payload = {
    role: msg.role,
    type: msg.type,
    content: msg.content,
    results: JSON.stringify(msg.results || []),
    model: msg.model,
    task_id: msg.taskId,
  }
  try {
    await api.post(`/api/conversations/${convId.value}/messages`, payload)
    await api.patch(`/api/conversations/${convId.value}`, { title: messages.value[0]?.content.slice(0, 50) || 'New Conversation' })
    await loadHistory()
  } catch (e) {
    console.warn('Failed to save assistant response', e)
  }
}

// ── Init ──────────────────────────────────────────────
onMounted(async () => {
  // Load models
  try {
    console.log('[GenerateView] fetching /profiles/models...')
    const resp = await api.get('/api/profiles/models')
    console.log('[GenerateView] models raw resp:', resp)
    console.log('[GenerateView] models resp.data:', resp.data)
    availableModels.value = resp.data as AvailableModels
    console.log('[GenerateView] models loaded:', availableModels.value)
    const preferred: Array<keyof AvailableModels> = ['image', 'voice', 'music', 'video']
    const firstCat = preferred.find(c => modelNamesFor(c).length)
    if (firstCat) {
      selectedCategory.value = firstCat as typeof selectedCategory.value
      selectedModel.value = modelNamesFor(firstCat)[0]
      console.log('[GenerateView] default category:', firstCat, 'model:', selectedModel.value)
    }
  } catch (e) {
    console.warn('Failed to load models', e)
  }

  // Load history list
  await loadHistory()

  // If URL has ?convId=, load that conversation
  const convIdParam = route.query.convId
  if (convIdParam) {
    const id = Number(convIdParam)
    const item = history.value.find(h => h.id === id)
    if (item) {
      await loadFromHistory(item)
    }
  }
})
</script>

<template>
  <div class="chat-page">
    <!-- Left Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-top">
        <!-- Brand + Editable Title -->
        <div class="brand-row">
          <svg class="brand-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          </svg>
          <div class="brand-title-group">
            <span class="brand-name">{{ t('generate.brand') }}</span>
            <div class="project-name-row">
              <input
                v-if="isEditingTitle"
                v-model="conversationTitle"
                class="title-edit-input"
                placeholder="项目名称..."
                @blur="saveTitleOnBlur"
                @keydown.enter.prevent="saveTitleOnBlur"
                autofocus
              />
              <span
                v-else
                class="project-name-display"
                @click="startEditTitle"
                :title="conversationTitle || '点击编辑项目名称'"
              >
                {{ conversationTitle || '未命名项目' }}
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="edit-icon">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </span>
            </div>
          </div>
          <div class="brand-actions">
            <button class="action-btn home-btn" @click.stop="goHome" title="返回主页">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9 22 9 12 15 12 15 22"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Category Tabs -->
      <div class="sidebar-section">
        <span class="section-label">{{ t('generate.category') }}</span>
        <div class="category-tabs">
          <button
            v-for="cat in ['image', 'voice', 'video', 'music'] as const"
            :key="cat"
            class="cat-tab"
            :class="{ active: selectedCategory === cat }"
            @click="selectedCategory = cat"
          >
            <span class="cat-icon">{{ cat === 'image' ? '🖼' : cat === 'voice' ? '🎙' : cat === 'video' ? '🎬' : '🎵' }}</span>
            <span>{{ t(`generate.category${cat.charAt(0).toUpperCase() + cat.slice(1)}`) }}</span>
          </button>
        </div>
      </div>

      <!-- History -->
      <div class="sidebar-section history-section">
        <span class="section-label">History</span>
        <div class="history-list" v-if="history.length">
          <button
            v-for="item in history"
            :key="item.id"
            class="history-item"
            @click="loadFromHistory(item)"
          >
            <div class="history-thumb" v-if="item.thumb">
              <img :src="item.thumb" :alt="item.prompt" />
            </div>
            <div class="history-thumb placeholder" v-else>
              <span>{{ item.type.charAt(0).toUpperCase() }}</span>
            </div>
            <div class="history-info">
              <span class="history-prompt">{{ item.prompt.slice(0, 40) }}{{ item.prompt.length > 40 ? '...' : '' }}</span>
              <span class="history-type">{{ item.type }}</span>
            </div>
          </button>
        </div>
        <div class="history-empty" v-else>
          <span>{{ t('generate.noHistory') }}</span>
        </div>
      </div>

      <!-- User -->
      <div class="sidebar-bottom">
        <div class="user-info">
          <div class="user-avatar">A</div>
          <div class="user-details">
            <span class="user-name">admin</span>
            <span class="user-plan">{{ t('generate.proPlan') }}</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Chat Area -->
    <main class="chat-main">
      <!-- Messages -->
      <div class="messages-container" ref="messagesContainer">
        <div v-if="messages.length === 0" class="chat-empty">
          <svg viewBox="0 0 24 24" fill="currentColor" width="48" height="48" style="color: rgba(0,217,255,0.2)">
            <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          </svg>
          <p>{{ t('generate.chatPlaceholder') }}</p>
        </div>

        <div
          v-for="msg in messages"
          :key="msg.id"
          class="message-wrapper"
          :class="msg.role"
        >
          <!-- User message -->
          <div v-if="msg.role === 'user'" class="message user-msg">
            <div class="msg-bubble">
              {{ msg.content }}
            </div>
          </div>

          <!-- Assistant / Error message -->
          <div v-else class="message assistant-msg" :class="{ error: msg.role === 'error' }">
            <div class="msg-avatar">
              <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
                <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
              </svg>
            </div>
            <div class="msg-content">
              <!-- Loading -->
              <div v-if="msg.loading" class="msg-loading">
                <div class="loading-dots"><span></span><span></span><span></span></div>
                <span class="loading-text">{{ t('generate.generating') }}</span>
              </div>

              <!-- Error -->
              <div v-else-if="msg.role === 'error'" class="msg-error">
                {{ msg.content }}
              </div>

              <!-- Image results -->
              <div v-else-if="msg.type === 'image' && msg.results?.length" class="msg-images">
                <div class="images-grid" :class="msg.results.length === 1 ? 'single' : 'multi'">
                  <div
                    v-for="(url, i) in msg.results"
                    :key="url"
                    style="position:relative"
                  >
                    <img
                      :src="url + '?cache=' + Date.now()"
                      class="result-image"
                      :alt="'Generated image ' + (i+1)"
                      loading="lazy"
                    />
                    <span style="position:absolute;top:4px;left:4px;font-size:10px;background:rgba(0,0,0,0.6);color:#fff;padding:2px 6px;border-radius:4px">
                      {{ i+1 }}. {{ url.split('/').pop()?.split('?')[0] }}
                    </span>
                  </div>
                </div>
                <span class="result-model">{{ msg.model }}</span>
              </div>

              <!-- Voice result -->
              <div v-else-if="msg.type === 'voice' && msg.results?.length" class="msg-audio">
                <audio :src="msg.results[0]" controls class="audio-player" />
                <span class="result-model">{{ msg.model }}</span>
              </div>

              <!-- Music result -->
              <div v-else-if="msg.type === 'music' && msg.results?.length" class="msg-audio">
                <audio :src="msg.results[0]" controls class="audio-player" />
                <span class="result-model">{{ msg.model }}</span>
              </div>

              <!-- Video result -->
              <div v-else-if="msg.type === 'video' && msg.results?.length" class="msg-video">
                <video
                  :src="msg.results[0]"
                  controls
                  class="video-player"
                />
                <span class="result-model">{{ msg.model }}</span>
              </div>

              <!-- Text-only (no results) -->
              <div v-else-if="msg.content" class="msg-text">
                {{ msg.content }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input Bar -->
      <div class="input-bar">
        <div class="input-row">
          <select v-model="selectedCategory" class="param-select" @change="selectedCategory = selectedCategory">
            <option value="image">{{ t('generate.categoryImage') }}</option>
            <option value="voice">{{ t('generate.categoryVoice') }}</option>
            <option value="video">{{ t('generate.categoryVideo') }}</option>
            <option value="music">{{ t('generate.categoryMusic') }}</option>
          </select>
          <select v-model="selectedModel" class="param-select">
            <option v-for="m in currentModelList" :key="m" :value="m">{{ m }}</option>
          </select>
          <select v-if="selectedCategory === 'image'" v-model="selectedStyle" class="param-select">
            <option v-for="s in styles" :key="s" :value="s">{{ s }}</option>
          </select>
          <select v-if="selectedCategory === 'image'" v-model="selectedAspect" class="param-select">
            <option v-for="a in aspects" :key="a" :value="a">{{ a }}</option>
          </select>
        </div>
        <div class="input-box">
          <textarea
            v-model="inputText"
            class="prompt-textarea"
            :placeholder="t('generate.chatPlaceholder')"
            rows="1"
            @keydown.enter.exact.prevent="sendMessage"
          ></textarea>
          <button
            class="send-btn"
            @click="sendMessage"
            :disabled="!inputText.trim() || isGenerating"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
          </button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.chat-page {
  height: 100vh;
  display: flex;
  overflow: hidden;
  background: #0a0a0f;
  color: white;
  font-family: 'Inter', -apple-system, sans-serif;
}

/* ── Sidebar ─────────────────────────────── */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #0d0d14;
  border-right: 1px solid rgba(255,255,255,0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 10;
}

.sidebar-top {
  padding: 14px 14px 10px;
}

.brand-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-icon {
  width: 22px;
  height: 22px;
  color: #00d9ff;
  filter: drop-shadow(0 0 5px rgba(0,217,255,0.5));
  flex-shrink: 0;
}

.brand-title-group {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.brand-name {
  font-size: 10px;
  font-weight: 500;
  color: rgba(255,255,255,0.35);
}

.project-name-row {
  display: flex;
  align-items: center;
}

.project-name-display {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  transition: background 0.15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
}

.project-name-display:hover {
  background: rgba(255,255,255,0.06);
}

.edit-icon {
  width: 12px;
  height: 12px;
  color: rgba(255,255,255,0.3);
  flex-shrink: 0;
}

.title-edit-input {
  width: 100%;
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(0,210,255,0.35);
  border-radius: 6px;
  color: #fff;
  font-size: 13px;
  font-family: 'Inter', sans-serif;
  padding: 4px 8px;
  outline: none;
}

.brand-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.5);
}

.action-btn:hover {
  background: rgba(255,255,255,0.1);
  color: #fff;
  border-color: rgba(255,255,255,0.2);
}

.home-btn:hover {
  background: rgba(0,217,255,0.1);
  color: #00d9ff;
  border-color: rgba(0,217,255,0.25);
}

.sidebar-section {
  padding: 10px 14px;
}

.section-label {
  display: block;
  font-size: 9px;
  font-weight: 600;
  color: rgba(255,255,255,0.25);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  margin-bottom: 8px;
}

.category-tabs {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cat-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  font-size: 12px;
  font-family: 'Inter', sans-serif;
  color: rgba(255,255,255,0.55);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.cat-tab:hover {
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.85);
}

.cat-tab.active {
  background: rgba(0,217,255,0.1);
  border-color: rgba(0,217,255,0.25);
  color: #00d9ff;
}

.cat-icon {
  font-size: 14px;
}

/* History */
.history-section {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.history-list::-webkit-scrollbar { width: 3px; }
.history-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.05);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.history-item:hover {
  background: rgba(255,255,255,0.04);
  border-color: rgba(0,217,255,0.2);
}

.history-thumb {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: rgba(255,255,255,0.05);
}

.history-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.history-thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: rgba(255,255,255,0.3);
}

.history-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-prompt {
  font-size: 10px;
  color: rgba(255,255,255,0.6);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-type {
  font-size: 9px;
  color: rgba(0,217,255,0.5);
  text-transform: capitalize;
}

.history-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: rgba(255,255,255,0.2);
}

.sidebar-bottom {
  padding: 10px 14px;
  border-top: 1px solid rgba(255,255,255,0.06);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6b21a8, #a855f7);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.user-details {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.user-name {
  font-size: 11px;
  font-weight: 600;
  color: #fff;
}

.user-plan {
  font-size: 9px;
  color: #a855f7;
}

/* ── Chat Main ─────────────────────────────── */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px 100px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.messages-container::-webkit-scrollbar { width: 4px; }
.messages-container::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: rgba(255,255,255,0.3);
  font-size: 14px;
}

/* ── Messages ─────────────────────────────── */
.message-wrapper {
  display: flex;
  flex-direction: column;
  max-width: 80%;
}

.message-wrapper.user {
  align-self: flex-end;
  align-items: flex-end;
}

.message-wrapper.assistant,
.message-wrapper.error {
  align-self: flex-start;
  align-items: flex-start;
}

.msg-bubble {
  padding: 10px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.5;
  background: rgba(0,217,255,0.15);
  border: 1px solid rgba(0,217,255,0.2);
  color: rgba(255,255,255,0.9);
  max-width: 100%;
  word-break: break-word;
}

.assistant-msg {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.msg-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(0,217,255,0.2), rgba(0,180,216,0.1));
  border: 1px solid rgba(0,217,255,0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #00d9ff;
  flex-shrink: 0;
}

.msg-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.msg-text {
  padding: 10px 16px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  font-size: 14px;
  color: rgba(255,255,255,0.8);
  max-width: 100%;
  word-break: break-word;
}

.msg-error {
  padding: 10px 16px;
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.2);
  border-radius: 16px;
  font-size: 14px;
  color: #ef4444;
}

/* Loading */
.msg-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 16px;
  width: fit-content;
}

.loading-dots {
  display: flex;
  gap: 4px;
}

.loading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #00d9ff;
  animation: dotBounce 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.loading-text {
  font-size: 13px;
  color: rgba(255,255,255,0.5);
}

/* Images */
.images-grid {
  display: grid;
  gap: 8px;
}

.images-grid.single {
  grid-template-columns: 1fr;
  max-width: 400px;
}

.images-grid.multi {
  grid-template-columns: repeat(2, 1fr);
  max-width: 500px;
}

.result-image {
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
  object-fit: cover;
  cursor: pointer;
  transition: transform 0.15s;
}

.result-image:hover {
  transform: scale(1.02);
}

.result-model {
  font-size: 11px;
  color: rgba(0,217,255,0.5);
}

/* Audio */
.audio-player {
  width: 300px;
  max-width: 100%;
  height: 36px;
  border-radius: 8px;
}

/* Video */
.video-player {
  width: 480px;
  max-width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
}

/* ── Input Bar ─────────────────────────────── */
.input-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(10,10,15,0.97);
  backdrop-filter: blur(16px);
  border-top: 1px solid rgba(255,255,255,0.08);
  padding: 12px 20px 16px;
  z-index: 20;
}

.input-row {
  display: flex;
  gap: 6px;
}

.param-select {
  flex: 1;
  padding: 5px 8px;
  font-size: 11px;
  font-family: 'Inter', sans-serif;
  color: rgba(255,255,255,0.6);
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 7px;
  outline: none;
  cursor: pointer;
}

.param-select option {
  background: #1a1a2e;
  color: #fff;
}

.input-box {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px;
  padding: 8px 8px 8px 16px;
  transition: border-color 0.2s;
}

.input-box:focus-within {
  border-color: rgba(0,217,255,0.4);
}

.prompt-textarea {
  flex: 1;
  font-size: 13px;
  font-family: 'Inter', sans-serif;
  color: #fff;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  line-height: 1.5;
  max-height: 100px;
}

.prompt-textarea::placeholder {
  color: rgba(255,255,255,0.3);
}

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  background: linear-gradient(135deg, #00d9ff, #00b4d8);
  border: none;
  border-radius: 50%;
  color: #000;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  box-shadow: 0 0 16px rgba(0,217,255,0.5);
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
