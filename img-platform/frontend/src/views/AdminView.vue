<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'

interface Profile {
  name: string
  api_key_masked?: string
  base_url?: string
  enabled: boolean
  priority: number
  models: Record<string, string[]>
}

interface User {
  id: number
  username: string
  is_admin: boolean
  created_at: string
}

interface ModelPath {
  id: string
  label: string
  category: string
  uri: string
  mount_path?: string
  notes?: string
  enabled: boolean
  created_at?: string
  updated_at?: string
}

interface ComfyWorkflow {
  id: string
  name: string
  description?: string
  category: string
  enabled: boolean
  workflow_json: Record<string, any>
  notes?: string
  created_at?: string
  updated_at?: string
}

type Category = 'all' | 'image' | 'voice' | 'video' | 'music' | 'text' | 'users' | 'paths' | 'workflows'

const categories: Array<{ key: Category; label: string; icon: string }> = [
  { key: 'all', label: 'All', icon: 'A' },
  { key: 'image', label: 'Image', icon: 'I' },
  { key: 'voice', label: 'Voice', icon: 'V' },
  { key: 'video', label: 'Video', icon: '▶' },
  { key: 'music', label: 'Music', icon: '♪' },
  { key: 'text', label: 'Text', icon: 'T' },
  { key: 'workflows', label: 'Workflows', icon: 'W' },
  { key: 'users', label: 'Users', icon: 'U' },
  { key: 'paths', label: 'Paths', icon: 'P' },
]

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || window.location.origin
const apiDocsUrl = `${apiBaseUrl.replace(/\/$/, '')}/docs`

const modelCategories: Record<Exclude<Category, 'all' | 'users' | 'paths' | 'workflows'>, string[]> = {
  image: ['image-01'],
  voice: ['speech-2.8-hd', 'speech-2.8-turbo', 'speech-2.6-hd', 'speech-2.6-turbo'],
  video: ['MiniMax-Hailuo-2.3', 'MiniMax-Hailuo-2.3-Fast', 'MiniMax-Hailuo-02', 'S2V-01'],
  music: ['music-2.6', 'music-2.5+', 'music-2.5'],
  text: ['MiniMax-M2.7'],
}

const profiles = ref<Profile[]>([])
const users = ref<User[]>([])
const modelPaths = ref<ModelPath[]>([])
const comfyWorkflows = ref<ComfyWorkflow[]>([])
const activeCategory = ref<Category>('all')
const selectedName = ref('')
const userSearch = ref('')
const pathSearch = ref('')
const workflowSearch = ref('')
const workflowImportSummary = ref('')
const isLoading = ref(false)
const loadError = ref('')
const showForm = ref(false)
const showUserForm = ref(false)
const showPathForm = ref(false)
const showWorkflowForm = ref(false)
const editingProfile = ref<Profile | null>(null)
const editingUser = ref<User | null>(null)
const editingModelPath = ref<ModelPath | null>(null)
const editingWorkflow = ref<ComfyWorkflow | null>(null)
const formError = ref('')
const userFormError = ref('')
const pathFormError = ref('')
const workflowFormError = ref('')
const form = ref({
  name: '',
  api_key: '',
  base_url: 'https://api.minimax.io',
  enabled: true,
  priority: 1,
  models: {
    image: ['image-01'],
    voice: [] as string[],
    video: ['MiniMax-Hailuo-2.3'],
    music: [] as string[],
    text: ['MiniMax-M2.7'],
  } as Record<string, string[]>,
})
const customModelInputs = ref<Record<string, string>>({
  image: '',
  voice: '',
  video: '',
  music: '',
  text: '',
})
const userForm = ref({
  username: '',
  password: '',
  is_admin: false,
})
const pathForm = ref({
  label: '',
  category: 'audio_encoders',
  uri: 'smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders',
  mount_path: '',
  notes: '',
  enabled: true,
})
const workflowForm = ref({
  name: '',
  description: '',
  category: 'image',
  enabled: true,
  workflow_json_text: '',
  notes: '',
})

const normalizedProfiles = computed(() => {
  if (Array.isArray(profiles.value)) return profiles.value
  return Object.values(profiles.value || {}) as Profile[]
})

const filteredProfiles = computed(() => {
  if (activeCategory.value === 'all') return normalizedProfiles.value
  if (activeCategory.value === 'users' || activeCategory.value === 'paths' || activeCategory.value === 'workflows') return normalizedProfiles.value
  return normalizedProfiles.value.filter((profile) => profile.models?.[activeCategory.value]?.length)
})

const enabledCount = computed(() => normalizedProfiles.value.filter((profile) => profile.enabled).length)
const modelCount = computed(() => {
  const names = new Set<string>()
  normalizedProfiles.value.forEach((profile) => {
    Object.values(profile.models || {}).forEach((models) => models.forEach((model) => names.add(model)))
  })
  return names.size
})

