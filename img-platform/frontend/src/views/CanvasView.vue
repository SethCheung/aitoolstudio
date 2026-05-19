<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  embedded?: boolean
  embeddedConversationId?: number | null
}>()

import {
  Handle,
  MarkerType,
  Position,
  VueFlow,
  useVueFlow,
  type Connection,
} from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import api from '@/services/api'

type CanvasNodeType = 'text' | 'media' | 'workflow' | 'video' | 'output' | 'llm' | 'loop'
type RunStatus = 'idle' | 'running' | 'success' | 'error' | 'done'

interface ComfyWorkflow {
  id: string
  name: string
  description?: string
  category: string
  enabled: boolean
  workflow_json?: Record<string, unknown>
  notes?: string
}

interface CanvasNodeData {
  title: string
  body?: string
  hint?: string
  assetUrl?: string
  workflowId?: string
  workflowCategory?: string
  workflowNotes?: string
  nodeCount?: number
  mode?: string
  model?: string
  spec?: string
  quantity?: number
  aspectRatio?: string
  seed?: number | null
  status?: RunStatus
  error?: string
  results?: string[]
  images?: { url: string; run_id?: number; generation_id?: number; source_node_id?: string; prompt?: string; created_at?: string }[]
  systemPrompt?: string
  outputText?: string
  sourceRunId?: number
  sourceGenerationId?: number
  sourceNodeId?: string
  sourcePrompt?: string
  sourceCreatedAt?: string
  count?: number
  loopStart?: number
  fixedPrompt?: string
  variablePrompt?: string
  lastRendered?: string
  lastIteration?: number
}

interface SavedCanvas {
  nodes: any[]
  edges: any[]
  documentId?: number
}

const STORAGE_KEY = 'aitoolstudio.pipeline.canvas.v1'

const router = useRouter()
onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', closeContextMenu)
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', closeContextMenu)
})
const { fitView, zoomIn, zoomOut } = useVueFlow()

const workflows = ref<ComfyWorkflow[]>([])
const workflowsLoading = ref(false)
const workflowError = ref('')
const workflowQuery = ref('')
const workflowModalOpen = ref(false)
const activeTool = ref<'assets' | 'workflows'>('workflows')
const selectedNodeId = ref<string | null>(null)
const showNodeMenu = ref(false)
const historyDrawerOpen = ref(false)
const promptDraft = ref('')
const assetDraft = ref('')
const aspectDraft = ref('1:1')
const quantityDraft = ref(1)
const seedDraft = ref('')
const runError = ref('')
const previewImage = ref<string | null>(null)
const agentOpen = ref(false)
const agentLoading = ref(false)
const agentQuestion = ref('下一步我该怎么搭这个流水线？')
const agentAnswer = ref('选中一个节点后，我可以根据当前画布、连线和可用工作流，告诉你下一步该加什么、怎么填 prompt、该选哪个 workflow。')
const canvasDocumentId = ref<number | null>(null)
const contextMenu = ref<{ x: number; y: number; nodeId: string | null; visible: boolean }>({
  x: 0, y: 0, nodeId: null, visible: false,
})
const selectedEdgeId = ref<string | null>(null)
const canvasSaveState = ref<'local' | 'saving' | 'saved' | 'error'>('local')
const isHydratingCanvas = ref(false)
let canvasSaveTimer: number | null = null

const nodes = ref<any[]>([
  {
    id: 'text-seed',
    type: 'text',
    position: { x: 140, y: 210 },
    data: {
      title: 'Text',
      body: '描述你想生成的内容。这个文本节点可以连接到图片、视频或 ComfyUI workflow 节点。',
      mode: 'Prompt',
      model: 'M2.7',
      status: 'idle',
    },
  },
  {
    id: 'workflow-preview',
    type: 'workflow',
    position: { x: 650, y: 170 },
    data: {
      title: '选择一个 Workflow',
      body: '打开左侧工作流，插入后台启用的 ComfyUI workflow 后再运行。',
      hint: '先替换成真实 workflow',
      mode: '全能参考',
      model: 'ComfyUI',
      spec: 'image / ComfyUI',
      quantity: 1,
      aspectRatio: '1:1',
      status: 'idle',
      results: [],
    },
  },
])

const edges = ref<any[]>([
  {
    id: 'edge-text-workflow',
    source: 'text-seed',
    target: 'workflow-preview',
    type: 'smoothstep',
    animated: true,
    markerEnd: MarkerType.ArrowClosed,
    style: { stroke: 'rgba(255,255,255,.45)', strokeWidth: 3 },
    data: { promptOrder: 1 },
  },
])

const selectedNode = computed((): any => nodes.value.find((node) => node.id === selectedNodeId.value) || null)
const selectedData = computed((): CanvasNodeData | undefined => selectedNode.value?.data)
const selectedCanRun = computed(() => selectedNode.value?.type === 'workflow' || selectedNode.value?.type === 'video' || selectedNode.value?.type === 'llm')
const canCascadeRun = computed(() => selectedNode.value?.type === 'workflow' || selectedNode.value?.type === 'video')
const selectedIsMedia = computed(() => selectedNode.value?.type === 'media')
const selectedIncomingPairs = computed(() => selectedNode.value ? incomingNodePairs(selectedNode.value.id) : [])
const nodeStats = computed(() => ({
  text: nodes.value.filter((node) => node.type === 'text').length,
  media: nodes.value.filter((node) => node.type === 'media').length,
  workflow: nodes.value.filter((node) => node.type === 'workflow' || node.type === 'video').length,
  output: nodes.value.filter((node) => node.type === 'output').length,
  llm: nodes.value.filter((node) => node.type === 'llm').length,
  loop: nodes.value.filter((node) => node.type === 'loop').length,
  edges: edges.value.length,
}))
const resultHistory = computed(() => nodes.value
  .filter((node) => node.type === 'media' && (node.data?.assetUrl || node.data?.results?.length))
  .map((node) => ({
    id: node.id,
    title: node.data?.title || '生成结果',
    url: node.data?.assetUrl || node.data?.results?.[0],
    model: node.data?.model || 'ComfyUI',
  }))
  .filter((item) => item.url)
  .slice(-12)
  .reverse())
const quickPrompts = [
  '产品主图，白底，真实摄影，高级电商质感',
  '欧美模特自然穿戴展示，产品清晰不变形',
  '侧面 45 度展示，保留材质细节，背景干净',
  '俯视角度产品展示，构图居中，高清细节',
]
const categories = computed(() => {
  const values = workflows.value.map((workflow) => workflow.category || 'image')
  return ['all', ...Array.from(new Set(values))]
})
const activeWorkflowCategory = ref('all')
const filteredWorkflows = computed(() => {
  const query = workflowQuery.value.trim().toLowerCase()
  return workflows.value.filter((workflow) => {
    const categoryMatch = activeWorkflowCategory.value === 'all' || workflow.category === activeWorkflowCategory.value
    const queryMatch = !query || [workflow.name, workflow.description, workflow.category, workflow.notes, workflow.id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query))
    return categoryMatch && queryMatch
  })
})

function safeNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function uniqueId(prefix: string, index = 0) {
  return `${prefix}-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 7)}`
}

function persistCanvas() {
  const payload = { nodes: nodes.value, edges: edges.value, documentId: canvasDocumentId.value || undefined } as SavedCanvas
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  scheduleRemoteSave()
}

function restoreCanvas() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (!saved) return
  try {
    const payload = JSON.parse(saved) as SavedCanvas
    if (Array.isArray(payload.nodes) && Array.isArray(payload.edges)) {
      nodes.value = payload.nodes
      edges.value = payload.edges
      canvasDocumentId.value = payload.documentId || null
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY)
  }
}

function graphPayload() {
  return {
    title: '流水线',
    viewport: {},
    nodes: nodes.value.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position || { x: 0, y: 0 },
      width: node.width,
      height: node.height,
      data: node.data || {},
    })),
    edges: edges.value.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      type: edge.type,
      data: edge.data || {},
    })),
  }
}

function applyRemoteGraph(payload: any) {
  if (!payload?.nodes?.length) return
  isHydratingCanvas.value = true
  canvasDocumentId.value = payload.id
  nodes.value = payload.nodes
  edges.value = payload.edges || []
  nextTick(() => {
    isHydratingCanvas.value = false
    resetCanvasView()
  })
}

async function saveCanvasRemote() {
  if (!canvasDocumentId.value || isHydratingCanvas.value) return
  canvasSaveState.value = 'saving'
  try {
    await api.put(`/api/canvas/documents/${canvasDocumentId.value}/graph`, graphPayload())
    canvasSaveState.value = 'saved'
  } catch {
    canvasSaveState.value = 'error'
  }
}

function scheduleRemoteSave() {
  if (!canvasDocumentId.value || isHydratingCanvas.value) return
  if (canvasSaveTimer) window.clearTimeout(canvasSaveTimer)
  canvasSaveTimer = window.setTimeout(() => {
    saveCanvasRemote()
  }, 700)
}

async function loadOrCreateCanvasDocument() {
  try {
    // If embedded in a project, use the conversation-bound endpoint
    if (props.embeddedConversationId) {
      const response = await api.get(
        `/api/canvas/documents/by-conversation/${props.embeddedConversationId}`
      )
      applyRemoteGraph(response.data)
      canvasSaveState.value = 'saved'
      return
    }

    const savedId = canvasDocumentId.value
    if (savedId) {
      const response = await api.get(`/api/canvas/documents/${savedId}`)
      applyRemoteGraph(response.data)
      canvasSaveState.value = 'saved'
      return
    }

    const listResponse = await api.get('/api/canvas/documents')
    const first = listResponse.data?.[0]
    if (first?.id) {
      const response = await api.get(`/api/canvas/documents/${first.id}`)
      applyRemoteGraph(response.data)
      canvasSaveState.value = 'saved'
      return
    }

    const createResponse = await api.post('/api/canvas/documents', { title: '流水线' })
    canvasDocumentId.value = createResponse.data?.id || null
    await saveCanvasRemote()
  } catch {
    canvasSaveState.value = 'local'
  }
}

async function fetchWorkflows() {
  workflowsLoading.value = true
  workflowError.value = ''
  try {
    const response = await api.get('/api/comfyui/workflows')
    workflows.value = response.data?.workflows || []
  } catch (error: any) {
    workflowError.value = error?.response?.data?.detail || error.message || '工作流加载失败'
  } finally {
    workflowsLoading.value = false
  }
}

function selectNode(nodeId: string) {
  selectedNodeId.value = nodeId
  showNodeMenu.value = false
  const data = nodes.value.find((node) => node.id === nodeId)?.data || {}
  promptDraft.value = data.body || ''
  assetDraft.value = data.assetUrl || ''
  aspectDraft.value = data.aspectRatio || '1:1'
  quantityDraft.value = safeNumber(data.quantity, 1)
  seedDraft.value = data.seed == null ? '' : String(data.seed)
  runError.value = ''
}

function updateNodeData(nodeId: string, patch: Partial<CanvasNodeData>) {
  nodes.value = nodes.value.map((node) => node.id === nodeId
    ? { ...node, data: { title: node.data?.title || 'Node', ...node.data, ...patch } }
    : node)
}

