from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.security import hash_password
from api.auth import require_admin
from models.database import get_db
from models.user import User

router = APIRouter(tags=["Admin UI"])


class AdminUserRequest(BaseModel):
    username: str
    password: Optional[str] = None
    is_admin: bool = False


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/", response_class=HTMLResponse)
async def admin_page(_: User = Depends(require_admin)):
    return HTMLResponse(ADMIN_HTML)


@router.get("/api/admin/users")
async def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
        for user in users
    ]


@router.post("/api/admin/users")
async def create_user(
    req: AdminUserRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not req.password or len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(username=username, password_hash=hash_password(req.password), is_admin=req.is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.put("/api/admin/users/{user_id}")
async def update_user(
    user_id: int,
    req: AdminUserRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    existing = db.query(User).filter(User.username == username, User.id != user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    user.username = username
    user.is_admin = req.is_admin
    if req.password:
        if len(req.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        user.password_hash = hash_password(req.password)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


ADMIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Tool Studio Admin</title>
  <style>
    :root {
      color-scheme: light;
      --blue: #1677ff;
      --text: #111827;
      --muted: #6b7280;
      --line: #e5e7eb;
      --soft: #f5f6f8;
      --orange: #ff7a1a;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: #fbfbfc; color: var(--text); }
    button, input, select, textarea { font: inherit; }
    button { cursor: pointer; border: 0; }
    .page { min-height: 100vh; padding: 30px 38px 64px; }
    .header { display: grid; grid-template-columns: minmax(240px, 1fr) auto minmax(190px, 1fr); gap: 18px; align-items: center; margin-bottom: 18px; }
    .brand { display: flex; gap: 12px; align-items: center; }
    .mark { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 12px; background: #eef6ff; color: var(--blue); font-weight: 900; }
    h1 { margin: 0; color: var(--blue); font-size: 24px; line-height: 1.1; }
    .brand p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    .tabs { justify-self: center; display: flex; gap: 6px; padding: 5px; border-radius: 16px; background: #f0f0f3; }
    .tab { display: inline-flex; align-items: center; gap: 8px; height: 38px; padding: 0 15px; border-radius: 12px; background: transparent; color: var(--muted); font-weight: 750; }
    .tab.active { background: #fff; color: var(--text); box-shadow: 0 1px 4px rgba(15,23,42,.08); }
    .tab b { color: var(--blue); }
    .actions { justify-self: end; display: flex; gap: 10px; align-items: center; }
    .icon-btn { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 11px; background: #f0f0f3; color: var(--muted); text-decoration: none; font-weight: 900; }
    .add-btn { width: 46px; height: 46px; border-radius: 50%; background: var(--orange); color: #fff; font-size: 28px; box-shadow: 0 10px 22px rgba(255,122,26,.28); }
    .summary { display: flex; gap: 12px; margin-bottom: 16px; }
    .summary-card { min-width: 160px; padding: 12px 16px; border: 1px solid var(--line); border-radius: 14px; background: #fff; }
    .summary-card.grow { flex: 1; }
    .summary-card strong { display: block; overflow: hidden; font-size: 18px; text-overflow: ellipsis; white-space: nowrap; }
    .summary-card span { display: block; margin-top: 4px; color: var(--muted); font-size: 13px; }
    .list { display: flex; flex-direction: column; gap: 16px; }
    .card { display: grid; grid-template-columns: 22px 44px minmax(0, 1fr) auto auto; gap: 16px; align-items: center; min-height: 116px; padding: 24px 30px; border: 1px solid #e1e4e8; border-radius: 18px; background: #fff; }
    .card.selected { border-color: var(--blue); background: linear-gradient(90deg, #eef6ff 0%, #fff 54%); box-shadow: inset 0 0 0 1px rgba(22,119,255,.08); }
    .card.disabled { opacity: .62; }
    .drag { color: #b7bcc5; font-size: 18px; letter-spacing: -3px; }
    .avatar { display: grid; place-items: center; width: 44px; height: 44px; border: 1px solid #e1e4e8; border-radius: 14px; background: #f7f8fa; color: var(--muted); font-weight: 900; }
    .main { min-width: 0; }
    .title { display: flex; align-items: center; gap: 10px; }
    .title h2 { margin: 0; font-size: 21px; line-height: 1.2; }
    .pill { padding: 3px 8px; border-radius: 999px; background: #f3f4f6; color: var(--muted); font-size: 12px; font-weight: 900; }
    .pill.on { background: #e8f7ee; color: #168a45; }
    .url { display: block; overflow: hidden; margin-top: 9px; color: var(--blue); font-size: 18px; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }
    .chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
    .chip { padding: 5px 9px; border-radius: 999px; background: #f5f7fb; color: #596273; font-size: 12px; font-weight: 750; }
    .quota { display: grid; gap: 6px; color: var(--muted); font-size: 13px; text-align: right; white-space: nowrap; }
    .card-actions { display: flex; gap: 10px; align-items: center; }
    .primary { height: 40px; padding: 0 16px; border-radius: 10px; background: var(--blue); color: #fff; font-weight: 800; }
    .tool { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; background: #f0f0f3; color: var(--muted); font-weight: 900; }
    .danger { color: #dc2626; }
    .empty { display: grid; place-items: center; min-height: 220px; border: 1px dashed #d1d5db; border-radius: 18px; background: #fff; color: var(--muted); }
    .modal { position: fixed; inset: 0; z-index: 10; display: none; place-items: center; padding: 24px; background: rgba(17,24,39,.34); }
    .modal.open { display: grid; }
    form { width: min(760px, 100%); max-height: calc(100vh - 48px); overflow: auto; padding: 24px; border-radius: 20px; background: #fff; box-shadow: 0 24px 60px rgba(15,23,42,.22); }
    .modal-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 20px; }
    .modal-head h2 { margin: 0; }
    .modal-head p { margin: 5px 0 0; color: var(--muted); }
    label { display: grid; gap: 8px; margin-bottom: 14px; color: #374151; font-size: 13px; font-weight: 850; }
    input, select, textarea { width: 100%; min-width: 0; border: 1px solid #d1d5db; border-radius: 10px; background: #fff; color: var(--text); }
    input, select { height: 42px; padding: 0 12px; }
    textarea { min-height: 76px; padding: 10px 12px; resize: vertical; }
    input:disabled { background: #f3f4f6; color: var(--muted); }
    .grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    .model-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 16px 0; }
    .model-box { padding: 14px; border: 1px solid var(--line); border-radius: 14px; background: #fafafa; }
    .model-box h3 { margin: 0 0 10px; font-size: 14px; text-transform: capitalize; }
    .check { display: flex; align-items: center; gap: 8px; margin: 8px 0; color: #4b5563; font-weight: 700; }
    .check input { width: 16px; height: 16px; }
    .custom-model-row { display: grid; grid-template-columns: minmax(0, 1fr) 34px; gap: 8px; margin-top: 12px; }
    .custom-model-row input { height: 34px; padding: 0 10px; font-size: 13px; }
    .mini-add { height: 34px; border-radius: 9px; background: var(--blue); color: #fff; font-weight: 900; }
    .form-error { color: #dc2626; font-weight: 800; min-height: 20px; }
    .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
    .secondary, .save { height: 40px; padding: 0 18px; border-radius: 10px; font-weight: 850; }
    .secondary { background: #f3f4f6; color: #374151; }
    .save { background: var(--blue); color: #fff; }
    @media (max-width: 920px) {
      .page { padding: 20px 16px 56px; }
      .header { grid-template-columns: 1fr; }
      .tabs, .actions { justify-self: stretch; }
      .tabs { overflow-x: auto; }
      .actions { justify-content: flex-end; }
      .summary { flex-wrap: wrap; }
      .summary-card { min-width: calc(50% - 6px); }
      .card { grid-template-columns: 22px 44px minmax(0, 1fr); padding: 18px; }
      .quota, .card-actions { grid-column: 3; justify-self: start; text-align: left; }
      .model-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <div class="brand">
        <div class="mark">AI</div>
        <div><h1>AI Tool Studio</h1><p>API profile routing and quota settings</p></div>
      </div>
      <nav class="tabs" id="tabs"></nav>
      <div class="actions">
        <a class="icon-btn" href="/docs" title="API 文档">⌘</a>
        <button class="icon-btn" onclick="loadAll()" title="刷新">↻</button>
        <button class="add-btn" onclick="active === 'users' ? openUserForm() : openForm()" title="新增">+</button>
      </div>
    </header>
    <section class="summary">
      <div class="summary-card"><strong id="total">0</strong><span id="totalLabel">API Profiles</span></div>
      <div class="summary-card"><strong id="enabled">0</strong><span id="enabledLabel">Enabled</span></div>
      <div class="summary-card"><strong id="models">0</strong><span id="modelsLabel">Models</span></div>
      <div class="summary-card grow"><strong id="status">Ready</strong><span>Backend status</span></div>
    </section>
    <section class="list" id="list"></section>
  </main>
  <div class="modal" id="modal" onclick="if(event.target === this) closeForm()">
    <form onsubmit="saveProfile(event)">
      <div class="modal-head">
        <div><h2 id="formTitle">Add API</h2><p>配置 API Key、Base URL、模型路由和额度。</p></div>
        <button type="button" class="tool" onclick="closeForm()">×</button>
      </div>
      <div class="grid2">
        <label>Name<input id="name" required placeholder="MiniMax" /></label>
        <label>Base URL<input id="base_url" required placeholder="https://api.minimax.io" /></label>
      </div>
      <div class="grid2">
        <label>Daily Quota<input id="daily_quota" type="number" min="0" placeholder="1000" /></label>
        <label>Monthly Quota<input id="monthly_quota" type="number" min="0" placeholder="30000" /></label>
      </div>
      <div class="grid2">
        <label>Priority<input id="priority" type="number" min="1" value="1" /></label>
        <label>Auth Type<select id="auth_type" onchange="toggleApiKeyRow()"><option value="http">HTTP API</option><option value="cli">CLI (Token Plan)</option></select></label>
      </div>
      <div id="apiKeyRow">
        <label>API Key<input id="api_key" type="password" placeholder="sk-..." /></label>
      </div>
      <label>Notes<textarea id="notes" placeholder="套餐、额度周期、负责人..."></textarea></label>
      <div class="model-grid" id="modelGrid"></div>
      <p class="form-error" id="formError"></p>
      <div class="modal-actions">
        <button type="button" class="secondary" onclick="closeForm()">Cancel</button>
        <button class="save" type="submit">Save</button>
      </div>
    </form>
  </div>
  <div class="modal" id="userModal" onclick="if(event.target === this) closeUserForm()">
    <form onsubmit="saveUser(event)">
      <div class="modal-head">
        <div><h2 id="userFormTitle">Add User</h2><p>管理登录账号、管理员权限和密码重置。</p></div>
        <button type="button" class="tool" onclick="closeUserForm()">×</button>
      </div>
      <label>Username<input id="user_username" required placeholder="admin" /></label>
      <label>Password<input id="user_password" type="password" placeholder="至少 8 位；编辑时留空则不修改" /></label>
      <label>Role<select id="user_is_admin"><option value="false">User</option><option value="true">Admin</option></select></label>
      <p class="form-error" id="userFormError"></p>
      <div class="modal-actions">
        <button type="button" class="secondary" onclick="closeUserForm()">Cancel</button>
        <button class="save" type="submit">Save</button>
      </div>
    </form>
  </div>
  <script>
    const categories = [
      { key: 'all', label: 'All', icon: 'A' },
      { key: 'image', label: 'Image', icon: 'I' },
      { key: 'voice', label: 'Voice', icon: 'V' },
      { key: 'video', label: 'Video', icon: '▶' },
      { key: 'music', label: 'Music', icon: '♪' },
      { key: 'users', label: 'Users', icon: 'U' },
    ];
    const modelCategories = {
      image: ['image-01', 'image-01-turbo'],
      voice: ['speech-02-hd', 'speech-02'],
      video: ['MiniMax-Hailuo-2.3', 'MiniMax-Hailuo-2.3-Fast', 'MiniMax-Hailuo-02', 'S2V-01'],
      music: ['music-01'],
    };
    let currentModelOptions = structuredClone(modelCategories);
    let profiles = [];
    let users = [];
    let active = 'all';
    let selected = '';
    let editing = null;
    let editingUser = null;

    function $(id) { return document.getElementById(id); }
    function numberOrNull(id) {
      const value = $(id).value.trim();
      return value ? Number(value) : null;
    }
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    function friendlyError(error) {
      return error.message === 'Failed to fetch'
        ? '后端服务未连接，请确认 uvicorn 正在 8001 端口运行'
        : error.message;
    }
    function renderTabs() {
      $('tabs').innerHTML = categories.map((cat) => `
        <button class="tab ${active === cat.key ? 'active' : ''}" onclick="setActive('${cat.key}')">
          <b>${cat.icon}</b>${cat.label}
        </button>`).join('');
    }
    function setActive(key) { active = key; renderTabs(); renderList(); }
    async function loadAll() {
      $('status').textContent = 'Loading';
      try {
        const [profileRes, userRes] = await Promise.all([
          fetch('/api/profiles'),
          fetch('/api/admin/users'),
        ]);
        if (!profileRes.ok) throw new Error(await profileRes.text());
        if (!userRes.ok) throw new Error(await userRes.text());
        profiles = await profileRes.json();
        users = await userRes.json();
        if (!selected && profiles.length) selected = profiles[0].name;
        $('status').textContent = 'Connected';
      } catch (error) {
        $('status').textContent = 'Failed: ' + friendlyError(error).slice(0, 80);
      }
      renderTabs();
      renderList();
    }
    const loadProfiles = loadAll;
    function renderList() {
      if (active === 'users') {
        renderUsers();
        return;
      }
      const visible = active === 'all' ? profiles : profiles.filter((p) => p.models?.[active]?.length);
      $('total').textContent = profiles.length;
      $('enabled').textContent = profiles.filter((p) => p.enabled).length;
      $('models').textContent = new Set(profiles.flatMap((p) => Object.values(p.models || {}).flat())).size;
      $('totalLabel').textContent = 'API Profiles';
      $('enabledLabel').textContent = 'Enabled';
      $('modelsLabel').textContent = 'Models';
      if (!visible.length) {
        $('list').innerHTML = '<div class="empty">暂无 API 配置，点击右上角 + 添加。</div>';
        return;
      }
      $('list').innerHTML = visible.map((p) => {
        const chips = Object.entries(p.models || {}).filter(([, v]) => v.length).map(([k, v]) =>
          `<span class="chip">${escapeHtml(k)} · ${escapeHtml(v.join(', '))}</span>`).join('');
        return `
          <article class="card ${selected === p.name ? 'selected' : ''} ${p.enabled ? '' : 'disabled'}" onclick="selected='${escapeHtml(p.name)}';renderList()">
            <div class="drag">⋮⋮</div>
            <div class="avatar">${escapeHtml(p.name.slice(0, 2).toUpperCase())}</div>
            <div class="main">
              <div class="title"><h2>${escapeHtml(p.name)}</h2><span class="pill ${p.enabled ? 'on' : ''}">${p.enabled ? 'Enabled' : 'Disabled'}</span></div>
              <a class="url" href="${escapeHtml(p.base_url || '#')}" onclick="event.stopPropagation()" target="_blank">${escapeHtml(p.base_url || '未配置 Base URL')}</a>
              <div class="chips">${chips || '<span class="chip">No models</span>'}</div>
            </div>
            <div class="quota">
              <span>Daily ${p.daily_quota ?? '∞'}</span>
              <span>Monthly ${p.monthly_quota ?? '∞'}</span>
              <span>${escapeHtml(p.api_key_masked || '****')}</span>
            </div>
            <div class="card-actions" onclick="event.stopPropagation()">
              <button class="primary" onclick="toggleProfile('${escapeHtml(p.name)}', ${p.enabled})">${p.enabled ? 'Disable' : 'Enable'}</button>
              <button class="tool" onclick="openForm('${escapeHtml(p.name)}')">✎</button>
              <button class="tool danger" onclick="deleteProfile('${escapeHtml(p.name)}')">⌫</button>
            </div>
          </article>`;
      }).join('');
    }
    function renderUsers() {
      $('total').textContent = users.length;
      $('enabled').textContent = users.filter((u) => u.is_admin).length;
      $('models').textContent = users.filter((u) => !u.is_admin).length;
      $('totalLabel').textContent = 'Users';
      $('enabledLabel').textContent = 'Admins';
      $('modelsLabel').textContent = 'Standard users';
      if (!users.length) {
        $('list').innerHTML = '<div class="empty">暂无用户，点击右上角 + 添加。</div>';
        return;
      }
      $('list').innerHTML = users.map((u) => `
        <article class="card ${selected === 'user-' + u.id ? 'selected' : ''}" onclick="selected='user-${u.id}';renderList()">
          <div class="drag">⋮⋮</div>
          <div class="avatar">${escapeHtml(u.username.slice(0, 2).toUpperCase())}</div>
          <div class="main">
            <div class="title"><h2>${escapeHtml(u.username)}</h2><span class="pill ${u.is_admin ? 'on' : ''}">${u.is_admin ? 'Admin' : 'User'}</span></div>
            <span class="url">User ID #${u.id}</span>
            <div class="chips">
              <span class="chip">created · ${escapeHtml(u.created_at ? new Date(u.created_at).toLocaleString() : '-')}</span>
              <span class="chip">updated · ${escapeHtml(u.updated_at ? new Date(u.updated_at).toLocaleString() : '-')}</span>
            </div>
          </div>
          <div class="quota">
            <span>${u.is_admin ? 'Full access' : 'Standard access'}</span>
            <span>Password hidden</span>
          </div>
          <div class="card-actions" onclick="event.stopPropagation()">
            <button class="primary" onclick="toggleAdmin(${u.id}, ${u.is_admin})">${u.is_admin ? 'Make User' : 'Make Admin'}</button>
            <button class="tool" onclick="openUserForm(${u.id})">✎</button>
            <button class="tool danger" onclick="deleteUser(${u.id}, '${escapeHtml(u.username)}')">⌫</button>
          </div>
        </article>
      `).join('');
    }
    function renderModelGrid() {
      $('modelGrid').innerHTML = Object.entries(currentModelOptions).map(([category, models]) => `
        <div class="model-box">
          <h3>${category}</h3>
          ${models.map((model) => `<label class="check"><input type="checkbox" data-category="${category}" value="${model}" />${model}</label>`).join('')}
          <div class="custom-model-row">
            <input id="custom_${category}" placeholder="自定义模型名" onkeydown="if(event.key === 'Enter'){event.preventDefault();addCustomModel('${category}')}" />
            <button class="mini-add" type="button" onclick="addCustomModel('${category}')">+</button>
          </div>
        </div>`).join('');
    }
    function addModelOption(category, model, checked = true) {
      const value = String(model || '').trim();
      if (!value) return;
      if (!currentModelOptions[category].includes(value)) {
        currentModelOptions[category].push(value);
      }
      renderModelGrid();
      const selector = `#modelGrid input[data-category="${category}"][value="${CSS.escape(value)}"]`;
      const box = document.querySelector(selector);
      if (box) box.checked = checked;
    }
    function addCustomModel(category) {
      const input = $(`custom_${category}`);
      addModelOption(category, input.value, true);
      input.value = '';
    }
    function openForm(name = '') {
      editing = profiles.find((p) => p.name === name) || null;
      currentModelOptions = structuredClone(modelCategories);
      Object.entries(editing?.models || {}).forEach(([category, models]) => {
        if (!currentModelOptions[category]) currentModelOptions[category] = [];
        models.forEach((model) => {
          if (!currentModelOptions[category].includes(model)) currentModelOptions[category].push(model);
        });
      });
      renderModelGrid();
      $('formTitle').textContent = editing ? 'Edit API' : 'Add API';
      $('name').disabled = !!editing;
      $('name').value = editing?.name || '';
      $('base_url').value = editing?.base_url || 'https://api.minimax.io';
      $('api_key').value = '';
      $('api_key').placeholder = editing ? 'Leave blank to keep current key' : 'sk-...';
      $('daily_quota').value = editing?.daily_quota ?? '';
      $('monthly_quota').value = editing?.monthly_quota ?? '';
      $('priority').value = editing?.priority || Math.max(1, profiles.length + 1);
      $('enabled').value = String(editing ? editing.enabled : true);
      $('auth_type').value = editing?.auth_type || 'http';
      $('notes').value = editing?.notes || '';
      toggleApiKeyRow();
      document.querySelectorAll('#modelGrid input[type=checkbox]').forEach((box) => {
        box.checked = !!editing?.models?.[box.dataset.category]?.includes(box.value);
      });
      if (!editing) document.querySelector('input[value="image-01"]').checked = true;
      $('formError').textContent = '';
      $('modal').classList.add('open');
    }
    function closeForm() { $('modal').classList.remove('open'); }
    function toggleApiKeyRow() {
      const row = $('apiKeyRow');
      if (!row) return;
      row.style.display = $('auth_type').value === 'cli' ? 'none' : 'block';
    }
    function collectModels() {
      const result = { image: [], voice: [], video: [], music: [] };
      document.querySelectorAll('#modelGrid input[type=checkbox]:checked').forEach((box) => result[box.dataset.category].push(box.value));
      return result;
    }
    async function saveProfile(event) {
      event.preventDefault();
      const authType = $('auth_type').value;
      const payload = {
        name: $('name').value.trim(),
        auth_type: authType,
        api_key: authType === 'http' ? ($('api_key').value.trim() || undefined) : undefined,
        base_url: $('base_url').value.trim(),
        enabled: $('enabled').value === 'true',
        priority: Number($('priority').value || 99),
        daily_quota: numberOrNull('daily_quota'),
        monthly_quota: numberOrNull('monthly_quota'),
        notes: $('notes').value.trim(),
        models: collectModels(),
      };
      if (authType === 'http' && !editing && !payload.api_key) {
        $('formError').textContent = 'HTTP 模式必须填写 API Key';
        return;
      }
      try {
        const url = editing ? `/api/profiles/${encodeURIComponent(editing.name)}` : '/api/profiles';
        const method = editing ? 'PUT' : 'POST';
        const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!res.ok) throw new Error(await res.text());
        selected = payload.name;
        closeForm();
        await loadProfiles();
      } catch (error) {
        $('formError').textContent = friendlyError(error);
      }
    }
    async function toggleProfile(name, enabled) {
      await fetch(`/api/profiles/${encodeURIComponent(name)}/${enabled ? 'disable' : 'enable'}`, { method: 'POST' });
      await loadProfiles();
    }
    async function deleteProfile(name) {
      if (!confirm(`删除 API "${name}"?`)) return;
      await fetch(`/api/profiles/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (selected === name) selected = '';
      await loadAll();
    }
    function openUserForm(id = null) {
      editingUser = users.find((u) => u.id === id) || null;
      $('userFormTitle').textContent = editingUser ? 'Edit User' : 'Add User';
      $('user_username').value = editingUser?.username || '';
      $('user_password').value = '';
      $('user_password').placeholder = editingUser ? '留空则不修改密码' : '至少 8 位';
      $('user_is_admin').value = String(editingUser ? editingUser.is_admin : false);
      $('userFormError').textContent = '';
      $('userModal').classList.add('open');
    }
    function closeUserForm() { $('userModal').classList.remove('open'); }
    async function saveUser(event) {
      event.preventDefault();
      const payload = {
        username: $('user_username').value.trim(),
        password: $('user_password').value.trim() || null,
        is_admin: $('user_is_admin').value === 'true',
      };
      if (!editingUser && !payload.password) {
        $('userFormError').textContent = '新增用户必须设置密码';
        return;
      }
      try {
        const url = editingUser ? `/api/admin/users/${editingUser.id}` : '/api/admin/users';
        const method = editingUser ? 'PUT' : 'POST';
        const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!res.ok) throw new Error(await res.text());
        closeUserForm();
        await loadAll();
      } catch (error) {
        $('userFormError').textContent = friendlyError(error);
      }
    }
    async function toggleAdmin(id, isAdmin) {
      const user = users.find((u) => u.id === id);
      if (!user) return;
      const res = await fetch(`/api/admin/users/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user.username, is_admin: !isAdmin }),
      });
      if (!res.ok) alert(await res.text());
      await loadAll();
    }
    async function deleteUser(id, username) {
      if (!confirm(`删除用户 "${username}"?`)) return;
      const res = await fetch(`/api/admin/users/${id}`, { method: 'DELETE' });
      if (!res.ok) alert(await res.text());
      if (selected === 'user-' + id) selected = '';
      await loadAll();
    }
    loadAll();
  </script>
</body>
</html>"""
