<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  embedded?: boolean
  embeddedConversationId?: number | null
}>()

const route = useRoute()
import {
  speechAudioFormats,
  speechBitrates,
  speechEmotions,
  speechInterjections,
  speechLanguageBoosts,
  speechSampleRates,
  speechVoiceEffects,
  speechVoices,
} from '@/lib/speech-options'
import {
  musicAudioFormats,
  musicBitrates,
  musicOutputFormats,
  musicSampleRates,
  musicStructureTags,
  musicTemplates,
} from '@/lib/music-options'

const router = useRouter()
const { t } = useI18n()
const auth = useAuthStore()

// ── Types ───────────────────────────────────────────────
type GenerationCategory = 'image' | 'voice' | 'video' | 'music'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'error'
  type: 'text' | GenerationCategory
  content: string
  results?: string[]
  model?: string
  aspect?: string
  style?: string
  loading?: boolean
  taskId?: string
  progressStartedAt?: number
  progressTargetSeconds?: number
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

interface ImageReferenceItem {
  id: string
  name: string
  src: string
}

interface VideoReferenceItem {
  id: string
  name: string
  src: string
}

interface ComfyWorkflow {
  id: string
  name: string
  description?: string
  notes?: string
  category: string
  enabled: boolean
  workflow_json?: Record<string, unknown>
}

// ── State ──────────────────────────────────────────────
const selectedCategory = ref<GenerationCategory>('image')
const selectedModel = ref('comfyui-local')
const selectedStyle = ref('默认')
const selectedAspect = ref('16:9')
const selectedImageCount = ref(4)
const useCustomImageSize = ref(false)
const imageWidth = ref(1024)
const imageHeight = ref(1024)
const imageSeed = ref<number | null>(null)
const comfyuiSteps = ref(28)
const comfyuiCfg = ref(7)
const comfyuiDenoise = ref(1)
const imagePromptOptimizer = ref(false)
const imageAigcWatermark = ref(false)
const imageStyleWeight = ref(0.8)
const imageReferenceItems = ref<ImageReferenceItem[]>([])
const imageReferenceUrl = ref('')
const inpaintMode = ref<'paint' | 'click'>('paint')
const samClickX = ref<number | null>(null)
const samClickY = ref<number | null>(null)
const autoMaskUrl = ref('')
const isAutoMasking = ref(false)
const maskCanvas = ref<HTMLCanvasElement | null>(null)
const isPaintingMask = ref(false)
const maskHasPaint = ref(false)
const comfyStatus = ref<'unknown' | 'online' | 'offline'>('unknown')
const comfyDeviceName = ref('')
const comfyVramUsedGb = ref(0)
const comfyVramTotalGb = ref(0)
const comfyVramPercent = ref(0)
const comfyTorchUsedGb = ref(0)
const comfyWorkflows = ref<ComfyWorkflow[]>([])
const selectedComfyWorkflow = ref('')
const selectedVideoComfyWorkflow = ref('')
const selectedVoiceId = ref('male-qn-qingse')
const customVoiceId = ref('')
const useCustomVoice = ref(false)
const selectedEmotion = ref('auto')
const voiceSpeed = ref(1)
const voiceVolume = ref(1)
const voicePitch = ref(0)
const audioFormat = ref('mp3')
const sampleRate = ref(32000)
const bitrate = ref(128000)
const audioChannel = ref<1 | 2>(1)
const subtitleEnabled = ref(false)
const latexReadEnabled = ref(false)
const languageBoost = ref('')
const pronunciationToneInput = ref('')
const voiceEffectPitch = ref(0)
const voiceEffectIntensity = ref(0)
const voiceEffectTimbre = ref(0)
const voiceEffect = ref('')
const musicLyrics = ref('')
const musicInstrumental = ref(false)
const musicLyricsOptimizer = ref(false)
const musicAudioFormat = ref('mp3')
const musicOutputFormat = ref('hex')
const musicSampleRate = ref(44100)
const musicBitrate = ref(256000)
const musicSeed = ref<number | null>(null)
const musicAigcWatermark = ref(false)
const musicReferenceAudioUrl = ref('')
const videoMode = ref<'text' | 'image' | 'start-end' | 'subject'>('text')
const videoDuration = ref(6)
const videoResolution = ref('768P')
const videoPromptOptimizer = ref(true)
const videoFastPretreatment = ref(false)
const videoFirstFrameUrl = ref('')
const videoLastFrameUrl = ref('')
const videoSubjectUrl = ref('')
const videoSubjectReferences = ref<VideoReferenceItem[]>([])

const messages = ref<Message[]>([])
const inputText = ref('')
const searchText = ref('')
const messagesContainer = ref<HTMLDivElement | null>(null)
const promptTextarea = ref<HTMLTextAreaElement | null>(null)
const musicLyricsTextarea = ref<HTMLTextAreaElement | null>(null)
const imageReferenceInput = ref<HTMLInputElement | null>(null)
const isGenerating = ref(false)
const isOptimizingPrompt = ref(false)
const generationProgressNow = ref(Date.now())
const generationAbortController = ref<AbortController | null>(null)
const convId = ref<number | null>(null)
const previewImageUrl = ref('')
const upscalingUrls = ref<Set<string>>(new Set())
let comfyStatusTimer: ReturnType<typeof window.setInterval> | null = null
let generationProgressTimer: ReturnType<typeof window.setInterval> | null = null

const styles = ['默认', '漫画', '元气', '中世纪', '水彩']
const aspects = ['1:1', '16:9', '4:3', '3:2', '2:3', '3:4', '9:16', '21:9']
const imageCounts = [1, 2, 3, 4] as const
const videoModes = [
  { id: 'text', label: '文生视频' },
  { id: 'image', label: '首帧图生视频' },
  { id: 'start-end', label: '首尾帧' },
  { id: 'subject', label: '主体参考' },
] as const
const videoDurations = [6, 10] as const
const videoResolutions = ['512P', '768P', '1080P'] as const

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
  progressStartedAt: number
  progressTargetSeconds: number
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
      progressStartedAt: response?.progressStartedAt || response?.createdAt.getTime() || msg.createdAt.getTime(),
      progressTargetSeconds: response?.progressTargetSeconds || estimateGenerationSeconds(response?.type || selectedCategory.value),
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

const composerPlaceholder = computed(() => {
  if (selectedCategory.value === 'voice') return '输入要合成的文本...'
  if (selectedCategory.value === 'music') return '描述你想要生成的音乐...'
  if (selectedCategory.value === 'video') return '描述你想要生成的视频...'
  return '描述你想要生成的图像...'
})

const optimizePromptTitle = computed(() => {
  if (selectedCategory.value === 'voice') return 'AI enhance：优化语音朗读文本'
  if (selectedCategory.value === 'music') return 'AI enhance：优化音乐风格描述'
  if (selectedCategory.value === 'video') return 'AI enhance：优化视频生成提示词'
  return 'AI enhance：优化图像生成提示词'
})

const optimizePromptSuccessLabel = computed(() => {
  if (selectedCategory.value === 'voice') return '语音文本'
  if (selectedCategory.value === 'music') return '音乐提示词'
  if (selectedCategory.value === 'video') return '视频提示词'
  return '图像提示词'
})

const activeVoiceId = computed(() => {
  return useCustomVoice.value ? customVoiceId.value.trim() : selectedVoiceId.value
})

const pronunciationTones = computed(() => {
  return pronunciationToneInput.value
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
})

const canSubmitGeneration = computed(() => {
  if (isOptimizingPrompt.value) return false
  if (isLocalComfyVideo.value && !selectedVideoComfyWorkflow.value) return false
  if (selectedCategory.value === 'image') {
    if (!inputText.value.trim()) return false
    if (localComfyNeedsSourceImage.value && imageReferenceItems.value.length < 1) return false
    if (localComfyUsesClickMask.value && inpaintMode.value === 'paint' && !maskHasPaint.value) return false
    if (localComfyUsesClickMask.value && inpaintMode.value === 'click' && (!autoMaskUrl.value || isAutoMasking.value)) return false
    if (!localComfyUsesClickMask.value && localComfyNeedsMaskImage.value && imageReferenceItems.value.length < 2) return false
    return true
  }
  if (inputText.value.trim()) return true
  if (selectedCategory.value === 'video') {
    return Boolean(videoFirstFrameUrl.value || videoLastFrameUrl.value || videoSubjectReferences.value.length)
  }
  if (selectedCategory.value !== 'music') return false
  return Boolean(musicLyrics.value.trim() || musicLyricsOptimizer.value)
})

const activeImageReferenceCount = computed(() => imageReferenceItems.value.length)
const activeVideoReferenceCount = computed(() => {
  const frameCount = Number(Boolean(videoFirstFrameUrl.value)) + Number(Boolean(videoLastFrameUrl.value))
  return frameCount + videoSubjectReferences.value.length
})
const isLocalComfyUI = computed(() => selectedCategory.value === 'image' && selectedModel.value === 'comfyui-local')
const isLocalComfyVideo = computed(() => selectedCategory.value === 'video' && selectedModel.value === 'comfyui-local-video')
const isLocalComfyActive = computed(() => isLocalComfyUI.value || isLocalComfyVideo.value)
const imageComfyWorkflows = computed(() => comfyWorkflows.value.filter(workflow => workflow.category === 'image'))
const videoComfyWorkflows = computed(() => comfyWorkflows.value.filter(workflow => workflow.category === 'video'))
const selectedImageComfyWorkflow = computed(() => imageComfyWorkflows.value.find(workflow => workflow.id === selectedComfyWorkflow.value))
const selectedImageComfyWorkflowText = computed(() => {
  const workflow = selectedImageComfyWorkflow.value
  if (!workflow) return ''
  return [
    workflow.name,
    workflow.description || '',
    workflow.notes || '',
    JSON.stringify(workflow.workflow_json || {}),
  ].join(' ')
})
const localComfyNeedsSourceImage = computed(() => isLocalComfyUI.value && /\{\{(?:source_|input_)?image\}\}/i.test(selectedImageComfyWorkflowText.value))
const localComfyNeedsMaskImage = computed(() => isLocalComfyUI.value && /\{\{(?:sam_)?mask(?:_image)?\}\}/i.test(selectedImageComfyWorkflowText.value))
const localComfyUsesClickMask = computed(() => localComfyNeedsSourceImage.value && localComfyNeedsMaskImage.value)
const localComfyAllowsImageReference = computed(() => localComfyNeedsSourceImage.value || localComfyNeedsMaskImage.value)
const maxImageReferences = computed(() => {
  if (!isLocalComfyUI.value) return 4
  if (localComfyUsesClickMask.value) return 1
  if (localComfyNeedsMaskImage.value) return 2
  if (localComfyNeedsSourceImage.value) return 1
  return 0
})
const imageReferenceUrlPlaceholder = computed(() => {
  if (localComfyUsesClickMask.value) return '粘贴原图 URL，添加后直接涂抹要重绘的位置'
  if (localComfyNeedsMaskImage.value) return '第 1 张填原图，第 2 张填遮罩图 URL'
  if (localComfyNeedsSourceImage.value) return '粘贴原图 URL，或把图片直接拖进对话框'
  return '粘贴参考图 URL，或把图片直接拖进对话框'
})
const comfyVramLabel = computed(() => {
  if (!comfyVramTotalGb.value) return 'VRAM --'
  return `VRAM ${comfyVramUsedGb.value.toFixed(1)} / ${comfyVramTotalGb.value.toFixed(1)} GB · ${comfyVramPercent.value}%`
})

