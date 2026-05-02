<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const apiClient = axios.create({ baseURL: '/api', timeout: 60000 })

// ── Types ───────────────────────────────────────────────
interface Position { x: number; y: number }

interface BaseNode {
  id: string
  type: string
  x: number
  y: number
  selected: boolean
}

interface PromptNode extends BaseNode {
  type: 'prompt'
  content: string
  refImage?: string  // optional reference image for img2img
  time: string
}

interface GenerationNode extends BaseNode {
  type: 'generation'
  images: string[]  // 4 images in 2x2 grid
  time: string
}

interface BranchNode extends BaseNode {
  type: 'upscale' | 'img2img' | 'video' | 'voice' | 'music'
  sourceGenId: string
  sourceImgIndex: number
  image?: string
  content?: string
  time: string
}

interface VoiceNode extends BaseNode {
  type: 'voice'
  content: string
  voiceId: string
  voiceModel: string
  audioUrl?: string
  time: string
}

interface MusicNode extends BaseNode {
  type: 'music'
  content: string
  musicModel: string
  audioUrl?: string
  time: string
}

type AnyNode = PromptNode | GenerationNode | BranchNode | VoiceNode | MusicNode

interface Connection {
  id: string
  from: string
  to: string
  fromImgIndex?: number  // which image slot (0-3) in generation node
}

// ── State ──────────────────────────────────────────────
const canvasRef = ref<HTMLDivElement | null>(null)

// Canvas transform (pan + zoom)
const pan = ref<Position>({ x: 0, y: 0 })
const zoom = ref(1)

// Interaction state
const isPanning = ref(false)
const panStart = ref<Position>({ x: 0, y: 0 })
const draggingNode = ref<string | null>(null)
const dragOffset = ref<Position>({ x: 0, y: 0 })

// Connecting state (draw line from image)
const isConnecting = ref(false)
const connectFrom = ref<{ nodeId: string; imgIndex: number } | null>(null)
const mousePos = ref<Position>({ x: 0, y: 0 })

// Nodes & connections
const nodes = ref<AnyNode[]>([
  {
    id: 'prompt-1',
    type: 'prompt',
    x: 400,
    y: 580,  // bottom
    selected: false,
    content: 'A cyberpunk city at night with neon lights reflecting on wet streets, cinematic lighting',
    refImage: '',
    time: '10:32 AM'
  },
  {
    id: 'gen-1',
    type: 'generation',
    x: 400,
    y: 220,  // above prompt
    selected: false,
    images: ['', '', '', ''],
    time: '10:32 AM'
  }
])

const connections = ref<Connection[]>([
  { id: 'conn-1', from: 'prompt-1', to: 'gen-1' }
])

// Right panel state
const activeNode = ref<AnyNode | null>(null)
const noteText = ref('')

// Context menu
const contextMenu = ref<{ show: boolean; x: number; y: number; nodeId: string | null }>({
  show: false, x: 0, y: 0, nodeId: null
})

// Input
const inputText = ref('')
const selectedModel = ref('SDXL Turbo')
const selectedStyle = ref('Cinematic')
const selectedAspect = ref('16:9')
const isGenerating = ref(false)

const models = ['SDXL Turbo', 'DALL-E 3', 'Stable Diffusion', 'Midjourney v6']
const styles = ['Cinematic', 'Photorealistic', 'Anime', 'Abstract', 'Minimalist']
const aspects = ['1:1', '16:9', '9:16', '4:3', '3:4']

// ── Computed ──────────────────────────────────────────
const canvasTransform = computed(() =>
  `translate(${pan.value.x}px, ${pan.value.y}px) scale(${zoom.value})`
)

// Temp connection line for drawing
const tempConnPath = computed(() => {
  if (!isConnecting.value || !connectFrom.value) return ''
  const fromNode = nodes.value.find(n => n.id === connectFrom.value!.nodeId)
  if (!fromNode) return ''

  // Generation node center is at x + 160, y + 80
  // Images are at 2x2 grid within node
  const imgW = 156
  const imgH = 104
  const padL = 12
  const padT = 56
  const col = connectFrom.value.imgIndex % 2
  const row = Math.floor(connectFrom.value.imgIndex / 2)
  const fx = fromNode.x + padL + col * imgW + imgW / 2
  const fy = fromNode.y + padT + row * imgH + imgH

  const tx = (mousePos.value.x - pan.value.x) / zoom.value
  const ty = (mousePos.value.y - pan.value.y) / zoom.value

  const dy = Math.max(Math.abs(ty - fy) * 0.5, 60)
  return `M ${fx} ${fy} C ${fx} ${fy + dy}, ${tx} ${ty - dy}, ${tx} ${ty}`
})

// ── Canvas Interaction ──────────────────────────────────
function onCanvasMouseDown(e: MouseEvent) {
  if (e.target === canvasRef.value || (e.target as HTMLElement).classList.contains('canvas-bg')) {
    isPanning.value = true
    panStart.value = { x: e.clientX - pan.value.x, y: e.clientY - pan.value.y }
    nodes.value.forEach(n => n.selected = false)
    activeNode.value = null
    contextMenu.value.show = false
    if (isConnecting.value) {
      isConnecting.value = false
      connectFrom.value = null
    }
  }
}

function onCanvasMouseMove(e: MouseEvent) {
  mousePos.value = { x: e.clientX, y: e.clientY }
  if (isPanning.value) {
    pan.value = { x: e.clientX - panStart.value.x, y: e.clientY - panStart.value.y }
  }
  if (draggingNode.value) {
    const node = nodes.value.find(n => n.id === draggingNode.value)
    if (node) {
      node.x = (e.clientX - pan.value.x - dragOffset.value.x) / zoom.value
      node.y = (e.clientY - pan.value.y - dragOffset.value.y) / zoom.value
    }
  }
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const rect = canvasRef.value!.getBoundingClientRect()
  const mouseX = e.clientX - rect.left
  const mouseY = e.clientY - rect.top
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.min(Math.max(zoom.value * delta, 0.2), 3)

  // Zoom towards mouse
  const scale = newZoom / zoom.value
  pan.value = {
    x: mouseX - (mouseX - pan.value.x) * scale,
    y: mouseY - (mouseY - pan.value.y) * scale
  }
  zoom.value = newZoom
}

