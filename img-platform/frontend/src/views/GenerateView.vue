<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
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
  aspect?: string
  style?: string
  loading?: boolean
  taskId?: string
  createdAt: Date
}

interface HistoryItem {
  id: number
  title: string
  type: string
  thumb?: string
  prompt: string
  createdAt: Date
}

// ── State ──────────────────────────────────────────────
const selectedCategory = ref<'image' | 'voice' | 'video' | 'music'>('image')
const selectedModel = ref('image-01')
const selectedStyle = ref('Cinematic')
const selectedAspect = ref('16:9')
const selectedImageCount = ref<1 | 2 | 4>(4)

const messages = ref<Message[]>([])
const inputText = ref('')
const searchText = ref('')
const messagesContainer = ref<HTMLDivElement | null>(null)
const isGenerating = ref(false)
const isOptimizingPrompt = ref(false)
const generationAbortController = ref<AbortController | null>(null)
const convId = ref<number | null>(null)
const previewImageUrl = ref('')

const styles = ['Cinematic', 'Photorealistic', 'Anime', 'Abstract', 'Minimalist']
const aspects = ['1:1', '16:9', '9:16', '4:3', '3:4']
const imageCounts = [1, 2, 4] as const

interface GenerationRecord {
  id: string
  prompt: string
  response?: Message
  type: Message['type']
  results: string[]
  model: string
  aspect: string
  style: string
  loading: boolean
  error: string
  createdAt: Date
}

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

const generationRecords = computed<GenerationRecord[]>(() => {
  const records: GenerationRecord[] = []

  for (let i = 0; i < messages.value.length; i += 1) {
    const msg = messages.value[i]
    if (msg.role !== 'user') continue

    let response: Message | undefined
    for (let j = i + 1; j < messages.value.length; j += 1) {
      if (messages.value[j].role === 'user') break
      if (messages.value[j].role === 'assistant' || messages.value[j].role === 'error') {
        response = messages.value[j]
        break
      }
    }

    records.push({
      id: `${msg.id}-${response?.id || 'pending'}`,
      prompt: msg.content,
      response,
      type: response?.type || selectedCategory.value,
      results: response?.results || [],
      model: response?.model || selectedModel.value,
      aspect: response?.aspect || selectedAspect.value,
      style: response?.style || selectedStyle.value,
      loading: Boolean(response?.loading),
      error: response?.role === 'error' ? response.content : '',
      createdAt: response?.createdAt || msg.createdAt,
    })
  }

  return records.reverse()
})

const filteredGenerationRecords = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return generationRecords.value
  return generationRecords.value.filter(record => {
    return [
      record.prompt,
      record.model,
      record.aspect,
      record.style,
      record.type,
    ].some(value => value.toLowerCase().includes(keyword))
  })
})

const generationCountLabel = computed(() => {
  return `${generationRecords.value.length} 条记录`
})

const projectTitleLabel = computed(() => {
  return conversationTitle.value.trim() || messages.value[0]?.content.slice(0, 42) || '未命名项目'
})

watch(selectedCategory, () => {
  const models = currentModelList.value
  if (models.length && !models.includes(selectedModel.value)) {
    selectedModel.value = models[0]
  }
})

// ── History ─────────────────────────────────────────────
const history = ref<HistoryItem[]>([])

const previewImageName = computed(() => {
  if (!previewImageUrl.value) return ''
  return previewImageUrl.value.split('/').pop()?.split('?')[0] || 'image'
})

function openImagePreview(url: string) {
  previewImageUrl.value = url
}

function closeImagePreview() {
  previewImageUrl.value = ''
}

function imageAspectRatio(aspect: string) {
  const normalized = aspect.match(/^(\d+):(\d+)$/)
  if (!normalized) return '16 / 9'
  return `${normalized[1]} / ${normalized[2]}`
}

function isRequestCanceled(err: any) {
  return err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.message === 'canceled'
}

function markActiveGenerationCanceled() {
  messages.value.forEach(msg => {
    if (msg.loading) {
      msg.loading = false
      msg.role = 'error'
      msg.content = '已取消生成'
    }
  })
}

function cancelGeneration() {
  if (!isGenerating.value) return
  generationAbortController.value?.abort()
  generationAbortController.value = null
  isGenerating.value = false
  markActiveGenerationCanceled()
  ElMessage.info('已取消当前生成')
}

function formatRecordTime(date: Date) {
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  if (sameDay) return `今天 ${time}`
  if (date.toDateString() === yesterday.toDateString()) return `昨天 ${time}`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ` ${time}`
}

function reusePrompt(prompt: string) {
  inputText.value = prompt
  nextTick(scrollToBottom)
}