watch(selectedCategory, () => {
  const models = currentModelList.value
  if (models.length && !models.includes(selectedModel.value)) {
    if (selectedCategory.value === 'image' && models.includes('comfyui-local')) {
      selectedModel.value = 'comfyui-local'
    } else {
      selectedModel.value = models[0]
    }
  }
  if (selectedCategory.value !== 'image') {
    imageReferenceUrl.value = ''
  }
  if (selectedCategory.value !== 'video') {
    videoSubjectUrl.value = ''
  }
})

watch(selectedImageCount, value => {
  if (!Number.isFinite(value)) {
    selectedImageCount.value = 1
    return
  }
  const normalized = Math.min(9, Math.max(1, Math.round(value)))
  if (normalized !== value) {
    selectedImageCount.value = normalized
  }
})

watch(selectedComfyWorkflow, () => {
  samClickX.value = null
  samClickY.value = null
  autoMaskUrl.value = ''
  isAutoMasking.value = false
  clearPaintMask()
  if (isLocalComfyUI.value && !localComfyAllowsImageReference.value) {
    imageReferenceItems.value = []
  } else if (isLocalComfyUI.value && imageReferenceItems.value.length > maxImageReferences.value) {
    imageReferenceItems.value = imageReferenceItems.value.slice(0, maxImageReferences.value)
  }
})

watch(selectedModel, value => {
  if (value !== 'image-01-live') {
    selectedStyle.value = '默认'
  }
  if (value !== 'image-01' && value !== 'comfyui-local') {
    useCustomImageSize.value = false
  }
  if (value === 'comfyui-local') {
    imagePromptOptimizer.value = false
    imageAigcWatermark.value = false
    if (imageReferenceItems.value.length > maxImageReferences.value) {
      imageReferenceItems.value = imageReferenceItems.value.slice(0, maxImageReferences.value)
    }
    void refreshComfyStatus()
  }
  if (value === 'comfyui-local-video') {
    videoPromptOptimizer.value = false
    videoFirstFrameUrl.value = ''
    videoLastFrameUrl.value = ''
    videoSubjectReferences.value = []
    void refreshComfyStatus()
  }
})

watch(videoMode, value => {
  if (value === 'text') {
    videoFirstFrameUrl.value = ''
    videoLastFrameUrl.value = ''
    videoSubjectReferences.value = []
  }
  if (value === 'image') {
    videoLastFrameUrl.value = ''
    videoSubjectReferences.value = []
  }
  if (value === 'start-end') {
    videoSubjectReferences.value = []
  }
  if (value === 'subject') {
    videoFirstFrameUrl.value = ''
    videoLastFrameUrl.value = ''
  }
})

watch([isGenerating, isLocalComfyActive], ([generating, local]) => {
  if (generating && local && !comfyStatusTimer) {
    void refreshComfyStatus()
    comfyStatusTimer = window.setInterval(() => {
      void refreshComfyStatus()
    }, 2000)
  }
  if ((!generating || !local) && comfyStatusTimer) {
    window.clearInterval(comfyStatusTimer)
    comfyStatusTimer = null
  }
})