// ── Node Interaction ────────────────────────────────────
function onNodeMouseDown(e: MouseEvent, nodeId: string) {
  e.stopPropagation()
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return

  nodes.value.forEach(n => n.selected = false)
  node.selected = true
  activeNode.value = node
  contextMenu.value.show = false
  if (isConnecting.value) {
    isConnecting.value = false
    connectFrom.value = null
  }

  draggingNode.value = nodeId
  dragOffset.value = {
    x: e.clientX - (node.x * zoom.value + pan.value.x),
    y: e.clientY - (node.y * zoom.value + pan.value.y)
  }
}

function onNodeRightClick(e: MouseEvent, nodeId: string) {
  e.preventDefault()
  e.stopPropagation()
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, nodeId }
}

function closeContextMenu() { contextMenu.value.show = false }

// ── Image-level connect (start dragging a connection) ────
function onImageConnectStart(e: MouseEvent, genId: string, imgIndex: number) {
  e.stopPropagation()
  isConnecting.value = true
  connectFrom.value = { nodeId: genId, imgIndex }
}

function onCanvasMouseUpWhileConnecting(e: MouseEvent) {
  if (!isConnecting.value || !connectFrom.value) return
  // Check if dropped on canvas (not on another node)
  const target = e.target as HTMLElement
  if (target === canvasRef.value || target.classList.contains('canvas-bg') || target.classList.contains('dot-grid')) {
    // Create branch menu near cursor
    contextMenu.value = {
      show: true,
      x: e.clientX,
      y: e.clientY,
      nodeId: null
    }
  }
  isConnecting.value = false
  connectFrom.value = null
}

// ── Node Actions ───────────────────────────────────────
function deleteNode(nodeId: string) {
  // Also delete child connections
  const childConns = connections.value.filter(c => c.from === nodeId)
  childConns.forEach(c => deleteNode(c.to))
  nodes.value = nodes.value.filter(n => n.id !== nodeId)
  connections.value = connections.value.filter(c => c.from !== nodeId && c.to !== nodeId)
  if (activeNode.value?.id === nodeId) activeNode.value = null
  contextMenu.value.show = false
}

function duplicateNode(nodeId: string) {
  const orig = nodes.value.find(n => n.id === nodeId)
  if (!orig) return
  const copy: AnyNode = {
    ...JSON.parse(JSON.stringify(orig)),
    id: `${orig.type}-${Date.now()}`,
    x: orig.x + 30,
    y: orig.y + 60,  // duplicate below
    selected: false
  }
  nodes.value.push(copy)
  contextMenu.value.show = false
}

function addBranch(branchType: 'upscale' | 'img2img' | 'video') {
  if (!connectFrom.value) return
  const sourceGen = nodes.value.find(n => n.id === connectFrom.value!.nodeId) as GenerationNode
  if (!sourceGen) return

  const newNode: BranchNode = {
    id: `${branchType}-${Date.now()}`,
    type: branchType,
    x: sourceGen.x + (connectFrom.value.imgIndex % 2 === 0 ? -120 : 120),
    y: sourceGen.y + 220,
    selected: false,
    sourceGenId: sourceGen.id,
    sourceImgIndex: connectFrom.value.imgIndex,
    image: '',
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }

  nodes.value.push(newNode)
  connections.value.push({
    id: `conn-${Date.now()}`,
    from: sourceGen.id,
    to: newNode.id,
    fromImgIndex: connectFrom.value.imgIndex
  })
  contextMenu.value.show = false
  isConnecting.value = false
  connectFrom.value = null
}

function addVariation(genId: string) {
  const gen = nodes.value.find(n => n.id === genId)
  if (!gen) return
  const newGen: GenerationNode = {
    id: `gen-${Date.now()}`,
    type: 'generation',
    x: gen.x + 320,
    y: gen.y,
    selected: false,
    images: ['', '', '', ''],
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }
  nodes.value.push(newGen)
  connections.value.push({ id: `conn-${Date.now()}`, from: gen.id, to: newGen.id })
}

function addUpscale(genId: string, imgIndex: number) {
  const gen = nodes.value.find(n => n.id === genId) as GenerationNode
  if (!gen) return
  const newNode: BranchNode = {
    id: `up-${Date.now()}`,
    type: 'upscale',
    x: gen.x + (imgIndex % 2 === 0 ? -130 : 130),
    y: gen.y + 240,
    selected: false,
    sourceGenId: gen.id,
    sourceImgIndex: imgIndex,
    image: '',
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }
  nodes.value.push(newNode)
  connections.value.push({ id: `conn-${Date.now()}`, from: gen.id, to: newNode.id, fromImgIndex: imgIndex })
}

// ── Add Voice Node ────────────────────────────────────
function addVoiceNode() {
  const cx = (-pan.value.x + (canvasRef.value?.clientWidth ?? 800) / 2) / zoom.value
  const cy = (-pan.value.y + (canvasRef.value?.clientHeight ?? 600) / 2) / zoom.value
  const newNode: VoiceNode = {
    id: `voice-${Date.now()}`,
    type: 'voice',
    x: cx - 100,
    y: cy,
    selected: false,
    content: '',
    voiceId: 'male-qn-qingse',
    voiceModel: 'speech-02-hd',
    audioUrl: '',
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }
  nodes.value.push(newNode)
  activeNode.value = newNode
  nodes.value.forEach(n => n.selected = n.id === newNode.id)
}

// ── Add Music Node ────────────────────────────────────
function addMusicNode() {
  const cx = (-pan.value.x + (canvasRef.value?.clientWidth ?? 800) / 2) / zoom.value
  const cy = (-pan.value.y + (canvasRef.value?.clientHeight ?? 600) / 2) / zoom.value
  const newNode: MusicNode = {
    id: `music-${Date.now()}`,
    type: 'music',
    x: cx - 100,
    y: cy,
    selected: false,
    content: '',
    musicModel: 'music-01',
    audioUrl: '',
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }
  nodes.value.push(newNode)
  activeNode.value = newNode
  nodes.value.forEach(n => n.selected = n.id === newNode.id)
}

// ── Send Voice ───────────────────────────────────────
async function sendVoice(nodeId: string) {
  const node = nodes.value.find(n => n.id === nodeId) as VoiceNode
  if (!node || !node.content.trim()) return
  isGenerating.value = true
  try {
    const resp = await apiClient.post('/voice/generate', {
      text: node.content,
      voice_id: node.voiceId,
      model: node.voiceModel,
    })
    const data = resp.data as { audio_url: string }
    node.audioUrl = data.audio_url
  } catch (err: any) {
    console.error('Voice generation failed:', err)
    alert(`Voice generation failed: ${err?.response?.data?.detail ?? err.message}`)
  } finally {
    isGenerating.value = false
  }
}