async function regenerateFromPrompt(prompt: string) {
  if (isGenerating.value || isOptimizingPrompt.value) return
  inputText.value = prompt
  await nextTick()
  await sendMessage()
}

async function createVariation(prompt: string) {
  if (isGenerating.value || isOptimizingPrompt.value) return
  inputText.value = `${prompt}, create a fresh variation with a different composition while preserving the core concept`
  await nextTick()
  await sendMessage()
}

function downloadFile(url: string) {
  const link = document.createElement('a')
  link.href = url
  link.download = url.split('/').pop()?.split('?')[0] || 'generated-image'
  link.target = '_blank'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function downloadAll(urls: string[]) {
  urls.forEach((url, index) => {
    window.setTimeout(() => downloadFile(url), index * 120)
  })
}

function handlePreviewKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeImagePreview()
  }
}

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
    const resp = await api.post('/api/conversations', { title: projectTitleLabel.value })
    convId.value = resp.data.id
    conversationTitle.value = projectTitleLabel.value
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
  const controller = new AbortController()
  generationAbortController.value = controller
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/image/generate', {
      prompt,
      model: selectedModel.value,
      aspect_ratio: selectedAspect.value,
      n: selectedImageCount.value,
      response_format: 'url',
    }, {
      signal: controller.signal,
    })
    const data = resp.data as { image_urls: string[] }
    placeholders.msg.loading = false
    console.log('[sendImage] image_urls:', JSON.stringify(data.image_urls))
    console.log('[sendImage] results count:', (data.image_urls || []).length)
    placeholders.msg.results = data.image_urls || []
    placeholders.msg.type = 'image'
    placeholders.msg.model = selectedModel.value
    placeholders.msg.aspect = selectedAspect.value
    placeholders.msg.style = selectedStyle.value
    await saveAssistantResponse(placeholders.msg)
  } catch (err: any) {
    if (isRequestCanceled(err) || controller.signal.aborted) {
      placeholders.msg.content = '已取消生成'
    } else {
      placeholders.msg.content = err?.response?.data?.detail || err.message || 'Generation failed'
    }
    placeholders.msg.role = 'error'
    placeholders.msg.loading = false
  } finally {
    if (generationAbortController.value === controller) {
      generationAbortController.value = null
    }
    isGenerating.value = false
    scrollToBottom()
  }
}

async function optimizePrompt() {
  const prompt = inputText.value.trim()
  if (!prompt || isGenerating.value || isOptimizingPrompt.value) return

  isOptimizingPrompt.value = true
  try {
    const resp = await api.post('/api/prompt/optimize', {
      prompt,
      model: 'MiniMax-M2.7',
      target: selectedCategory.value,
    })
    const data = resp.data as { optimized_prompt: string }
    if (data.optimized_prompt?.trim()) {
      inputText.value = data.optimized_prompt.trim()
      ElMessage.success('提示词已优化，可继续编辑或直接发送')
      await nextTick()
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || err.message || '提示词优化失败')
  } finally {
    isOptimizingPrompt.value = false
  }
}

async function sendVoice(text: string) {
  const placeholders = createPlaceholder('voice')
  const controller = new AbortController()
  generationAbortController.value = controller
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/voice/generate', {
      text,
      voice_id: 'male-qn-qingse',
      model: selectedModel.value,
    }, {
      signal: controller.signal,
    })
    const data = resp.data as { audio_url: string }
    placeholders.msg.loading = false
    placeholders.msg.results = [data.audio_url]
    placeholders.msg.type = 'voice'
    placeholders.msg.model = selectedModel.value
    await saveAssistantResponse(placeholders.msg)
  } catch (err: any) {
    placeholders.msg.content = isRequestCanceled(err) || controller.signal.aborted
      ? '已取消生成'
      : err?.response?.data?.detail || err.message || 'Voice generation failed'
    placeholders.msg.role = 'error'
    placeholders.msg.loading = false
  } finally {
    if (generationAbortController.value === controller) {
      generationAbortController.value = null
    }
    isGenerating.value = false
    scrollToBottom()
  }
}

async function sendMusic(text: string) {
  const placeholders = createPlaceholder('music')
  const controller = new AbortController()
  generationAbortController.value = controller
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/music/generate', {
      prompt: text,
      model: selectedModel.value,
    }, {
      signal: controller.signal,
    })
    const data = resp.data as { audio_url: string }
    placeholders.msg.loading = false
    placeholders.msg.results = [data.audio_url]
    placeholders.msg.type = 'music'
    placeholders.msg.model = selectedModel.value
    await saveAssistantResponse(placeholders.msg)
  } catch (err: any) {
    placeholders.msg.content = isRequestCanceled(err) || controller.signal.aborted
      ? '已取消生成'
      : err?.response?.data?.detail || err.message || 'Music generation failed'
    placeholders.msg.role = 'error'
    placeholders.msg.loading = false
  } finally {
    if (generationAbortController.value === controller) {
      generationAbortController.value = null
    }
    isGenerating.value = false
    scrollToBottom()
  }
}