function updateSelectedData(patch: Partial<CanvasNodeData>) {
  if (!selectedNode.value) return
  updateNodeData(selectedNode.value.id, patch)
}

function onConnect(params: Connection) {
  if (!params.source || !params.target) return
  const sourceNode = nodes.value.find((node) => node.id === params.source)
  const incoming = edges.value.filter((edge) => edge.target === params.target)
  const edgeData = sourceNode?.type === 'text'
    ? { promptOrder: incoming.filter((edge) => nodes.value.find((node) => node.id === edge.source)?.type === 'text').length + 1 }
    : sourceNode?.type === 'media'
      ? { imageOrder: incoming.filter((edge) => nodes.value.find((node) => node.id === edge.source)?.type === 'media').length + 1 }
      : {}
  edges.value = [
    ...edges.value,
    {
      id: `edge-${params.source}-${params.target}-${Date.now()}`,
      source: params.source,
      target: params.target,
      type: 'smoothstep',
      animated: true,
      markerEnd: MarkerType.ArrowClosed,
      style: { stroke: 'rgba(255,255,255,.45)', strokeWidth: 3 },
      data: edgeData,
    },
  ]
}

function duplicateNode(nodeId: string) {
  const source = nodes.value.find((n: any) => n.id === nodeId)
  if (!source) return
  const newId = uniqueId(source.type)
  nodes.value = [
    ...nodes.value,
    {
      ...JSON.parse(JSON.stringify(source)),
      id: newId,
      position: { x: source.position.x + 40, y: source.position.y + 40 },
      data: { ...source.data, status: 'idle', error: '', results: [] },
    },
  ]
  selectNode(newId)
  nextTick(() => fitView({ padding: 0.18, duration: 350 }))
}

function deleteSelected() {
  if (selectedEdgeId.value) {
    edges.value = edges.value.filter((e: any) => e.id !== selectedEdgeId.value)
    selectedEdgeId.value = null
    return
  }
  if (contextMenu.value.visible && contextMenu.value.nodeId) {
    const nid = contextMenu.value.nodeId
    nodes.value = nodes.value.filter((n: any) => n.id !== nid)
    edges.value = edges.value.filter((e: any) => e.source !== nid && e.target !== nid)
    if (selectedNodeId.value === nid) selectedNodeId.value = null
    closeContextMenu()
    return
  }
  if (selectedNodeId.value) {
    const nid = selectedNodeId.value
    nodes.value = nodes.value.filter((n: any) => n.id !== nid)
    edges.value = edges.value.filter((e: any) => e.source !== nid && e.target !== nid)
    selectedNodeId.value = null
  }
}

function onNodeContextMenu(event: any, node: any) {
  event.preventDefault()
  event.stopPropagation()
  contextMenu.value = {
    x: event.clientX,
    y: event.clientY,
    nodeId: node.id,
    visible: true,
  }
  selectedEdgeId.value = null
}

function onEdgeClick(event: any, edge: any) {
  event.stopPropagation()
  selectedEdgeId.value = edge.id
  selectedNodeId.value = null
  closeContextMenu()
}

function closeContextMenu() {
  contextMenu.value.visible = false
}

function onNodeDragStop() {
  if (canvasDocumentId.value) persistCanvas()
}

function onPaneClick() {
  selectedNodeId.value = null
  selectedEdgeId.value = null
  closeContextMenu()
}

function handleKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault()
    deleteSelected()
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
    e.preventDefault()
    const nid = contextMenu.value.visible ? contextMenu.value.nodeId : selectedNodeId.value
    if (nid) duplicateNode(nid)
  }
}

function addNode(type: CanvasNodeType, workflow?: ComfyWorkflow) {
  const offset = nodes.value.length * 38
  const base = { x: 260 + offset, y: 170 + offset }
  const id = uniqueId(type)
  const nodeCount = workflow?.workflow_json ? Object.keys(workflow.workflow_json).length : undefined
  const data: CanvasNodeData = workflow
    ? {
        title: workflow.name,
        body: workflow.description || '选中节点后在下方配置并生成',
        hint: workflow.notes || '使用现有 ComfyUI workflow',
        workflowId: workflow.id,
        workflowCategory: workflow.category,
        workflowNotes: workflow.notes,
        nodeCount,
        mode: workflow.category === 'video' ? '文生视频' : '全能参考',
        model: workflow.name,
        spec: workflow.category === 'video' ? '480p / 5s / 是 / 自适应 / 否' : `${workflow.category} / ComfyUI / ${nodeCount || 0} nodes`,
        quantity: 1,
        aspectRatio: workflow.category === 'video' ? '16:9' : '1:1',
        seed: null,
        status: 'idle',
        results: [],
      }
    : {
        title: type === 'text' ? 'Text' : type === 'video' ? 'Video' : type === 'output' ? 'Output' : type === 'llm' ? 'LLM' : type === 'loop' ? 'Loop' : 'Media',
        body: type === 'text' ? '输入提示词，连接到下游工作流。' : type === 'llm' ? 'LLM 处理节点' : type === 'loop' ? '第《进度》批' : '',
        hint: type === 'media' ? '上传或引用素材后连接到工作流节点' : type === 'output' ? '收集生成结果' : type === 'llm' ? '连接上游 Text/Media，运行后输出文本给下游' : type === 'loop' ? '设置循环次数、提示词模板。串联运行时每轮调用下游链。' : '选中节点后在下方配置并生成',
        mode: type === 'video' ? '文生视频' : type === 'output' ? '结果容器' : type === 'llm' ? 'LLM' : type === 'loop' ? 'Loop' : '全能参考',
        model: type === 'video' ? 'Seedance2.0' : type === 'output' ? '—' : type === 'llm' ? 'MiniMax-M2.7' : type === 'loop' ? 'Serial' : 'ComfyUI',
        spec: type === 'video' ? '480p / 5s / 是 / 自适应 / 否' : type === 'output' ? '—' : type === 'llm' ? 'Node 模式' : type === 'loop' ? '《计数》《总数》《进度》' : '默认参数',
        quantity: 1,
        aspectRatio: type === 'video' ? '16:9' : '1:1',
        seed: null,
        status: 'idle',
        results: [],
        images: type === 'output' ? [] : undefined,
        systemPrompt: type === 'llm' ? 'You are a helpful assistant.' : undefined,
        outputText: type === 'llm' ? '' : undefined,
        count: type === 'loop' ? 3 : undefined,
        loopStart: type === 'loop' ? 1 : undefined,
        fixedPrompt: type === 'loop' ? '生成第《计数》张图片' : undefined,
        variablePrompt: type === 'loop' ? '第《进度》批生成：' : undefined,
        lastRendered: type === 'loop' ? '' : undefined,
        lastIteration: type === 'loop' ? 0 : undefined,
      }
  nodes.value = [...nodes.value, { id, type, position: base, data }]
  selectNode(id)
  showNodeMenu.value = false
  workflowModalOpen.value = false
}

function duplicateSelectedNode() {
  if (!selectedNode.value) return
  const copy = {
    ...selectedNode.value,
    id: uniqueId(selectedNode.value.type || 'node'),
    selected: false,
    position: {
      x: safeNumber(selectedNode.value.position?.x, 260) + 42,
      y: safeNumber(selectedNode.value.position?.y, 170) + 42,
    },
    data: { ...(selectedNode.value.data || {}), title: `${selectedNode.value.data?.title || 'Node'} 副本` },
  }
  nodes.value = [...nodes.value, copy]
  selectNode(copy.id)
}

function deleteSelectedNode() {
  if (!selectedNode.value) return
  const id = selectedNode.value.id
  nodes.value = nodes.value.filter((node) => node.id !== id)
  edges.value = edges.value.filter((edge) => edge.source !== id && edge.target !== id)
  selectedNodeId.value = null
}

function useQuickPrompt(prompt: string) {
  promptDraft.value = promptDraft.value.trim() ? `${promptDraft.value.trim()}\n${prompt}` : prompt
  savePrompt()
}

function addWorkflowNode(workflow: ComfyWorkflow) {
  addNode(workflow.category === 'video' ? 'video' : 'workflow', workflow)
}

function openTool(tool: typeof activeTool.value) {
  activeTool.value = tool
  if (tool === 'workflows') {
    workflowModalOpen.value = true
    fetchWorkflows()
  }
}

function resetCanvasView() {
  nextTick(() => fitView({ padding: 0.25, duration: 350 }))
}

function savePrompt() {
  updateSelectedData({
    body: promptDraft.value,
    assetUrl: assetDraft.value.trim() || undefined,
    aspectRatio: aspectDraft.value,
    quantity: Math.max(1, Math.min(9, Math.round(quantityDraft.value || 1))),
    seed: seedDraft.value.trim() ? Number(seedDraft.value) : null,
  })
}

function incomingEdges(nodeId: string) {
  return edges.value.filter((edge) => edge.target === nodeId)
}

function incomingNodePairs(nodeId: string) {
  return incomingEdges(nodeId)
    .map((edge, index) => ({ edge, index, node: nodes.value.find((item) => item.id === edge.source) }))
    .filter((pair) => pair.node)
}

function upstreamText(node: any): string {
  const directText = incomingNodePairs(node.id)
    .filter((pair: any) => pair.node.type === 'text')
    .sort((a: any, b: any) => safeNumber(a.edge.data?.promptOrder, a.index + 1) - safeNumber(b.edge.data?.promptOrder, b.index + 1))
    .map((pair: any) => pair.node.data?.body)
    .filter(Boolean)
    .join('\n\n')
    .trim()
  return directText || promptDraft.value.trim() || String(node.data?.body || '').trim()
}

function resultKind(url: string) {
  return /\.(mp4|mov|webm|m4v)(\?.*)?$/i.test(url) ? 'video' : 'image'
}

async function handleAssetFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    assetDraft.value = String(reader.result || '')
    savePrompt()
  }
  reader.readAsDataURL(file)
  input.value = ''
}

function onOutputDragStart(event: DragEvent, img: { url: string; prompt?: string; generation_id?: number }) {
  event.dataTransfer?.setData('application/output-image', JSON.stringify(img))
  event.dataTransfer!.effectAllowed = 'copy'
}

function onCanvasDrop(event: DragEvent) {
  const raw = event.dataTransfer?.getData('application/output-image')
  if (!raw) return
  event.preventDefault()
  try {
    const img = JSON.parse(raw)
    // Create a new media node at drop position
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
    const pos = { x: event.clientX - rect.left, y: event.clientY - rect.top }
    addOutputImageNode(img, pos)
  } catch { /* not our drag */ }
}

function addOutputImageNode(img: { url: string; prompt?: string; generation_id?: number; run_id?: number; source_node_id?: string; created_at?: string }, pos: { x: number; y: number }) {
  const id = uniqueId('media')
  const isVideo = /\.(mp4|webm|mov)(\?|$)/i.test(img.url) || img.url.includes('video')
  nodes.value = [...nodes.value, {
    id,
    type: 'media' as CanvasNodeType,
    position: pos,
    data: {
      title: img.prompt ? img.prompt.slice(0, 40) : (isVideo ? 'Video Result' : 'Image Result'),
      body: '',
      hint: '从 Output 拖入，可连接下游 workflow',
      assetUrl: img.url,
      mode: '素材',
      model: 'Output',
      status: 'success',
      results: [img.url],
      sourceRunId: img.run_id,
      sourceGenerationId: img.generation_id,
      sourceNodeId: img.source_node_id,
      sourcePrompt: img.prompt,
      sourceCreatedAt: img.created_at,
    },
  }]
  selectNode(id)
}