// ── Send Music ───────────────────────────────────────
async function sendMusic(nodeId: string) {
  const node = nodes.value.find(n => n.id === nodeId) as MusicNode
  if (!node || !node.content.trim()) return
  isGenerating.value = true
  try {
    const resp = await apiClient.post('/music/generate', {
      prompt: node.content,
      model: node.musicModel,
    })
    const data = resp.data as { audio_url: string }
    node.audioUrl = data.audio_url
  } catch (err: any) {
    console.error('Music generation failed:', err)
    alert(`Music generation failed: ${err?.response?.data?.detail ?? err.message}`)
  } finally {
    isGenerating.value = false
  }
}

// ── Connection Path ────────────────────────────────────
function getConnectionPath(conn: Connection) {
  const from = nodes.value.find(n => n.id === conn.from)
  const to = nodes.value.find(n => n.id === conn.to)
  if (!from || !to) return ''

  let fx = 0, fy = 0, tx = 0, ty = 0

  if (from.type === 'prompt') {
    fx = from.x + 140
    fy = from.y
    tx = to.x + 160
    ty = to.y + 200
  } else if (from.type === 'generation') {
    const idx = conn.fromImgIndex ?? 0
    const imgW = 156
    const imgH = 104
    const padL = 12
    const padT = 56
    const col = idx % 2
    const row = Math.floor(idx / 2)
    fx = from.x + padL + col * imgW + imgW / 2
    fy = from.y + padT + row * imgH + imgH
    tx = to.x + 100
    ty = to.y
  } else {
    // Branch node output
    fx = from.x + 100
    fy = from.y + 80
    tx = to.x + 100
    ty = to.y
  }

  const dx = Math.abs(tx - fx) * 0.5
  return `M ${fx} ${fy} C ${fx} ${fy + dx}, ${tx} ${ty - dx}, ${tx} ${ty}`
}

// MiniMax model mapping (frontend name → API model)
const modelMap: Record<string, string> = {
  'SDXL Turbo': 'image-01',
  'DALL-E 3': 'image-01',
  'Stable Diffusion': 'image-01',
  'Midjourney v6': 'image-01-live',
}

// ── Send Message ───────────────────────────────────────
async function sendMessage() {
  if (!inputText.value.trim()) return
  const promptId = `prompt-${Date.now()}`
  const genId = `gen-${Date.now() + 1}`

  const cx = (-pan.value.x + canvasRef.value!.clientWidth / 2) / zoom.value
  const cy = (-pan.value.y + canvasRef.value!.clientHeight / 2) / zoom.value

  const promptNode: PromptNode = {
    id: promptId,
    type: 'prompt',
    x: cx - 140,
    y: cy + 100,
    selected: false,
    content: inputText.value,
    refImage: '',
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }

  const genNode: GenerationNode = {
    id: genId,
    type: 'generation',
    x: cx - 160,
    y: cy - 120,
    selected: false,
    images: ['', '', '', ''],
    time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  }

  nodes.value.push(promptNode, genNode)
  connections.value.push({ id: `conn-${Date.now()}`, from: promptId, to: genId })

  inputText.value = ''
  isGenerating.value = true

  try {
    const resp = await apiClient.post('/image/generate', {
      prompt: promptNode.content,
      model: modelMap[selectedModel.value] ?? 'image-01',
      aspect_ratio: selectedAspect.value,
      n: 4,
      response_format: 'url',
      prompt_optimizer: false,
    })
    const data = resp.data as { image_urls: string[] }
    // Fill up to 4 image slots
    for (let i = 0; i < Math.min(data.image_urls.length, 4); i++) {
      genNode.images[i] = data.image_urls[i]
    }
  } catch (err: any) {
    console.error('生成失败:', err)
    alert(`生成失败: ${err?.response?.data?.detail ?? err.message ?? '未知错误'}`)
  } finally {
    isGenerating.value = false
  }
}

// ── Auto Layout ───────────────────────────────────────
function autoLayout() {
  const prompts = nodes.value.filter(n => n.type === 'prompt')
  prompts.forEach((prompt, pi) => {
    const baseY = 580 + pi * 500
    prompt.x = 400
    prompt.y = baseY

    const gens = connections.value
      .filter(c => c.from === prompt.id)
      .map(c => nodes.value.find(n => n.id === c.to))
      .filter(n => n?.type === 'generation') as GenerationNode[]

    gens.forEach((gen, _gi) => {
      gen.x = prompt.x
      gen.y = baseY - 360

      // Branch nodes
      const branches = connections.value
        .filter(c => c.from === gen.id)
        .map(c => nodes.value.find(n => n.id === c.to))
        .filter(Boolean) as BranchNode[]

      branches.forEach((branch, bi) => {
        branch.x = gen.x + (bi % 2 === 0 ? -140 : 140)
        branch.y = gen.y + 240
      })
    })
  })
}

// ── Zoom Controls ─────────────────────────────────────
function zoomIn() { zoom.value = Math.min(zoom.value * 1.2, 3) }
function zoomOut() { zoom.value = Math.max(zoom.value / 1.2, 0.2) }
function zoomReset() { zoom.value = 1; pan.value = { x: 0, y: 0 } }

// ── Global listeners ───────────────────────────────────
function globalMouseUp(e: MouseEvent) {
  isPanning.value = false
  draggingNode.value = null
  if (isConnecting.value) {
    onCanvasMouseUpWhileConnecting(e)
  }
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Delete' && activeNode.value) {
    deleteNode(activeNode.value.id)
  }
  if (e.key === 'Escape') {
    contextMenu.value.show = false
    isConnecting.value = false
    connectFrom.value = null
    nodes.value.forEach(n => n.selected = false)
    activeNode.value = null
  }
}

onMounted(() => {
  window.addEventListener('mouseup', globalMouseUp)
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('click', closeContextMenu)
})

onUnmounted(() => {
  window.removeEventListener('mouseup', globalMouseUp)
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('click', closeContextMenu)
})

// Branch type colors
const branchColor: Record<string, string> = {
  upscale: '#00d9ff',
  img2img: '#a855f7',
  video: '#f59e0b',
  voice: '#22d3ee',
  music: '#f97316'
}
const branchLabel: Record<string, string> = {
  upscale: 'UPSCAL',
  img2img: 'IMG2IMG',
  video: 'VIDEO',
  voice: 'VOICE',
  music: 'MUSIC'
}
</script>