async function sendVideo(text: string) {
  const placeholders = createPlaceholder('video')
  const controller = new AbortController()
  generationAbortController.value = controller
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/video/generate', {
      prompt: text,
      model: selectedModel.value,
    }, {
      signal: controller.signal,
    })
    const data = resp.data as { task_id: string }
    placeholders.msg.taskId = data.task_id
    placeholders.msg.loading = true

    // Poll for video completion
    await pollVideoStatus(placeholders.msg, data.task_id, controller.signal)
  } catch (err: any) {
    placeholders.msg.content = isRequestCanceled(err) || controller.signal.aborted
      ? '已取消生成'
      : err?.response?.data?.detail || err.message || 'Video generation failed'
    placeholders.msg.role = 'error'
    placeholders.msg.loading = false
  } finally {
    if (generationAbortController.value === controller) {
      generationAbortController.value = null
    }
    isGenerating.value = false
    scrollToBottom()
  }
}

async function pollVideoStatus(msg: Message, taskId: string, signal?: AbortSignal) {
  const maxAttempts = 30
  for (let i = 0; i < maxAttempts; i++) {
    if (signal?.aborted) {
      throw new DOMException('canceled', 'CanceledError')
    }
    await new Promise(r => setTimeout(r, 3000))
    if (signal?.aborted) {
      throw new DOMException('canceled', 'CanceledError')
    }
    try {
      const resp = await api.get(`/api/video/status/${taskId}`, { signal })
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
      messagesContainer.value.scrollTop = 0
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
  window.addEventListener('keydown', handlePreviewKeydown)

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

onUnmounted(() => {
  window.removeEventListener('keydown', handlePreviewKeydown)
})
</script>

<template>
  <div class="generate-page">
    <header class="topbar">
      <div class="project-brand">
        <svg class="brand-mark" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
        </svg>
        <input
          v-if="isEditingTitle"
          v-model="conversationTitle"
          class="project-title-input"
          placeholder="项目名称..."
          @blur="saveTitleOnBlur"
          @keydown.enter.prevent="saveTitleOnBlur"
          autofocus
        />
        <button v-else class="project-title-button" type="button" @click="startEditTitle" :title="projectTitleLabel">
          <span>{{ projectTitleLabel }}</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
        </button>
      </div>

      <label class="top-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="7"/>
          <path d="M21 21l-4.35-4.35"/>
        </svg>
        <input v-model="searchText" type="search" placeholder="搜索你的生成记录..." />
        <kbd>⌘ K</kbd>
      </label>

      <button class="home-return" type="button" @click="goHome">
        返回主页
      </button>
    </header>

    <div class="workspace">
      <main class="generation-main">
        <section class="feed-header">
          <div>
            <h1>全部生成</h1>
            <span>{{ generationCountLabel }}</span>
          </div>
        </section>

        <section class="records-scroll" ref="messagesContainer">
          <div v-if="filteredGenerationRecords.length === 0" class="empty-state">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
            </svg>
            <h2>{{ searchText ? '没有匹配的生成记录' : '开始一次生成' }}</h2>
            <p>{{ searchText ? '换个关键词试试。' : '底部输入提示词，AI enhance 可先帮你扩写。' }}</p>
            <div v-if="history.length && !searchText" class="history-strip">
              <button v-for="item in history.slice(0, 5)" :key="item.id" type="button" @click="loadFromHistory(item)">
                <img v-if="item.thumb" :src="item.thumb" :alt="item.prompt" />
                <span>{{ item.title || item.prompt || '历史项目' }}</span>
              </button>
            </div>
          </div>

          <article
            v-for="record in filteredGenerationRecords"
            :key="record.id"
            class="record-card"
            :class="{ loading: record.loading, error: Boolean(record.error) }"
          >
            <header class="record-head">
              <div class="record-title-block">
                <p class="record-prompt">{{ record.prompt }}</p>
                <div class="record-meta">
                  <span class="chip model-chip">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
                    </svg>
                    {{ record.model }}
                  </span>
                  <span v-if="record.type === 'image'" class="chip">{{ record.aspect }}</span>
                  <span v-if="record.type === 'image'" class="chip">{{ record.style }}</span>
                  <span class="time-chip">{{ formatRecordTime(record.createdAt) }}</span>
                </div>
              </div>

              <div class="record-actions">
                <button type="button" @click="regenerateFromPrompt(record.prompt)" :disabled="isGenerating || isOptimizingPrompt">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 12a9 9 0 0 1-15.6 6.1"/>
                    <path d="M3 12A9 9 0 0 1 18.6 5.9"/>
                    <path d="M18 2v4h4M6 22v-4H2"/>
                  </svg>
                  重新生成
                </button>
                <button type="button" @click="createVariation(record.prompt)" :disabled="isGenerating || isOptimizingPrompt">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>
                    <path d="M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M18.36 5.64l-2.12 2.12M7.76 16.24l-2.12 2.12"/>
                  </svg>
                  生成变体
                </button>
                <button type="button" @click="downloadAll(record.results)" :disabled="!record.results.length">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <path d="M7 10l5 5 5-5M12 15V3"/>
                  </svg>
                  下载全部
                </button>
                <button class="only-icon" type="button" @click="reusePrompt(record.prompt)" title="复用提示词">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>
                  </svg>
                </button>
              </div>
            </header>

            <div v-if="record.loading" class="record-loading">
              <div class="loading-dots"><span></span><span></span><span></span></div>
              <span>{{ t('generate.generating') }}</span>
              <button class="loading-cancel-btn" type="button" @click="cancelGeneration">
                取消生成
              </button>
            </div>

            <div v-else-if="record.error" class="record-error">
              {{ record.error }}
            </div>

            <div v-else-if="record.type === 'image' && record.results.length" class="record-images">
              <figure v-for="(url, i) in record.results" :key="url" class="generated-tile">
                <button
                  class="image-view-button"
                  type="button"
                  :title="'查看原图 ' + (i + 1)"
                  :style="{ aspectRatio: imageAspectRatio(record.aspect) }"
                  @click="openImagePreview(url)"
                >
                  <img :src="url" :alt="'Generated image ' + (i + 1)" loading="lazy" />
                </button>
                <div class="tile-top-actions">
                  <button type="button" title="收藏">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27z"/>
                    </svg>
                  </button>
                  <button type="button" title="下载" @click="downloadFile(url)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <path d="M7 10l5 5 5-5M12 15V3"/>
                    </svg>
                  </button>
                </div>
                <figcaption>
                  <button type="button" @click="openImagePreview(url)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="11" cy="11" r="7"/>
                      <path d="M21 21l-4.35-4.35"/>
                    </svg>
                    放大
                  </button>
                  <button type="button" @click="createVariation(record.prompt)" :disabled="isGenerating || isOptimizingPrompt">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>
                      <path d="M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12"/>
                    </svg>
                    变体
                  </button>
                  <button type="button" disabled title="暂未接入超分接口">
                    <span>HD</span>
                    Upscale
                  </button>
                  <button type="button" @click="downloadFile(url)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <path d="M7 10l5 5 5-5M12 15V3"/>
                    </svg>
                    下载
                  </button>
                </figcaption>
              </figure>
            </div>

            <div v-else-if="(record.type === 'voice' || record.type === 'music') && record.results.length" class="media-result">
              <audio :src="record.results[0]" controls />
            </div>

            <div v-else-if="record.type === 'video' && record.results.length" class="media-result">
              <video :src="record.results[0]" controls />
            </div>
          </article>
        </section>
      </main>
    </div>

    <form class="composer" @submit.prevent="sendMessage">
      <div class="composer-input">
        <button class="upload-btn" type="button" title="添加参考图">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="5" width="18" height="14" rx="2"/>
            <circle cx="8.5" cy="10.5" r="1.5"/>
            <path d="M21 15l-5-5L5 21"/>
          </svg>
        </button>
        <textarea
          v-model="inputText"
          class="prompt-textarea"
          placeholder="描述你想要生成的图像..."
          rows="1"
          @keydown.enter.exact.prevent="sendMessage"
        ></textarea>
        <button
          class="optimize-btn"
          type="button"
          title="AI enhance：扩写并优化提示词"
          @click="optimizePrompt"
          :disabled="!inputText.trim() || isGenerating || isOptimizingPrompt"
        >
          <span v-if="isOptimizingPrompt" class="mini-spinner"></span>
          <span v-else>AI enhance</span>
        </button>
      </div>

      <div class="composer-controls">
        <select v-model="selectedCategory" class="param-select">
          <option value="image">{{ t('generate.categoryImage') }}</option>
          <option value="voice">{{ t('generate.categoryVoice') }}</option>
          <option value="video">{{ t('generate.categoryVideo') }}</option>
          <option value="music">{{ t('generate.categoryMusic') }}</option>
        </select>
        <select v-if="selectedCategory === 'image'" v-model="selectedStyle" class="param-select">
          <option v-for="s in styles" :key="s" :value="s">风格 {{ s }}</option>
        </select>
        <select v-if="selectedCategory === 'image'" v-model="selectedAspect" class="param-select">
          <option v-for="a in aspects" :key="a" :value="a">宽高比 {{ a }}</option>
        </select>
        <div v-if="selectedCategory === 'image'" class="count-toggle" aria-label="生成数量">
          <button
            v-for="count in imageCounts"
            :key="count"
            type="button"
            :class="{ active: selectedImageCount === count }"
            @click="selectedImageCount = count"
          >
            {{ count }}x
          </button>
        </div>
        <select v-model="selectedModel" class="param-select">
          <option v-for="m in currentModelList" :key="m" :value="m">模型 {{ m }}</option>
        </select>
        <button class="control-icon" type="button" title="高级参数">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/>
            <path d="M1 14h6M9 8h6M17 16h6"/>
          </svg>
        </button>
        <button
          v-if="isGenerating"
          class="cancel-generate-btn"
          type="button"
          @click="cancelGeneration"
        >
          取消生成
        </button>
        <button
          v-else
          class="generate-btn"
          type="submit"
          :disabled="!inputText.trim() || isOptimizingPrompt"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          </svg>
          生成
        </button>
      </div>
    </form>

    <Teleport to="body">
      <div v-if="previewImageUrl" class="image-preview-overlay" @click.self="closeImagePreview">
        <div class="image-preview-toolbar">
          <span class="image-preview-title">{{ previewImageName }}</span>
          <button class="image-preview-close" type="button" title="关闭预览" @click="closeImagePreview">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <img :src="previewImageUrl" :alt="previewImageName" class="image-preview-full" />
      </div>
    </Teleport>
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

.image-thumb-button {
  position: relative;
  display: block;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: zoom-in;
  text-align: left;
}

.result-image {
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
  object-fit: cover;
  transition: transform 0.15s;
  display: block;
}

.image-thumb-button:hover .result-image {
  transform: scale(1.02);
}

.image-thumb-button:focus-visible {
  outline: 2px solid rgba(0,217,255,0.75);
  outline-offset: 3px;
  border-radius: 12px;
}

.result-model {
  font-size: 11px;
  color: rgba(0,217,255,0.5);
}

.image-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 64px 28px 32px;
  background: rgba(3, 6, 12, 0.88);
  backdrop-filter: blur(12px);
}

.image-preview-toolbar {
  position: fixed;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: min(760px, calc(100vw - 32px));
  min-height: 40px;
  padding: 6px 8px 6px 14px;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 10px;
  background: rgba(10,10,15,0.82);
  box-shadow: 0 12px 40px rgba(0,0,0,0.35);
}

.image-preview-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: rgba(255,255,255,0.78);
}

.image-preview-close {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 8px;
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.72);
  cursor: pointer;
}