const adminCount = computed(() => users.value.filter((u) => u.is_admin).length)
const regularUserCount = computed(() => users.value.filter((u) => !u.is_admin).length)
const filteredUsers = computed(() => {
  const query = userSearch.value.trim().toLowerCase()
  if (!query) return users.value
  return users.value.filter((user) => user.username.toLowerCase().includes(query) || String(user.id).includes(query))
})
const filteredModelPaths = computed(() => {
  const query = pathSearch.value.trim().toLowerCase()
  if (!query) return modelPaths.value
  return modelPaths.value.filter((path) =>
    [path.label, path.category, path.uri, path.mount_path || '', path.notes || '']
      .some((value) => value.toLowerCase().includes(query))
  )
})
const filteredWorkflows = computed(() => {
  const query = workflowSearch.value.trim().toLowerCase()
  if (!query) return comfyWorkflows.value
  return comfyWorkflows.value.filter((workflow) =>
    [workflow.name, workflow.description || '', workflow.category, workflow.notes || '', workflow.id]
      .some((value) => value.toLowerCase().includes(query))
  )
})
const enabledPathCount = computed(() => modelPaths.value.filter((path) => path.enabled).length)
const modelPathCategoryCount = computed(() => new Set(modelPaths.value.map((path) => path.category)).size)
const enabledWorkflowCount = computed(() => comfyWorkflows.value.filter((workflow) => workflow.enabled).length)
const workflowCategoryCount = computed(() => new Set(comfyWorkflows.value.map((workflow) => workflow.category)).size)
const summaryStats = computed(() => {
  if (activeCategory.value === 'users') {
    return {
      total: users.value.length,
      totalLabel: 'Total users',
      second: adminCount.value,
      secondLabel: 'Admins',
      third: regularUserCount.value,
      thirdLabel: 'Regular users',
    }
  }
  if (activeCategory.value === 'paths') {
    return {
      total: modelPaths.value.length,
      totalLabel: 'Model paths',
      second: enabledPathCount.value,
      secondLabel: 'Enabled',
      third: modelPathCategoryCount.value,
      thirdLabel: 'Categories',
    }
  }
  if (activeCategory.value === 'workflows') {
    return {
      total: comfyWorkflows.value.length,
      totalLabel: 'Workflows',
      second: enabledWorkflowCount.value,
      secondLabel: 'Enabled',
      third: workflowCategoryCount.value,
      thirdLabel: 'Categories',
    }
  }
  return {
    total: normalizedProfiles.value.length,
    totalLabel: 'Total profiles',
    second: enabledCount.value,
    secondLabel: 'Enabled',
    third: modelCount.value,
    thirdLabel: 'Routed models',
  }
})

async function fetchProfiles() {
  isLoading.value = true
  loadError.value = ''
  try {
    const response = await api.get('/api/profiles')
    const data = response.data
    profiles.value = Array.isArray(data) ? data : Object.values(data || {})
    if (!selectedName.value && profiles.value.length) selectedName.value = profiles.value[0].name
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to load profiles'
  } finally {
    isLoading.value = false
  }
}

function emptyModels() {
  return { image: [], voice: [], video: [], music: [], text: [] } as Record<string, string[]>
}

function openAdd() {
  editingProfile.value = null
  form.value = {
    name: '',
    api_key: '',
    base_url: 'https://api.minimax.io',
    enabled: true,
    priority: Math.max(1, normalizedProfiles.value.length + 1),
    models: { ...emptyModels(), image: ['image-01'], video: ['MiniMax-Hailuo-2.3'], text: ['MiniMax-M2.7'] },
  }
  formError.value = ''
  showForm.value = true
}

function openEdit(profile: Profile) {
  editingProfile.value = profile
  form.value = {
    name: profile.name,
    api_key: '',
    base_url: profile.base_url || 'https://api.minimax.io',
    enabled: profile.enabled,
    priority: profile.priority,
    models: { ...emptyModels(), ...(profile.models || {}) },
  }
  formError.value = ''
  showForm.value = true
}

async function saveProfile() {
  if (!form.value.name.trim()) {
    formError.value = 'Name is required'
    return
  }
  if (!editingProfile.value && !form.value.api_key.trim()) {
    formError.value = 'API key is required for new profiles'
    return
  }

  const payload = {
    ...form.value,
    name: form.value.name.trim(),
    api_key: form.value.api_key.trim() || undefined,
  }

  try {
    if (editingProfile.value) {
      await api.put(`/api/profiles/${editingProfile.value.name}`, payload)
    } else {
      await api.post('/api/profiles', payload)
    }
    showForm.value = false
    await fetchProfiles()
    selectedName.value = payload.name
  } catch (error: any) {
    formError.value = error?.response?.data?.detail || error.message || 'Failed to save profile'
  }
}

async function toggleProfile(profile: Profile) {
  const action = profile.enabled ? 'disable' : 'enable'
  await api.post(`/api/profiles/${profile.name}/${action}`)
  await fetchProfiles()
}

async function deleteProfile(profile: Profile) {
  if (!confirm(`Delete profile "${profile.name}"?`)) return
  await api.delete(`/api/profiles/${profile.name}`)
  if (selectedName.value === profile.name) selectedName.value = ''
  await fetchProfiles()
}

function categoryModels(profile: Profile) {
  return Object.entries(profile.models || {}).filter(([, models]) => models.length)
}

function modelsForCategory(category: string, defaults: string[]) {
  const selected = form.value.models[category] || []
  return Array.from(new Set([...defaults, ...selected]))
}

function addCustomModel(category: string) {
  const model = (customModelInputs.value[category] || '').trim()
  if (!model) return
  const current = form.value.models[category] || []
  if (!current.includes(model)) {
    form.value.models[category] = [...current, model]
  }
  customModelInputs.value[category] = ''
}

async function fetchUsers() {
  try {
    const response = await api.get('/api/admin/users')
    users.value = response.data
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to load users'
  }
}

async function fetchModelPaths() {
  try {
    const response = await api.get('/api/comfyui/model-paths')
    modelPaths.value = response.data?.paths || []
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to load model paths'
  }
}

async function fetchWorkflows() {
  try {
    const response = await api.get('/api/comfyui/workflows?include_disabled=true')
    comfyWorkflows.value = response.data?.workflows || []
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to load workflows'
  }
}

async function importWorkflowsFromFolder() {
  workflowImportSummary.value = ''
  try {
    const response = await api.post('/api/comfyui/workflows/import')
    const imported = response.data?.imported || []
    const skipped = response.data?.skipped || []
    workflowImportSummary.value = `Imported ${imported.length}, skipped ${skipped.length}`
    await fetchWorkflows()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to import workflows'
  }
}