watch(isGenerating, generating => {
  if (generating && !generationProgressTimer) {
    generationProgressNow.value = Date.now()
    generationProgressTimer = window.setInterval(() => {
      generationProgressNow.value = Date.now()
    }, 1000)
  }
  if (!generating && generationProgressTimer) {
    window.clearInterval(generationProgressTimer)
    generationProgressTimer = null
    generationProgressNow.value = Date.now()
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
  if (!aspect) return '16 / 9'
  const custom = aspect.match(/^(\d+)x(\d+)$/)
  if (custom) return `${custom[1]} / ${custom[2]}`
  const normalized = aspect.match(/^(\d+):(\d+)$/)
  if (!normalized) return '16 / 9'
  return `${normalized[1]} / ${normalized[2]}`
}

function isRequestCanceled(err: any) {
  return err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.message === 'canceled'
}

async function refreshComfyStatus() {
  try {
    const [statusResp, workflowsResp] = await Promise.all([
      api.get('/api/comfyui/status'),
      api.get('/api/comfyui/workflows'),
    ])
    const devices = statusResp.data?.devices || []
    const device = devices[0] || {}
    comfyDeviceName.value = device.name || ''
    const total = Number(device.vram_total || 0)
    const free = Number(device.vram_free || 0)
    const torchTotal = Number(device.torch_vram_total || 0)
    const torchFree = Number(device.torch_vram_free || 0)
    const used = Math.max(0, total - free)
    const torchUsed = Math.max(0, torchTotal - torchFree)
    comfyVramTotalGb.value = total / 1024 / 1024 / 1024
    comfyVramUsedGb.value = used / 1024 / 1024 / 1024
    comfyTorchUsedGb.value = torchUsed / 1024 / 1024 / 1024
    comfyVramPercent.value = total ? Math.round((used / total) * 100) : 0
    comfyWorkflows.value = workflowsResp.data?.workflows || []
    if (imageComfyWorkflows.value.length && !imageComfyWorkflows.value.some(workflow => workflow.id === selectedComfyWorkflow.value)) {
      selectedComfyWorkflow.value =
        imageComfyWorkflows.value.find(workflow => workflow.id === 'default-txt2img')?.id
        || imageComfyWorkflows.value[0].id
    }
    if (videoComfyWorkflows.value.length && !videoComfyWorkflows.value.some(workflow => workflow.id === selectedVideoComfyWorkflow.value)) {
      selectedVideoComfyWorkflow.value = videoComfyWorkflows.value[0].id
    }
    comfyStatus.value = 'online'
  } catch (e) {
    comfyStatus.value = 'offline'
    comfyDeviceName.value = ''
    comfyVramUsedGb.value = 0
    comfyVramTotalGb.value = 0
    comfyVramPercent.value = 0
    comfyTorchUsedGb.value = 0
  }
}

function patchMessage(id: string, patch: Partial<Message>) {
  const index = messages.value.findIndex(msg => msg.id === id)
  if (index < 0) return null
  const updated = { ...messages.value[index], ...patch }
  messages.value.splice(index, 1, updated)
  return updated
}

function isUpscaling(url: string) {
  return upscalingUrls.value.has(url)
}

function setUpscaling(url: string, value: boolean) {
  const next = new Set(upscalingUrls.value)
  if (value) {
    next.add(url)
  } else {
    next.delete(url)
  }
  upscalingUrls.value = next
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

function clampImageDimension(value: number) {
  const bounded = Math.min(2048, Math.max(512, Number(value) || 1024))
  return Math.round(bounded / 8) * 8
}

function updateImageDimension(kind: 'width' | 'height', event: Event) {
  const value = clampImageDimension(Number((event.target as HTMLInputElement).value))
  if (kind === 'width') {
    imageWidth.value = value
  } else {
    imageHeight.value = value
  }
}

function updateImageSeed(event: Event) {
  const value = (event.target as HTMLInputElement).value
  imageSeed.value = value ? Number(value) : null
}

function openImageReferencePicker() {
  imageReferenceInput.value?.click()
}

function addImageReference(src: string, name = '参考图') {
  if (!src) return
  if (isLocalComfyUI.value && !localComfyAllowsImageReference.value) {
    ElMessage.warning('当前 ComfyUI workflow 不需要参考图。要局部重绘，先选 Flux 局部重绘。')
    return
  }
  if (imageReferenceItems.value.some(item => item.src === src)) return
  if (imageReferenceItems.value.length >= maxImageReferences.value) {
    ElMessage.warning(
      localComfyUsesClickMask.value
        ? '局部重绘只需要 1 张原图，然后在图上点击要重绘的位置。'
        : localComfyNeedsMaskImage.value
          ? '局部重绘需要 2 张图：第 1 张原图，第 2 张遮罩图。'
        : '参考图最多添加 4 张，别贪多，模型也会迷糊。',
    )
    return
  }
  imageReferenceItems.value.push({
    id: `ref-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name,
    src,
  })
  if (localComfyUsesClickMask.value) {
    samClickX.value = null
    samClickY.value = null
    autoMaskUrl.value = ''
    nextTick(resetPaintMask)
  }
}

function removeImageReference(id: string) {
  imageReferenceItems.value = imageReferenceItems.value.filter(item => item.id !== id)
  if (!imageReferenceItems.value.length) {
    samClickX.value = null
    samClickY.value = null
    autoMaskUrl.value = ''
    clearPaintMask()
  }
}

async function markSamClick(event: MouseEvent) {
  if (!localComfyUsesClickMask.value || isAutoMasking.value) return
  const sourceImage = imageReferenceItems.value[0]?.src
  if (!sourceImage) return
  const target = event.currentTarget as HTMLElement
  const image = target.querySelector('img')
  if (!image) return
  const rect = image.getBoundingClientRect()
  samClickX.value = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  samClickY.value = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))
  autoMaskUrl.value = ''
  isAutoMasking.value = true
  try {
    const resp = await api.post('/api/comfyui/sam-mask', {
      source_image: sourceImage,
      x: samClickX.value,
      y: samClickY.value,
      dilation: 8,
      bbox_expansion: 20,
    })
    autoMaskUrl.value = resp.data?.data?.mask_url || ''
    if (!autoMaskUrl.value) {
      ElMessage.error('SAM 没返回蒙版图，换个位置再点。')
    }
  } catch (error: unknown) {
    const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
    ElMessage.error(detail || 'SAM 自动蒙版失败，请检查 ComfyUI。')
  } finally {
    isAutoMasking.value = false
  }
}

function resetPaintMask() {
  const canvas = maskCanvas.value
  if (!canvas) return
  const image = canvas.parentElement?.querySelector('img')
  const width = image instanceof HTMLImageElement && image.naturalWidth ? image.naturalWidth : 1024
  const height = image instanceof HTMLImageElement && image.naturalHeight ? image.naturalHeight : 1024
  canvas.width = width
  canvas.height = height
  clearPaintMask()
}

function clearPaintMask() {
  const canvas = maskCanvas.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) {
    maskHasPaint.value = false
    return
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  maskHasPaint.value = false
}

function paintMaskAt(event: PointerEvent) {
  const canvas = maskCanvas.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) return
  const rect = canvas.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * canvas.width
  const y = ((event.clientY - rect.top) / rect.height) * canvas.height
  const radius = Math.max(24, Math.min(96, Math.round(Math.min(canvas.width, canvas.height) * 0.035)))
  ctx.globalCompositeOperation = 'source-over'
  ctx.fillStyle = '#ff0000'
  ctx.beginPath()
  ctx.arc(x, y, radius, 0, Math.PI * 2)
  ctx.fill()
  maskHasPaint.value = true
}

function startPaintMask(event: PointerEvent) {
  if (!localComfyUsesClickMask.value || inpaintMode.value !== 'paint') return
  isPaintingMask.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
  paintMaskAt(event)
}

function continuePaintMask(event: PointerEvent) {
  if (!isPaintingMask.value) return
  paintMaskAt(event)
}

function stopPaintMask(event?: PointerEvent) {
  if (event) {
    ;(event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId)
  }
  isPaintingMask.value = false
}

function paintedMaskDataUrl() {
  if (!maskHasPaint.value || !maskCanvas.value) return null
  return maskCanvas.value.toDataURL('image/png')
}

function imageSubjectReferences() {
  const refs = imageReferenceItems.value.map(item => ({
    type: 'character',
    image_file: item.src,
  }))
  if (isLocalComfyUI.value && localComfyUsesClickMask.value && inpaintMode.value === 'paint') {
    const mask = paintedMaskDataUrl()
    if (mask && refs.length === 1) {
      refs.push({ type: 'character', image_file: mask })
    }
  } else if (isLocalComfyUI.value && localComfyUsesClickMask.value && inpaintMode.value === 'click') {
    if (autoMaskUrl.value && refs.length === 1) {
      refs.push({ type: 'character', image_file: autoMaskUrl.value })
    }
  }
  return refs
}

async function addImageReferenceFiles(files: FileList | File[]) {
  const imageFiles = Array.from(files).filter(file => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
  if (!imageFiles.length) {
    ElMessage.warning('参考图只支持 JPG、PNG、WebP')
    return
  }
  selectedCategory.value = 'image'
  for (const file of imageFiles) {
    if (file.size > 10 * 1024 * 1024) {
      ElMessage.error(`${file.name} 超过 10MB，官方调试台也是这个限制。`)
      continue
    }
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error('图片读取失败'))
      reader.readAsDataURL(file)
    })
    addImageReference(dataUrl, file.name)
  }
}

function addImageReferenceUrl() {
  const url = imageReferenceUrl.value.trim()
  if (!url) return
  if (!/^https?:\/\//i.test(url) && !url.startsWith('data:image/')) {
    ElMessage.warning('参考图 URL 需要是 http(s) 或 data:image')
    return
  }
  selectedCategory.value = 'image'
  addImageReference(url, 'URL 参考图')
  imageReferenceUrl.value = ''
}

function assignVideoFrameReference(src: string, name = '视频参考图') {
  if (!src) return
  if (isLocalComfyVideo.value) {
    ElMessage.warning('本地 ComfyUI 视频 workflow 当前只接提示词，参考图先别塞。')
    return
  }
  if (videoMode.value === 'text') {
    videoMode.value = 'image'
  }
  if (videoMode.value === 'subject') {
    addVideoSubjectReference(src, name)
    return
  }
  if (videoMode.value === 'start-end' && videoFirstFrameUrl.value && !videoLastFrameUrl.value) {
    videoLastFrameUrl.value = src
    return
  }
  videoFirstFrameUrl.value = src
}

function addVideoSubjectReference(src: string, name = '主体参考图') {
  if (!src) return
  if (videoSubjectReferences.value.some(item => item.src === src)) return
  if (videoSubjectReferences.value.length >= 4) {
    ElMessage.warning('主体参考图最多 4 张。再多不是专业，是给模型添乱。')
    return
  }
  videoSubjectReferences.value.push({
    id: `video-ref-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name,
    src,
  })
}

function removeVideoReference(kind: 'first' | 'last' | 'subject', id?: string) {
  if (kind === 'first') videoFirstFrameUrl.value = ''
  if (kind === 'last') videoLastFrameUrl.value = ''
  if (kind === 'subject' && id) {
    videoSubjectReferences.value = videoSubjectReferences.value.filter(item => item.id !== id)
  }
}

async function addVideoReferenceFiles(files: FileList | File[]) {
  if (isLocalComfyVideo.value) {
    ElMessage.warning('本地 ComfyUI 视频 workflow 当前只接提示词，参考图先别塞。')
    return
  }
  const imageFiles = Array.from(files).filter(file =>
    ['image/jpeg', 'image/png', 'image/webp'].includes(file.type),
  )
  if (!imageFiles.length) {
    ElMessage.warning('视频参考图只支持 JPG、PNG、WebP')
    return
  }
  selectedCategory.value = 'video'
  for (const file of imageFiles) {
    if (file.size > 20 * 1024 * 1024) {
      ElMessage.error(`${file.name} 超过 20MB，MiniMax 视频接口不会收。`)
      continue
    }
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error('图片读取失败'))
      reader.readAsDataURL(file)
    })
    assignVideoFrameReference(dataUrl, file.name)
  }
}

function addVideoFrameUrl(kind: 'first' | 'last' | 'subject') {
  if (isLocalComfyVideo.value) {
    ElMessage.warning('本地 ComfyUI 视频 workflow 当前只接提示词，参考图先别塞。')
    return
  }
  const source = kind === 'last' ? videoLastFrameUrl.value : kind === 'subject' ? videoSubjectUrl.value : videoFirstFrameUrl.value
  const url = source.trim()
  if (!url) return
  if (!/^https?:\/\//i.test(url) && !url.startsWith('data:image/')) {
    ElMessage.warning('视频参考图需要是 http(s) URL 或 data:image')
    return
  }
  selectedCategory.value = 'video'
  if (kind === 'subject') {
    addVideoSubjectReference(url, '主体 URL')
    videoSubjectUrl.value = ''
  } else if (kind === 'last') {
    videoLastFrameUrl.value = url
  } else {
    videoFirstFrameUrl.value = url
  }
}

async function handleImageReferenceInput(event: Event) {
  const files = (event.target as HTMLInputElement).files
  if (files && selectedCategory.value === 'video') {
    await addVideoReferenceFiles(files)
  } else if (files) {
    await addImageReferenceFiles(files)
  }
  if (imageReferenceInput.value) {
    imageReferenceInput.value.value = ''
  }
}

async function handleComposerDrop(event: DragEvent) {
  const files = event.dataTransfer?.files
  if (files?.length) {
    event.preventDefault()
    if (selectedCategory.value === 'video') {
      await addVideoReferenceFiles(files)
    } else {
      await addImageReferenceFiles(files)
    }
    return
  }
  const url = event.dataTransfer?.getData('text/uri-list') || event.dataTransfer?.getData('text/plain') || ''
  if (url && /^https?:\/\/.+\.(png|jpe?g|webp)(\?.*)?$/i.test(url.trim())) {
    event.preventDefault()
    if (selectedCategory.value === 'video') {
      assignVideoFrameReference(url.trim(), '拖入参考图')
    } else {
      selectedCategory.value = 'image'
      addImageReference(url.trim(), '拖入参考图')
    }
  }
}

function isGenerationCategory(type: Message['type']): type is GenerationCategory {
  return type !== 'text'
}

function insertSpeechTag(tag: string) {
  const textarea = promptTextarea.value
  if (!textarea) {
    inputText.value = `${inputText.value}${tag}`
    return
  }
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  inputText.value = `${inputText.value.slice(0, start)}${tag}${inputText.value.slice(end)}`
  nextTick(() => {
    textarea.focus()
    const pos = start + tag.length
    textarea.setSelectionRange(pos, pos)
  })
}

function insertMusicTag(tag: string) {
  const textarea = musicLyricsTextarea.value
  if (!textarea) {
    musicLyrics.value = `${musicLyrics.value}${musicLyrics.value ? '\n' : ''}${tag}\n`
    return
  }
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const insertion = `${tag}\n`
  musicLyrics.value = `${musicLyrics.value.slice(0, start)}${insertion}${musicLyrics.value.slice(end)}`
  nextTick(() => {
    textarea.focus()
    const pos = start + insertion.length
    textarea.setSelectionRange(pos, pos)
  })
}

function applyMusicTemplate(template: { prompt: string; lyrics: string }) {
  inputText.value = template.prompt
  musicLyrics.value = template.lyrics
  selectedCategory.value = 'music'
  nextTick(scrollToBottom)
}

function updateMusicSeed(event: Event) {
  const value = (event.target as HTMLInputElement).value
  musicSeed.value = value ? Number(value) : null
}

function variationPromptFor(prompt: string, type: GenerationCategory) {
  if (type === 'image') {
    return `${prompt}, create a fresh variation with a different composition while preserving the core concept`
  }
  if (type === 'music') {
    return `${prompt}, create a fresh musical variation while preserving the core mood`
  }
  if (type === 'video') {
    return `${prompt}, create a fresh video variation while preserving the core scene`
  }
  return prompt
}