.image-preview-close:hover {
  background: rgba(255,255,255,0.14);
  color: #fff;
}

.image-preview-close svg {
  width: 16px;
  height: 16px;
}

.image-preview-full {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 10px;
  box-shadow: 0 20px 80px rgba(0,0,0,0.48);
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

.optimize-btn {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(0,217,255,0.24);
  border-radius: 9px;
  background: rgba(0,217,255,0.08);
  color: #00d9ff;
  font-size: 11px;
  font-weight: 750;
  cursor: pointer;
  transition: all 0.2s;
}

.optimize-btn:hover:not(:disabled) {
  background: rgba(0,217,255,0.14);
  border-color: rgba(0,217,255,0.4);
  box-shadow: 0 0 14px rgba(0,217,255,0.18);
}

.optimize-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.mini-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0,217,255,0.24);
  border-top-color: #00d9ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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

/* ── Reference-style Generate Workspace ───────────────── */
.generate-page {
  min-height: 100vh;
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at 24% 0%, rgba(0, 217, 255, 0.08), transparent 34%),
    radial-gradient(circle at 82% 22%, rgba(97, 116, 255, 0.05), transparent 30%),
    #05080d;
  color: #f8fafc;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.topbar {
  height: 68px;
  min-height: 68px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 0 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(5, 8, 13, 0.78);
  backdrop-filter: blur(18px);
  z-index: 30;
}