<template>
  <div class="generate-page" @keydown="onKeyDown">
    <!-- Left Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-top">
        <div class="brand">
          <svg class="brand-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          </svg>
          <span class="brand-name">AI 图片生成器</span>
        </div>
        <button class="new-canvas-btn" @click="zoomReset">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          新建画布
        </button>
      </div>

      <div class="sidebar-section">
        <span class="section-label">画布控制</span>
        <div class="sidebar-btns">
          <button class="sidebar-action-btn" @click="zoomIn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35M11 8v6M8 11h6"/>
            </svg>
            放大
          </button>
          <button class="sidebar-action-btn" @click="zoomOut">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35M8 11h6"/>
            </svg>
            缩小
          </button>
          <button class="sidebar-action-btn" @click="zoomReset">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
              <path d="M3 3v5h5"/>
            </svg>
            重置视图
          </button>
        </div>
      </div>

      <div class="sidebar-section">
        <span class="section-label">节点</span>
        <div class="sidebar-btns">
          <button class="sidebar-action-btn" @click="autoLayout">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
              <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
            </svg>
            自动布局
          </button>
          <button class="sidebar-action-btn" @click="() => { nodes = []; connections = []; activeNode = null }">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            清空全部
          </button>
        </div>
      </div>

      <div class="sidebar-section">
        <span class="section-label">快捷操作</span>
        <div class="sidebar-btns">
          <button
            class="sidebar-action-btn"
            @click="addVariation(activeNode?.id || '')"
            :disabled="!activeNode || activeNode.type !== 'generation'"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <path d="M1 4v6h6M23 20v-6h-6"/>
              <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
            </svg>
            添加变体
          </button>
          <button
            class="sidebar-action-btn"
            @click="addUpscale(activeNode?.id || '', 0)"
            :disabled="!activeNode || activeNode.type !== 'generation'"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
            添加放大
          </button>
        </div>
      </div>

      <div class="sidebar-section">
        <span class="section-label">音频</span>
        <div class="sidebar-btns">
          <button class="sidebar-action-btn" @click="addVoiceNode">
            <svg viewBox="0 0 24 24" fill="none" stroke="#22d3ee" stroke-width="2" width="13" height="13">
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
            </svg>
            新建语音
          </button>
          <button class="sidebar-action-btn" @click="addMusicNode">
            <svg viewBox="0 0 24 24" fill="none" stroke="#f97316" stroke-width="2" width="13" height="13">
              <path d="M9 18V5l12-2v13"/>
              <circle cx="6" cy="18" r="3"/>
              <circle cx="18" cy="16" r="3"/>
            </svg>
            新建音乐
          </button>
        </div>
      </div>

      <div class="sidebar-node-list">
        <span class="section-label">节点 ({{ nodes.length }})</span>
        <div class="node-list-items">
          <button
            v-for="node in nodes"
            :key="node.id"
            class="node-list-item"
            :class="{ active: activeNode?.id === node.id }"
            @click="() => {
              activeNode = node
              nodes.forEach(n => n.selected = n.id === node.id)
            }"
          >
            <span class="node-type-dot" :class="node.type"></span>
            <span class="node-list-label">{{ node.type }}</span>
          </button>
        </div>
      </div>

      <div class="sidebar-bottom">
        <div class="user-info">
          <div class="user-avatar">A</div>
          <div class="user-details">
            <span class="user-name">admin</span>
            <span class="user-plan">专业版</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- Center: Infinite Canvas -->
    <main
      class="canvas-container"
      ref="canvasRef"
      @mousedown="onCanvasMouseDown"
      @mousemove="onCanvasMouseMove"
      @wheel.prevent="onWheel"
    >
      <!-- SVG Connections Layer -->
      <svg class="connections-svg" :style="{ transform: canvasTransform }">
        <defs>
          <marker id="arrow-up" markerWidth="10" markerHeight="8" refX="5" refY="4" orient="auto">
            <polygon points="0 8, 5 0, 10 8" fill="#00d9ff" opacity="0.7"/>
          </marker>
          <marker id="arrow-down" markerWidth="10" markerHeight="8" refX="5" refY="4" orient="auto">
            <polygon points="0 0, 5 8, 10 0" fill="#00d9ff" opacity="0.7"/>
          </marker>
        </defs>

        <!-- Existing connections -->
        <path
          v-for="conn in connections"
          :key="conn.id"
          :d="getConnectionPath(conn)"
          fill="none"
          :stroke="branchColor[conn.from] || '#00d9ff'"
          :stroke-width="1.5"
          :stroke-opacity="0.5"
          :marker-end="conn.from.includes('gen') ? 'url(#arrow-down)' : 'url(#arrow-up)'"
          class="connection-path"
          @contextmenu.prevent="(e) => {
            e.preventDefault()
            // Remove connection on right-click
            connections = connections.filter(c => c.id !== conn.id)
          }"
        />

        <!-- Temp connecting line -->
        <path
          v-if="isConnecting"
          :d="tempConnPath"
          fill="none"
          stroke="#00d9ff"
          stroke-width="1.5"
          stroke-opacity="0.6"
          stroke-dasharray="6 4"
        />
      </svg>

      <!-- Dot Grid Background -->
      <div class="canvas-bg dot-grid"></div>

      <!-- Nodes Canvas -->
      <div class="nodes-canvas" :style="{ transform: canvasTransform }">

        <!-- PROMPT NODE (bottom) -->
        <div
          v-for="node in nodes.filter(n => n.type === 'prompt')"
          :key="node.id"
          class="node prompt-node"
          :class="{ selected: node.selected, dragging: draggingNode === node.id }"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @mousedown="(e) => onNodeMouseDown(e, node.id)"
          @contextmenu="(e) => onNodeRightClick(e, node.id)"
        >
          <div class="node-header">
            <span class="node-tag prompt-tag">PROMPT</span>
            <span class="node-time">{{ (node as PromptNode).time }}</span>
          </div>
          <div class="prompt-content">
            {{ (node as PromptNode).content }}
          </div>
          <!-- Reference image thumbnail (bottom-left) -->
          <div v-if="(node as PromptNode).refImage" class="ref-thumb">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="14" height="14">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <path d="M21 15l-5-5L5 21"/>
            </svg>
          </div>
          <div class="node-toolbar">
            <button class="tool-btn" title="Copy" @click.stop="duplicateNode(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
            </button>
            <button class="tool-btn danger" title="Delete" @click.stop="deleteNode(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- GENERATION NODE (middle/upper) -->
        <div
          v-for="node in nodes.filter(n => n.type === 'generation')"
          :key="node.id"
          class="node generation-node"
          :class="{ selected: node.selected, dragging: draggingNode === node.id }"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @mousedown="(e) => onNodeMouseDown(e, node.id)"
          @contextmenu="(e) => onNodeRightClick(e, node.id)"
        >
          <div class="node-header">
            <span class="node-tag gen-tag">GENERATED</span>
            <span class="node-badge">2×2</span>
            <span class="node-time">{{ (node as GenerationNode).time }}</span>
          </div>

          <!-- 2x2 Image Grid -->
          <div class="gen-images">
            <div
              v-for="(_img, i) in (node as GenerationNode).images"
              :key="i"
              class="gen-img-slot"
              @mousedown.stop="onImageConnectStart($event, node.id, i)"
            >
              <div class="gen-img-placeholder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="24" height="24">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="8.5" cy="8.5" r="1.5"/>
                  <path d="M21 15l-5-5L5 21"/>
                </svg>
              </div>

              <!-- Hover toolbar per image -->
              <div class="img-hover-toolbar">
                <button class="img-tool-btn" title="Download">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                  </svg>
                </button>
                <button class="img-tool-btn" title="Favorite">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                  </svg>
                </button>
                <button class="img-tool-btn" title="Regenerate">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                    <path d="M23 4v6h-6M1 20v-6h6"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                  </svg>
                </button>
                <button class="img-tool-btn danger" title="Delete" @click.stop="() => {}">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                </button>
              </div>

              <!-- "引用此图" label below image -->
              <div class="ref-img-label">↓ 引用此图</div>
            </div>
          </div>

          <div class="node-toolbar">
            <button class="tool-btn" title="Variation" @click.stop="addVariation(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <path d="M1 4v6h6M23 20v-6h-6"/>
                <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
              </svg>
            </button>
            <button class="tool-btn" title="Upscale" @click.stop="addUpscale(node.id, 0)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
              </svg>
            </button>
            <button class="tool-btn" title="Favorite">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
            </button>
            <button class="tool-btn danger" title="Delete" @click.stop="deleteNode(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- BRANCH NODES (below generation, from single images) -->
        <div
          v-for="node in nodes.filter(n => n.type !== 'prompt' && n.type !== 'generation')"
          :key="node.id"
          class="node branch-node"
          :class="['branch-' + node.type, { selected: node.selected, dragging: draggingNode === node.id }]"
          :style="{
            left: node.x + 'px',
            top: node.y + 'px',
            borderColor: branchColor[node.type] + '40',
          }"
          @mousedown="(e) => onNodeMouseDown(e, node.id)"
          @contextmenu="(e) => onNodeRightClick(e, node.id)"
        >
          <div class="node-header">
            <span class="node-tag" :style="{ background: branchColor[node.type] + '22', color: branchColor[node.type] }">
              {{ branchLabel[node.type] }}
            </span>
            <span class="node-time">{{ (node as BranchNode).time }}</span>
          </div>

          <div class="branch-img">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="28" height="28">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <path d="M21 15l-5-5L5 21"/>
            </svg>
          </div>

          <div class="node-toolbar">
            <button class="tool-btn" title="Download">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
            </button>
            <button class="tool-btn danger" title="Delete" @click.stop="deleteNode(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- VOICE NODE -->
        <div
          v-for="node in nodes.filter(n => n.type === 'voice')"
          :key="node.id"
          class="node voice-node"
          :class="{ selected: node.selected, dragging: draggingNode === node.id }"
          :style="{ left: node.x + 'px', top: node.y + 'px', borderColor: branchColor['voice'] + '40' }"
          @mousedown="(e) => onNodeMouseDown(e, node.id)"
          @contextmenu="(e) => onNodeRightClick(e, node.id)"
        >
          <div class="node-header">
            <span class="node-tag" :style="{ background: branchColor['voice'] + '22', color: branchColor['voice'] }">VOICE</span>
            <span class="node-time">{{ (node as VoiceNode).time }}</span>
          </div>
          <div class="voice-content">
            <textarea
              class="voice-textarea"
              v-model="(node as VoiceNode).content"
              placeholder="输入要合成的文本..."
              rows="3"
            ></textarea>
            <div class="voice-controls">
              <select v-model="(node as VoiceNode).voiceId" class="voice-select">
                <option value="male-qn-qingse">male-qn-qingse</option>
                <option value="female-qn-qingse">female-qn-qingse</option>
                <option value="male-qn-baihua">male-qn-baihua</option>
                <option value="female-qn-baihua">female-qn-baihua</option>
              </select>
            </div>
            <audio v-if="(node as VoiceNode).audioUrl" :src="(node as VoiceNode).audioUrl" controls class="voice-audio"></audio>
          </div>
          <div class="node-toolbar">
            <button class="tool-btn" title="Generate Voice" @click.stop="sendVoice(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
              </svg>
            </button>
            <button class="tool-btn danger" title="Delete" @click.stop="deleteNode(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- MUSIC NODE -->
        <div
          v-for="node in nodes.filter(n => n.type === 'music')"
          :key="node.id"
          class="node music-node"
          :class="{ selected: node.selected, dragging: draggingNode === node.id }"
          :style="{ left: node.x + 'px', top: node.y + 'px', borderColor: branchColor['music'] + '40' }"
          @mousedown="(e) => onNodeMouseDown(e, node.id)"
          @contextmenu="(e) => onNodeRightClick(e, node.id)"
        >
          <div class="node-header">
            <span class="node-tag" :style="{ background: branchColor['music'] + '22', color: branchColor['music'] }">MUSIC</span>
            <span class="node-time">{{ (node as MusicNode).time }}</span>
          </div>
          <div class="music-content">
            <textarea
              class="music-textarea"
              v-model="(node as MusicNode).content"
              placeholder="描述你想要的音乐..."
              rows="3"
            ></textarea>
            <audio v-if="(node as MusicNode).audioUrl" :src="(node as MusicNode).audioUrl" controls class="music-audio"></audio>
          </div>
          <div class="node-toolbar">
            <button class="tool-btn" title="Generate Music" @click.stop="sendMusic(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <path d="M9 18V5l12-2v13"/>
                <circle cx="6" cy="18" r="3"/>
                <circle cx="18" cy="16" r="3"/>
              </svg>
            </button>
            <button class="tool-btn danger" title="Delete" @click.stop="deleteNode(node.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>


      </div><!-- /nodes-canvas -->

      <!-- Zoom indicator -->
      <div class="zoom-indicator">{{ Math.round(zoom * 100) }}%</div>

      <!-- Generating overlay hint -->
      <div v-if="isGenerating" class="generating-hint">
        <div class="gen-orbs"><div class="orb"></div><div class="orb"></div><div class="orb"></div></div>
        AI 正在创作你的图片...
      </div>
    </main>

    <!-- Right Panel -->
    <aside class="right-panel">
      <template v-if="activeNode">
        <div class="panel-section">
          <h3 class="section-title">节点信息</h3>
          <div class="info-grid">
            <div class="info-row">
              <span class="info-key">类型</span>
              <span class="info-val" :style="{ color: activeNode.type === 'prompt' ? '#a855f7' : activeNode.type === 'generation' ? '#00d9ff' : branchColor[activeNode.type] }">
                {{ activeNode.type.toUpperCase() }}
              </span>
            </div>
            <div class="info-row">
              <span class="info-key">位置</span>
              <span class="info-val">{{ Math.round(activeNode.x) }}, {{ Math.round(activeNode.y) }}</span>
            </div>
            <div class="info-row">
              <span class="info-key">ID</span>
              <span class="info-val id-val">{{ activeNode.id }}</span>
            </div>
          </div>
        </div>

        <template v-if="activeNode.type === 'prompt'">
          <div class="panel-section">
            <h3 class="section-title">提示词</h3>
            <div class="prompt-preview">{{ (activeNode as PromptNode).content }}</div>
          </div>
        </template>

        <template v-if="activeNode.type === 'generation'">
          <div class="panel-section">
            <h3 class="section-title">图片 ({{ (activeNode as GenerationNode).images.length }})</h3>
            <p class="panel-hint">点击图片开始分支连接</p>
          </div>
        </template>

        <div class="panel-section">
          <h3 class="section-title">参数</h3>
          <div class="param-list">
            <div class="param-item">
              <span class="param-key">模型</span>
              <select v-model="selectedModel" class="param-val-select">
                <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
              </select>
            </div>
            <div class="param-item">
              <span class="param-key">风格</span>
              <select v-model="selectedStyle" class="param-val-select">
                <option v-for="s in styles" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="param-item">
              <span class="param-key">比例</span>
              <select v-model="selectedAspect" class="param-val-select">
                <option v-for="a in aspects" :key="a" :value="a">{{ a }}</option>
              </select>
            </div>
          </div>
          <button class="regen-btn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <path d="M23 4v6h-6M1 20v-6h6"/>
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            重新生成
          </button>
        </div>

        <div class="panel-section">
          <h3 class="section-title">分支操作</h3>
          <div class="branch-btns">
            <button
              v-for="bt in (['upscale', 'img2img', 'video'] as const)"
              :key="bt"
              class="branch-btn"
              :style="{ borderColor: branchColor[bt] + '50', color: branchColor[bt] }"
              @click="addBranch(bt)"
              :disabled="!activeNode || activeNode.type !== 'generation'"
            >
              + {{ bt.toUpperCase() }}
            </button>
          </div>
        </div>

        <div class="panel-section">
          <h3 class="section-title">备注</h3>
          <textarea
            v-model="noteText"
            class="note-textarea"
            placeholder="添加关于此节点的备注..."
          ></textarea>
        </div>
      </template>

      <template v-else>
        <div class="empty-panel">
          <svg viewBox="0 0 24 24" fill="currentColor" width="32" height="32" style="color: rgba(0,217,255,0.25)">
            <path d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"/>
          </svg>
          <p>选择节点查看详情</p>
        </div>
      </template>
    </aside>

    <!-- Bottom Input Bar -->
    <div class="bottom-input-bar">
      <div class="input-row">
        <select v-model="selectedModel" class="param-select">
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
        <select v-model="selectedStyle" class="param-select">
          <option v-for="s in styles" :key="s" :value="s">{{ s }}</option>
        </select>
        <select v-model="selectedAspect" class="param-select">
          <option v-for="a in aspects" :key="a" :value="a">{{ a }}</option>
        </select>
      </div>
      <div class="input-box">
        <textarea
          v-model="inputText"
          class="prompt-textarea"
          placeholder="描述你想创作的内容... (Enter 发送)"
          rows="1"
          @keydown.enter.exact.prevent="sendMessage"
        ></textarea>
        <button class="send-btn" @click="sendMessage" :disabled="!inputText.trim() || isGenerating">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16">
            <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Context Menu (branch type selector) -->
    <Teleport to="body">
      <div
        v-if="contextMenu.show && !contextMenu.nodeId"
        class="context-menu branch-context"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <div class="ctx-title">添加分支节点</div>
        <button class="ctx-branch-btn upscale" @click="addBranch('upscale')">
          <svg viewBox="0 0 24 24" fill="none" stroke="#00d9ff" stroke-width="2" width="13" height="13">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
          </svg>
          放大 (超分辨率)
        </button>
        <button class="ctx-branch-btn img2img" @click="addBranch('img2img')">
          <svg viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2" width="13" height="13">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <path d="M21 15l-5-5L5 21"/>
          </svg>
          图生图
        </button>
        <button class="ctx-branch-btn video" @click="addBranch('video')">
          <svg viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" width="13" height="13">
            <polygon points="23 7 16 12 23 17 23 7"/>
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
          </svg>
          视频生成
        </button>
        <div class="ctx-divider"></div>
        <button class="ctx-item" @click="contextMenu.show = false">取消</button>
      </div>

      <div
        v-if="contextMenu.show && contextMenu.nodeId"
        class="context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <button class="ctx-item" @click="duplicateNode(contextMenu.nodeId!)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          复制
        </button>
        <div class="ctx-divider"></div>
        <button class="ctx-item danger" @click="deleteNode(contextMenu.nodeId!)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
          删除
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.generate-page {
  height: 100vh;
  display: flex;
  flex-direction: row;
  overflow: hidden;
  background: #0a0a0f;
}