function refreshActive() {
  if (activeCategory.value === 'users') {
    fetchUsers()
  } else if (activeCategory.value === 'paths') {
    fetchModelPaths()
  } else if (activeCategory.value === 'workflows') {
    fetchWorkflows()
  } else {
    fetchProfiles()
  }
}

function openAddModelPath() {
  editingModelPath.value = null
  pathForm.value = {
    label: 'SJM audio_encoders',
    category: 'audio_encoders',
    uri: 'smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders',
    mount_path: '',
    notes: 'Fill mount path with the local path used by the ComfyUI host at 192.168.1.195.',
    enabled: true,
  }
  pathFormError.value = ''
  showPathForm.value = true
}

function openEditModelPath(path: ModelPath) {
  editingModelPath.value = path
  pathForm.value = {
    label: path.label,
    category: path.category,
    uri: path.uri,
    mount_path: path.mount_path || '',
    notes: path.notes || '',
    enabled: path.enabled,
  }
  pathFormError.value = ''
  showPathForm.value = true
}

async function saveModelPath() {
  pathFormError.value = ''
  if (!pathForm.value.label.trim()) {
    pathFormError.value = 'Label is required'
    return
  }
  if (!pathForm.value.category.trim()) {
    pathFormError.value = 'Category is required'
    return
  }
  if (!pathForm.value.uri.trim()) {
    pathFormError.value = 'SMB or local path is required'
    return
  }

  const payload = {
    ...pathForm.value,
    label: pathForm.value.label.trim(),
    category: pathForm.value.category.trim(),
    uri: pathForm.value.uri.trim(),
    mount_path: pathForm.value.mount_path.trim(),
    notes: pathForm.value.notes.trim(),
  }

  try {
    if (editingModelPath.value) {
      await api.put(`/api/comfyui/model-paths/${editingModelPath.value.id}`, payload)
    } else {
      await api.post('/api/comfyui/model-paths', payload)
    }
    showPathForm.value = false
    await fetchModelPaths()
  } catch (error: any) {
    pathFormError.value = error?.response?.data?.detail || error.message || 'Failed to save model path'
  }
}

async function deleteModelPath(path: ModelPath) {
  if (!confirm(`Delete model path "${path.label}"?`)) return
  try {
    await api.delete(`/api/comfyui/model-paths/${path.id}`)
    await fetchModelPaths()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to delete model path'
  }
}

async function copyPath(value: string) {
  try {
    await navigator.clipboard.writeText(value)
  } catch {
    loadError.value = 'Copy failed. Select the path text and copy it manually.'
  }
}

function formatWorkflowJson(workflow: Record<string, any>) {
  return JSON.stringify(workflow || {}, null, 2)
}

function openAddWorkflow() {
  editingWorkflow.value = null
  workflowForm.value = {
    name: '',
    description: '',
    category: 'image',
    enabled: true,
    workflow_json_text: '{\n  "1": {\n    "class_type": "SaveImage",\n    "inputs": {}\n  }\n}',
    notes: '',
  }
  workflowFormError.value = ''
  showWorkflowForm.value = true
}

function openEditWorkflow(workflow: ComfyWorkflow) {
  editingWorkflow.value = workflow
  workflowForm.value = {
    name: workflow.name,
    description: workflow.description || '',
    category: workflow.category || 'image',
    enabled: workflow.enabled,
    workflow_json_text: formatWorkflowJson(workflow.workflow_json),
    notes: workflow.notes || '',
  }
  workflowFormError.value = ''
  showWorkflowForm.value = true
}

async function saveWorkflow() {
  workflowFormError.value = ''
  let workflowJson: Record<string, any>
  try {
    workflowJson = JSON.parse(workflowForm.value.workflow_json_text)
  } catch (error: any) {
    workflowFormError.value = `Invalid JSON: ${error.message}`
    return
  }
  const payload = {
    name: workflowForm.value.name.trim(),
    description: workflowForm.value.description.trim(),
    category: workflowForm.value.category.trim() || 'image',
    enabled: workflowForm.value.enabled,
    workflow_json: workflowJson,
    notes: workflowForm.value.notes.trim(),
  }
  if (!payload.name) {
    workflowFormError.value = 'Workflow name is required'
    return
  }

  try {
    if (editingWorkflow.value) {
      await api.put(`/api/comfyui/workflows/${editingWorkflow.value.id}`, payload)
    } else {
      await api.post('/api/comfyui/workflows', payload)
    }
    showWorkflowForm.value = false
    await fetchWorkflows()
  } catch (error: any) {
    workflowFormError.value = error?.response?.data?.detail || error.message || 'Failed to save workflow'
  }
}

async function deleteWorkflow(workflow: ComfyWorkflow) {
  if (!confirm(`Delete workflow "${workflow.name}"?`)) return
  try {
    await api.delete(`/api/comfyui/workflows/${workflow.id}`)
    await fetchWorkflows()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to delete workflow'
  }
}

async function toggleWorkflow(workflow: ComfyWorkflow) {
  try {
    await api.put(`/api/comfyui/workflows/${workflow.id}`, {
      name: workflow.name,
      description: workflow.description || '',
      category: workflow.category || 'image',
      enabled: !workflow.enabled,
      workflow_json: workflow.workflow_json,
      notes: workflow.notes || '',
    })
    await fetchWorkflows()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to toggle workflow'
  }
}

function openAddUser() {
  editingUser.value = null
  userForm.value = { username: '', password: '', is_admin: false }
  showUserForm.value = true
  userFormError.value = ''
}

function openEditUser(user: User) {
  editingUser.value = user
  userForm.value = { username: user.username, password: '', is_admin: user.is_admin }
  showUserForm.value = true
  userFormError.value = ''
}