.project-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  width: 330px;
  min-width: 0;
  color: #fff;
  z-index: 2;
}

.brand-mark {
  width: 25px;
  height: 25px;
  color: #19c9ff;
  filter: drop-shadow(0 0 10px rgba(25, 201, 255, 0.45));
  flex-shrink: 0;
}

.project-title-button {
  min-width: 0;
  height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #fff;
  cursor: text;
  font: inherit;
  font-size: 16px;
  font-weight: 760;
  letter-spacing: 0;
}

.project-title-button:hover {
  border-color: rgba(148, 163, 184, 0.14);
  background: rgba(255,255,255,0.035);
}

.project-title-button span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-title-button svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: rgba(226, 232, 240, 0.45);
}

.project-title-input {
  width: min(280px, calc(100vw - 180px));
  height: 42px;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 10px;
  outline: 0;
  background: rgba(8, 12, 20, 0.86);
  color: #e2e8f0;
  font: inherit;
  font-size: 15px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
}

.project-title-input:focus {
  border-color: rgba(25, 201, 255, 0.42);
  box-shadow: 0 0 0 3px rgba(25, 201, 255, 0.08);
}

.top-search {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  width: min(520px, calc(100vw - 760px));
  min-width: 360px;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: rgba(8, 12, 20, 0.82);
  color: rgba(226, 232, 240, 0.55);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
}