/* ── Left Sidebar ────────────────────────────── */
.sidebar {
  width: 210px;
  flex-shrink: 0;
  background: #0d0d14;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding-bottom: 80px; /* space for bottom bar */
  z-index: 10;
}

.sidebar-top { padding: 14px 14px 10px; }

.brand {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
}

.brand-icon {
  width: 19px;
  height: 19px;
  color: #00d9ff;
  filter: drop-shadow(0 0 5px rgba(0, 217, 255, 0.5));
}

.brand-name {
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
}

.new-canvas-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 100%;
  padding: 7px;
  font-size: 11px;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  color: #000;
  background: linear-gradient(135deg, #00d9ff, #00b4d8);
  border: none;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.2s;
}

.new-canvas-btn:hover { box-shadow: 0 0 14px rgba(0, 217, 255, 0.4); }

.sidebar-section { padding: 8px 14px; }

.section-label {
  display: block;
  font-size: 9px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.25);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  margin-bottom: 5px;
}

.sidebar-btns { display: flex; flex-direction: column; gap: 3px; }

.sidebar-action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  font-size: 11px;
  font-family: 'Inter', sans-serif;
  color: rgba(255, 255, 255, 0.55);
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.sidebar-action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.85);
  border-color: rgba(255, 255, 255, 0.12);
}