async function saveUser() {
  userFormError.value = ''
  if (!userForm.value.username.trim()) {
    userFormError.value = 'Username is required'
    return
  }
  if (!editingUser.value && !userForm.value.password) {
    userFormError.value = 'Password is required for new users'
    return
  }

  const payload: any = {
    username: userForm.value.username.trim(),
    is_admin: userForm.value.is_admin,
  }
  if (userForm.value.password) {
    payload.password = userForm.value.password
  }

  try {
    if (editingUser.value) {
      await api.put(`/api/admin/users/${editingUser.value.id}`, payload)
    } else {
      await api.post('/api/admin/users', payload)
    }
    showUserForm.value = false
    await fetchUsers()
  } catch (error: any) {
    userFormError.value = error?.response?.data?.detail || error.message || 'Failed to save user'
  }
}

async function deleteUser(user: User) {
  if (!confirm(`Delete user "${user.username}"?`)) return
  try {
    await api.delete(`/api/admin/users/${user.id}`)
    await fetchUsers()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to delete user'
  }
}

async function toggleAdmin(user: User) {
  try {
    await api.put(`/api/admin/users/${user.id}`, {
      username: user.username,
      is_admin: !user.is_admin,
    })
    await fetchUsers()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error.message || 'Failed to toggle admin'
  }
}

onMounted(() => {
  fetchProfiles()
  fetchUsers()
  fetchModelPaths()
  fetchWorkflows()
})
</script>