.top-search svg {
  width: 17px;
  height: 17px;
  flex-shrink: 0;
}

.top-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: #e2e8f0;
  font: inherit;
  font-size: 13px;
}

.top-search input::placeholder {
  color: rgba(226, 232, 240, 0.42);
}

.top-search kbd {
  height: 22px;
  min-width: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 6px;
  color: rgba(226, 232, 240, 0.46);
  font-size: 11px;
  font-family: inherit;
}

.home-return {
  z-index: 2;
  height: 40px;
  min-width: 108px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
  border: 1px solid rgba(25, 201, 255, 0.24);
  border-radius: 8px;
  background: rgba(25, 201, 255, 0.08);
  color: #35d7ff;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 720;
}

.home-return:hover {
  border-color: rgba(25, 201, 255, 0.42);
  background: rgba(25, 201, 255, 0.14);
  color: #fff;
}

.workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  position: relative;
}

.rail {
  width: 82px;
  min-width: 82px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 18px 12px 14px;
  border-right: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(4, 8, 14, 0.72);
}

.rail-actions,
.rail-bottom {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 14px;
}

.rail-item {
  width: 58px;
  min-height: 54px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: rgba(226, 232, 240, 0.66);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.rail-item svg {
  width: 21px;
  height: 21px;
}

.rail-item:hover {
  background: rgba(255,255,255,0.04);
  color: #fff;
}

.rail-item.active {
  color: #10d7ff;
  border-color: rgba(16, 215, 255, 0.2);
  background: rgba(16, 215, 255, 0.08);
  box-shadow: inset 0 0 0 1px rgba(16, 215, 255, 0.03);
}

.storage-meter {
  width: 58px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: rgba(226, 232, 240, 0.56);
  font-size: 10px;
  line-height: 1.25;
}

.storage-meter strong {
  color: rgba(226, 232, 240, 0.78);
  font-size: 10px;
  font-weight: 600;
}

.storage-meter small {
  color: rgba(226, 232, 240, 0.48);
  font-size: 10px;
}

.storage-meter i {
  display: block;
  width: 40px;
  height: 4px;
  margin-top: 5px;
  border-radius: 999px;
  background: linear-gradient(90deg, #19c9ff 36%, rgba(148, 163, 184, 0.18) 36%);
}

.generation-main {
  flex: 1;
  min-width: 0;
  width: min(100%, 1680px);
  display: flex;
  flex-direction: column;
  margin: 0 auto;
  padding: 18px 24px 16px;
}

.feed-header {
  min-height: 36px;
  display: flex;
  align-items: flex-end;
  justify-content: flex-start;
  gap: 18px;
  margin-bottom: 14px;
}

.feed-header h1 {
  margin: 0;
  font-size: 18px;
  line-height: 1;
  font-weight: 760;
  letter-spacing: 0;
}

.feed-header span {
  margin-left: 10px;
  color: rgba(226, 232, 240, 0.42);
  font-size: 13px;
}

.records-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0 2px 10px 0;
  overscroll-behavior: contain;
}

.records-scroll::-webkit-scrollbar {
  width: 5px;
}

.records-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.16);
}

.empty-state {
  flex: 1;
  min-height: 400px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: rgba(226, 232, 240, 0.48);
}

.empty-state svg {
  width: 48px;
  height: 48px;
  color: rgba(25, 201, 255, 0.22);
}

.empty-state h2 {
  margin: 14px 0 7px;
  font-size: 18px;
  color: rgba(248, 250, 252, 0.9);
}

.empty-state p {
  margin: 0;
  font-size: 13px;
}

.history-strip {
  width: min(760px, 100%);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
  margin-top: 22px;
}

.history-strip button {
  min-width: 0;
  height: 74px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.44);
  color: rgba(226, 232, 240, 0.72);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  text-align: left;
}

.history-strip img {
  width: 56px;
  height: 56px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}