.sidebar-action-btn:disabled { opacity: 0.3; cursor: not-allowed; }

.sidebar-node-list { padding: 8px 14px; flex: 1; }

.node-list-items {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 280px;
  overflow-y: auto;
}

.node-list-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 7px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.node-list-item:hover { background: rgba(255, 255, 255, 0.04); }
.node-list-item.active { background: rgba(0, 217, 255, 0.08); border-color: rgba(0, 217, 255, 0.2); }

.node-type-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.node-type-dot.prompt { background: #a855f7; box-shadow: 0 0 4px #a855f7; }
.node-type-dot.generation { background: #00d9ff; box-shadow: 0 0 4px #00d9ff; }
.node-type-dot.upscale { background: #00d9ff; box-shadow: 0 0 4px #00d9ff; }
.node-type-dot.img2img { background: #a855f7; box-shadow: 0 0 4px #a855f7; }
.node-type-dot.video { background: #f59e0b; box-shadow: 0 0 4px #f59e0b; }

.node-list-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  text-transform: capitalize;
}

.sidebar-bottom {
  padding: 10px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: auto;
}

.user-info { display: flex; align-items: center; gap: 7px; }

.user-avatar {
  width: 27px;
  height: 27px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6b21a8, #a855f7);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.user-details { display: flex; flex-direction: column; gap: 1px; }
.user-name { font-size: 11px; font-weight: 600; color: #fff; }
.user-plan { font-size: 9px; color: #a855f7; }

/* ── Canvas ──────────────────────────────────── */
.canvas-container {
  flex: 1;
  position: relative;
  overflow: hidden;
  cursor: grab;
}

.canvas-container:active { cursor: grabbing; }

.dot-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(255, 255, 255, 0.07) 1px, transparent 1px);
  background-size: 28px 28px;
  pointer-events: none;
}

.connections-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}

.connection-path {
  transition: stroke-opacity 0.2s;
  cursor: pointer;
}

.connection-path:hover { stroke-opacity: 1; stroke-width: 2; }

.nodes-canvas {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  will-change: transform;
}

/* ── Nodes ────────────────────────────────────── */
.node {
  position: absolute;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: #1a1a24;
  cursor: move;
  user-select: none;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.node:hover { border-color: rgba(255, 255, 255, 0.15); }

.node.selected {
  border-color: #00d9ff;
  box-shadow: 0 0 0 2px rgba(0, 217, 255, 0.25), 0 0 20px rgba(0, 217, 255, 0.1);
}

.node.dragging {
  opacity: 0.92;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), 0 0 0 2px rgba(0, 217, 255, 0.3);
  z-index: 100;
}

/* Node Header */
.node-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 10px 0;
}

.node-tag {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.8px;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.prompt-tag {
  background: rgba(168, 85, 247, 0.2);
  color: #a855f7;
  border: 1px solid rgba(168, 85, 247, 0.3);
}

.gen-tag {
  background: rgba(0, 217, 255, 0.12);
  color: #00d9ff;
  border: 1px solid rgba(0, 217, 255, 0.2);
}

.node-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(0, 217, 255, 0.15);
  color: #00d9ff;
  border: 1px solid rgba(0, 217, 255, 0.2);
}

.node-time {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.25);
  margin-left: auto;
}

/* Prompt Node */
.prompt-node {
  width: 280px;
  padding: 8px 12px 10px;
  border-color: rgba(168, 85, 247, 0.3);
  background: linear-gradient(180deg, rgba(107, 33, 168, 0.25), rgba(168, 85, 247, 0.1));
}

.prompt-content {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  line-height: 1.5;
  margin: 8px 0 6px;
  max-height: 80px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
}

.ref-thumb {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 7px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 5px;
  color: rgba(255, 255, 255, 0.35);
  font-size: 9px;
  margin-bottom: 4px;
}

/* Generation Node */
.generation-node {
  width: 320px;
  padding: 8px 10px 10px;
}

.gen-images {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 5px;
  margin: 8px 0 6px;
}

.gen-img-slot {
  position: relative;
  aspect-ratio: 1;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 7px;
  cursor: crosshair;
  overflow: hidden;
  transition: border-color 0.2s;
}

.gen-img-slot:hover { border-color: rgba(0, 217, 255, 0.35); }

.gen-img-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.1);
}