<template>
  <main class="profiles-page">
    <header class="app-header">
      <div class="brand-group">
        <div class="brand-mark">AI</div>
        <div>
          <h1>AI Tool Studio</h1>
          <p>Provider profile routing</p>
        </div>
      </div>

      <nav class="category-tabs" aria-label="Profile categories">
        <button
          v-for="category in categories"
          :key="category.key"
          class="category-tab"
          :class="{ active: activeCategory === category.key }"
          @click="activeCategory = category.key"
        >
          <span class="tab-icon">{{ category.icon }}</span>
          {{ category.label }}
        </button>
      </nav>

      <div class="header-actions">
        <a class="icon-button" :href="apiDocsUrl" target="_blank" title="Open API docs">⌘</a>
        <button class="icon-button" title="Refresh" @click="refreshActive">↻</button>
        <button class="text-action muted" title="Manage all users" @click="activeCategory = 'users'">
          Users
        </button>
        <button class="text-action muted" title="Manage ComfyUI model paths" @click="activeCategory = 'paths'">
          Paths
        </button>
        <button
          class="text-action"
          :title="activeCategory === 'paths' ? 'Add model path' : activeCategory === 'workflows' ? 'Add workflow' : 'Add user'"
          @click="activeCategory === 'paths' ? openAddModelPath() : activeCategory === 'workflows' ? openAddWorkflow() : openAddUser()"
        >
          <span>+</span>
          {{ activeCategory === 'paths' ? 'Add Path' : activeCategory === 'workflows' ? 'Add Workflow' : 'Add User' }}
        </button>
        <button
          class="add-button"
          :title="activeCategory === 'users' ? 'Add user' : activeCategory === 'paths' ? 'Add model path' : activeCategory === 'workflows' ? 'Add workflow' : 'Add profile'"
          @click="activeCategory === 'users' ? openAddUser() : activeCategory === 'paths' ? openAddModelPath() : activeCategory === 'workflows' ? openAddWorkflow() : openAdd()"
        >+</button>
      </div>
    </header>

    <section class="summary-strip">
      <div class="summary-item">
        <span>{{ summaryStats.total }}</span>
        <p>{{ summaryStats.totalLabel }}</p>
      </div>
      <div class="summary-item">
        <span>{{ summaryStats.second }}</span>
        <p>{{ summaryStats.secondLabel }}</p>
      </div>
      <div class="summary-item">
        <span>{{ summaryStats.third }}</span>
        <p>{{ summaryStats.thirdLabel }}</p>
      </div>
      <div class="summary-item grow">
        <span>{{ loadError || 'Backend target: /api' }}</span>
        <p>{{ loadError ? 'Connection issue' : 'Ready' }}</p>
      </div>
    </section>

    <section class="profile-list" aria-label="Profiles">
      <!-- Profile Management View -->
      <template v-if="activeCategory !== 'users' && activeCategory !== 'paths' && activeCategory !== 'workflows'">
        <div v-if="isLoading" class="empty-state">Loading profiles...</div>
        <div v-else-if="filteredProfiles.length === 0" class="empty-state">
          No profiles in this category.
          <button @click="openAdd">Add Profile</button>
        </div>

        <article
          v-for="profile in filteredProfiles"
          :key="profile.name"
          class="profile-card"
          :class="{ selected: selectedName === profile.name, disabled: !profile.enabled }"
          @click="selectedName = profile.name"
        >
          <div class="drag-handle">⋮⋮</div>
          <div class="profile-avatar">{{ profile.name.slice(0, 2).toUpperCase() }}</div>

          <div class="profile-main">
            <div class="profile-title-row">
              <h2>{{ profile.name }}</h2>
              <span class="status-pill" :class="{ on: profile.enabled }">
                {{ profile.enabled ? 'Enabled' : 'Disabled' }}
              </span>
            </div>
            <a class="base-url" :href="profile.base_url || '#'" target="_blank" @click.stop>
              {{ profile.base_url || 'No base URL configured' }}
            </a>
            <div class="model-row">
              <span v-for="[category, models] in categoryModels(profile)" :key="category" class="model-chip">
                {{ category }} · {{ models.join(', ') }}
              </span>
            </div>
          </div>

          <div class="profile-meta">
            <span>Priority {{ profile.priority }}</span>
            <span>{{ profile.api_key_masked || '****' }}</span>
          </div>

          <div class="profile-actions" @click.stop>
            <button class="primary-action" @click="toggleProfile(profile)">
              {{ profile.enabled ? 'Disable' : 'Enable' }}
            </button>
            <button class="tool-button" title="Edit" @click="openEdit(profile)">✎</button>
            <button class="tool-button danger" title="Delete" @click="deleteProfile(profile)">⌫</button>
          </div>
        </article>
      </template>

      <!-- ComfyUI Workflows View -->
      <template v-else-if="activeCategory === 'workflows'">
        <section class="users-panel">
          <div class="users-toolbar">
            <div>
              <h2>ComfyUI Workflows</h2>
              <p>Manage API-format workflows used by local ComfyUI generation.</p>
            </div>
            <div class="users-tools">
              <input v-model="workflowSearch" type="search" placeholder="Search workflow, category, or note" />
              <button class="secondary-button compact-action" @click="importWorkflowsFromFolder">Sync Folder</button>
              <button class="primary-action" @click="openAddWorkflow">Add Workflow</button>
            </div>
          </div>

          <p v-if="workflowImportSummary" class="sync-summary">{{ workflowImportSummary }}</p>

          <div v-if="filteredWorkflows.length === 0" class="empty-state">
            No workflows found.
            <button @click="openAddWorkflow">Add Workflow</button>
          </div>

          <article
            v-for="workflow in filteredWorkflows"
            :key="workflow.id"
            class="path-card"
            :class="{ disabled: !workflow.enabled }"
          >
            <div class="profile-avatar">{{ workflow.category.slice(0, 2).toUpperCase() }}</div>

            <div class="profile-main">
              <div class="profile-title-row">
                <h2>{{ workflow.name }}</h2>
                <span class="status-pill" :class="{ on: workflow.enabled }">
                  {{ workflow.enabled ? 'Enabled' : 'Disabled' }}
                </span>
              </div>
              <p class="path-category">{{ workflow.category }} · {{ Object.keys(workflow.workflow_json || {}).length }} nodes</p>
              <p v-if="workflow.description" class="user-meta">{{ workflow.description }}</p>
              <p v-if="workflow.notes" class="user-meta">{{ workflow.notes }}</p>
            </div>

            <div class="profile-actions" @click.stop>
              <button class="primary-action" @click="toggleWorkflow(workflow)">
                {{ workflow.enabled ? 'Disable' : 'Enable' }}
              </button>
              <button class="tool-button" title="Copy workflow JSON" @click="copyPath(formatWorkflowJson(workflow.workflow_json))">⧉</button>
              <button class="tool-button" title="Edit workflow" @click="openEditWorkflow(workflow)">✎</button>
              <button class="tool-button danger" title="Delete workflow" @click="deleteWorkflow(workflow)">⌫</button>
            </div>
          </article>
        </section>
      </template>

      <!-- ComfyUI Model Paths View -->
      <template v-else-if="activeCategory === 'paths'">
        <section class="users-panel">
          <div class="users-toolbar">
            <div>
              <h2>ComfyUI Model Paths</h2>
              <p>Quick references for SMB storage and the local mount paths used by the ComfyUI host.</p>
            </div>
            <div class="users-tools">
              <input v-model="pathSearch" type="search" placeholder="Search path, category, or note" />
              <button class="primary-action" @click="openAddModelPath">Add Path</button>
            </div>
          </div>

          <div v-if="filteredModelPaths.length === 0" class="empty-state">
            No model paths found.
            <button @click="openAddModelPath">Add Path</button>
          </div>

          <article
            v-for="path in filteredModelPaths"
            :key="path.id"
            class="path-card"
            :class="{ disabled: !path.enabled }"
          >
            <div class="profile-avatar">{{ path.category.slice(0, 2).toUpperCase() }}</div>

            <div class="profile-main">
              <div class="profile-title-row">
                <h2>{{ path.label }}</h2>
                <span class="status-pill" :class="{ on: path.enabled }">
                  {{ path.enabled ? 'Enabled' : 'Disabled' }}
                </span>
              </div>
              <p class="path-category">{{ path.category }}</p>
              <div class="path-lines">
                <div>
                  <span>SMB</span>
                  <code>{{ path.uri }}</code>
                </div>
                <div>
                  <span>195 mount</span>
                  <code>{{ path.mount_path || 'Not set' }}</code>
                </div>
              </div>
              <p v-if="path.notes" class="user-meta">{{ path.notes }}</p>
            </div>

            <div class="profile-actions" @click.stop>
              <button class="primary-action" @click="copyPath(path.uri)">Copy SMB</button>
              <button v-if="path.mount_path" class="tool-button" title="Copy mount path" @click="copyPath(path.mount_path)">⧉</button>
              <button class="tool-button" title="Edit model path" @click="openEditModelPath(path)">✎</button>
              <button class="tool-button danger" title="Delete model path" @click="deleteModelPath(path)">⌫</button>
            </div>
          </article>
        </section>
      </template>

      <!-- User Management View -->
      <template v-else>
        <section class="users-panel">
          <div class="users-toolbar">
            <div>
              <h2>All Users</h2>
              <p>Manage login accounts, role changes, password resets, and user deletion.</p>
            </div>
            <div class="users-tools">
              <input v-model="userSearch" type="search" placeholder="Search username or ID" />
              <button class="primary-action" @click="openAddUser">Add User</button>
            </div>
          </div>

          <div v-if="isLoading" class="empty-state">Loading users...</div>
          <div v-else-if="filteredUsers.length === 0" class="empty-state">
            No users found.
            <button @click="openAddUser">Add User</button>
          </div>

          <article
            v-for="user in filteredUsers"
            :key="user.id"
            class="user-row"
          >
            <div class="profile-avatar">{{ user.username.slice(0, 2).toUpperCase() }}</div>

            <div class="profile-main">
              <div class="profile-title-row">
                <h2>{{ user.username }}</h2>
                <span class="status-pill" :class="{ on: user.is_admin }">
                  {{ user.is_admin ? 'Admin' : 'User' }}
                </span>
              </div>
              <p class="user-meta">User ID {{ user.id }} · Created {{ user.created_at ? new Date(user.created_at).toLocaleString() : 'unknown' }}</p>
            </div>

            <div class="profile-actions" @click.stop>
              <button class="primary-action" @click="toggleAdmin(user)">
                {{ user.is_admin ? 'Revoke Admin' : 'Make Admin' }}
              </button>
              <button class="tool-button" title="Edit user / reset password" @click="openEditUser(user)">✎</button>
              <button class="tool-button danger" title="Delete user" @click="deleteUser(user)">⌫</button>
            </div>
          </article>
        </section>
      </template>
    </section>

    <div v-if="showForm" class="modal-overlay" @click.self="showForm = false">
      <form class="modal-card" @submit.prevent="saveProfile">
        <div class="modal-header">
          <div>
            <h2>{{ editingProfile ? 'Edit Profile' : 'Add Profile' }}</h2>
            <p>{{ editingProfile ? 'Leave API key blank to keep the existing key.' : 'Create a routed provider endpoint.' }}</p>
          </div>
          <button type="button" class="tool-button" @click="showForm = false">×</button>
        </div>

        <label>
          Name
          <input v-model="form.name" :disabled="!!editingProfile" placeholder="MiniMax" />
        </label>
        <label>
          Base URL
          <input v-model="form.base_url" placeholder="https://api.minimax.io" />
        </label>
        <label>
          API Key
          <input v-model="form.api_key" type="password" placeholder="sk-..." />
        </label>

        <div class="form-row">
          <label>
            Priority
            <input v-model.number="form.priority" min="1" type="number" />
          </label>
          <label>
            Status
            <select v-model="form.enabled">
              <option :value="true">Enabled</option>
              <option :value="false">Disabled</option>
            </select>
          </label>
        </div>

        <div class="model-picker">
          <div v-for="(models, category) in modelCategories" :key="category" class="model-group">
            <h3>{{ category }}</h3>
            <label v-for="model in modelsForCategory(category, models)" :key="model" class="check-row">
              <input v-model="form.models[category]" :value="model" type="checkbox" />
              {{ model }}
            </label>
            <div class="custom-model-row">
              <input
                v-model="customModelInputs[category]"
                placeholder="Custom model ID"
                @keydown.enter.prevent="addCustomModel(category)"
              />
              <button type="button" @click="addCustomModel(category)">Add</button>
            </div>
          </div>
        </div>

        <p v-if="formError" class="form-error">{{ formError }}</p>
        <div class="modal-actions">
          <button type="button" class="secondary-button" @click="showForm = false">Cancel</button>
          <button type="submit" class="save-button">Save</button>
        </div>
      </form>
    </div>

    <!-- Workflow Form Modal -->
    <div v-if="showWorkflowForm" class="modal-overlay" @click.self="showWorkflowForm = false">
      <form class="modal-card workflow-modal" @submit.prevent="saveWorkflow">
        <div class="modal-header">
          <div>
            <h2>{{ editingWorkflow ? 'Edit Workflow' : 'Add Workflow' }}</h2>
            <p>Paste ComfyUI API-format JSON. Runtime patches prompt, checkpoint, seed, size, and batch size.</p>
          </div>
          <button type="button" class="tool-button" @click="showWorkflowForm = false">×</button>
        </div>

        <div class="form-row">
          <label>
            Name
            <input v-model="workflowForm.name" placeholder="Default txt2img" required />
          </label>
          <label>
            Category
            <input v-model="workflowForm.category" placeholder="image" required />
          </label>
        </div>
        <label>
          Description
          <input v-model="workflowForm.description" placeholder="What this workflow is for" />
        </label>
        <label>
          Workflow JSON
          <textarea v-model="workflowForm.workflow_json_text" class="json-editor" spellcheck="false" required />
        </label>
        <label>
          Notes
          <textarea v-model="workflowForm.notes" placeholder="Required models, mount paths, unsupported nodes, or restart notes." />
        </label>

        <label class="check-row">
          <input v-model="workflowForm.enabled" type="checkbox" />
          Enabled
        </label>

        <p v-if="workflowFormError" class="form-error">{{ workflowFormError }}</p>
        <div class="modal-actions">
          <button type="button" class="secondary-button" @click="showWorkflowForm = false">Cancel</button>
          <button type="submit" class="save-button">Save</button>
        </div>
      </form>
    </div>

    <!-- Model Path Form Modal -->
    <div v-if="showPathForm" class="modal-overlay" @click.self="showPathForm = false">
      <form class="modal-card" @submit.prevent="saveModelPath">
        <div class="modal-header">
          <div>
            <h2>{{ editingModelPath ? 'Edit Model Path' : 'Add Model Path' }}</h2>
            <p>Store SMB shortcuts and the ComfyUI host mount path. This does not mount storage by itself.</p>
          </div>
          <button type="button" class="tool-button" @click="showPathForm = false">×</button>
        </div>

        <label>
          Label
          <input v-model="pathForm.label" placeholder="SJM audio_encoders" required />
        </label>
        <label>
          Category
          <input v-model="pathForm.category" placeholder="audio_encoders" required />
        </label>
        <label>
          SMB / Storage URI
          <input v-model="pathForm.uri" placeholder="smb://192.168.1.60/团队文件-SJM-MediaFile/Comfyui_Model/audio_encoders" required />
        </label>
        <label>
          195 local mount path
          <input v-model="pathForm.mount_path" placeholder="/mnt/Comfyui_Model/audio_encoders" />
        </label>
        <label>
          Notes
          <textarea v-model="pathForm.notes" placeholder="Where this is mounted, which workflow needs it, or restart notes." />
        </label>

        <label class="check-row">
          <input v-model="pathForm.enabled" type="checkbox" />
          Enabled
        </label>

        <p v-if="pathFormError" class="form-error">{{ pathFormError }}</p>
        <div class="modal-actions">
          <button type="button" class="secondary-button" @click="showPathForm = false">Cancel</button>
          <button type="submit" class="save-button">Save</button>
        </div>
      </form>
    </div>

    <!-- User Form Modal -->
    <div v-if="showUserForm" class="modal-overlay" @click.self="showUserForm = false">
      <form class="modal-card" @submit.prevent="saveUser">
        <div class="modal-header">
          <div>
            <h2>{{ editingUser ? 'Edit User' : 'Add User' }}</h2>
            <p>{{ editingUser ? 'Leave password blank to keep the existing password.' : 'Create a new user account.' }}</p>
          </div>
          <button type="button" class="tool-button" @click="showUserForm = false">×</button>
        </div>

        <label>
          Username
          <input v-model="userForm.username" :disabled="!!editingUser" placeholder="username" required />
        </label>
        <label>
          Password
          <input v-model="userForm.password" type="password" :placeholder="editingUser ? 'Leave blank to keep current' : 'Enter password'" :required="!editingUser" />
        </label>

        <label class="check-row">
          <input v-model="userForm.is_admin" type="checkbox" />
          Administrator privileges
        </label>

        <p v-if="userFormError" class="form-error">{{ userFormError }}</p>
        <div class="modal-actions">
          <button type="button" class="secondary-button" @click="showUserForm = false">Cancel</button>
          <button type="submit" class="save-button">Save</button>
        </div>
      </form>
    </div>
  </main>