.history-strip span {
  min-width: 0;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.record-card {
  flex: 0 0 auto;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.11);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(20, 28, 40, 0.78), rgba(10, 15, 24, 0.72)),
    rgba(8, 12, 20, 0.8);
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.22);
}

.record-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 18px 10px;
}

.record-title-block {
  min-width: 0;
  flex: 1;
}

.record-prompt {
  margin: 0 0 8px;
  color: rgba(248, 250, 252, 0.96);
  font-size: 13px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.record-meta,
.record-actions,
.tile-top-actions,
.generated-tile figcaption,
.composer-controls {
  display: flex;
  align-items: center;
}

.record-meta {
  gap: 8px;
  flex-wrap: wrap;
}

.chip,
.time-chip {
  height: 22px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 9px;
  border-radius: 7px;
  background: rgba(255,255,255,0.045);
  color: rgba(226, 232, 240, 0.55);
  font-size: 11px;
  line-height: 1;
}

.model-chip {
  color: #c4a6ff;
  background: rgba(124, 58, 237, 0.12);
}

.model-chip svg {
  width: 12px;
  height: 12px;
}

.time-chip {
  background: transparent;
  padding-inline: 0;
}

.record-actions {
  gap: 8px;
  flex-shrink: 0;
}

.record-actions button,
.generated-tile figcaption button,
.tile-top-actions button,
.control-icon,
.upload-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(148, 163, 184, 0.11);
  background: rgba(15, 23, 42, 0.5);
  color: rgba(226, 232, 240, 0.78);
  cursor: pointer;
  font: inherit;
}

.record-actions button {
  height: 34px;
  gap: 7px;
  padding: 0 12px;
  border-radius: 7px;
  font-size: 12px;
}

.record-actions button svg {
  width: 15px;
  height: 15px;
}

.record-actions .only-icon {
  width: 34px;
  padding: 0;
}

.record-actions button:hover:not(:disabled),
.generated-tile figcaption button:hover:not(:disabled),
.tile-top-actions button:hover,
.control-icon:hover,
.upload-btn:hover {
  color: #fff;
  border-color: rgba(25, 201, 255, 0.25);
  background: rgba(25, 201, 255, 0.08);
}

.record-actions button:disabled,
.generated-tile figcaption button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.record-images {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
  padding: 0 18px 16px;
}

.generated-tile {
  position: relative;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  border-radius: 8px;
  background: rgba(7, 12, 20, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.image-view-button {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: rgba(2, 6, 12, 0.42);
  cursor: zoom-in;
  overflow: hidden;
}

.image-view-button:focus-visible {
  outline: 2px solid rgba(25, 201, 255, 0.78);
  outline-offset: -2px;
}

.image-view-button img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
}

.tile-top-actions {
  position: absolute;
  top: 8px;
  right: 8px;
  gap: 5px;
  padding: 4px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.28);
  backdrop-filter: blur(10px);
}

.tile-top-actions button {
  width: 25px;
  height: 25px;
  border: 0;
  border-radius: 7px;
  color: rgba(255,255,255,0.88);
  background: rgba(255,255,255,0.14);
}

.tile-top-actions svg {
  width: 14px;
  height: 14px;
}

.generated-tile figcaption {
  justify-content: space-between;
  gap: 6px;
  min-height: 38px;
  padding: 6px 8px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(7, 12, 20, 0.92);
}

.generated-tile figcaption button {
  height: 24px;
  gap: 4px;
  padding: 0 6px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: rgba(255,255,255,0.88);
  font-size: 11px;
}

.generated-tile figcaption svg {
  width: 13px;
  height: 13px;
}

.generated-tile figcaption span {
  font-size: 9px;
  border: 1px solid currentColor;
  border-radius: 3px;
  padding: 0 2px;
}

.record-loading,
.record-error {
  min-height: clamp(220px, 24vh, 320px);
  margin: 0 18px 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(15, 23, 42, 0.35);
  color: rgba(226, 232, 240, 0.62);
  font-size: 13px;
}

.loading-cancel-btn {
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 12px;
  border: 1px solid rgba(248, 113, 113, 0.26);
  border-radius: 8px;
  background: rgba(127, 29, 29, 0.18);
  color: #fca5a5;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
}

.loading-cancel-btn:hover {
  border-color: rgba(248, 113, 113, 0.42);
  background: rgba(127, 29, 29, 0.28);
  color: #fff;
}

.record-error {
  color: #ff7a7a;
  border-color: rgba(255, 122, 122, 0.22);
  background: rgba(127, 29, 29, 0.12);
}

.media-result {
  padding: 0 18px 16px;
}

.media-result audio,
.media-result video {
  width: 100%;
  max-height: 360px;
  border-radius: 8px;
}