/* Per-image hover toolbar */
.img-hover-toolbar {
  position: absolute;
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 3px;
  opacity: 0;
  transition: opacity 0.15s;
}

.gen-img-slot:hover .img-hover-toolbar { opacity: 1; }

.img-tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 5px;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  transition: all 0.15s;
}

.img-tool-btn:hover { background: rgba(0, 217, 255, 0.2); border-color: rgba(0, 217, 255, 0.4); color: #00d9ff; }
.img-tool-btn.danger:hover { background: rgba(239, 68, 68, 0.2); border-color: rgba(239, 68, 68, 0.4); color: #ef4444; }

/* "引用此图" label */
.ref-img-label {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 8px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  padding: 3px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.6));
  opacity: 0;
  transition: opacity 0.15s;
}

.gen-img-slot:hover .ref-img-label { opacity: 1; }

/* Branch Nodes */
.branch-node {
  width: 200px;
  padding: 8px 10px 10px;
  border-style: dashed;
  background: rgba(10, 10, 15, 0.8);
}

.branch-img {
  aspect-ratio: 16/9;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.1);
  margin: 8px 0 6px;
}

/* Voice Node */
.voice-node {
  width: 220px;
}
.voice-content {
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.voice-textarea {
  width: 100%;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(34, 211, 238, 0.15);
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 11px;
  font-family: inherit;
  resize: none;
  padding: 6px 8px;
  box-sizing: border-box;
}
.voice-textarea:focus {
  outline: none;
  border-color: rgba(34, 211, 238, 0.4);
}
.voice-select {
  width: 100%;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(34, 211, 238, 0.15);
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 11px;
  padding: 4px 6px;
  cursor: pointer;
}
.voice-audio {
  width: 100%;
  height: 28px;
  border-radius: 4px;
}

/* Music Node */
.music-node {
  width: 220px;
}
.music-content {
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.music-textarea {
  width: 100%;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(249, 115, 22, 0.15);
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.8);
  font-size: 11px;
  font-family: inherit;
  resize: none;
  padding: 6px 8px;
  box-sizing: border-box;
}
.music-textarea:focus {
  outline: none;
  border-color: rgba(249, 115, 22, 0.4);
}
.music-audio {
  width: 100%;
  height: 28px;
  border-radius: 4px;
}

/* Node Toolbar */
.node-toolbar {
  display: flex;
  gap: 3px;
  opacity: 0;
  transition: opacity 0.15s;
}

.node:hover .node-toolbar { opacity: 1; }

.tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 5px;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
  transition: all 0.15s;
}