function makeWorkflowNode(workflow: ComfyWorkflow, id: string, x: number, y: number, title: string) {
  const nodeCount = workflow.workflow_json ? Object.keys(workflow.workflow_json).length : 0
  return {
    id,
    type: workflow.category === 'video' ? 'video' : 'workflow',
    position: { x, y },
    data: {
      title,
      body: workflow.description || '选中后运行此节点',
      hint: workflow.notes || '使用后台启用的 ComfyUI workflow',
      workflowId: workflow.id,
      workflowCategory: workflow.category || 'image',
      workflowNotes: workflow.notes,
      nodeCount,
      mode: workflow.category === 'video' ? '文生视频' : '全能参考',
      model: workflow.name,
      spec: workflow.category === 'video' ? '16:9 / video / ComfyUI' : `1:1 / ${workflow.category || 'image'} / ${nodeCount} nodes`,
      quantity: 1,
      aspectRatio: workflow.category === 'video' ? '16:9' : '1:1',
      seed: null,
      status: 'idle',
      results: [],
    },
  }
}

function addEcommerceTemplate(workflow: ComfyWorkflow) {
  const baseX = 160 + nodes.value.length * 18
  const baseY = 120 + nodes.value.length * 14
  const row = 250
  const col = 430
  const productInfoId = uniqueId('product-info')
  const productImageId = uniqueId('product-image')
  const modelPromptId = uniqueId('model-prompt')
  const sidePromptId = uniqueId('side-prompt')
  const topPromptId = uniqueId('top-prompt')
  const modelWorkflowId = uniqueId('workflow-model')
  const sideWorkflowId = uniqueId('workflow-side')
  const topWorkflowId = uniqueId('workflow-top')

  const templateNodes = [
    {
      id: productInfoId,
      type: 'text',
      position: { x: baseX, y: baseY },
      data: {
        title: '产品信息',
        body: '在这里粘贴产品名称、卖点、材质、使用场景和目标人群。',
        mode: 'Prompt',
        model: 'M2.7',
        status: 'idle',
      },
    },
    {
      id: productImageId,
      type: 'media',
      position: { x: baseX, y: baseY + row },
      data: {
        title: '产品图',
        hint: '上传产品主图，作为所有下游生成的参考图。',
        mode: 'Input',
        model: 'Reference',
        status: 'idle',
        results: [],
      },
    },
    {
      id: modelPromptId,
      type: 'text',
      position: { x: baseX + col, y: baseY },
      data: {
        title: '模特图提示词',
        body: '根据产品特性，生成一张适合展示该产品且时尚、有高级感的模特图，彩色人像，白底，人物居中，欧美人优先，产品清晰可见且不变形。',
        mode: 'Prompt',
        model: 'M2.7',
        status: 'idle',
      },
    },
    {
      id: sidePromptId,
      type: 'text',
      position: { x: baseX + col, y: baseY + row },
      data: {
        title: '侧面展示提示词',
        body: '侧面展示图：根据产品图和产品信息，生成左侧 45 度侧面展示图，高清展示侧面形状和细节，保持产品不变形，背景简洁。',
        mode: 'Prompt',
        model: 'M2.7',
        status: 'idle',
      },
    },
    {
      id: topPromptId,
      type: 'text',
      position: { x: baseX + col, y: baseY + row * 2 },
      data: {
        title: '俯瞰展示提示词',
        body: '俯瞰展示图：根据产品图和产品信息，生成从上往下俯瞰的产品展示图，高清展示俯瞰角度的形状和细节，保持产品不变形。',
        mode: 'Prompt',
        model: 'M2.7',
        status: 'idle',
      },
    },
    makeWorkflowNode(workflow, modelWorkflowId, baseX + col * 2, baseY, '生成模特图'),
    makeWorkflowNode(workflow, sideWorkflowId, baseX + col * 2, baseY + row, '生成侧面展示图'),
    makeWorkflowNode(workflow, topWorkflowId, baseX + col * 2, baseY + row * 2, '生成俯瞰展示图'),
  ]

  const connect = (source: string, target: string, data: Record<string, number>) => ({
    id: `edge-${source}-${target}`,
    source,
    target,
    type: 'smoothstep',
    animated: true,
    markerEnd: MarkerType.ArrowClosed,
    style: { stroke: 'rgba(255,255,255,.45)', strokeWidth: 3 },
    data,
  })
  const templateEdges = [
    connect(productInfoId, modelWorkflowId, { promptOrder: 1 }),
    connect(productImageId, modelWorkflowId, { imageOrder: 1 }),
    connect(modelPromptId, modelWorkflowId, { promptOrder: 2 }),
    connect(productInfoId, sideWorkflowId, { promptOrder: 1 }),
    connect(productImageId, sideWorkflowId, { imageOrder: 1 }),
    connect(sidePromptId, sideWorkflowId, { promptOrder: 2 }),
    connect(productInfoId, topWorkflowId, { promptOrder: 1 }),
    connect(productImageId, topWorkflowId, { imageOrder: 1 }),
    connect(topPromptId, topWorkflowId, { promptOrder: 2 }),
  ]

  nodes.value = [...nodes.value, ...templateNodes]
  edges.value = [...edges.value, ...templateEdges]
  workflowModalOpen.value = false
  selectNode(productInfoId)
  nextTick(() => fitView({ padding: 0.18, duration: 350 }))
}

async function runCascade() {
  if (!selectedNode.value || !canCascadeRun.value) return
  savePrompt()
  const node = selectedNode.value

  const workflowId = node.data?.workflowId
  if (!workflowId) {
    runError.value = '节点还没绑定 workflow'
    updateNodeData(node.id, { status: 'error', error: runError.value })
    return
  }

  runError.value = ''
  updateNodeData(node.id, { status: 'running', error: '', results: [] })

  try {
    if (!canvasDocumentId.value) await loadOrCreateCanvasDocument()
    if (!canvasDocumentId.value) throw new Error('画布文档创建失败')

    const response = await api.post(`/api/canvas/documents/${canvasDocumentId.value}/nodes/${node.id}/run-cascade`, {
      ...graphPayload(),
      aspect_ratio: aspectDraft.value || '1:1',
      quantity: Math.max(1, Math.min(9, Math.round(quantityDraft.value || 1))),
      seed: seedDraft.value.trim() ? Number(seedDraft.value) : null,
      duration: 6,
    })

    const cascadeData = response.data || {}
    const iterations = cascadeData.iterations || []
    const allUrls: string[] = []
    for (const iter of iterations) {
      if (iter.workflow_urls?.length) {
        allUrls.push(...iter.workflow_urls)
      }
    }

    updateNodeData(node.id, {
      status: cascadeData.status === 'error' ? 'error' : 'success',
      error: cascadeData.failed_at_node
        ? `Failed at ${cascadeData.failed_at_node} (iter ${cascadeData.failed_at_iteration})`
        : '',
      results: allUrls.filter(Boolean),
      // If LLM output exists in last iteration, store it
      outputText: iterations[iterations.length - 1]?.llm_output || node.data?.outputText || '',
    })

    // Update loop node if present
    const loopNode = nodes.value.find((n: any) => n.type === 'loop')
    if (loopNode && iterations.length) {
      const lastIter = iterations[iterations.length - 1]
      updateNodeData(loopNode.id, {
        lastRendered: lastIter.loop_prompt || '',
        lastIteration: lastIter.iteration || iterations.length,
        status: 'done',
      })
    }

    await hydrateCanvasFromServer()
  } catch (error: any) {
    const message = error?.response?.data?.detail || error.message || '级联运行失败'
    runError.value = message
    updateNodeData(node.id, { status: 'error', error: message, results: [] })
  }
}

async function hydrateCanvasFromServer() {
  if (!canvasDocumentId.value) return
  try {
    const response = await api.get(`/api/canvas/documents/${canvasDocumentId.value}`)
    const serverNodes: any[] = response.data?.nodes || []
    let merged = false
    for (const serverNode of serverNodes) {
      if (serverNode.type === 'output' && serverNode.data?.images?.length) {
        const localNode = nodes.value.find((n: any) => n.id === serverNode.id)
        if (localNode) {
          localNode.data = { ...localNode.data, images: serverNode.data.images, status: 'done' }
          merged = true
        }
      }
      if (serverNode.type === 'llm') {
        const localNode = nodes.value.find((n: any) => n.id === serverNode.id)
        if (localNode) {
          localNode.data = {
            ...localNode.data,
            outputText: serverNode.data?.outputText || localNode.data?.outputText || '',
            status: serverNode.data?.status || localNode.data?.status || 'idle',
            error: serverNode.data?.error || localNode.data?.error || '',
          }
          merged = true
        }
      }
    }
    if (merged) canvasSaveState.value = 'saved'
  } catch { /* best effort */ }
}

async function runSelectedNode() {
  if (!selectedNode.value) return
  savePrompt()
  const node = selectedNode.value

  if (!selectedCanRun.value) {
    runError.value = '已保存。要生成结果，请选中 Workflow 节点。'
    return
  }

  const isLLM = node.type === 'llm'
  const workflowId = node.data?.workflowId
  if (!isLLM && !workflowId) {
    runError.value = '这个节点还没绑定真实 workflow。先从“工作流”里插入一个。'
    updateNodeData(node.id, { status: 'error', error: runError.value })
    return
  }

  const prompt = upstreamText(node)
  if (!isLLM && !prompt) {
    runError.value = '缺 prompt。把 Text 节点连到这个 workflow，或者直接在下方输入。'
    updateNodeData(node.id, { status: 'error', error: runError.value })
    return
  }

  runError.value = ''
  updateNodeData(node.id, { status: 'running', error: '', results: [] })

  try {
    if (!canvasDocumentId.value) {
      await loadOrCreateCanvasDocument()
    }
    if (!canvasDocumentId.value) {
      throw new Error('画布文档创建失败，当前只能本地编辑，不能运行节点')
    }

    const response = await api.post(`/api/canvas/documents/${canvasDocumentId.value}/nodes/${node.id}/run`, {
      ...graphPayload(),
      aspect_ratio: aspectDraft.value || '1:1',
      quantity: Math.max(1, Math.min(9, Math.round(quantityDraft.value || 1))),
      seed: seedDraft.value.trim() ? Number(seedDraft.value) : null,
      duration: 6,
    })
    const respData = response.data || {}
    const urls = respData.urls || []
    const resultType = respData.result_type || (urls.length ? 'media' : '')
    if (resultType === 'text') {
      const outputText = respData.output?.output_text || ''
      updateNodeData(node.id, {
        body: respData.prompt || prompt,
        status: 'success',
        error: '',
        outputText,
        results: [],
      })
    } else {
      updateNodeData(node.id, {
        body: respData.prompt || prompt,
        status: urls.length ? 'success' : 'error',
        error: urls.length ? '' : '接口没有返回结果地址',
        results: urls,
      })
    }
    // Re-fetch document graph to get backend-written output node images
    await hydrateCanvasFromServer()
  } catch (error: any) {
    const message = error?.response?.data?.detail || error.message || '节点运行失败'
    runError.value = message
    updateNodeData(node.id, { status: 'error', error: message, results: [] })
  }
}