.composer {
  position: relative;
  width: min(1360px, calc(100vw - 96px));
  flex-shrink: 0;
  margin: 0 auto 18px;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px 13px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(19, 28, 40, 0.94), rgba(9, 14, 23, 0.96)),
    rgba(8, 12, 20, 0.96);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.38);
  backdrop-filter: blur(18px);
}

.composer-input {
  display: flex;
  align-items: center;
  gap: 12px;
}

.upload-btn {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 8px;
}

.upload-btn svg,
.control-icon svg {
  width: 17px;
  height: 17px;
}

.composer .prompt-textarea {
  flex: 1;
  min-height: 34px;
  max-height: 92px;
  padding: 7px 0;
  border: 0;
  outline: 0;
  resize: none;
  background: transparent;
  color: #f8fafc;
  font: inherit;
  font-size: 13px;
  line-height: 1.45;
}

.composer .prompt-textarea::placeholder {
  color: rgba(226, 232, 240, 0.4);
}

.composer .optimize-btn {
  width: auto;
  min-width: 98px;
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid rgba(168, 85, 247, 0.24);
  background: rgba(124, 58, 237, 0.12);
  color: #d9c2ff;
  font-size: 12px;
  font-weight: 720;
}

.composer .optimize-btn:hover:not(:disabled) {
  border-color: rgba(168, 85, 247, 0.42);
  background: rgba(124, 58, 237, 0.2);
  box-shadow: 0 0 18px rgba(124, 58, 237, 0.18);
}

.composer-controls {
  gap: 10px;
  flex-wrap: wrap;
}

.composer .param-select {
  flex: 0 1 180px;
  min-width: 142px;
  height: 38px;
  padding: 0 36px 0 14px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(9, 14, 23, 0.72);
  color: rgba(226, 232, 240, 0.78);
  outline: 0;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.count-toggle {
  height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(9, 14, 23, 0.72);
}

.count-toggle button {
  width: 42px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(226, 232, 240, 0.58);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
}

.count-toggle button:hover {
  color: #fff;
  background: rgba(255,255,255,0.06);
}

.count-toggle button.active {
  color: #07131d;
  background: linear-gradient(135deg, #19d3ff, #44a8ff);
}

.composer .param-select option {
  background: #0b1220;
  color: #fff;
}

.control-icon {
  width: 38px;
  height: 38px;
  margin-left: auto;
  border-radius: 8px;
}

.generate-btn,
.cancel-generate-btn {
  min-width: 132px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  margin-left: 8px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, #19d3ff, #078cff);
  color: #00131f;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 760;
  box-shadow: 0 10px 28px rgba(8, 140, 255, 0.24);
}

.cancel-generate-btn {
  background: linear-gradient(135deg, #fb7185, #ef4444);
  color: #fff;
  box-shadow: 0 10px 28px rgba(239, 68, 68, 0.22);
}

.generate-btn svg {
  width: 16px;
  height: 16px;
}

.generate-btn:hover:not(:disabled) {
  box-shadow: 0 12px 34px rgba(8, 140, 255, 0.34);
}

.cancel-generate-btn:hover {
  box-shadow: 0 12px 34px rgba(239, 68, 68, 0.34);
}

.generate-btn:disabled,
.composer .optimize-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 1040px) {
  .topbar {
    padding-inline: 16px;
  }

  .project-brand {
    width: 260px;
  }

  .top-search {
    width: min(420px, calc(100vw - 460px));
    min-width: 280px;
  }

  .record-images {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .record-head {
    flex-direction: column;
    align-items: stretch;
  }

  .record-actions {
    overflow-x: auto;
    padding-bottom: 2px;
  }
}

@media (max-width: 760px) {
  .topbar {
    height: auto;
    min-height: 64px;
    padding: 12px 14px;
  }

  .top-search {
    display: none;
  }

  .project-brand {
    width: min(100%, 260px);
  }

  .home-return {
    min-width: 88px;
    padding-inline: 12px;
  }

  .generation-main {
    padding: 16px 12px 16px;
  }

  .records-scroll {
    padding-bottom: 8px;
  }

  .feed-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .record-images {
    grid-template-columns: 1fr;
  }

  .record-prompt {
    white-space: normal;
  }

  .generated-tile {
    aspect-ratio: auto;
  }

  .image-view-button img {
    width: 100%;
    height: 100%;
  }

  .composer {
    width: calc(100vw - 20px);
    margin-bottom: 10px;
  }

  .composer .param-select {
    flex: 1 1 140px;
    min-width: 0;
  }

  .control-icon {
    margin-left: 0;
  }

  .generate-btn {
    flex: 1 1 100%;
    margin-left: 0;
  }
}
</style>