.tool-btn:hover { background: rgba(0, 217, 255, 0.15); border-color: rgba(0, 217, 255, 0.3); color: #00d9ff; }
.tool-btn.danger:hover { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.3); color: #ef4444; }

/* Zoom Indicator */
.zoom-indicator {
  position: absolute;
  bottom: 90px;
  right: 16px;
  font-size: 10px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.3);
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  padding: 4px 9px;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  pointer-events: none;
}

/* Generating hint */
.generating-hint {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(13, 13, 20, 0.9);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 217, 255, 0.2);
  border-radius: 10px;
  padding: 10px 18px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  pointer-events: none;
}

.gen-orbs { display: flex; gap: 4px; }
.orb {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #00d9ff;
  animation: orbBounce 1.4s ease-in-out infinite;
}
.orb:nth-child(2) { animation-delay: 0.2s; }
.orb:nth-child(3) { animation-delay: 0.4s; }
@keyframes orbBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

/* ── Right Panel ─────────────────────────────── */
.right-panel {
  width: 230px;
  flex-shrink: 0;
  background: #0d0d14;
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-bottom: 90px;
}

.right-panel::-webkit-scrollbar { width: 3px; }
.right-panel::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

.panel-section { display: flex; flex-direction: column; gap: 7px; }

.section-title {
  font-size: 9px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.3);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  margin: 0;
}

.panel-hint {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  margin: 0;
  font-style: italic;
}

.info-grid { display: flex; flex-direction: column; gap: 4px; }
.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.info-key { font-size: 11px; color: rgba(255, 255, 255, 0.4); }
.info-val { font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.8); }
.id-val { font-size: 9px; font-family: monospace; color: rgba(0, 217, 255, 0.5); }

.prompt-preview {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.5;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 7px;
  padding: 8px 10px;
  word-break: break-word;
}

.param-list { display: flex; flex-direction: column; gap: 4px; }
.param-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.param-key { font-size: 11px; color: rgba(255, 255, 255, 0.4); }
.param-val-select {
  font-size: 10px;
  font-family: 'Inter', sans-serif;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  padding: 2px 5px;
  outline: none;
}
.param-val-select option { background: #1a1a2e; }

.regen-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 7px;
  margin-top: 5px;
  font-size: 11px;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  color: #000;
  background: linear-gradient(135deg, #00d9ff, #00b4d8);
  border: none;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.2s;
}
.regen-btn:hover { box-shadow: 0 0 14px rgba(0, 217, 255, 0.4); }

.branch-btns { display: flex; flex-direction: column; gap: 4px; }
.branch-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 7px 10px;
  font-size: 11px;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  background: transparent;
  border: 1px solid;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}
.branch-btn:hover:not(:disabled) { background: rgba(255, 255, 255, 0.04); }
.branch-btn:disabled { opacity: 0.3; cursor: not-allowed; }

.note-textarea {
  width: 100%;
  min-height: 65px;
  padding: 8px;
  font-size: 11px;
  font-family: 'Inter', sans-serif;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 7px;
  outline: none;
  resize: vertical;
  line-height: 1.5;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.note-textarea::placeholder { color: rgba(255, 255, 255, 0.25); }
.note-textarea:focus { border-color: rgba(0, 217, 255, 0.3); }

.empty-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}
.empty-panel p { font-size: 11px; color: rgba(255, 255, 255, 0.3); margin: 0; }

/* ── Bottom Input Bar ─────────────────────────── */
.bottom-input-bar {
  position: absolute;
  bottom: 0;
  left: 210px;
  right: 230px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  background: rgba(10, 10, 15, 0.97);
  backdrop-filter: blur(16px);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  padding: 10px 16px;
  z-index: 20;
}

.input-row {
  display: flex;
  gap: 5px;
}

.param-select {
  flex: 1;
  padding: 5px 7px;
  font-size: 10px;
  font-family: 'Inter', sans-serif;
  color: rgba(255, 255, 255, 0.6);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 6px;
  outline: none;
  cursor: pointer;
}
.param-select option { background: #1a1a2e; color: #fff; }

.input-box {
  display: flex;
  align-items: flex-end;
  gap: 7px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 7px 7px 7px 14px;
  transition: border-color 0.2s;
}
.input-box:focus-within { border-color: rgba(0, 217, 255, 0.4); }

.prompt-textarea {
  flex: 1;
  font-size: 12px;
  font-family: 'Inter', sans-serif;
  color: #fff;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  line-height: 1.5;
  max-height: 100px;
}
.prompt-textarea::placeholder { color: rgba(255, 255, 255, 0.3); }

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #00d9ff, #00b4d8);
  border: none;
  border-radius: 50%;
  color: #000;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.send-btn:hover:not(:disabled) { box-shadow: 0 0 16px rgba(0, 217, 255, 0.5); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Context Menu ─────────────────────────────── */
.context-menu {
  position: fixed;
  background: rgba(13, 13, 22, 0.98);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 5px;
  min-width: 155px;
  z-index: 9999;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.ctx-title {
  font-size: 10px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.4);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  padding: 5px 10px 6px;
}

.ctx-item {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 7px 10px;
  font-size: 12px;
  font-family: 'Inter', sans-serif;
  color: rgba(255, 255, 255, 0.7);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}
.ctx-item:hover { background: rgba(255, 255, 255, 0.06); color: rgba(255, 255, 255, 0.95); }
.ctx-item.danger:hover { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

.ctx-branch-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  font-size: 12px;
  font-family: 'Inter', sans-serif;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}
.ctx-branch-btn:hover { background: rgba(255, 255, 255, 0.05); }
.ctx-branch-btn.upscale { color: #00d9ff; border-color: rgba(0, 217, 255, 0.2); }
.ctx-branch-btn.img2img { color: #a855f7; border-color: rgba(168, 85, 247, 0.2); }
.ctx-branch-btn.video { color: #f59e0b; border-color: rgba(245, 158, 11, 0.2); }

.ctx-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.06);
  margin: 4px 0;
}
</style>