</template>

<style scoped>
.profiles-page {
  min-height: 100vh;
  padding: 28px 38px 64px;
  background: #fbfbfc;
  color: #111827;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.app-header {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto minmax(190px, 1fr);
  align-items: center;
  gap: 18px;
  margin-bottom: 18px;
}

.brand-group,
.header-actions,
.category-tabs,
.profile-title-row,
.profile-actions,
.model-row,
.modal-header,
.modal-actions,
.form-row {
  display: flex;
  align-items: center;
}

.brand-group { gap: 12px; }
.brand-mark {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: #eef6ff;
  color: #1677ff;
  font-weight: 800;
}
.brand-group h1 {
  margin: 0;
  color: #1677ff;
  font-size: 24px;
  line-height: 1.1;
}
.brand-group p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.category-tabs {
  justify-self: center;
  gap: 6px;
  padding: 5px;
  border-radius: 16px;
  background: #f0f0f3;
}
.category-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 15px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: #6b7280;
  font-size: 15px;
  font-weight: 650;
  cursor: pointer;
}
.category-tab.active {
  background: #fff;
  color: #111827;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
}
.tab-icon {
  color: #1677ff;
  font-weight: 800;
}

.header-actions {
  justify-self: end;
  gap: 10px;
}
.icon-button,
.tool-button,
.add-button,
.text-action,
.primary-action,
.secondary-button,
.save-button,
.empty-state button {
  border: 0;
  cursor: pointer;
  font-weight: 700;
}
.icon-button,
.tool-button {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #f0f0f3;
  color: #6b7280;
  text-decoration: none;
  font-size: 17px;
}
.text-action {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 14px;
  border-radius: 10px;
  background: #111827;
  color: #fff;
  white-space: nowrap;
}
.text-action.muted {
  background: #f3f4f6;
  color: #111827;
}
.text-action span {
  font-size: 18px;
  line-height: 1;
}
.add-button {
  width: 46px;
  height: 46px;
  border-radius: 999px;
  background: #ff7a1a;
  color: #fff;
  font-size: 28px;
  line-height: 1;
  box-shadow: 0 10px 22px rgba(255, 122, 26, 0.28);
}