function canvasSummary() {
  const selected = selectedNode.value
  const nodeLines = nodes.value.slice(0, 8).map((node) => {
    const data = node.data || {}
    return `${node.id}:${node.type}:${data.title || ''}:${data.workflowId || ''}:${String(data.body || data.hint || '').slice(0, 80)}`
  })
  const workflowLines = workflows.value.slice(0, 10).map((workflow) =>
    `${workflow.id}:${workflow.name}:${workflow.category}:${workflow.description || workflow.notes || ''}`.slice(0, 140),
  )
  return [
    '你是 AI Tool Studio 流水线画布 Agent，请用中文给短而具体的下一步建议。',
    '不要泛泛而谈，要结合现有节点、连线和 ComfyUI workflow。',
    `用户问题：${agentQuestion.value || '下一步怎么做？'}`,
    `选中节点：${selected ? `${selected.id}/${selected.type}/${selected.data?.title || ''}/${selected.data?.workflowId || ''}` : '无'}`,
    `画布节点：${nodeLines.join(' | ') || '无'}`,
    `连线：${edges.value.map((edge) => `${edge.source}->${edge.target}`).join(' | ') || '无'}`,
    `可用工作流：${workflowLines.join(' | ') || '无'}`,
    '输出格式：1. 先说下一步做什么；2. 给推荐 workflow 或节点；3. 给可直接粘贴的 prompt 草稿。',
  ].join('\n').slice(0, 1400)
}

async function askAgent() {
  if (agentLoading.value) return
  agentLoading.value = true
  agentAnswer.value = '正在让 MiniMax 看画布，别催，催也不能让 token 跑更快。'
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 45000)
  try {
    const response = await api.post('/api/prompt/canvas-agent', {
      prompt: canvasSummary(),
      model: 'MiniMax-M2.7',
    }, {
      signal: controller.signal,
    })
    agentAnswer.value = response.data?.answer?.trim() || 'MiniMax 没吐出有效建议。'
  } catch (error: any) {
    agentAnswer.value = error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED'
      ? 'MiniMax 响应超时。先按当前节点继续搭：补一个 Text 节点写清目标，再选择最贴近的 ComfyUI workflow。'
      : error?.response?.data?.detail || error.message || 'Agent 建议生成失败'
  } finally {
    window.clearTimeout(timeout)
    agentLoading.value = false
  }
}

onMounted(() => {
  restoreCanvas()
  fetchWorkflows()
  loadOrCreateCanvasDocument()
  nextTick(() => resetCanvasView())
})

watch([nodes, edges], persistCanvas, { deep: true })
</script>