function estimateImageGenerationSeconds() {
  if (selectedModel.value !== 'comfyui-local') return Math.max(45, selectedImageCount.value * 28)
  const workflowName = comfyWorkflows.value.find(workflow => workflow.id === selectedComfyWorkflow.value)?.name || ''
  const isErnie = /ernie/i.test(`${selectedComfyWorkflow.value} ${workflowName}`)
  return Math.max(90, selectedImageCount.value * (isErnie ? 150 : 75))
}

function estimateGenerationSeconds(type: Message['type']) {
  if (type === 'voice') return 60
  if (type === 'music') return 180
  if (type === 'video') return selectedModel.value === 'comfyui-local-video' ? 720 : 420
  if (type === 'image') return estimateImageGenerationSeconds()
  return 90
}

function formatElapsed(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(safeSeconds / 60)
  const rest = safeSeconds % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

function generationProgressFor(record: GenerationRecord) {
  const elapsed = Math.max(0, (generationProgressNow.value - record.progressStartedAt) / 1000)
  const target = Math.max(30, record.progressTargetSeconds)
  const eased = 1 - Math.exp(-elapsed / Math.max(18, target * 0.45))
  const percent = Math.min(98, Math.max(8, Math.round(eased * 100)))
  let stage = '排队中'
  if (percent >= 80) stage = '保存结果'
  else if (percent >= 55) stage = '生成细节'
  else if (percent >= 28) stage = '模型推理'
  return {
    percent,
    elapsedLabel: formatElapsed(elapsed),
    stage,
  }
}

function loadingLabelFor(type: Message['type']) {
  if (type === 'voice') return 'AI 正在合成你的语音...'
  if (type === 'music') return 'AI 正在创作你的音乐...'
  if (type === 'video') return 'AI 正在创作你的视频...'
  return t('generate.generating')
}

async function sendRecordPrompt(prompt: string, type: Message['type'], model: string, variation = false) {
  if (!isGenerationCategory(type) || isGenerating.value || isOptimizingPrompt.value) return
  selectedCategory.value = type
  const models = modelNamesFor(type)
  if (model && (!models.length || models.includes(model))) {
    selectedModel.value = model
  }
  inputText.value = variation ? variationPromptFor(prompt, type) : prompt
  await nextTick()
  await sendMessage()
}

async function regenerateFromPrompt(prompt: string, type: Message['type'], model: string) {
  if (isGenerating.value || isOptimizingPrompt.value) return
  await sendRecordPrompt(prompt, type, model)
}

async function createVariation(prompt: string, type: Message['type'], model: string) {
  if (isGenerating.value || isOptimizingPrompt.value) return
  await sendRecordPrompt(prompt, type, model, true)
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

async function upscaleImage(url: string, record: GenerationRecord) {
  if (isGenerating.value || isOptimizingPrompt.value || isUpscaling(url)) return
  const previewAspect = record.aspect || '16:9'
  setUpscaling(url, true)
  await ensureConversation()

  const userMsg: Message = {
    id: `user-upscale-${Date.now()}`,
    role: 'user',
    type: 'text',
    content: `Upscale: ${record.prompt}`,
    createdAt: new Date(),
  }
  messages.value.push(userMsg)
  await saveMessages()

  const placeholders = createPlaceholder('image', 120)
  const placeholderId = placeholders.msg.id
  const controller = new AbortController()
  generationAbortController.value = controller
  messages.value.push({
    ...placeholders.msg,
    model: 'comfyui-upscale',
    aspect: previewAspect,
    style: 'Upscale 2x',
  })
  isGenerating.value = true
  void refreshComfyStatus()
  scrollToBottom()

  try {
    const resp = await api.post('/api/image/upscale', {
      source_url: url,
      scale: 2,
      method: 'lanczos',
      aspect_ratio: previewAspect,
    }, {
      signal: controller.signal,
    })
    const data = resp.data as { image_urls: string[] }
    const updated = patchMessage(placeholderId, {
      loading: false,
      results: data.image_urls || [],
      type: 'image',
      model: 'comfyui-upscale',
      aspect: previewAspect,
      style: 'Upscale 2x',
    })
    if (updated) {
      await saveAssistantResponse(updated)
    }
  } catch (err: any) {
    patchMessage(placeholderId, {
      content: isRequestCanceled(err) || controller.signal.aborted
        ? '已取消放大'
        : err?.response?.data?.detail || err.message || 'Upscale failed',
      role: 'error',
      loading: false,
      model: 'comfyui-upscale',
      aspect: previewAspect,
      style: 'Upscale 2x',
    })
  } finally {
    if (generationAbortController.value === controller) {
      generationAbortController.value = null
    }
    isGenerating.value = false
    setUpscaling(url, false)
    void refreshComfyStatus()
    scrollToBottom()
  }
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
  if ((!inputText.value.trim() && !canSubmitGeneration.value) || isGenerating.value) return
  const text = inputText.value.trim()
  const displayText = text
    || (selectedCategory.value === 'music' ? musicLyrics.value.trim().slice(0, 120) || 'AI 歌词优化音乐' : '')
    || (selectedCategory.value === 'video' ? '视频参考图生成' : '')
    || '生成请求'
  inputText.value = ''

  await ensureConversation()

  const userMsg: Message = {
    id: `user-${Date.now()}`,
    role: 'user',
    type: 'text',
    content: displayText,
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
  const placeholderId = placeholders.msg.id
  const controller = new AbortController()
  generationAbortController.value = controller
  messages.value.push(placeholders.msg)
  isGenerating.value = true
  scrollToBottom()

  try {
    const resp = await api.post('/api/image/generate', {
      prompt,
      model: selectedModel.value,
      aspect_ratio: useCustomImageSize.value ? null : selectedAspect.value,
      width: useCustomImageSize.value ? imageWidth.value : null,
      height: useCustomImageSize.value ? imageHeight.value : null,
      n: selectedImageCount.value,
      response_format: 'url',
      prompt_optimizer: imagePromptOptimizer.value,
      seed: imageSeed.value,
      aigc_watermark: imageAigcWatermark.value,
      comfyui_workflow_id: isLocalComfyUI.value ? selectedComfyWorkflow.value || null : null,
      comfyui_steps: isLocalComfyUI.value ? comfyuiSteps.value : null,
      comfyui_cfg: isLocalComfyUI.value ? comfyuiCfg.value : null,
      comfyui_denoise: isLocalComfyUI.value ? comfyuiDenoise.value : null,
      sam_x: localComfyUsesClickMask.value && inpaintMode.value === 'click' ? samClickX.value : null,
      sam_y: localComfyUsesClickMask.value && inpaintMode.value === 'click' ? samClickY.value : null,
      style: selectedModel.value === 'image-01-live' && selectedStyle.value !== '默认'
        ? { style_type: selectedStyle.value, style_weight: imageStyleWeight.value }
        : null,
      subject_reference: imageSubjectReferences(),
    }, {
      signal: controller.signal,
    })
    const data = resp.data as { image_urls: string[] }
    console.log('[sendImage] image_urls:', JSON.stringify(data.image_urls))
    console.log('[sendImage] results count:', (data.image_urls || []).length)
    const updated = patchMessage(placeholderId, {
      loading: false,
      results: data.image_urls || [],
      type: 'image',
      model: selectedModel.value,
      aspect: useCustomImageSize.value ? `${imageWidth.value}x${imageHeight.value}` : selectedAspect.value,
      style: selectedStyle.value,
    })
    if (updated) {
      await saveAssistantResponse(updated)
    }
  } catch (err: any) {
    patchMessage(placeholderId, {
      content: isRequestCanceled(err) || controller.signal.aborted
        ? '已取消生成'
        : err?.response?.data?.detail || err.message || 'Generation failed',
      role: 'error',
      loading: false,
    })
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
      generation_model: selectedModel.value,
    })
    const data = resp.data as { optimized_prompt: string }
    if (data.optimized_prompt?.trim()) {
      inputText.value = data.optimized_prompt.trim()
      ElMessage.success(`${optimizePromptSuccessLabel.value}已优化，可继续编辑或直接发送`)
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
      voice_id: activeVoiceId.value || 'male-qn-qingse',
      model: selectedModel.value,
      speed: voiceSpeed.value,
      vol: voiceVolume.value,
      pitch: voicePitch.value,
      emotion: selectedEmotion.value,
      audio_format: audioFormat.value,
      sample_rate: sampleRate.value,
      bitrate: bitrate.value,
      channel: audioChannel.value,
      subtitle_enable: subtitleEnabled.value,
      latex_read: latexReadEnabled.value,
      language_boost: languageBoost.value || null,
      pronunciation_tones: pronunciationTones.value,
      voice_effect_pitch: voiceEffectPitch.value,
      voice_effect_intensity: voiceEffectIntensity.value,
      voice_effect_timbre: voiceEffectTimbre.value,
      voice_effect: voiceEffect.value || null,
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
      lyrics: musicLyrics.value,
      is_instrumental: musicInstrumental.value,
      lyrics_optimizer: musicLyricsOptimizer.value,
      audio_format: musicAudioFormat.value,
      output_format: musicOutputFormat.value,
      sample_rate: musicSampleRate.value,
      bitrate: musicBitrate.value,
      seed: musicSeed.value,
      aigc_watermark: musicAigcWatermark.value,
      reference_audio_url: musicReferenceAudioUrl.value || null,
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
      duration: videoDuration.value,
      resolution: videoResolution.value,
      first_frame_image: videoMode.value === 'image' || videoMode.value === 'start-end'
        ? videoFirstFrameUrl.value || null
        : null,
      last_frame_image: videoMode.value === 'start-end'
        ? videoLastFrameUrl.value || null
        : null,
      subject_reference: videoMode.value === 'subject' && videoSubjectReferences.value.length
        ? [{
            type: 'character',
            image: videoSubjectReferences.value.map(item => item.src),
          }]
        : null,
      prompt_optimizer: videoPromptOptimizer.value,
      fast_pretreatment: videoFastPretreatment.value,
      aspect_ratio: isLocalComfyVideo.value ? selectedAspect.value : null,
      comfyui_workflow_id: isLocalComfyVideo.value ? selectedVideoComfyWorkflow.value || null : null,
    }, {
      signal: controller.signal,
    })
    const data = resp.data as { task_id: string; video_url?: string }
    placeholders.msg.taskId = data.task_id
    placeholders.msg.model = selectedModel.value

    if (data.video_url) {
      placeholders.msg.loading = false
      placeholders.msg.results = [data.video_url]
      placeholders.msg.type = 'video'
      await saveAssistantResponse(placeholders.msg)
      return
    }

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
  const maxAttempts = 90
  for (let i = 0; i < maxAttempts; i++) {
    if (signal?.aborted) {
      throw new DOMException('canceled', 'CanceledError')
    }
    await new Promise(r => setTimeout(r, 10000))
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

function createPlaceholder(type: Message['type'], progressTargetSeconds = estimateGenerationSeconds(type)): { msg: Message } {
  const now = Date.now()
  return {
    msg: {
      id: `assistant-${now}`,
      role: 'assistant',
      type,
      content: '',
      loading: true,
      progressStartedAt: now,
      progressTargetSeconds,
      createdAt: new Date(now),
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

function goCanvas() {
  if (convId.value) {
    router.push({ path: `/project/${convId.value}`, query: { mode: 'canvas' } })
  } else {
    router.push('/')
  }
}

async function sendToCanvas(url: string, record: any) {
  if (!convId.value) return
  try {
    // Get or create the project's canvas document
    const docResp = await api.get(`/api/canvas/documents/by-conversation/${convId.value}`)
    const docId = docResp.data?.id
    if (!docId) {
      ElMessage.error('Canvas document not found')
      return
    }
    // Create a media node with this image
    await api.post(`/api/canvas/documents/${docId}/media-nodes`, {
      asset_url: url,
      title: `Result - ${record.prompt?.slice(0, 40) || 'Image'}`,
      source: 'conversation',
      source_generation_id: record.id,
      position: { x: 200, y: 200 },
    })
    ElMessage.success('已发送到 Canvas')
    router.push({ path: `/project/${convId.value}`, query: { mode: 'canvas' } })
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '发送失败')
  }
}

async function logout() {
  auth.logout()
  await router.replace('/login')
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

    // Default to image category, prioritize comfyui-local
    const imageModels = modelNamesFor('image')
    if (imageModels.length) {
      selectedCategory.value = 'image'
      selectedModel.value = imageModels.includes('comfyui-local') ? 'comfyui-local' : imageModels[0]
    } else {
      // Fallback: auto-detect first available category
      const preferred: Array<keyof AvailableModels> = ['voice', 'music', 'video']
      const firstCat = preferred.find(c => modelNamesFor(c).length)
      if (firstCat) {
        selectedCategory.value = firstCat as GenerationCategory
        selectedModel.value = modelNamesFor(firstCat)[0]
      }
    }
    console.log('[GenerateView] default category:', selectedCategory.value, 'model:', selectedModel.value)

    if (selectedModel.value === 'comfyui-local' || selectedModel.value === 'comfyui-local-video') {
      await refreshComfyStatus()
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

  // If embedded, use the embeddedConversationId
  if (props.embeddedConversationId) {
    convId.value = props.embeddedConversationId
    const item = history.value.find(h => h.id === props.embeddedConversationId)
    if (item) {
      await loadFromHistory(item)
    }
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', handlePreviewKeydown)
  if (comfyStatusTimer) {
    window.clearInterval(comfyStatusTimer)
    comfyStatusTimer = null
  }
  if (generationProgressTimer) {
    window.clearInterval(generationProgressTimer)
    generationProgressTimer = null
  }
})
</script>

<template>
  <div class="generate-page" :class="[`mode-${selectedCategory}`, { embedded: props.embedded }]">
    <header v-if="!props.embedded" class="topbar">
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

      <div class="topbar-actions">
        <button v-if="convId" class="home-return" type="button" @click="goCanvas()">
          流水线画布
        </button>
        <button class="home-return" type="button" @click="goHome">
          返回主页
        </button>
        <button class="logout-return" type="button" @click="logout">
          退出登录
        </button>
      </div>
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
                <button type="button" @click="regenerateFromPrompt(record.prompt, record.type, record.model)" :disabled="isGenerating || isOptimizingPrompt">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 12a9 9 0 0 1-15.6 6.1"/>
                    <path d="M3 12A9 9 0 0 1 18.6 5.9"/>
                    <path d="M18 2v4h4M6 22v-4H2"/>
                  </svg>
                  重新生成
                </button>
                <button type="button" @click="createVariation(record.prompt, record.type, record.model)" :disabled="isGenerating || isOptimizingPrompt">
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
              <div class="record-loading-main">
                <div class="loading-dots"><span></span><span></span><span></span></div>
                <div class="loading-copy">
                  <strong>{{ loadingLabelFor(record.type) }}</strong>
                  <span>{{ generationProgressFor(record).stage }} · {{ generationProgressFor(record).elapsedLabel }}</span>
                </div>
              </div>
              <div class="generation-progress" :aria-label="`生成进度 ${generationProgressFor(record).percent}%`">
                <span :style="{ width: `${generationProgressFor(record).percent}%` }"></span>
              </div>
              <button class="loading-cancel-btn" type="button" @click="cancelGeneration">
                取消生成
              </button>
            </div>

            <div v-else-if="record.error" class="record-error">
              {{ record.error }}
            </div>

            <div
              v-else-if="record.type === 'image' && record.results.length"
              class="record-images"
              :class="{ single: record.results.length === 1, pair: record.results.length === 2, multi: record.results.length > 2 }"
            >
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
                  <button type="button" @click="createVariation(record.prompt, record.type, record.model)" :disabled="isGenerating || isOptimizingPrompt">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>
                      <path d="M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12"/>
                    </svg>
                    变体
                  </button>
                  <button
                    type="button"
                    title="使用 ComfyUI 放大 2x"
                    :disabled="isGenerating || isOptimizingPrompt || isUpscaling(url)"
                    @click="upscaleImage(url, record)"
                  >
                    <span>HD</span>
                    {{ isUpscaling(url) ? '放大中' : 'Upscale' }}
                  </button>
                  <button type="button" @click="downloadFile(url)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <path d="M7 10l5 5 5-5M12 15V3"/>
                    </svg>
                    下载
                  </button>
                  <button
                    v-if="convId"
                    type="button"
                    title="发送到 Canvas"
                    @click="sendToCanvas(url, record)"
                  >
                    ⬡ Canvas
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

    <form
      class="composer"
      :class="{ 'drop-ready': selectedCategory === 'image' || selectedCategory === 'video' }"
      @submit.prevent="sendMessage"
      @dragover.prevent
      @drop="handleComposerDrop"
    >
      <div v-if="selectedCategory === 'image' && activeImageReferenceCount" class="reference-strip">
        <figure v-for="(item, index) in imageReferenceItems" :key="item.id" class="reference-thumb">
          <img :src="item.src" :alt="item.name" />
          <figcaption v-if="isLocalComfyUI && localComfyAllowsImageReference">
            {{ localComfyUsesClickMask ? '原图' : index === 0 ? '原图' : '遮罩' }}
          </figcaption>
          <button type="button" title="移除参考图" @click="removeImageReference(item.id)">×</button>
        </figure>
        <button
          v-if="imageReferenceItems.length < maxImageReferences"
          class="reference-add"
          type="button"
          title="继续添加参考图"
          @click="openImageReferencePicker"
        >+</button>
      </div>
      <div v-if="selectedCategory === 'image' && localComfyUsesClickMask && imageReferenceItems[0]" class="inpaint-panel">
        <div class="inpaint-mode-row" aria-label="局部重绘方式">
          <button
            type="button"
            :class="{ active: inpaintMode === 'paint' }"
            @click="inpaintMode = 'paint'"
          >涂抹区域</button>
          <button
            type="button"
            :class="{ active: inpaintMode === 'click' }"
            @click="inpaintMode = 'click'"
          >自动蒙版</button>
          <button v-if="inpaintMode === 'paint'" type="button" class="inpaint-clear" @click="clearPaintMask">清除涂抹</button>
          <button v-else-if="autoMaskUrl" type="button" class="inpaint-clear" @click="autoMaskUrl = ''">重选</button>
        </div>

        <div v-if="inpaintMode === 'paint'" class="inpaint-paint-stage">
          <img :src="imageReferenceItems[0].src" :alt="imageReferenceItems[0].name" @load="resetPaintMask" />
          <canvas
            ref="maskCanvas"
            @pointerdown.prevent="startPaintMask"
            @pointermove.prevent="continuePaintMask"
            @pointerup.prevent="stopPaintMask"
            @pointerleave.prevent="stopPaintMask"
          ></canvas>
        </div>

        <div v-else class="inpaint-click-stage" @click="markSamClick">
          <img :src="imageReferenceItems[0].src" :alt="imageReferenceItems[0].name" />
          <img v-if="autoMaskUrl" class="inpaint-auto-mask" :src="autoMaskUrl" alt="自动蒙版" />
          <span
            v-if="samClickX !== null && samClickY !== null"
            class="inpaint-click-dot"
            :style="{ left: `${samClickX * 100}%`, top: `${samClickY * 100}%` }"
          ></span>
          <span v-if="isAutoMasking" class="inpaint-mask-loading">正在生成蒙版</span>
        </div>

        <p>
          {{
            inpaintMode === 'paint'
              ? (maskHasPaint ? '红色区域会被重绘，可继续补涂或清除重来。' : '直接在图上涂红要修改的区域。')
              : (autoMaskUrl ? '蒙版已生成，红色高亮区域会被重绘；不准就点别的位置重选。' : (isAutoMasking ? 'SAM 正在圈选目标。' : '点击图片上的目标，先生成可见自动蒙版。'))
          }}
        </p>
      </div>
      <div v-if="selectedCategory === 'video' && activeVideoReferenceCount" class="reference-strip">
        <figure v-if="videoFirstFrameUrl" class="reference-thumb">
          <img :src="videoFirstFrameUrl" alt="首帧参考图" />
          <button type="button" title="移除首帧" @click="removeVideoReference('first')">×</button>
        </figure>
        <figure v-if="videoLastFrameUrl" class="reference-thumb">
          <img :src="videoLastFrameUrl" alt="尾帧参考图" />
          <button type="button" title="移除尾帧" @click="removeVideoReference('last')">×</button>
        </figure>
        <figure v-for="item in videoSubjectReferences" :key="item.id" class="reference-thumb">
          <img :src="item.src" :alt="item.name" />
          <button type="button" title="移除主体参考图" @click="removeVideoReference('subject', item.id)">×</button>
        </figure>
        <button class="reference-add" type="button" title="继续添加视频参考图" @click="openImageReferencePicker">+</button>
      </div>

      <div class="composer-input">
        <button
          v-if="selectedCategory === 'image' || selectedCategory === 'video'"
          class="upload-btn"
          type="button"
          :title="selectedCategory === 'video' ? '添加视频参考图' : '添加参考图'"
          :disabled="(selectedCategory === 'image' && isLocalComfyUI && !localComfyAllowsImageReference) || (selectedCategory === 'video' && isLocalComfyVideo)"
          @click="openImageReferencePicker"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="5" width="18" height="14" rx="2"/>
            <circle cx="8.5" cy="10.5" r="1.5"/>
            <path d="M21 15l-5-5L5 21"/>
          </svg>
        </button>
        <input
          ref="imageReferenceInput"
          class="hidden-file-input"
          type="file"
          accept="image/jpeg,image/jpg,image/png,image/webp"
          multiple
          :disabled="(selectedCategory === 'image' && isLocalComfyUI && !localComfyAllowsImageReference) || (selectedCategory === 'video' && isLocalComfyVideo)"
          @change="handleImageReferenceInput"
        />
        <textarea
          ref="promptTextarea"
          v-model="inputText"
          class="prompt-textarea"
          :placeholder="composerPlaceholder"
          rows="1"
          @keydown.enter.exact.prevent="sendMessage"
        ></textarea>
        <button
          class="optimize-btn"
          type="button"
          :title="optimizePromptTitle"
          @click="optimizePrompt"
          :disabled="!inputText.trim() || isGenerating || isOptimizingPrompt"
        >
          <span v-if="isOptimizingPrompt" class="mini-spinner"></span>
          <span v-else>AI enhance</span>
        </button>
      </div>

      <div v-if="selectedCategory === 'image'" class="image-panel">
        <div v-if="isLocalComfyUI" class="comfy-status-row" :class="comfyStatus">
          <span class="status-dot"></span>
          <span>本地 ComfyUI</span>
          <strong>{{ comfyStatus === 'online' ? '在线' : comfyStatus === 'offline' ? '离线' : '检测中' }}</strong>
          <small>{{ comfyVramLabel }}</small>
          <small v-if="comfyTorchUsedGb">Torch {{ comfyTorchUsedGb.toFixed(1) }} GB</small>
          <small v-if="comfyDeviceName">{{ comfyDeviceName }}</small>
          <button type="button" @click="refreshComfyStatus">刷新</button>
        </div>

        <label v-if="isLocalComfyUI" class="voice-field comfy-checkpoint-field">
          <span>ComfyUI workflow</span>
          <select v-model="selectedComfyWorkflow">
            <option value="">默认代码工作流</option>
            <option v-for="workflow in imageComfyWorkflows" :key="workflow.id" :value="workflow.id">
              {{ workflow.name }}
            </option>
          </select>
        </label>

        <div v-if="!isLocalComfyUI || localComfyAllowsImageReference" class="image-reference-row">
          <input
            v-model="imageReferenceUrl"
            type="url"
            :placeholder="imageReferenceUrlPlaceholder"
            @keydown.enter.prevent="addImageReferenceUrl"
          />
          <button type="button" @click="addImageReferenceUrl">添加</button>
        </div>

        <details class="voice-advanced image-advanced">
          <summary>图片高级设置</summary>
          <div class="advanced-grid image-settings-grid">
            <label class="voice-check">
              <input v-model="imagePromptOptimizer" type="checkbox" :disabled="isLocalComfyUI" />
              <span>官方 Prompt 优化</span>
            </label>
            <label class="voice-check">
              <input v-model="imageAigcWatermark" type="checkbox" :disabled="isLocalComfyUI" />
              <span>AIGC 水印</span>
            </label>
            <label class="voice-check">
              <input v-model="useCustomImageSize" type="checkbox" :disabled="selectedModel !== 'image-01' && selectedModel !== 'comfyui-local'" />
              <span>自定义尺寸</span>
            </label>
            <label class="voice-field">
              <span>宽度</span>
              <input
                :value="imageWidth"
                type="number"
                min="512"
                max="2048"
                step="8"
                :disabled="!useCustomImageSize || (selectedModel !== 'image-01' && selectedModel !== 'comfyui-local')"
                @input="updateImageDimension('width', $event)"
              />
            </label>
            <label class="voice-field">
              <span>高度</span>
              <input
                :value="imageHeight"
                type="number"
                min="512"
                max="2048"
                step="8"
                :disabled="!useCustomImageSize || (selectedModel !== 'image-01' && selectedModel !== 'comfyui-local')"
                @input="updateImageDimension('height', $event)"
              />
            </label>
            <label class="voice-field">
              <span>Seed</span>
              <input
                :value="imageSeed ?? ''"
                type="number"
                placeholder="留空随机"
                @input="updateImageSeed"
              />
            </label>
            <template v-if="isLocalComfyUI">
              <label class="voice-field">
                <span>Steps</span>
                <input v-model.number="comfyuiSteps" type="number" min="1" max="100" step="1" />
              </label>
              <label class="voice-field">
                <span>CFG</span>
                <input v-model.number="comfyuiCfg" type="number" min="0" max="30" step="0.5" />
              </label>
              <label class="voice-field">
                <span>Denoise</span>
                <input v-model.number="comfyuiDenoise" type="number" min="0" max="1" step="0.01" />
              </label>
            </template>
            <label v-if="selectedModel === 'image-01-live'" class="voice-field">
              <span>画风权重 {{ imageStyleWeight.toFixed(1) }}</span>
              <input v-model.number="imageStyleWeight" type="range" min="0.1" max="1" step="0.1" />
            </label>
          </div>
        </details>
      </div>

      <div v-if="selectedCategory === 'voice'" class="voice-panel">
        <div class="speech-tags" aria-label="语气词标签">
          <button
            v-for="item in speechInterjections"
            :key="item.tag"
            type="button"
            @click="insertSpeechTag(item.tag)"
          >
            {{ item.label }}
          </button>
          <button type="button" @click="insertSpeechTag('<#0.5#>')">停顿 0.5s</button>
        </div>

        <div class="voice-grid">
          <label class="voice-field">
            <span>音色</span>
            <select v-if="!useCustomVoice" v-model="selectedVoiceId">
              <option v-for="voice in speechVoices" :key="voice.id" :value="voice.id">{{ voice.name }}</option>
            </select>
            <input v-else v-model="customVoiceId" type="text" placeholder="输入 voice_id" />
          </label>
          <button class="voice-switch" type="button" @click="useCustomVoice = !useCustomVoice">
            {{ useCustomVoice ? '系统音色' : '自定义音色' }}
          </button>

          <label class="voice-field">
            <span>格式</span>
            <select v-model="audioFormat">
              <option v-for="format in speechAudioFormats" :key="format" :value="format">{{ format.toUpperCase() }}</option>
            </select>
          </label>

          <label class="voice-field">
            <span>采样率</span>
            <select v-model.number="sampleRate">
              <option v-for="rate in speechSampleRates" :key="rate" :value="rate">{{ rate }} Hz</option>
            </select>
          </label>

          <label class="voice-field">
            <span>比特率</span>
            <select v-model.number="bitrate">
              <option v-for="rate in speechBitrates" :key="rate" :value="rate">{{ rate / 1000 }} kbps</option>
            </select>
          </label>

          <label class="voice-field">
            <span>声道</span>
            <select v-model.number="audioChannel">
              <option :value="1">单声道</option>
              <option :value="2">立体声</option>
            </select>
          </label>
        </div>

        <div class="emotion-row" aria-label="情绪">
          <button
            v-for="emotion in speechEmotions"
            :key="emotion.id"
            type="button"
            :class="{ active: selectedEmotion === emotion.id }"
            @click="selectedEmotion = emotion.id"
          >
            {{ emotion.name }}
          </button>
        </div>

        <div class="voice-sliders">
          <label>
            <span>语速 {{ voiceSpeed }}</span>
            <input v-model.number="voiceSpeed" type="range" min="0.5" max="2" step="0.1" />
          </label>
          <label>
            <span>音量 {{ voiceVolume }}</span>
            <input v-model.number="voiceVolume" type="range" min="0" max="10" step="0.1" />
          </label>
          <label>
            <span>音调 {{ voicePitch }}</span>
            <input v-model.number="voicePitch" type="range" min="-12" max="12" step="1" />
          </label>
        </div>

        <details class="voice-advanced">
          <summary>高级设置</summary>
          <div class="advanced-grid">
            <label class="voice-check">
              <input v-model="subtitleEnabled" type="checkbox" />
              <span>生成字幕</span>
            </label>
            <label class="voice-check">
              <input v-model="latexReadEnabled" type="checkbox" />
              <span>LaTeX 朗读</span>
            </label>
            <label class="voice-field">
              <span>语言增强</span>
              <select v-model="languageBoost">
                <option v-for="item in speechLanguageBoosts" :key="item.id" :value="item.id">{{ item.name }}</option>
              </select>
            </label>
            <label class="voice-field">
              <span>音效</span>
              <select v-model="voiceEffect">
                <option v-for="item in speechVoiceEffects" :key="item.id" :value="item.id">{{ item.name }}</option>
              </select>
            </label>
            <label class="voice-field span-2">
              <span>发音词典</span>
              <textarea v-model="pronunciationToneInput" rows="2" placeholder="每行一个：词语/读音"></textarea>
            </label>
            <label class="voice-range">
              <span>效果音高 {{ voiceEffectPitch }}</span>
              <input v-model.number="voiceEffectPitch" type="range" min="-100" max="100" step="1" />
            </label>
            <label class="voice-range">
              <span>效果强度 {{ voiceEffectIntensity }}</span>
              <input v-model.number="voiceEffectIntensity" type="range" min="-100" max="100" step="1" />
            </label>
            <label class="voice-range">
              <span>效果音色 {{ voiceEffectTimbre }}</span>
              <input v-model.number="voiceEffectTimbre" type="range" min="-100" max="100" step="1" />
            </label>
          </div>
        </details>
      </div>

      <div v-if="selectedCategory === 'video'" class="video-panel">
        <div v-if="isLocalComfyVideo" class="comfy-status-row" :class="comfyStatus">
          <span class="status-dot"></span>
          <span>本地 ComfyUI</span>
          <strong>{{ comfyStatus === 'online' ? '在线' : comfyStatus === 'offline' ? '离线' : '检测中' }}</strong>
          <small>{{ comfyVramLabel }}</small>
          <small v-if="comfyTorchUsedGb">Torch {{ comfyTorchUsedGb.toFixed(1) }} GB</small>
          <small v-if="comfyDeviceName">{{ comfyDeviceName }}</small>
          <button type="button" @click="refreshComfyStatus">刷新</button>
        </div>

        <label v-if="isLocalComfyVideo" class="voice-field comfy-checkpoint-field">
          <span>ComfyUI video workflow</span>
          <select v-model="selectedVideoComfyWorkflow">
            <option value="" disabled>选择视频工作流</option>
            <option v-for="workflow in videoComfyWorkflows" :key="workflow.id" :value="workflow.id">
              {{ workflow.name }}
            </option>
          </select>
        </label>

        <label v-if="isLocalComfyVideo" class="voice-field comfy-checkpoint-field">
          <span>视频宽高比</span>
          <select v-model="selectedAspect">
            <option v-for="a in aspects" :key="a" :value="a">{{ a }}</option>
          </select>
        </label>

        <div v-if="!isLocalComfyVideo" class="video-mode-row" aria-label="视频生成模式">
          <button
            v-for="mode in videoModes"
            :key="mode.id"
            type="button"
            :class="{ active: videoMode === mode.id }"
            @click="videoMode = mode.id"
          >
            {{ mode.label }}
          </button>
        </div>

        <div v-if="!isLocalComfyVideo && (videoMode === 'image' || videoMode === 'start-end')" class="image-reference-row">
          <input
            v-model="videoFirstFrameUrl"
            type="url"
            placeholder="首帧图片 URL，或把图片拖进对话框"
            @keydown.enter.prevent="addVideoFrameUrl('first')"
          />
          <button type="button" @click="addVideoFrameUrl('first')">首帧</button>
        </div>

        <div v-if="!isLocalComfyVideo && videoMode === 'start-end'" class="image-reference-row">
          <input
            v-model="videoLastFrameUrl"
            type="url"
            placeholder="尾帧图片 URL；尺寸不一致时官方会按首帧裁切"
            @keydown.enter.prevent="addVideoFrameUrl('last')"
          />
          <button type="button" @click="addVideoFrameUrl('last')">尾帧</button>
        </div>

        <div v-if="!isLocalComfyVideo && videoMode === 'subject'" class="image-reference-row">
          <input
            v-model="videoSubjectUrl"
            type="url"
            placeholder="主体参考图 URL，支持多张主体一致性参考"
            @keydown.enter.prevent="addVideoFrameUrl('subject')"
          />
          <button type="button" @click="addVideoFrameUrl('subject')">主体</button>
        </div>

        <details class="voice-advanced">
          <summary>视频高级设置</summary>
          <div class="advanced-grid video-settings-grid">
            <label v-if="!isLocalComfyVideo" class="voice-check">
              <input v-model="videoPromptOptimizer" type="checkbox" />
              <span>官方 Prompt 优化</span>
            </label>
            <label v-if="!isLocalComfyVideo" class="voice-check">
              <input v-model="videoFastPretreatment" type="checkbox" />
              <span>快速预处理</span>
            </label>
            <label class="voice-field">
              <span>时长</span>
              <select v-model.number="videoDuration">
                <option v-for="duration in videoDurations" :key="duration" :value="duration">{{ duration }} 秒</option>
              </select>
            </label>
            <label class="voice-field">
              <span>分辨率</span>
              <select v-model="videoResolution">
                <option v-for="resolution in videoResolutions" :key="resolution" :value="resolution">{{ resolution }}</option>
              </select>
            </label>
          </div>
        </details>
      </div>

      <div v-if="selectedCategory === 'music'" class="music-panel">
        <div class="music-templates" aria-label="歌曲模板">
          <button
            v-for="template in musicTemplates"
            :key="template.name"
            type="button"
            @click="applyMusicTemplate(template)"
          >
            <strong>{{ template.name }}</strong>
            <span>{{ template.prompt }}</span>
          </button>
        </div>

        <div class="music-tags" aria-label="歌词结构标签">
          <button
            v-for="tag in musicStructureTags"
            :key="tag"
            type="button"
            @click="insertMusicTag(tag)"
          >
            {{ tag }}
          </button>
        </div>

        <div class="music-options-row">
          <label class="voice-check">
            <input v-model="musicInstrumental" type="checkbox" />
            <span>纯音乐模式</span>
          </label>
          <label class="voice-check">
            <input v-model="musicLyricsOptimizer" type="checkbox" />
            <span>AI 歌词优化</span>
          </label>
          <label class="voice-check">
            <input v-model="musicAigcWatermark" type="checkbox" />
            <span>AI 音频水印</span>
          </label>
        </div>

        <label v-if="selectedModel === 'music-cover'" class="voice-field">
          <span>参考音频 URL</span>
          <input v-model="musicReferenceAudioUrl" type="url" placeholder="https://example.com/reference.mp3" />
        </label>

        <label class="voice-field">
          <span>歌词</span>
          <textarea
            ref="musicLyricsTextarea"
            v-model="musicLyrics"
            rows="5"
            :placeholder="musicInstrumental ? '纯音乐模式下歌词可选，可用结构标签定义段落' : '输入歌词，可插入 [Verse]、[Chorus] 等结构标签'"
          ></textarea>
        </label>

        <details class="voice-advanced">
          <summary>高级设置</summary>
          <div class="advanced-grid">
            <label class="voice-field">
              <span>采样率</span>
              <select v-model.number="musicSampleRate">
                <option v-for="rate in musicSampleRates" :key="rate" :value="rate">{{ rate }} Hz</option>
              </select>
            </label>
            <label class="voice-field">
              <span>比特率</span>
              <select v-model.number="musicBitrate">
                <option v-for="rate in musicBitrates" :key="rate" :value="rate">{{ rate / 1000 }} kbps</option>
              </select>
            </label>
            <label class="voice-field">
              <span>音频格式</span>
              <select v-model="musicAudioFormat">
                <option v-for="format in musicAudioFormats" :key="format" :value="format">{{ format.toUpperCase() }}</option>
              </select>
            </label>
            <label class="voice-field">
              <span>返回格式</span>
              <select v-model="musicOutputFormat">
                <option v-for="format in musicOutputFormats" :key="format" :value="format">{{ format === 'hex' ? 'Hex 编码' : 'URL 链接' }}</option>
              </select>
            </label>
            <label class="voice-field">
              <span>Seed</span>
              <input
                :value="musicSeed ?? ''"
                type="number"
                min="0"
                max="1000000"
                placeholder="0 - 1000000"
                @input="updateMusicSeed"
              />
            </label>
          </div>
        </details>
      </div>

      <div class="composer-controls">
        <select v-model="selectedCategory" class="param-select">
          <option value="image">{{ t('generate.categoryImage') }}</option>
          <option value="voice">{{ t('generate.categoryVoice') }}</option>
          <option value="video">{{ t('generate.categoryVideo') }}</option>
          <option value="music">{{ t('generate.categoryMusic') }}</option>
        </select>
        <select v-if="selectedCategory === 'image'" v-model="selectedStyle" class="param-select" :disabled="selectedModel !== 'image-01-live'">
          <option v-for="s in styles" :key="s" :value="s">画风 {{ s }}</option>
        </select>
        <select v-if="selectedCategory === 'image'" v-model="selectedAspect" class="param-select" :disabled="useCustomImageSize">
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
          <input
            v-model.number="selectedImageCount"
            class="count-input"
            type="number"
            min="1"
            max="9"
            title="生成数量 1-9"
          />
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
          :disabled="!canSubmitGeneration"
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
  --composer-clearance: 180px;
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

.generate-page.mode-image {
  --composer-clearance: 290px;
}

.generate-page.mode-voice {
  --composer-clearance: 430px;
}

.generate-page.mode-video {
  --composer-clearance: 420px;
}

.generate-page.mode-music {
  --composer-clearance: 560px;
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

.topbar-actions {
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.home-return,
.logout-return {
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

.logout-return {
  min-width: 92px;
  border-color: rgba(148, 163, 184, 0.18);
  background: rgba(148, 163, 184, 0.08);
  color: rgba(226, 232, 240, 0.76);
}

.home-return:hover {
  border-color: rgba(25, 201, 255, 0.42);
  background: rgba(25, 201, 255, 0.14);
  color: #fff;
}

.logout-return:hover {
  border-color: rgba(244, 63, 94, 0.38);
  background: rgba(244, 63, 94, 0.12);
  color: #fecdd3;
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
  padding: 0 2px var(--composer-clearance) 0;
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
.generated-tile figcaption button:disabled,
.upload-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.record-images {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 360px));
  justify-content: start;
  gap: 12px;
  padding: 0 18px 16px;
}

.record-images.single {
  grid-template-columns: minmax(0, min(620px, 100%));
  justify-content: center;
}

.record-images.pair {
  grid-template-columns: repeat(2, minmax(0, min(420px, calc((100vw - 96px) / 2))));
  justify-content: center;
}

.record-images.multi {
  align-items: start;
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
  height: clamp(220px, 20vw, 360px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: rgba(2, 6, 12, 0.42);
  cursor: zoom-in;
  overflow: hidden;
}

.record-images.single .image-view-button {
  height: min(36vh, 360px);
}

.record-images.pair .image-view-button {
  height: min(34vh, 320px);
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
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(15, 23, 42, 0.35);
  color: rgba(226, 232, 240, 0.62);
  font-size: 13px;
}

.record-loading-main {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.loading-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: min(320px, calc(100vw - 96px));
}

.loading-copy strong {
  color: rgba(248, 250, 252, 0.86);
  font-size: 13px;
  font-weight: 750;
}

.loading-copy span {
  color: rgba(148, 163, 184, 0.72);
  font-size: 12px;
}

.generation-progress {
  width: min(420px, calc(100% - 36px));
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.82);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
}

.generation-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #19c9ff, #8b5cf6);
  transition: width 0.6s ease;
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
  position: fixed;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  width: min(1080px, calc(100vw - 48px));
  max-height: calc(100vh - 96px);
  overflow-y: auto;
  flex-shrink: 0;
  margin: 0;
  z-index: 1200;
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

.composer::-webkit-scrollbar {
  width: 5px;
}

.composer::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.2);
}

.composer-input {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hidden-file-input {
  display: none;
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

.reference-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.reference-thumb {
  position: relative;
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  margin: 0;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 10px;
  background: rgba(9, 14, 23, 0.72);
}

.reference-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.reference-thumb figcaption {
  position: absolute;
  left: 4px;
  bottom: 4px;
  max-width: calc(100% - 8px);
  padding: 2px 5px;
  border-radius: 6px;
  background: rgba(2, 6, 23, 0.76);
  color: #f8fafc;
  font-size: 10px;
  line-height: 1;
}

.reference-thumb button {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  background: rgba(2, 6, 23, 0.74);
  color: #fff;
  cursor: pointer;
  line-height: 1;
}

.reference-add {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  border: 1px dashed rgba(148, 163, 184, 0.28);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.5);
  color: rgba(226, 232, 240, 0.74);
  cursor: pointer;
  font-size: 24px;
}

.inpaint-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.58);
}

.inpaint-mode-row {
  display: flex;
  justify-content: center;
  gap: 8px;
  width: 100%;
}

.inpaint-mode-row button {
  height: 30px;
  padding: 0 12px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.72);
  color: rgba(226, 232, 240, 0.78);
  cursor: pointer;
  font-size: 12px;
}

.inpaint-mode-row button.active {
  border-color: rgba(34, 197, 94, 0.5);
  background: rgba(22, 163, 74, 0.18);
  color: #dcfce7;
}

.inpaint-mode-row .inpaint-clear {
  margin-left: auto;
  border-color: rgba(248, 113, 113, 0.32);
  color: #fecaca;
}

.inpaint-paint-stage,
.inpaint-click-stage {
  display: grid;
  position: relative;
  overflow: hidden;
  width: min(100%, 560px);
  max-height: 340px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  background: #020617;
  cursor: crosshair;
  touch-action: none;
}

.inpaint-paint-stage img,
.inpaint-paint-stage canvas,
.inpaint-click-stage img {
  grid-area: 1 / 1;
  width: 100%;
  max-height: 340px;
  object-fit: contain;
  display: block;
}

.inpaint-paint-stage canvas {
  height: 100%;
}

.inpaint-auto-mask {
  opacity: 0.58;
  filter: sepia(1) saturate(12) hue-rotate(310deg);
  mix-blend-mode: screen;
  pointer-events: none;
}

.inpaint-click-dot {
  position: absolute;
  width: 16px;
  height: 16px;
  transform: translate(-50%, -50%);
  border: 2px solid #fff;
  border-radius: 50%;
  background: #ef4444;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.24);
  pointer-events: none;
}

.inpaint-mask-loading {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  padding: 7px 12px;
  border: 1px solid rgba(34, 197, 94, 0.45);
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.82);
  color: #dcfce7;
  font-size: 12px;
  pointer-events: none;
}

.inpaint-panel p {
  margin: 0;
  color: rgba(226, 232, 240, 0.74);
  font-size: 12px;
  line-height: 1.5;
}

.image-panel,
.voice-panel,
.video-panel,
.music-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.image-reference-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.image-reference-row input {
  min-width: 0;
  height: 34px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(9, 14, 23, 0.72);
  color: #e2e8f0;
  outline: 0;
  padding: 0 10px;
  font: inherit;
  font-size: 12px;
}

.image-reference-row button {
  height: 34px;
  padding: 0 12px;
  border: 1px solid rgba(25, 211, 255, 0.24);
  border-radius: 8px;
  background: rgba(14, 165, 233, 0.12);
  color: #bdefff;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
}

.comfy-status-row {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(9, 14, 23, 0.72);
  color: rgba(226, 232, 240, 0.76);
  font-size: 12px;
}

.comfy-status-row strong {
  color: #e2e8f0;
  font-size: 12px;
}

.comfy-status-row small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(148, 163, 184, 0.78);
}

.comfy-status-row button {
  margin-left: auto;
  height: 26px;
  padding: 0 9px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 7px;
  background: rgba(15, 23, 42, 0.72);
  color: rgba(226, 232, 240, 0.8);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}

.status-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #94a3b8;
}

.comfy-status-row.online .status-dot {
  background: #22c55e;
}

.comfy-status-row.offline .status-dot {
  background: #ef4444;
}

.comfy-checkpoint-field {
  max-width: 100%;
}

.comfy-checkpoint-field select {
  text-overflow: ellipsis;
}

.image-settings-grid {
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.speech-tags,
.emotion-row,
.video-mode-row,
.music-tags,
.music-options-row {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.speech-tags button,
.video-mode-row button,
.music-tags button,
.emotion-row button,
.voice-switch {
  height: 30px;
  flex: 0 0 auto;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 7px;
  background: rgba(15, 23, 42, 0.72);
  color: rgba(226, 232, 240, 0.72);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.speech-tags button:hover,
.video-mode-row button:hover,
.music-tags button:hover,
.emotion-row button:hover,
.voice-switch:hover,
.video-mode-row button.active,
.emotion-row button.active {
  border-color: rgba(25, 211, 255, 0.38);
  background: rgba(14, 165, 233, 0.16);
  color: #e0f7ff;
}

.video-settings-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.music-templates {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.music-templates button {
  min-width: 0;
  min-height: 58px;
  padding: 9px 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.62);
  color: #e2e8f0;
  cursor: pointer;
  text-align: left;
  font: inherit;
}

.music-templates button:hover {
  border-color: rgba(244, 114, 182, 0.36);
  background: rgba(190, 24, 93, 0.16);
}

.music-templates strong,
.music-templates span {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.music-templates strong {
  font-size: 12px;
}

.music-templates span {
  margin-top: 4px;
  color: rgba(203, 213, 225, 0.58);
  font-size: 11px;
}

.voice-grid,
.advanced-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  align-items: end;
}

.voice-field,
.voice-range,
.voice-check {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: rgba(203, 213, 225, 0.7);
  font-size: 11px;
}

.voice-field span,
.voice-range span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.voice-field select,
.voice-field input,
.voice-field textarea {
  width: 100%;
  min-height: 34px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(9, 14, 23, 0.72);
  color: #e2e8f0;
  outline: 0;
  padding: 0 10px;
  font: inherit;
  font-size: 12px;
}

.voice-field textarea {
  padding: 8px 10px;
  resize: vertical;
}

.voice-field option {
  background: #0b1220;
  color: #fff;
}

.voice-sliders {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.voice-sliders label,
.voice-range {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: rgba(203, 213, 225, 0.7);
  font-size: 11px;
}

.voice-sliders input,
.voice-range input {
  width: 100%;
  accent-color: #19d3ff;
}

.voice-advanced {
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 8px;
  padding: 9px 10px;
  background: rgba(2, 6, 23, 0.24);
}

.voice-advanced summary {
  cursor: pointer;
  color: rgba(226, 232, 240, 0.72);
  font-size: 12px;
  font-weight: 700;
}

.advanced-grid {
  margin-top: 10px;
}

.voice-check {
  min-height: 34px;
  flex-direction: row;
  align-items: center;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 8px;
  background: rgba(9, 14, 23, 0.72);
}

.voice-check input {
  accent-color: #19d3ff;
}

.span-2 {
  grid-column: span 2;
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

.composer .param-select:disabled {
  opacity: 0.45;
  cursor: not-allowed;
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

.count-input {
  width: 48px;
  height: 28px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 6px;
  background: rgba(2, 6, 23, 0.58);
  color: rgba(226, 232, 240, 0.78);
  outline: 0;
  padding: 0 6px;
  font: inherit;
  font-size: 12px;
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

  .voice-grid,
  .advanced-grid,
  .music-templates {
    grid-template-columns: repeat(3, minmax(0, 1fr));
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

  .topbar-actions {
    gap: 8px;
  }

  .home-return,
  .logout-return {
    min-width: 88px;
    padding-inline: 12px;
  }

  .generation-main {
    padding: 16px 12px 16px;
  }

  .generate-page {
    --composer-clearance: 210px;
  }

  .generate-page.mode-image {
    --composer-clearance: 500px;
  }

  .generate-page.mode-voice {
    --composer-clearance: 650px;
  }

  .generate-page.mode-video {
    --composer-clearance: 640px;
  }

  .generate-page.mode-music {
    --composer-clearance: 720px;
  }

  .feed-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .record-images,
  .record-images.single,
  .record-images.pair,
  .record-images.multi {
    grid-template-columns: 1fr;
    justify-content: stretch;
  }

  .record-prompt {
    white-space: normal;
  }

  .generated-tile {
    aspect-ratio: auto;
  }

  .image-view-button,
  .record-images.single .image-view-button,
  .record-images.pair .image-view-button {
    height: min(52vh, 420px);
  }

  .image-view-button img {
    width: 100%;
    height: 100%;
  }

  .composer {
    width: calc(100vw - 20px);
    bottom: 10px;
    max-height: calc(100vh - 84px);
  }

  .composer .param-select {
    flex: 1 1 140px;
    min-width: 0;
  }

  .voice-grid,
  .advanced-grid,
  .voice-sliders {
    grid-template-columns: 1fr;
  }

  .music-templates {
    grid-template-columns: none;
    grid-auto-flow: column;
    grid-auto-columns: minmax(150px, 72vw);
    overflow-x: auto;
  }

  .span-2 {
    grid-column: span 1;
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