.summary-strip {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.summary-item {
  min-width: 160px;
  padding: 12px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
}
.summary-item.grow { flex: 1; }
.summary-item span {
  display: block;
  overflow: hidden;
  color: #111827;
  font-size: 18px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-item p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.profile-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.users-panel {
  display: grid;
  gap: 14px;
}
.users-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 26px;
  border: 1px solid #e1e4e8;
  border-radius: 18px;
  background: #fff;
}
.users-toolbar h2 {
  margin: 0;
  color: #111827;
  font-size: 22px;
}
.users-toolbar p {
  margin: 6px 0 0;
  color: #6b7280;
  font-size: 14px;
}
.users-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: min(460px, 48vw);
}
.users-tools input {
  width: 100%;
  height: 40px;
  padding: 0 13px;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  background: #fff;
  color: #111827;
  font: inherit;
}
.user-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  min-height: 88px;
  padding: 20px 24px;
  border: 1px solid #e1e4e8;
  border-radius: 16px;
  background: #fff;
}
.path-card {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  min-height: 128px;
  padding: 20px 24px;
  border: 1px solid #e1e4e8;
  border-radius: 16px;
  background: #fff;
}
.path-card.disabled {
  opacity: 0.62;
}
.path-category {
  margin: 7px 0 0;
  color: #6b7280;
  font-size: 13px;
  font-weight: 800;
}
.path-lines {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.path-lines div {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}
.path-lines span {
  color: #6b7280;
  font-size: 12px;
  font-weight: 850;
  text-transform: uppercase;
}
.path-lines code {
  overflow: hidden;
  padding: 8px 10px;
  border-radius: 9px;
  background: #f5f7fb;
  color: #111827;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-meta {
  margin: 8px 0 0;
  overflow: hidden;
  color: #6b7280;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.profile-card {
  display: grid;
  grid-template-columns: 22px 44px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 16px;
  min-height: 116px;
  padding: 24px 30px;
  border: 1px solid #e1e4e8;
  border-radius: 18px;
  background: #fff;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}
.profile-card.selected {
  border-color: #1677ff;
  background: linear-gradient(90deg, #eef6ff 0%, #fff 54%);
  box-shadow: inset 0 0 0 1px rgba(22, 119, 255, 0.08);
}
.profile-card.disabled {
  opacity: 0.64;
}
.drag-handle {
  color: #b7bcc5;
  font-size: 18px;
  letter-spacing: -3px;
}
.profile-avatar {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid #e1e4e8;
  border-radius: 14px;
  background: #f7f8fa;
  color: #6b7280;
  font-weight: 800;
}
.profile-main {
  min-width: 0;
}
.profile-title-row {
  gap: 10px;
}
.profile-title-row h2 {
  margin: 0;
  color: #111827;
  font-size: 21px;
  line-height: 1.2;
}
.status-pill {
  padding: 3px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 12px;
  font-weight: 800;
}
.status-pill.on {
  background: #e8f7ee;
  color: #168a45;
}
.base-url {
  display: block;
  margin-top: 9px;
  overflow: hidden;
  color: #1677ff;
  font-size: 18px;
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-row {
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 12px;
}
.model-chip {
  padding: 5px 9px;
  border-radius: 999px;
  background: #f5f7fb;
  color: #596273;
  font-size: 12px;
  font-weight: 700;
}
.profile-meta {
  display: grid;
  gap: 6px;
  color: #6b7280;
  font-size: 13px;
  text-align: right;
  white-space: nowrap;
}
.profile-actions {
  gap: 10px;
}
.primary-action {
  height: 40px;
  padding: 0 16px;
  border-radius: 10px;
  background: #1677ff;
  color: #fff;
}
.compact-action {
  height: 40px;
  white-space: nowrap;
}
.sync-summary {
  margin: -4px 0 0;
  color: #168a45;
  font-size: 13px;
  font-weight: 800;
}
.tool-button.danger {
  color: #dc2626;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 180px;
  border: 1px dashed #d1d5db;
  border-radius: 18px;
  background: #fff;
  color: #6b7280;
}
.empty-state button {
  height: 36px;
  padding: 0 14px;
  border-radius: 10px;
  background: #1677ff;
  color: #fff;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(17, 24, 39, 0.34);
}
.modal-card {
  width: min(720px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  padding: 24px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);
}
.workflow-modal {
  width: min(980px, 100%);
}
.modal-header {
  justify-content: space-between;
  margin-bottom: 20px;
}
.modal-header h2 {
  margin: 0;
  font-size: 22px;
}
.modal-header p {
  margin: 5px 0 0;
  color: #6b7280;
}
.modal-card label {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  color: #374151;
  font-size: 13px;
  font-weight: 800;
}
.modal-card input,
.modal-card select,
.modal-card textarea {
  width: 100%;
  padding: 0 12px;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  background: #fff;
  color: #111827;
  font: inherit;
}
.modal-card input,
.modal-card select {
  height: 42px;
}
.modal-card textarea {
  min-height: 86px;
  padding: 10px 12px;
  resize: vertical;
}
.modal-card .json-editor {
  min-height: 320px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 1.45;
}
.modal-card input:disabled {
  background: #f3f4f6;
  color: #6b7280;
}
.form-row {
  gap: 14px;
}
.form-row label {
  flex: 1;
}
.model-picker {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.model-group {
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fafafa;
}
.model-group h3 {
  margin: 0 0 10px;
  color: #111827;
  font-size: 14px;
  text-transform: capitalize;
}
.check-row {
  display: flex !important;
  grid-template-columns: none !important;
  align-items: center;
  gap: 8px !important;
  margin: 8px 0 !important;
  color: #4b5563 !important;
  font-weight: 650 !important;
}
.check-row input {
  width: 16px;
  height: 16px;
}
.custom-model-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  margin-top: 12px;
}
.custom-model-row input {
  height: 34px;
  padding: 0 10px;
  font-size: 13px;
}
.custom-model-row button {
  height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: 9px;
  background: #1677ff;
  color: #fff;
  font-weight: 800;
  cursor: pointer;
}
.form-error {
  margin: 10px 0 0;
  color: #dc2626;
  font-weight: 700;
}
.modal-actions {
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
.secondary-button,
.save-button {
  height: 40px;
  padding: 0 18px;
  border-radius: 10px;
}
.secondary-button {
  background: #f3f4f6;
  color: #374151;
}
.save-button {
  background: #1677ff;
  color: #fff;
}

@media (max-width: 960px) {
  .profiles-page {
    padding: 20px 16px 56px;
  }
  .app-header {
    grid-template-columns: 1fr;
  }
  .category-tabs,
  .header-actions {
    justify-self: stretch;
  }
  .category-tabs {
    overflow-x: auto;
  }
  .header-actions {
    justify-content: flex-end;
  }
  .summary-strip {
    flex-wrap: wrap;
  }
  .summary-item {
    min-width: calc(50% - 6px);
  }
  .profile-card {
    grid-template-columns: 22px 44px minmax(0, 1fr);
  }
  .users-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
  .users-tools {
    min-width: 0;
    width: 100%;
  }
  .user-row {
    grid-template-columns: 44px minmax(0, 1fr);
  }
  .path-card {
    grid-template-columns: 44px minmax(0, 1fr);
  }
  .profile-meta,
  .profile-actions,
  .user-row .profile-actions,
  .path-card .profile-actions {
    grid-column: 3;
    justify-self: start;
  }
  .user-row .profile-actions,
  .path-card .profile-actions {
    grid-column: 2;
  }
  .profile-actions {
    flex-wrap: wrap;
  }
  .model-picker {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .summary-item {
    min-width: 100%;
  }
  .profile-card {
    padding: 18px;
  }
  .users-toolbar,
  .user-row,
  .path-card {
    padding: 18px;
  }
  .path-lines div {
    grid-template-columns: 1fr;
  }
  .users-tools {
    flex-direction: column;
    align-items: stretch;
  }
  .model-picker {
    grid-template-columns: 1fr;
  }
}
</style>