<template>
  <main class="pipeline-page" :class="{ embedded: props.embedded }">
    <header v-if="!props.embedded" class="pipeline-header">
      <button class="brand" type="button" @click="router.push('/')">
        <span class="brand-mark">AI</span>
        <span>AI Tool Studio</span>
      </button>
      <div class="title-stack">
        <input class="canvas-title" value="流水线" aria-label="Canvas title" />
        <span>{{ canvasSaveState === 'saved' ? '已保存到服务端' : canvasSaveState === 'saving' ? '正在保存' : canvasSaveState === 'error' ? '服务端保存失败' : '本地缓存模式' }}</span>
      </div>
      <div class="header-actions">
        <button type="button" @click="historyDrawerOpen = true">历史</button>
        <button type="button" @click="router.push('/generate')">生成工作台</button>
        <button type="button" @click="openTool('workflows')">工作流</button>
        <button class="intranet-pill" type="button">ComfyUI Local</button>
      </div>
    </header>

    <VueFlow
      v-model:nodes="nodes"
      v-model:edges="edges"
      class="pipeline-flow"
      :default-viewport="{ x: 0, y: 0, zoom: 1 }"
      :min-zoom="0.25"
      :max-zoom="1.7"
      :snap-to-grid="true"
      :snap-grid="[20, 20]"
      fit-view-on-init
      @connect="onConnect"
      @node-click="({ node }) => selectNode(node.id)"
      @node-contextmenu="(e: any) => onNodeContextMenu(e.event, e.node)"
      @node-drag-stop="onNodeDragStop"
      @edge-click="(e: any) => onEdgeClick(e.event, e.edge)"
      @pane-click="onPaneClick"
      @pane-contextmenu.prevent
      @drop="onCanvasDrop"
      @dragover.prevent
    >
      <template #node-text="{ data, id, selected }">
        <div class="flow-node text-node" :class="{ selected }" @click.stop="selectNode(id)">
          <Handle type="source" :position="Position.Right" />
          <div class="node-label">Text</div>
          <div class="node-card">
            <p>{{ data.body }}</p>
            <small class="node-status">Prompt source</small>
          </div>
        </div>
      </template>

      <template #node-media="{ data, id, selected }">
        <div class="flow-node media-node" :class="{ selected }" @click.stop="selectNode(id)">
          <Handle type="target" :position="Position.Left" />
          <Handle type="source" :position="Position.Right" />
          <div class="node-label">Media</div>
          <div class="node-card empty-media">
            <img v-if="data.assetUrl" :src="data.assetUrl" alt="" />
            <template v-else>
              <span>▣</span>
              <p>{{ data.hint }}</p>
            </template>
          </div>
        </div>
      </template>

      <template #node-workflow="{ data, id, selected }">
        <div class="flow-node workflow-node" :class="{ selected }" @click.stop="selectNode(id)">
          <Handle type="target" :position="Position.Left" />
          <Handle type="source" :position="Position.Right" />
          <div class="node-label">{{ data.workflowCategory || 'Workflow' }}</div>
          <div class="node-card">
            <span class="status-chip" :class="data.status || 'idle'">{{ data.status || 'idle' }}</span>
            <strong>{{ data.title }}</strong>
            <p>{{ data.body || data.hint }}</p>
            <small>{{ data.nodeCount || 0 }} nodes · {{ data.workflowId }}</small>
            <p v-if="data.error" class="node-error">{{ data.error }}</p>
            <div v-if="data.results?.length" class="node-results">
              <template v-for="url in data.results" :key="url">
                <video v-if="resultKind(url) === 'video'" :src="url" muted loop controls />
                <img v-else :src="url" alt="" />
              </template>
            </div>
          </div>
        </div>
      </template>

      <template #node-video="{ data, id, selected }">
        <div class="flow-node video-node" :class="{ selected }" @click.stop="selectNode(id)">
          <Handle type="target" :position="Position.Left" />
          <Handle type="source" :position="Position.Right" />
          <div class="node-label">Video</div>
          <div class="node-card empty-video">
            <span class="status-chip" :class="data.status || 'idle'">{{ data.status || 'idle' }}</span>
            <div v-if="data.results?.length" class="node-results video-result">
              <video :src="data.results[0]" controls />
            </div>
            <template v-else>
              <span>▻</span>
              <p>{{ data.hint || '选中节点后在下方配置并生成' }}</p>
              <p v-if="data.error" class="node-error">{{ data.error }}</p>
            </template>
          </div>
        </div>
      </template>

      <template #node-output="{ data, id, selected }">
        <div class="flow-node output-node" :class="{ selected }" @click.stop="selectNode(id)">
          <Handle type="target" :position="Position.Left" />
          <div class="node-label">Output</div>
          <div class="node-card">
            <span class="status-chip" :class="data.status || 'idle'">{{ data.status || 'idle' }}</span>
            <strong>{{ data.title }}</strong>
            <div v-if="data.images?.length" class="output-grid">
              <template v-for="(img, i) in data.images" :key="i">
                <video
                  v-if="resultKind(img.url) === 'video'"
                  :src="img.url"
                  muted
                  loop
                  :title="img.prompt || ''"
                  draggable="true"
                  @dragstart="onOutputDragStart($event, img)"
                  @click.stop="previewImage = img.url"
                />
                <img
                  v-else
                  :src="img.url"
                  :alt="img.prompt || ''"
                  :title="img.prompt || ''"
                  draggable="true"
                  @dragstart="onOutputDragStart($event, img)"
                  @click.stop="previewImage = img.url"
                />
              </template>
            </div>
            <p v-else class="output-empty">连接生成节点到此收集结果。结果可拖回画布作为素材节点。</p>
          </div>
        </div>
      </template>

      <template #node-loop="{ data, id, selected }">
        <div class="flow-node loop-node" :class="{ selected }" @click.stop="selectNode(id)">
          <Handle type="target" :position="Position.Left" />
          <Handle type="source" :position="Position.Right" />
          <div class="node-label">Loop</div>
          <div class="node-card">
            <span class="status-chip" :class="data.status || 'idle'">{{ data.status || 'idle' }}</span>
            <strong>{{ data.title || 'Loop' }}</strong>
            <div class="loop-info">
              <small>次数: {{ data.count || 1 }} · 模式: {{ data.mode || 'serial' }}</small>
              <p v-if="data.lastRendered" class="loop-preview">最近: {{ data.lastRendered.slice(0, 80) }}{{ data.lastRendered.length > 80 ? '…' : '' }}</p>
              <p v-else class="loop-empty">{{ data.hint || '连接上游 Text 和下游 LLM/Workflow，级联运行时逐次替换占位符。' }}</p>
            </div>
            <p v-if="data.error" class="node-error">{{ data.error }}</p>
            <small>占位符: 《计数》《总数》《进度》</small>
          </div>
        </div>
      </template>

      <template #node-llm="{ data, id, selected }">
        <div class="flow-node llm-node" :class="{ selected }" @click.stop="selectNode(id)">
          <Handle type="target" :position="Position.Left" />
          <Handle type="source" :position="Position.Right" />
          <div class="node-label">LLM</div>
          <div class="node-card">
            <span class="status-chip" :class="data.status || 'idle'">{{ data.status || 'idle' }}</span>
            <strong>{{ data.title }}</strong>
            <div v-if="data.outputText" class="llm-output">
              <p>{{ data.outputText.slice(0, 180) }}{{ data.outputText.length > 180 ? '…' : '' }}</p>
            </div>
            <p v-else class="llm-empty">运行 LLM 节点后，输出文本会显示在这里，并可传下游 workflow。</p>
            <p v-if="data.error" class="node-error">{{ data.error }}</p>
            <small>{{ data.model || 'MiniMax-M2.7' }}</small>
          </div>
        </div>
      </template>
    </VueFlow>

    <section v-if="!selectedNode && nodes.length <= 2" class="canvas-launcher">
      <div class="launcher-chip">从这里开始搭建你的画布</div>
      <div class="launcher-actions">
        <button type="button" @click="addNode('text')">文本节点</button>
        <button type="button" @click="addNode('media')">素材节点</button>
        <button type="button" @click="addNode('output')">输出收集</button>
        <button type="button" @click="addNode('llm')">LLM 处理</button>
        <button type="button" @click="addNode('loop')">Loop 循环</button>
        <button type="button" @click="openTool('workflows')">选择工作流</button>
      </div>
    </section>

    <aside class="side-toolbar">
      <button class="add-node" type="button" title="添加节点" @click="showNodeMenu = !showNodeMenu">+</button>
      <button type="button" title="添加 Text 节点" @click="addNode('text')"><span>T</span></button>
      <button type="button" title="添加 Media 节点" @click="addNode('media')"><span>M</span></button>
      <button type="button" title="添加 Output 节点" @click="addNode('output')"><span>O</span></button>
      <button type="button" title="添加 LLM 节点" @click="addNode('llm')"><span>L</span></button>
      <button type="button" title="添加 Loop 节点" @click="addNode('loop')"><span>↻</span></button>
      <button type="button" :class="{ active: activeTool === 'workflows' }" title="工作流模板" @click="openTool('workflows')"><span>W</span></button>
    </aside>

    <section v-if="showNodeMenu" class="node-menu">
      <button type="button" @click="addNode('text')">
        <span>T</span>
        <strong>Text Prompt</strong>
        <small>提示词、产品信息、分镜描述</small>
      </button>
      <button type="button" @click="addNode('media')">
        <span>M</span>
        <strong>Media Asset</strong>
        <small>上传参考图或承接生成结果</small>
      </button>
      <button type="button" @click="addNode('output')">
        <span>O</span>
        <strong>Output Collector</strong>
        <small>收集生成结果，可拖回画布作为素材</small>
      </button>
      <button type="button" @click="addNode('llm')">
        <span>L</span>
        <strong>LLM Processor</strong>
      </button>
      <button type="button" @click="addNode('loop')">
        <span>↻</span>
        <strong>Loop Controller</strong>
        <small>调用 MiniMax 处理上游文本/图片，输出给下游 workflow</small>
      </button>
      <button type="button" @click="openTool('workflows')">
        <span>W</span>
        <strong>ComfyUI Workflow</strong>
        <small>插入本地已启用 workflow</small>
      </button>
    </section>

    <div class="canvas-controls">
      <button type="button" title="缩小" @click="zoomOut()">−</button>
      <button type="button" title="适配视图" @click="resetCanvasView">⌗</button>
      <button type="button" title="放大" @click="zoomIn()">+</button>
    </div>

    <section class="canvas-overview">
      <header>
        <strong>Canvas</strong>
        <span>{{ Math.max(1, nodes.length) }} nodes</span>
      </header>
      <div class="overview-stats">
        <span>{{ nodeStats.text }} Text</span>
        <span>{{ nodeStats.media }} Media</span>
        <span>{{ nodeStats.workflow }} Flow</span>
        <span>{{ nodeStats.output }} Output</span>
        <span>{{ nodeStats.llm }} LLM</span>
        <span>{{ nodeStats.loop }} Loop</span>
        <span>{{ nodeStats.edges }} Edge</span>
      </div>
    </section>

    <aside class="studio-panel" :class="{ empty: !selectedNode }">
      <header>
        <div>
          <span>Studio</span>
          <strong>{{ selectedData?.title || '未选择节点' }}</strong>
        </div>
        <button type="button" @click="agentOpen = !agentOpen">Agent</button>
      </header>

      <div v-if="selectedNode" class="studio-section">
        <div class="studio-actions">
          <button type="button" @click="duplicateSelectedNode">复制</button>
          <button type="button" class="danger" @click="deleteSelectedNode">删除</button>
        </div>
        <label>节点类型</label>
        <p>{{ selectedNode.type }}</p>
        <label>绑定模型</label>
        <p>{{ selectedData?.model || selectedData?.workflowId || '未绑定' }}</p>
        <label>运行状态</label>
        <p>{{ selectedData?.status || 'idle' }}</p>
        <label>上游输入</label>
        <div v-if="selectedIncomingPairs.length" class="upstream-list">
          <button
            v-for="pair in selectedIncomingPairs"
            :key="pair.edge.id"
            type="button"
            @click="selectNode(pair.node.id)"
          >
            <span>{{ pair.node.type }}</span>
            <strong>{{ pair.node.data?.title || pair.node.id }}</strong>
            <small>{{ pair.edge.data?.promptOrder ? `Prompt #${pair.edge.data.promptOrder}` : pair.edge.data?.imageOrder ? `Image #${pair.edge.data.imageOrder}` : 'Input' }}</small>
          </button>
        </div>
        <p v-else>暂无上游节点</p>
        <label v-if="selectedData?.workflowId">Workflow ID</label>
        <p v-if="selectedData?.workflowId">{{ selectedData?.workflowId }}</p>
      </div>
      <div v-else class="studio-empty">
        <strong>选择一个节点</strong>
        <p>右侧会显示节点配置、上游输入、生成状态和结果历史。</p>
      </div>

      <div class="agent-panel" :class="{ open: agentOpen }">
        <header>
          <strong>Pipeline Agent</strong>
          <button type="button" @click="agentOpen = false">×</button>
        </header>
        <p>{{ agentAnswer }}</p>
        <textarea v-model="agentQuestion" placeholder="问它：我该选哪个工作流？这个节点怎么接？prompt 怎么写？" />
        <button type="button" :disabled="agentLoading" @click="askAgent">
          {{ agentLoading ? '思考中...' : '问 MiniMax' }}
        </button>
      </div>
    </aside>

    <section v-if="selectedNode" class="node-composer">
      <div class="composer-tabs">
        <button type="button" class="active">{{ selectedData?.mode || '全能参考' }}</button>
        <button type="button">{{ selectedNode.type === 'video' ? '文生视频' : '节点配置' }}</button>
      </div>
      <button class="asset-pill" type="button">▣<span>素材库</span></button>
      <textarea
        v-model="promptDraft"
        :placeholder="selectedIsMedia ? '粘贴图片 URL，或点击左侧素材库上传图片' : '描述你想要生成的内容。Workflow 节点会优先读取上游 Text 节点。'"
        @blur="savePrompt"
      />
      <div v-if="selectedIsMedia" class="asset-editor">
        <label>
          上传素材
          <input type="file" accept="image/*" @change="handleAssetFile" />
        </label>
        <input v-model="assetDraft" type="url" placeholder="https://... 或 data:image/..." @blur="savePrompt" />
      </div>
      <div class="composer-footer">
        <button type="button" class="model-select">{{ selectedData?.model || selectedData?.title }}⌄</button>
        <label v-if="selectedCanRun" class="inline-field">
          比例
          <select v-model="aspectDraft" @change="savePrompt">
            <option value="1:1">1:1</option>
            <option value="16:9">16:9</option>
            <option value="9:16">9:16</option>
            <option value="4:3">4:3</option>
            <option value="3:4">3:4</option>
          </select>
        </label>
        <label v-if="selectedCanRun" class="inline-field">
          数量
          <input v-model.number="quantityDraft" type="number" min="1" max="9" @blur="savePrompt" />
        </label>
        <label v-if="selectedCanRun" class="inline-field">
          Seed
          <input v-model="seedDraft" type="number" placeholder="随机" @blur="savePrompt" />
        </label>
        <button type="button" class="submit-run" :disabled="selectedData?.status === 'running'" @click="runSelectedNode">
        运行
      </button>
      <button
        v-if="canCascadeRun"
        type="button"
        class="submit-run cascade"
        :disabled="selectedData?.status === 'running'"
        @click="runCascade"
      >
        级联运行
        </button>
      </div>
      <div v-if="!selectedIsMedia" class="quick-prompts">
        <button v-for="item in quickPrompts" :key="item" type="button" @click="useQuickPrompt(item)">
          {{ item }}
        </button>
      </div>
      <p v-if="runError || selectedData?.error" class="composer-error">{{ runError || selectedData?.error }}</p>
    </section>

    <section v-if="historyDrawerOpen" class="history-drawer" @click.self="historyDrawerOpen = false">
      <aside>
        <header>
          <div>
            <span>Generation</span>
            <strong>结果历史</strong>
          </div>
          <button type="button" @click="historyDrawerOpen = false">×</button>
        </header>
        <div v-if="!resultHistory.length" class="history-empty">还没有生成结果。先选中一个 workflow 跑起来，别盯着空抽屉发呆。</div>
        <div v-else class="history-grid">
          <button
            v-for="item in resultHistory"
            :key="item.id"
            type="button"
            @click="selectNode(item.id); historyDrawerOpen = false"
          >
            <video v-if="resultKind(item.url) === 'video'" :src="item.url" muted />
            <img v-else :src="item.url" alt="" />
            <strong>{{ item.title }}</strong>
            <span>{{ item.model }}</span>
          </button>
        </div>
      </aside>
    </section>

    <section v-if="workflowModalOpen" class="workflow-modal" @click.self="workflowModalOpen = false">
      <div class="workflow-panel">
        <header>
          <div>
            <h2>公共工作流</h2>
            <p>来自后台已启用的 ComfyUI workflow，可直接插入画布。</p>
          </div>
          <button type="button" @click="workflowModalOpen = false">×</button>
        </header>
        <div class="workflow-filters">
          <button
            v-for="category in categories"
            :key="category"
            type="button"
            :class="{ active: activeWorkflowCategory === category }"
            @click="activeWorkflowCategory = category"
          >
            {{ category === 'all' ? '全部' : category }}
          </button>
          <input v-model="workflowQuery" type="search" placeholder="搜索 workflow、分类或备注" />
        </div>
        <div v-if="workflowsLoading" class="workflow-empty">正在加载工作流...</div>
        <div v-else-if="workflowError" class="workflow-empty">{{ workflowError }}</div>
        <div v-else-if="!filteredWorkflows.length" class="workflow-empty">没有可用工作流。先去 Admin / Workflows 启用几个，别让画布干瞪眼。</div>
        <div v-else class="workflow-list-wrap">
          <div class="template-strip">
            <button
              v-for="workflow in filteredWorkflows.filter((item) => item.category !== 'video').slice(0, 3)"
              :key="`template-${workflow.id}`"
              type="button"
              class="template-card"
              @click="addEcommerceTemplate(workflow)"
            >
              <span>电商套图模板</span>
              <strong>产品信息 + 产品图 → 模特/侧面/俯瞰</strong>
              <small>使用 {{ workflow.name }} 作为三个生成节点</small>
            </button>
          </div>
          <div class="workflow-grid">
            <button
              v-for="workflow in filteredWorkflows"
              :key="workflow.id"
              type="button"
              class="workflow-card"
              @click="addWorkflowNode(workflow)"
            >
              <span>{{ workflow.category || 'image' }}</span>
              <strong>{{ workflow.name }}</strong>
              <p>{{ workflow.description || workflow.notes || 'ComfyUI workflow' }}</p>
              <small>{{ workflow.workflow_json ? Object.keys(workflow.workflow_json).length : 0 }} nodes · {{ workflow.id }}</small>
            </button>
          </div>
        </div>
      </div>
    </section>
  </main>

  <!-- Preview overlay for output media (image/video) -->
  <Teleport to="body">
    <div v-if="previewImage" class="preview-overlay" @click="previewImage = null">
      <video v-if="resultKind(previewImage) === 'video'" :src="previewImage" controls autoplay />
      <img v-else :src="previewImage" alt="Preview" />
    </div>
  </Teleport>

  <!-- Context menu -->
  <Teleport to="body">
    <div
      v-if="contextMenu.visible"
      class="canvas-context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @click.stop
    >
      <button @click="duplicateNode(contextMenu.nodeId!)">
        <span>+</span>
        <div><strong>Duplicate</strong><small>Ctrl+D</small></div>
      </button>
      <button @click="deleteSelected()" class="danger">
        <span>×</span>
        <div><strong>Delete</strong><small>Delete</small></div>
      </button>
      <button @click="contextMenu.visible = false; selectNode(contextMenu.nodeId!); fitView({ padding: 0.25, duration: 350 })">
        <span>⊙</span>
        <div><strong>Focus</strong><small>Center viewport</small></div>
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.pipeline-page {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  position: relative;
  background-color: #030304;
  background-image: radial-gradient(circle, rgba(255,255,255,.13) 1px, transparent 1px);
  background-size: 26px 26px;
  color: #f7f7f7;
}
.pipeline-page.embedded {
  width: 100%;
  height: 100%;
}
.pipeline-header {
  position: absolute;
  inset: 0 0 auto 0;
  height: 64px;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 0 32px;
  z-index: 20;
  background: linear-gradient(180deg, rgba(0,0,0,.76), rgba(0,0,0,0));
}
.brand,
.header-actions button {
  border: 0;
  background: transparent;
  color: #fff;
  font-weight: 760;
  cursor: pointer;
}
.brand { display: flex; align-items: center; gap: 14px; font-size: 16px; }
.brand-mark { color: #72ff9c; font-size: 28px; }
.canvas-title {
  width: 180px;
  border: 0;
  outline: 0;
  background: transparent;
  color: #fff;
  font-size: 24px;
  font-weight: 800;
}
.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-actions button { font-size: 14px; color: rgba(255,255,255,.86); }
.header-actions .intranet-pill { color: #c8ff00; font-size: 15px; }
.pipeline-flow {
  width: 100%;
  height: 100%;
  background: transparent;
}
:deep(.vue-flow__pane),
:deep(.vue-flow__viewport),
:deep(.vue-flow__container) {
  background: transparent;
}
:deep(.vue-flow__handle) {
  width: 22px;
  height: 22px;
  border: 2px solid rgba(219,229,245,.8);
  background: rgba(10,12,18,.8);
}
:deep(.vue-flow__edge-path) { stroke: rgba(255,255,255,.5); stroke-width: 3; }
.flow-node { min-width: 300px; color: #f8fafc; }
.node-label {
  margin: 0 0 8px 8px;
  color: rgba(255,255,255,.72);
  font-size: 16px;
  font-weight: 780;
}
.node-card {
  min-height: 210px;
  padding: 26px;
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 16px;
  background: #1b1b1e;
  box-shadow: 0 24px 80px rgba(0,0,0,.45);
  overflow: hidden;
}
.flow-node.selected .node-card {
  border-color: #12e2bc;
  box-shadow: 0 0 0 2px rgba(18,226,188,.15), 0 24px 80px rgba(0,0,0,.5);
}
.text-node .node-card { width: 304px; max-height: 300px; overflow: auto; }
.text-node p {
  margin: 0;
  color: white;
  font-size: 19px;
  line-height: 1.7;
  font-weight: 720;
}
.workflow-node .node-card { width: 360px; }
.workflow-node strong { display: block; font-size: 18px; margin-bottom: 12px; }
.workflow-node p { color: rgba(255,255,255,.72); line-height: 1.55; }
.workflow-node small { color: rgba(20,255,205,.78); }
.node-status {
  display: inline-flex;
  margin-top: 16px;
  color: rgba(125,255,154,.72);
  font-size: 12px;
}
.status-chip {
  display: inline-flex;
  margin-bottom: 12px;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.7);
  font-size: 12px;
  font-weight: 900;
  text-transform: uppercase;
}
.status-chip.running { background: rgba(233,255,0,.16); color: #e9ff00; }
.status-chip.success { background: rgba(25,226,147,.16); color: #7dff9a; }
.status-chip.error { background: rgba(255,89,102,.16); color: #ff8c96; }
.node-error {
  margin-top: 12px !important;
  color: #ff8c96 !important;
  font-size: 13px;
}
.node-results {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
  gap: 10px;
  margin-top: 14px;
}
.node-results img,
.node-results video {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 10px;
  object-fit: cover;
  background: rgba(255,255,255,.05);
}
.empty-video,
.empty-media {
  width: 384px;
  height: 288px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  color: rgba(255,255,255,.32);
}
.empty-video span,
.empty-media span { font-size: 46px; }
.empty-video p,
.empty-media p { margin: 0; font-weight: 700; }
.empty-media img,
.empty-video video {
  width: 100%;
  height: 100%;
  border-radius: 10px;
  object-fit: contain;
}
.video-result {
  width: 100%;
  height: 100%;
  display: block;
}
.output-node .node-card {
  width: 360px;
  max-height: 480px;
  overflow-y: auto;
}
.output-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 12px;
}
.output-grid img {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 8px;
  object-fit: cover;
  cursor: grab;
  transition: transform .15s;
}
.output-grid img:hover { transform: scale(1.06); }
.output-empty {
  margin-top: 20px;
  color: rgba(255,255,255,.38);
  font-size: 13px;
  line-height: 1.6;
}
.llm-node .node-card {
  width: 340px;
  max-height: 360px;
  overflow-y: auto;
}
.llm-output {
  margin-top: 12px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(255,255,255,.06);
}
.llm-output p {
  margin: 0;
  color: rgba(200,255,220,.9);
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.loop-node .node-card {
  width: 340px;
  max-height: 360px;
  overflow-y: auto;
}
.loop-info {
  margin-top: 12px;
}
.loop-info small {
  display: block;
  color: rgba(255, 255, 255, .55);
  font-size: 12px;
  margin-bottom: 6px;
}
.loop-preview {
  margin: 8px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(100, 150, 255, .12);
  color: rgba(200, 220, 255, .9);
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.loop-empty {
  margin: 8px 0 0;
  color: rgba(255, 255, 255, .35);
  font-size: 13px;
  line-height: 1.5;
}
.llm-empty {
  margin-top: 12px;
  color: rgba(255,255,255,.38);
  font-size: 13px;
  line-height: 1.5;
}
.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,.82);
  cursor: pointer;
}
.preview-overlay img {
  max-width: 86vw;
  max-height: 86vh;
  border-radius: 12px;
  box-shadow: 0 24px 80px rgba(0,0,0,.5);
}
.side-toolbar {
  position: absolute;
  left: 18px;
  top: 50%;
  z-index: 25;
  width: 58px;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 34px;
  background: rgba(26,26,29,.86);
  box-shadow: 0 18px 54px rgba(0,0,0,.42);
}
.side-toolbar button {
  width: 48px;
  min-height: 62px;
  border: 0;
  border-radius: 24px;
  background: transparent;
  color: rgba(255,255,255,.72);
  font-size: 22px;
  cursor: pointer;
}
.side-toolbar button.active { color: #15e2bd; background: rgba(255,255,255,.06); }
.side-toolbar span { display: block; margin-top: 6px; font-size: 12px; font-weight: 700; }
.side-toolbar .add-node {
  width: 48px;
  min-height: 48px;
  margin-bottom: 6px;
  border-radius: 50%;
  background: #fff;
  color: #111;
  font-size: 34px;
  line-height: 1;
}
.canvas-controls {
  position: absolute;
  left: 28px;
  bottom: 26px;
  z-index: 25;
  display: flex;
  gap: 10px;
  padding: 10px;
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 26px;
  background: rgba(26,26,29,.86);
}
.canvas-controls button {
  width: 42px;
  height: 42px;
  border: 0;
  border-radius: 50%;
  background: rgba(255,255,255,.08);
  color: #fff;
  font-size: 20px;
  cursor: pointer;
}
.agent-assistant {
  position: absolute;
  right: 34px;
  bottom: 30px;
  z-index: 35;
}
.agent-orb {
  width: 86px;
  height: 86px;
  border: 2px solid rgba(255,70,90,.88);
  border-radius: 50%;
  background:
    radial-gradient(circle at 50% 50%, #10f2b3 0 18%, #dfff9b 28%, rgba(135,255,206,.48) 42%, transparent 68%),
    #050607;
  color: #062018;
  font-weight: 900;
  box-shadow: 0 0 42px rgba(32,255,178,.28);
  cursor: pointer;
}
.agent-orb span {
  display: block;
  transform: translateY(8px);
  font-size: 12px;
  letter-spacing: 3px;
}
.agent-panel {
  position: absolute;
  right: 0;
  bottom: 100px;
  width: 360px;
  padding: 16px;
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 16px;
  background: rgba(24,24,27,.96);
  box-shadow: 0 24px 80px rgba(0,0,0,.58);
}
.agent-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.agent-panel header button {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: rgba(255,255,255,.08);
  color: #fff;
}
.agent-panel p {
  max-height: 180px;
  overflow: auto;
  margin: 0 0 12px;
  color: rgba(255,255,255,.78);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}
.agent-panel textarea {
  width: 100%;
  min-height: 76px;
  resize: vertical;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 10px;
  background: rgba(255,255,255,.06);
  color: #fff;
  padding: 10px;
  outline: 0;
}
.agent-panel > button {
  width: 100%;
  height: 40px;
  margin-top: 10px;
  border: 0;
  border-radius: 10px;
  background: #e9ff00;
  color: #111;
  font-weight: 900;
  cursor: pointer;
}
.agent-panel > button:disabled { opacity: .58; cursor: wait; }
.node-composer {
  position: absolute;
  left: 50%;
  bottom: 28px;
  z-index: 30;
  width: min(1120px, calc(100vw - 240px));
  min-height: 260px;
  transform: translateX(-50%);
  padding: 18px;
  border: 1px solid rgba(255,255,255,.16);
  border-radius: 20px;
  background: #1a1a1d;
  box-shadow: 0 28px 90px rgba(0,0,0,.55);
}
.composer-tabs { display: flex; gap: 12px; margin-bottom: 16px; }
.composer-tabs button,
.asset-pill {
  height: 44px;
  padding: 0 22px;
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 11px;
  background: rgba(255,255,255,.05);
  color: #fff;
  font-weight: 800;
}
.composer-tabs button.active { background: transparent; border-color: transparent; }
.asset-pill {
  width: 112px;
  height: 112px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: rgba(255,255,255,.72);
}
.node-composer textarea {
  position: absolute;
  left: 146px;
  right: 18px;
  top: 94px;
  bottom: 76px;
  resize: none;
  border: 0;
  outline: 0;
  background: transparent;
  color: #fff;
  font-size: 20px;
  line-height: 1.55;
}
.node-composer textarea::placeholder { color: rgba(180,187,200,.82); }
.composer-footer {
  position: absolute;
  left: 30px;
  right: 18px;
  bottom: 18px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.composer-footer button {
  border: 0;
  background: transparent;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
}
.inline-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: rgba(255,255,255,.62);
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}
.inline-field select,
.inline-field input,
.asset-editor input {
  height: 38px;
  min-width: 76px;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 10px;
  background: rgba(255,255,255,.06);
  color: #fff;
  padding: 0 10px;
  outline: 0;
}
.inline-field input { width: 86px; }
.asset-editor {
  position: absolute;
  left: 146px;
  right: 18px;
  bottom: 82px;
  display: grid;
  grid-template-columns: 132px 1fr;
  gap: 12px;
}
.asset-editor label {
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(125,255,154,.14);
  color: #7dff9a;
  font-weight: 900;
  cursor: pointer;
}
.asset-editor input[type="file"] { display: none; }
.composer-error {
  position: absolute;
  left: 30px;
  right: 260px;
  bottom: 88px;
  margin: 0;
  color: #ff8c96;
  font-size: 13px;
}
.spec-select { margin-left: auto; }
.submit-run {
  height: 66px;
  min-width: 200px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0 12px 0 28px;
  border-radius: 36px;
  background: linear-gradient(145deg, #555, #2b2b2d) !important;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.22);
  cursor: pointer;
}
.submit-run.cascade {
  background: rgba(100, 149, 237, .25);
  color: #a0c4ff;
  border-color: rgba(100, 149, 237, .4);
}
.submit-run.cascade:hover:not(:disabled) {
  background: rgba(100, 149, 237, .4);
  color: #fff;
}
.submit-run:disabled { opacity: .58; cursor: wait; }
.submit-run span { color: #7dff9a; }
.submit-run strong {
  width: 52px;
  height: 52px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #fff;
  color: #111;
  font-size: 28px;
}
.workflow-modal {
  position: absolute;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,.22);
}
.workflow-panel {
  width: min(1320px, calc(100vw - 160px));
  max-height: 78vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 18px;
  background: #171719;
  box-shadow: 0 38px 120px rgba(0,0,0,.72);
}
.workflow-panel header,
.workflow-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 22px;
}
.workflow-panel h2 { margin: 0 0 6px; }
.workflow-panel p { margin: 0; color: rgba(255,255,255,.62); }
.workflow-panel header button {
  margin-left: auto;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 50%;
  background: rgba(255,255,255,.08);
  color: #fff;
  font-size: 26px;
}
.workflow-filters { padding-top: 0; flex-wrap: wrap; }
.workflow-filters button {
  height: 34px;
  padding: 0 16px;
  border: 0;
  border-radius: 18px;
  background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.72);
  cursor: pointer;
}
.workflow-filters button.active { background: #e9ff00; color: #111; font-weight: 900; }
.workflow-filters input {
  margin-left: auto;
  width: 320px;
  height: 38px;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 10px;
  background: rgba(255,255,255,.06);
  color: #fff;
  padding: 0 12px;
}
.workflow-grid {
  overflow: auto;
  padding: 0 22px 24px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
.workflow-list-wrap {
  overflow: auto;
  padding-bottom: 24px;
}
.template-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  padding: 0 22px 18px;
}
.template-card {
  min-height: 132px;
  text-align: left;
  padding: 18px;
  border: 1px solid rgba(125,255,154,.28);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(125,255,154,.12), rgba(255,255,255,.04));
  color: #fff;
  cursor: pointer;
}
.template-card span {
  display: inline-flex;
  margin-bottom: 18px;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(233,255,0,.16);
  color: #e9ff00;
  font-size: 12px;
  font-weight: 900;
}
.template-card strong { display: block; margin-bottom: 10px; font-size: 15px; }
.template-card small { color: rgba(255,255,255,.58); }
.workflow-card {
  min-height: 232px;
  text-align: left;
  padding: 16px;
  border: 1px solid rgba(255,255,255,.1);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04));
  color: #fff;
  cursor: pointer;
}
.workflow-card:hover { border-color: rgba(18,226,188,.66); transform: translateY(-2px); }
.workflow-card span {
  display: inline-flex;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(18,226,188,.14);
  color: #6fffe0;
  font-size: 12px;
}
.workflow-card strong { display: block; margin: 38px 0 10px; font-size: 16px; }
.workflow-card p { min-height: 42px; font-size: 13px; line-height: 1.5; }
.workflow-card small { color: rgba(255,255,255,.48); }
.workflow-empty {
  padding: 80px 24px;
  text-align: center;
  color: rgba(255,255,255,.64);
}

.canvas-context-menu {
  position: fixed;
  z-index: 9999;
  width: 220px;
  padding: 8px;
  border: 1px solid rgba(34,57,98,.10);
  border-radius: 16px;
  background: rgba(255,255,255,.98);
  box-shadow: 0 18px 44px rgba(34,57,98,.18);
  backdrop-filter: blur(14px);
}
.canvas-context-menu button {
  width: 100%;
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 0 12px;
  align-items: center;
  text-align: left;
  padding: 10px 12px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: #1f2a44;
  cursor: pointer;
}
.canvas-context-menu button:hover {
  background: #f3f6fb;
}
.canvas-context-menu button span {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: #edf2fb;
  color: #355ce0;
  font-size: 16px;
  font-weight: 900;
}
.canvas-context-menu button.danger span {
  background: #fce8e6;
  color: #b42318;
}
.canvas-context-menu button.danger:hover {
  background: #fef2f2;
}
.canvas-context-menu small {
  display: block;
  color: #8a94a6;
  font-size: 11px;
}
.canvas-context-menu strong {
  font-size: 13px;
}

:deep(.vue-flow__edge.selected .vue-flow__edge-path) {
  stroke: #4b78ff !important;
  stroke-width: 3.5 !important;
  filter: drop-shadow(0 0 6px rgba(75,120,255,.35));
}

/* Studio shell: closer to huobao-canvas + AICON workbench */
.pipeline-page {
  background-color: #eef2f6;
  background-image:
    linear-gradient(rgba(45, 58, 84, .045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(45, 58, 84, .045) 1px, transparent 1px);
  background-size: 28px 28px;
  color: #1f2a44;
}
.pipeline-page::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 28% 18%, rgba(75,120,255,.10), transparent 24%),
    radial-gradient(circle at 80% 80%, rgba(22,163,116,.08), transparent 28%);
}
.pipeline-header {
  inset: 18px 24px auto 24px;
  height: 48px;
  padding: 0;
  background: transparent;
}
.brand {
  height: 42px;
  padding: 0 14px 0 8px;
  border-radius: 999px;
  background: rgba(255,255,255,.96);
  color: #1f2a44;
  border: 1px solid rgba(34,57,98,.08);
  box-shadow: 0 12px 28px rgba(34,57,98,.08);
}
.brand-mark {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(180deg, #4b78ff, #355ce0);
  color: #fff;
  font-size: 11px;
  font-weight: 900;
}
.title-stack {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.title-stack span {
  color: #6b7280;
  font-size: 11px;
  font-weight: 700;
}
.canvas-title {
  height: 24px;
  color: #1f2a44;
  font-size: 18px;
  letter-spacing: 0;
}
.header-actions {
  height: 42px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(255,255,255,.96);
  border: 1px solid rgba(34,57,98,.08);
  box-shadow: 0 12px 28px rgba(34,57,98,.08);
}
.header-actions button {
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  color: #52607a;
  font-size: 13px;
}
.header-actions button:hover {
  background: #f0f4fb;
  color: #1f2a44;
}
.header-actions .intranet-pill {
  background: #eff8f2;
  color: #16855d;
}
.pipeline-flow {
  padding-top: 24px;
}
:deep(.vue-flow__handle) {
  width: 18px;
  height: 18px;
  border: 3px solid #fff;
  background: #202124;
  box-shadow: 0 0 0 4px rgba(32,33,36,.10);
}
:deep(.vue-flow__edge-path) {
  stroke: rgba(54, 72, 105, .42);
  stroke-width: 2.6;
}
.flow-node {
  min-width: 260px;
  color: #1f2a44;
}
.node-label {
  margin: 0 0 8px 8px;
  color: #6b7280;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}
.node-card {
  min-height: 178px;
  padding: 16px;
  border: 1px solid rgba(34,57,98,.10);
  border-radius: 18px;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  box-shadow: 0 18px 34px rgba(34,57,98,.09);
}
.flow-node.selected .node-card {
  border-color: rgba(75,120,255,.58);
  box-shadow: 0 0 0 3px rgba(75,120,255,.12), 0 24px 44px rgba(34,57,98,.14);
}
.text-node .node-card {
  width: 300px;
  max-height: 270px;
}
.text-node p {
  color: #1f2a44;
  font-size: 15px;
  line-height: 1.65;
  font-weight: 600;
}
.workflow-node .node-card {
  width: 338px;
}
.workflow-node strong {
  color: #1f2a44;
  font-size: 16px;
}
.workflow-node p {
  color: #5f6b82;
}
.workflow-node small {
  color: #355ce0;
}
.node-status {
  color: #16855d;
}
.status-chip {
  background: #eef2f6;
  color: #64748b;
}
.status-chip.running { background: #fff3d6; color: #b06000; }
.status-chip.success { background: #e8f3eb; color: #0f6a36; }
.status-chip.error { background: #fce8e6; color: #b42318; }
.node-error {
  color: #b42318 !important;
}
.empty-video,
.empty-media {
  width: 316px;
  height: 236px;
  color: #8a94a6;
}
.empty-media,
.empty-video {
  background: linear-gradient(180deg, #fff 0%, #f4f7fb 100%);
}
.side-toolbar {
  left: 20px;
  width: 56px;
  padding: 10px 6px;
  border-color: rgba(34,57,98,.08);
  background: rgba(255,255,255,.96);
  border-radius: 999px;
  box-shadow: 0 14px 32px rgba(34,57,98,.10);
}
.side-toolbar button {
  width: 42px;
  min-height: 42px;
  border-radius: 50%;
  color: #52607a;
  font-size: 14px;
  font-weight: 900;
}
.side-toolbar button:hover,
.side-toolbar button.active {
  background: #edf2fb;
  color: #355ce0;
}
.side-toolbar span {
  margin: 0;
  font-size: 13px;
}
.side-toolbar .add-node {
  width: 44px;
  min-height: 44px;
  background: linear-gradient(180deg, #4b78ff, #355ce0);
  color: #fff;
  font-size: 28px;
}
.node-menu {
  position: absolute;
  left: 88px;
  top: 50%;
  z-index: 31;
  width: 260px;
  transform: translateY(-50%);
  padding: 10px;
  border: 1px solid rgba(34,57,98,.08);
  border-radius: 18px;
  background: rgba(255,255,255,.98);
  box-shadow: 0 22px 52px rgba(34,57,98,.16);
}
.node-menu button {
  width: 100%;
  display: grid;
  grid-template-columns: 38px 1fr;
  gap: 2px 12px;
  text-align: left;
  padding: 12px;
  border: 0;
  border-radius: 14px;
  background: transparent;
  color: #1f2a44;
  cursor: pointer;
}
.node-menu button:hover {
  background: #f3f6fb;
}
.node-menu span {
  grid-row: span 2;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 11px;
  background: #edf2fb;
  color: #355ce0;
  font-weight: 900;
}
.node-menu strong {
  font-size: 14px;
}
.node-menu small {
  color: #6b7280;
  font-size: 12px;
}
.canvas-controls {
  left: 16px;
  bottom: 16px;
  border-color: rgba(34,57,98,.08);
  background: rgba(255,255,255,.96);
  box-shadow: 0 12px 28px rgba(34,57,98,.08);
}
.canvas-controls button {
  background: #f3f6fb;
  color: #52607a;
}
.canvas-overview {
  position: absolute;
  right: 430px;
  top: 18px;
  z-index: 24;
  width: 230px;
  padding: 12px;
  border: 1px solid rgba(34,57,98,.08);
  border-radius: 18px;
  background: rgba(255,255,255,.94);
  box-shadow: 0 12px 28px rgba(34,57,98,.08);
}
.canvas-overview header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.canvas-overview strong {
  color: #1f2a44;
  font-size: 13px;
}
.canvas-overview header span {
  color: #8a94a6;
  font-size: 11px;
  font-weight: 800;
}
.overview-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 7px;
}
.overview-stats span {
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #f3f6fb;
  color: #52607a;
  font-size: 11px;
  font-weight: 800;
}
.canvas-launcher {
  position: absolute;
  left: 50%;
  bottom: 116px;
  z-index: 22;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.launcher-chip,
.launcher-actions button {
  border: 1px solid rgba(34,57,98,.08);
  background: rgba(255,255,255,.96);
  color: #52607a;
  box-shadow: 0 12px 28px rgba(34,57,98,.08);
}
.launcher-chip {
  height: 36px;
  display: inline-flex;
  align-items: center;
  padding: 0 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}
.launcher-actions {
  display: flex;
  gap: 10px;
}
.launcher-actions button {
  height: 38px;
  padding: 0 16px;
  border-radius: 999px;
  font-weight: 800;
  cursor: pointer;
}
.launcher-actions button:hover {
  background: #f8fbff;
  color: #1f2a44;
  transform: translateY(-1px);
}
.studio-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 26;
  width: min(410px, calc(100vw - 132px));
  padding: 20px 18px;
  background: rgba(255,255,255,.84);
  backdrop-filter: blur(22px);
  border-left: 1px solid rgba(34,57,98,.08);
  box-shadow: -18px 0 38px rgba(34,57,98,.08);
}
.studio-panel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.studio-panel > header span {
  display: block;
  color: #8a94a6;
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}
.studio-panel > header strong {
  display: block;
  margin-top: 4px;
  color: #1f2a44;
  font-size: 18px;
}
.studio-panel > header button {
  height: 34px;
  padding: 0 14px;
  border: 1px solid rgba(75,120,255,.16);
  border-radius: 999px;
  background: #f4f7ff;
  color: #355ce0;
  font-weight: 800;
}
.studio-section,
.studio-empty {
  padding: 16px;
  border-radius: 18px;
  background: rgba(255,255,255,.86);
  border: 1px solid rgba(34,57,98,.08);
  box-shadow: 0 12px 28px rgba(34,57,98,.06);
}
.studio-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.studio-actions button {
  height: 32px;
  padding: 0 12px;
  border: 1px solid rgba(34,57,98,.08);
  border-radius: 999px;
  background: #f3f6fb;
  color: #52607a;
  font-weight: 800;
  cursor: pointer;
}
.studio-actions button:hover {
  color: #1f2a44;
}
.studio-actions .danger {
  margin-left: auto;
  background: #fce8e6;
  color: #b42318;
}
.upstream-list {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}
.upstream-list button {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 2px 10px;
  text-align: left;
  padding: 10px;
  border: 1px solid rgba(34,57,98,.08);
  border-radius: 13px;
  background: #f8fafc;
  cursor: pointer;
}
.upstream-list button:hover {
  border-color: rgba(75,120,255,.35);
}
.upstream-list span {
  grid-row: span 2;
  align-self: center;
  text-transform: uppercase;
  color: #355ce0;
  font-size: 11px;
  font-weight: 900;
}
.upstream-list strong {
  color: #1f2a44;
  font-size: 13px;
}
.upstream-list small {
  color: #8a94a6;
  font-size: 11px;
  font-weight: 700;
}
.studio-section label {
  display: block;
  margin-top: 14px;
  color: #8a94a6;
  font-size: 11px;
  font-weight: 900;
}
.studio-section label:first-child {
  margin-top: 0;
}
.studio-section p,
.studio-empty p {
  margin: 5px 0 0;
  color: #52607a;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
.studio-empty strong {
  color: #1f2a44;
}
.agent-panel {
  position: static;
  display: none;
  width: auto;
  margin-top: 14px;
  padding: 14px;
  border-color: rgba(34,57,98,.08);
  border-radius: 18px;
  background: rgba(255,255,255,.90);
  box-shadow: 0 12px 28px rgba(34,57,98,.06);
}
.agent-panel.open {
  display: block;
}
.agent-panel header button {
  background: #eef2f6;
  color: #52607a;
}
.agent-panel p {
  color: #52607a;
}
.agent-panel textarea {
  border-color: rgba(34,57,98,.10);
  background: #f8fafc;
  color: #1f2a44;
}
.agent-panel > button {
  background: #1f2a44;
  color: #fff;
}
.node-composer {
  bottom: 24px;
  width: min(860px, calc(100vw - 560px));
  min-height: 190px;
  padding: 14px;
  border-color: rgba(34,57,98,.08);
  border-radius: 22px;
  background: rgba(255,255,255,.96);
  box-shadow: 0 20px 46px rgba(34,57,98,.14);
}
.composer-tabs {
  gap: 8px;
  margin-bottom: 10px;
}
.composer-tabs button,
.asset-pill {
  height: 34px;
  border-color: rgba(34,57,98,.08);
  border-radius: 999px;
  background: #f3f6fb;
  color: #52607a;
  font-size: 12px;
}
.composer-tabs button.active {
  background: #1f2a44;
  color: #fff;
}
.asset-pill {
  width: 84px;
  height: 84px;
  border-radius: 18px;
  color: #52607a;
}
.node-composer textarea {
  left: 116px;
  right: 18px;
  top: 64px;
  bottom: 64px;
  color: #1f2a44;
  font-size: 16px;
}
.node-composer textarea::placeholder { color: #8a94a6; }
.composer-footer {
  left: 18px;
  right: 14px;
  bottom: 12px;
  gap: 12px;
}
.composer-footer button {
  color: #1f2a44;
  font-size: 14px;
}
.inline-field {
  color: #6b7280;
}
.inline-field select,
.inline-field input,
.asset-editor input {
  border-color: rgba(34,57,98,.10);
  background: #f8fafc;
  color: #1f2a44;
}
.asset-editor {
  left: 116px;
  right: 18px;
  bottom: 62px;
}
.asset-editor label {
  background: #eff8f2;
  color: #16855d;
}
.submit-run {
  height: 50px;
  min-width: 154px;
  padding: 0 8px 0 18px;
  background: linear-gradient(180deg, #4b78ff, #355ce0) !important;
  box-shadow: 0 12px 24px rgba(75,120,255,.22);
}
.submit-run span { color: #fff; }
.submit-run strong {
  width: 38px;
  height: 38px;
  font-size: 22px;
}
.composer-error {
  left: 18px;
  bottom: 66px;
  color: #b42318;
}
.quick-prompts {
  position: absolute;
  left: 116px;
  right: 190px;
  bottom: -42px;
  display: flex;
  gap: 8px;
  overflow: hidden;
}
.quick-prompts button {
  height: 30px;
  flex: 0 0 auto;
  max-width: 210px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 12px;
  border: 1px solid rgba(34,57,98,.08);
  border-radius: 999px;
  background: rgba(255,255,255,.92);
  color: #52607a;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}
.quick-prompts button:hover {
  color: #355ce0;
  border-color: rgba(75,120,255,.28);
}
.history-drawer {
  position: absolute;
  inset: 0;
  z-index: 70;
  display: flex;
  justify-content: flex-end;
  background: rgba(31,42,68,.16);
  backdrop-filter: blur(3px);
}
.history-drawer aside {
  width: min(420px, calc(100vw - 32px));
  height: 100%;
  padding: 20px;
  background: rgba(255,255,255,.98);
  border-left: 1px solid rgba(34,57,98,.08);
  box-shadow: -18px 0 44px rgba(34,57,98,.13);
}
.history-drawer header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.history-drawer header span {
  display: block;
  color: #8a94a6;
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}
.history-drawer header strong {
  display: block;
  margin-top: 4px;
  color: #1f2a44;
  font-size: 20px;
}
.history-drawer header button {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: #eef2f6;
  color: #52607a;
  font-size: 24px;
  cursor: pointer;
}
.history-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.history-grid button {
  text-align: left;
  padding: 8px;
  border: 1px solid rgba(34,57,98,.08);
  border-radius: 16px;
  background: #f8fafc;
  cursor: pointer;
}
.history-grid img,
.history-grid video {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 12px;
  object-fit: cover;
  background: #eef2f6;
}
.history-grid strong {
  display: block;
  margin-top: 8px;
  color: #1f2a44;
  font-size: 13px;
}
.history-grid span,
.history-empty {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.5;
}
.workflow-modal {
  justify-content: flex-start;
  align-items: stretch;
  background: rgba(31,42,68,.18);
  backdrop-filter: blur(3px);
}
.workflow-panel {
  width: min(560px, calc(100vw - 96px));
  max-height: none;
  height: calc(100vh - 40px);
  margin: 20px 0 20px 86px;
  border-color: rgba(34,57,98,.08);
  border-radius: 22px;
  background: rgba(255,255,255,.98);
  box-shadow: 0 24px 60px rgba(34,57,98,.18);
}
.workflow-panel h2 {
  color: #1f2a44;
}
.workflow-panel p {
  color: #6b7280;
}
.workflow-panel header button {
  background: #eef2f6;
  color: #52607a;
}
.workflow-filters button {
  background: #f3f6fb;
  color: #52607a;
}
.workflow-filters button.active {
  background: #1f2a44;
  color: #fff;
}
.workflow-filters input {
  width: 100%;
  margin-left: 0;
  border-color: rgba(34,57,98,.10);
  background: #f8fafc;
  color: #1f2a44;
}
.template-strip {
  grid-template-columns: 1fr;
}
.template-card {
  border-color: rgba(22,133,93,.18);
  background: linear-gradient(180deg, #f2fbf5, #fff);
  color: #1f2a44;
}
.template-card span {
  background: #e8f3eb;
  color: #0f6a36;
}
.template-card small {
  color: #6b7280;
}
.workflow-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.workflow-card {
  min-height: 188px;
  border-color: rgba(34,57,98,.08);
  background: linear-gradient(180deg, #fff, #f8fafc);
  color: #1f2a44;
}
.workflow-card:hover {
  border-color: rgba(75,120,255,.46);
  box-shadow: 0 16px 32px rgba(34,57,98,.10);
}
.workflow-card span {
  background: #eff4ff;
  color: #355ce0;
}
.workflow-card strong {
  margin: 30px 0 10px;
}
.workflow-card p,
.workflow-card small,
.workflow-empty {
  color: #6b7280;
}
@media (max-width: 760px) {
  .pipeline-header { padding: 0 16px; }
  .canvas-title { width: 120px; font-size: 20px; }
  .header-actions button:not(.intranet-pill) { display: none; }
  .node-composer {
    width: calc(100vw - 24px);
    min-height: 300px;
    bottom: 12px;
  }
  .node-composer textarea { left: 18px; top: 154px; }
  .asset-pill { width: 100%; height: 64px; flex-direction: row; }
  .workflow-panel { width: calc(100vw - 24px); }
  .workflow-filters input { width: 100%; margin-left: 0; }
}
</style>
