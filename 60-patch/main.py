import json
import uuid
import base64
import urllib.request
import urllib.parse
import urllib.error
import os
import re
import random
import sys
import subprocess
import time
import shutil
import asyncio
import logging
import sqlite3
import secrets
import hashlib
import hmac
import requests
import zipfile
import mimetypes
from typing import List, Dict, Any, Optional
from threading import Lock, Thread
import httpx
from PIL import Image
from io import BytesIO
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

try:
    import bcrypt  # type: ignore
except Exception:
    bcrypt = None

QUIET_ACCESS_PATHS = {
    "/api/queue_status",
    "/api/canvases",
    "/api/canvases/trash",
}
QUIET_ACCESS_PREFIXES = (
    "/api/canvases/",
)

class QuietAccessLogFilter(logging.Filter):
    def filter(self, record):
        args = record.args if isinstance(record.args, tuple) else ()
        if len(args) >= 3:
            path = str(args[2]).split("?", 1)[0]
            status = int(args[4]) if len(args) >= 5 and str(args[4]).isdigit() else 0
            quiet_dynamic = any(path.startswith(prefix) and path.endswith("/meta") for prefix in QUIET_ACCESS_PREFIXES)
            if (path in QUIET_ACCESS_PATHS or quiet_dynamic) and status < 400:
                return False
        message = record.getMessage()
        if any(f'"GET {path}' in message and '" 200' in message for path in QUIET_ACCESS_PATHS):
            return False
        if 'GET /api/canvases/' in message and '/meta' in message and '" 200' in message:
            return False
        return True

logging.getLogger("uvicorn.access").addFilter(QuietAccessLogFilter())

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def serve_static_no_stale(request: Request, call_next, path: str):
    """静态 js/css/html 走协商缓存（ETag 304），避免发版后浏览器继续用旧缓存。"""
    response = await call_next(request)
    if path.lower().endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache"
    return response

@app.middleware("http")
async def auth_guard_middleware(request: Request, call_next):
    path = request.url.path or "/"
    method = request.method.upper()
    if path.startswith("/static/") and path.endswith(".html"):
        if path == "/static/login.html":
            return await serve_static_no_stale(request, call_next, path)
        token = request_session_token(request)
        user = authenticate_token(token) if token else None
        request.state.current_user = user
        request.state.session_token = token or ""
        if path in ADMIN_STATIC_PAGES:
            if not user:
                return login_redirect_response(request)
            if not user.get("is_admin"):
                return JSONResponse(status_code=403, content={"detail": "管理员权限不足"})
            return await serve_static_no_stale(request, call_next, path)
        if not user:
            return login_redirect_response(request)
        return await serve_static_no_stale(request, call_next, path)
    if path.startswith("/static/") or path.startswith("/assets/") or path.startswith("/output/"):
        return await serve_static_no_stale(request, call_next, path)
    if path in PUBLIC_PATHS or path == "/ws/stats":
        return await call_next(request)
    token = request_session_token(request)
    user = authenticate_token(token) if token else None
    request.state.current_user = user
    request.state.session_token = token or ""

    if path in LOGIN_REQUIRED_PAGES:
        if not user:
            return login_redirect_response(request)
        return await call_next(request)
    if path in ADMIN_REQUIRED_PAGES:
        if not user:
            return login_redirect_response(request)
        if not user.get("is_admin"):
            return JSONResponse(status_code=403, content={"detail": "管理员权限不足"})
        return await call_next(request)

    if path.startswith("/api/"):
        if path in PUBLIC_API_PATHS:
            return await call_next(request)
        if not user:
            return JSONResponse(status_code=401, content={"detail": "未登录"})
        if is_admin_api_path(path, method) and not user.get("is_admin"):
            return JSONResponse(status_code=403, content={"detail": "管理员权限不足"})
    return await call_next(request)

# --- WebSocket 状态管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[str, WebSocket] = {}
        self.connection_clients: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, client_id: str = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_clients[websocket] = client_id or f"anon-{id(websocket)}"
        if client_id:
            self.user_connections[client_id] = websocket
        print(f"WS Connected. Total: {len(self.active_connections)}, Online: {self.online_count()}")
        await self.broadcast_count()

    async def disconnect(self, websocket: WebSocket, client_id: str = None):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.connection_clients.pop(websocket, None)
        if client_id and self.user_connections.get(client_id) is websocket:
            del self.user_connections[client_id]
        print(f"WS Disconnected. Total: {len(self.active_connections)}, Online: {self.online_count()}")
        await self.broadcast_count()

    def online_count(self):
        visible_clients = {
            client_id for client_id in self.connection_clients.values()
            if client_id and not str(client_id).startswith("canvas_")
        }
        return len(visible_clients)

    async def broadcast_count(self):
        count = self.online_count()
        data = json.dumps({"type": "stats", "online_count": count})
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(data)
            except Exception as e:
                print(f"Broadcast error: {e}")
                self.active_connections.remove(connection)

    async def broadcast_new_image(self, image_data: dict):
        data = json.dumps({"type": "new_image", "data": image_data})
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(data)
            except Exception as e:
                print(f"Broadcast image error: {e}")
                self.active_connections.remove(connection)

    async def broadcast_canvas_updated(self, canvas_id: str, updated_at: int, client_id: str = ""):
        data = json.dumps({
            "type": "canvas_updated",
            "canvas_id": canvas_id,
            "updated_at": updated_at,
            "client_id": client_id or "",
        })
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(data)
            except Exception as e:
                print(f"Broadcast canvas error: {e}")
                self.active_connections.remove(connection)

    async def send_personal_message(self, message: dict, client_id: str):
        ws = self.user_connections.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                print(f"Personal message error for {client_id}: {e}")

manager = ConnectionManager()
GLOBAL_LOOP = None
APP_VERSION = "2026.05.19"
GITHUB_REPO_URL = "https://github.com/hero8152/Infinite-Canvas"
GITHUB_VERSION_URL = "https://raw.githubusercontent.com/hero8152/Infinite-Canvas/main/VERSION"
GITHUB_TREE_URL = "https://api.github.com/repos/hero8152/Infinite-Canvas/git/trees/main?recursive=1"
GITHUB_RAW_ROOT = "https://raw.githubusercontent.com/hero8152/Infinite-Canvas/main"

@app.on_event("startup")
async def startup_event():
    global GLOBAL_LOOP
    GLOBAL_LOOP = asyncio.get_running_loop()
    sync_static_html_versions()

@app.websocket("/ws/stats")
async def websocket_endpoint(websocket: WebSocket, client_id: str = None):
    auth_header = websocket.headers.get("authorization", "")
    token = extract_bearer_token(auth_header) or str(websocket.cookies.get(AUTH_COOKIE_NAME) or "").strip()
    if not authenticate_token(token):
        await websocket.close(code=1008)
        return
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        await manager.disconnect(websocket, client_id)
    except Exception as e:
        print(f"WS Error: {e}")
        await manager.disconnect(websocket, client_id)

# --- 配置区域 ---

CLIENT_ID = str(uuid.uuid4())
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_DIR = os.path.join(BASE_DIR, "workflows")
WORKFLOW_PATH = os.path.join(WORKFLOW_DIR, "Z-Image.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
STATIC_RUNNINGHUB_DIR = os.path.join(STATIC_DIR, "runninghub")
STATIC_RUNNINGHUB_THUMBNAIL_DIR = os.path.join(STATIC_RUNNINGHUB_DIR, "thumbnails")
STATIC_RUNNINGHUB_API_PROVIDERS_FILE = os.path.join(STATIC_RUNNINGHUB_DIR, "api_providers.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
OUTPUT_INPUT_DIR = os.path.join(ASSETS_DIR, "input")
OUTPUT_OUTPUT_DIR = os.path.join(ASSETS_DIR, "output")
ASSET_LIBRARY_DIR = os.path.join(ASSETS_DIR, "library")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
API_ENV_FILE = os.path.join(BASE_DIR, "API", ".env")
DATA_DIR = os.path.join(BASE_DIR, "data")
CONVERSATION_DIR = os.path.join(DATA_DIR, "conversations")
HISTORY_DIR = os.path.join(DATA_DIR, "histories")
CANVAS_DIR = os.path.join(DATA_DIR, "canvases")
ASSET_LIBRARY_PATH = os.path.join(DATA_DIR, "asset_library.json")
API_PROVIDERS_FILE = os.path.join(DATA_DIR, "api_providers.json")
RUNNINGHUB_WORKFLOW_STORE_FILE = os.path.join(DATA_DIR, "runninghub_workflows.json")
GLOBAL_CONFIG_FILE = os.path.join(BASE_DIR, "global_config.json")
RESOURCE_ROOT_ENV_KEYS = ("AITOOL_RESOURCE_ROOT", "RESOURCE_ROOT")
RESOURCE_ROOT_PRIMARY_ENV = "AITOOL_RESOURCE_ROOT"
RESOURCE_ROOT_SECONDARY_ENV = "RESOURCE_ROOT"
RESOURCE_ROOT_SUGGESTED_SUBDIRS = [
    "models/checkpoints",
    "models/loras",
    "models/vae",
    "models/clip",
    "models/unet",
    "models/controlnet",
    "models/upscale_models",
    "workflows",
    "assets/input",
    "assets/output",
    "downloads/cache",
]
CANVAS_TRASH_RETENTION_MS = 30 * 24 * 60 * 60 * 1000
LOCAL_IMAGE_IMPORT_MAX_BYTES = int(os.getenv("LOCAL_IMAGE_IMPORT_MAX_BYTES", str(50 * 1024 * 1024)))
LOCAL_IMAGE_IMPORT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
RUNNINGHUB_THUMBNAIL_EXTS = (".jpg",)

QUEUE = []
QUEUE_LOCK = Lock()
HISTORY_LOCK = Lock()
GLOBAL_CONFIG_LOCK = Lock()
CONVERSATION_LOCK = Lock()
CANVAS_LOCK = Lock()
LOAD_LOCK = Lock()
OBJECT_INFO_CACHE_LOCK = Lock()
RUNNINGHUB_WORKFLOW_LOCK = Lock()
NEXT_TASK_ID = 1
UPDATE_LOCK = Lock()

PROVIDER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{2,40}$")
SUPPORTED_PROVIDER_PROTOCOLS = {"openai", "apimart", "gemini", "volcengine", "runninghub"}
RUNNINGHUB_DEFAULT_BASE_URL = "https://www.runninghub.cn"
RUNNINGHUB_DEFAULT_IMAGE_MODELS = [
    "seedream-v5-lite/text-to-image",
    "seedream-v5-lite/image-to-image",
]
RUNNINGHUB_DEFAULT_APPS = [
    {
        "id": "2058517022748798977",
        "appId": "2058517022748798977",
        "title": "2511-风格迁移",
        "note": "",
        "thumbnail": "",
        "enabled": True,
        "fields": [
            {
                "id": "100::image",
                "nodeId": "100",
                "fieldName": "image",
                "fieldValue": "pasted/57ef7dc980b6446bca366caaf3f94eb12b22b23f78aa30e294b39cabd7d0187b.png",
                "fieldType": "IMAGE",
                "label": "image",
                "enabled": True,
                "sourceFromUpstream": True,
                "group": "AI 应用参数",
                "note": "image",
                "options": [],
                "random_enabled": False,
                "min": "",
                "max": "",
                "step": "",
                "imageOrder": 0,
                "required": False,
            },
            {
                "id": "112::image",
                "nodeId": "112",
                "fieldName": "image",
                "fieldValue": "8cff63ee4b3e0285ca85ab90a52e26746df84ed0dec0be9d76c679cbb62a247d.png",
                "fieldType": "IMAGE",
                "label": "image",
                "enabled": True,
                "sourceFromUpstream": True,
                "group": "AI 应用参数",
                "note": "image",
                "options": [],
                "random_enabled": False,
                "min": "",
                "max": "",
                "step": "",
                "imageOrder": 0,
                "required": False,
            },
            {
                "id": "14::seed",
                "nodeId": "14",
                "fieldName": "seed",
                "fieldValue": "554049736557817",
                "fieldType": "INT",
                "label": "seed",
                "enabled": True,
                "sourceFromUpstream": True,
                "group": "AI 应用参数",
                "note": "seed",
                "options": [],
                "random_enabled": True,
                "min": "",
                "max": "",
                "step": "",
                "imageOrder": 0,
                "required": False,
            },
        ],
    },
    {
        "id": "1997622492837646338",
        "appId": "1997622492837646338",
        "title": "2511-光线迁移",
        "note": "",
        "thumbnail": "",
        "enabled": True,
    },
]
RUNNINGHUB_DEFAULT_WORKFLOWS = [
    {
        "id": "2058554058318897153",
        "workflowId": "2058554058318897153",
        "title": "GPT-Image-2-图片编辑",
        "note": "",
        "thumbnail": "",
        "enabled": True,
        "optionalImageMode": "prune-workflow",
    },
    {
        "id": "2058541134623891458",
        "workflowId": "2058541134623891458",
        "title": "NanoBanana-2-图片编辑",
        "note": "",
        "thumbnail": "",
        "enabled": True,
        "optionalImageMode": "prune-workflow",
    },
]

AUTH_DB_FILE = os.path.join(DATA_DIR, "auth.db")
AUTH_COOKIE_NAME = "studio_session_token"
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(30 * 24 * 60 * 60)))
AUTH_DEFAULT_ADMIN_USERNAME = (os.getenv("AITOOL_ADMIN_USERNAME") or os.getenv("ADMIN_USERNAME") or "admin").strip()
AUTH_DEFAULT_ADMIN_PASSWORD = (os.getenv("AITOOL_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD") or "admin123").strip()
AUTH_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")
AUTH_PASSWORD_MIN_LENGTH = 6
AUTH_LOCK = Lock()

LOGIN_REQUIRED_PAGES = {"/", "/projects", "/studio", "/canvas", "/smart-canvas", "/comfyui-workbench"}
ADMIN_REQUIRED_PAGES = {"/admin", "/admin/users", "/api-settings", "/comfyui-settings"}
ADMIN_STATIC_PAGES = {"/static/admin-dashboard.html", "/static/admin-users.html", "/static/api-settings.html", "/static/comfyui-settings.html"}
PUBLIC_PATHS = {"/login", "/favicon.ico"}
PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/logout", "/api/auth/me"}
ADMIN_API_EXACT_PATHS = {
    "/api/config/token",
    "/api/comfyui/instances",
    "/api/comfyui/status",
    "/api/resource-root",
    "/api/resource-root/detect",
    "/api/resource-root/models/check",
    "/api/update-from-github",
    "/api/update-backups",
    "/api/update-rollback",
}
ADMIN_API_PREFIXES = ("/api/providers", "/api/workflow-install")
ADMIN_WRITE_PREFIXES = ("/api/workflows",)
WORKFLOW_RUN_API_RE = re.compile(r"^/api/workflows/.+/run$")

def now_ts() -> int:
    return int(time.time())

def now_utc_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def auth_db_conn():
    conn = sqlite3.connect(AUTH_DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password: str, salt: Optional[str] = None, iterations: int = 200_000) -> str:
    salt_hex = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations)
    return f"pbkdf2_sha256${iterations}${salt_hex}${digest.hex()}"

def verify_password(password: str, password_hash: str) -> bool:
    encoded_password = str(password or "").encode("utf-8")
    stored_hash = str(password_hash or "")
    if stored_hash.startswith(("pbkdf2_sha256$",)):
        try:
            algo, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
            if algo != "pbkdf2_sha256":
                return False
            iterations = int(iterations_text)
            expected = hash_password(password, salt=salt_hex, iterations=iterations)
            return hmac.compare_digest(expected, stored_hash)
        except Exception:
            return False
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        if bcrypt is None:
            return False
        try:
            return bool(bcrypt.checkpw(encoded_password, stored_hash.encode("utf-8")))
        except Exception:
            return False
    try:
        algo, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        expected = hash_password(password, salt=salt_hex, iterations=iterations)
        return hmac.compare_digest(expected, stored_hash)
    except Exception:
        return False

def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def validate_username(username: str) -> str:
    cleaned = str(username or "").strip()
    if not AUTH_USERNAME_RE.match(cleaned):
        raise HTTPException(status_code=400, detail="用户名仅支持 3-40 位字母、数字、._-")
    return cleaned

def validate_password(password: str) -> str:
    text = str(password or "")
    if len(text) < AUTH_PASSWORD_MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"密码至少 {AUTH_PASSWORD_MIN_LENGTH} 位")
    return text

def auth_user_public(row: sqlite3.Row) -> Dict[str, Any]:
    row_keys = set(row.keys()) if hasattr(row, "keys") else set()
    is_disabled = bool(int(row["is_disabled"])) if "is_disabled" in row_keys else False
    disabled_at = str(row["disabled_at"]) if "disabled_at" in row_keys and row["disabled_at"] else ""
    updated_at = str(row["updated_at"]) if "updated_at" in row_keys and row["updated_at"] else str(row["created_at"])
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "is_admin": bool(row["is_admin"]),
        "is_disabled": is_disabled,
        "disabled_at": disabled_at,
        "created_at": str(row["created_at"]),
        "updated_at": updated_at,
    }

def ensure_users_table_columns(conn: sqlite3.Connection):
    columns = {str(item["name"]) for item in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_disabled" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_disabled INTEGER NOT NULL DEFAULT 0")
    if "disabled_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN disabled_at TEXT DEFAULT ''")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    conn.execute("UPDATE users SET is_disabled = 0 WHERE is_disabled IS NULL")
    conn.execute("UPDATE users SET disabled_at = '' WHERE disabled_at IS NULL")
    conn.execute("UPDATE users SET updated_at = created_at WHERE COALESCE(updated_at, '') = ''")
    conn.execute("UPDATE users SET updated_at = ? WHERE updated_at IS NULL", (now_utc_iso(),))

def init_auth_db():
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    is_disabled INTEGER NOT NULL DEFAULT 0,
                    disabled_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            ensure_users_table_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    owner_user_id INTEGER NOT NULL,
                    default_canvas_id TEXT NOT NULL,
                    thumbnail_url TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    archived_at INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_members (
                    project_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(project_id, user_id),
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_owner_status ON projects(owner_user_id, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id)")
            conn.commit()
        finally:
            conn.close()

def create_user(username: str, password: str, is_admin: bool = False) -> Dict[str, Any]:
    clean_username = validate_username(username)
    clean_password = validate_password(password)
    created_at = now_utc_iso()
    password_hash = hash_password(clean_password)
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, is_admin, is_disabled, disabled_at, created_at, updated_at)
                VALUES (?, ?, ?, 0, '', ?, ?)
                """,
                (clean_username, password_hash, 1 if is_admin else 0, created_at, created_at),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, username, is_admin, is_disabled, disabled_at, created_at, updated_at FROM users WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
            return auth_user_public(row)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="用户名已存在") from exc
        finally:
            conn.close()

def ensure_default_admin_user():
    username = AUTH_DEFAULT_ADMIN_USERNAME or "admin"
    password = AUTH_DEFAULT_ADMIN_PASSWORD or "admin123"
    if not AUTH_USERNAME_RE.match(username):
        username = "admin"
    if len(password) < AUTH_PASSWORD_MIN_LENGTH:
        password = "admin123"
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if row:
                return
            created_at = now_utc_iso()
            conn.execute(
                """
                INSERT INTO users (username, password_hash, is_admin, is_disabled, disabled_at, created_at, updated_at)
                VALUES (?, ?, 1, 0, '', ?, ?)
                """,
                (username, hash_password(password), created_at, created_at),
            )
            conn.commit()
            print(f"[auth] 默认管理员已初始化：{username}（首次本地使用后请立即修改密码）")
        finally:
            conn.close()

def find_user_by_username(username: str):
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            return conn.execute(
                "SELECT id, username, password_hash, is_admin, is_disabled, disabled_at, created_at, updated_at FROM users WHERE username = ?",
                (str(username or "").strip(),),
            ).fetchone()
        finally:
            conn.close()

def find_user_by_id(user_id: int):
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            return conn.execute(
                "SELECT id, username, is_admin, is_disabled, disabled_at, created_at, updated_at FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
        finally:
            conn.close()

def list_users() -> List[Dict[str, Any]]:
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            rows = conn.execute(
                """
                SELECT id, username, is_admin, is_disabled, disabled_at, created_at, updated_at
                FROM users
                ORDER BY id ASC
                """
            ).fetchall()
            return [auth_user_public(row) for row in rows]
        finally:
            conn.close()

def active_admin_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(1) AS c FROM users WHERE is_admin = 1 AND COALESCE(is_disabled, 0) = 0"
    ).fetchone()
    return int(row["c"] or 0) if row else 0

def update_user_admin_state(user_id: int, is_admin: Optional[bool], is_disabled: Optional[bool]) -> Dict[str, Any]:
    if is_admin is None and is_disabled is None:
        raise HTTPException(status_code=400, detail="至少提供一个可更新字段")
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            row = conn.execute(
                "SELECT id, username, is_admin, is_disabled, disabled_at, created_at, updated_at FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="用户不存在")
            curr_admin = bool(int(row["is_admin"] or 0))
            curr_disabled = bool(int(row["is_disabled"] or 0))
            next_admin = curr_admin if is_admin is None else bool(is_admin)
            next_disabled = curr_disabled if is_disabled is None else bool(is_disabled)
            if curr_admin and not curr_disabled and ((not next_admin) or next_disabled):
                if active_admin_count(conn) <= 1:
                    raise HTTPException(status_code=400, detail="不能降权或禁用最后一个管理员")
            disabled_at = str(row["disabled_at"] or "")
            if next_disabled and not disabled_at:
                disabled_at = now_utc_iso()
            if not next_disabled:
                disabled_at = ""
            updated_at = now_utc_iso()
            conn.execute(
                """
                UPDATE users
                SET is_admin = ?, is_disabled = ?, disabled_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (1 if next_admin else 0, 1 if next_disabled else 0, disabled_at, updated_at, int(user_id)),
            )
            if next_disabled:
                conn.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = 0",
                    (now_ts(), int(user_id)),
                )
            conn.commit()
            updated = conn.execute(
                "SELECT id, username, is_admin, is_disabled, disabled_at, created_at, updated_at FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
            return auth_user_public(updated)
        finally:
            conn.close()

def reset_user_password(user_id: int, new_password: str) -> Dict[str, Any]:
    clean_password = validate_password(new_password)
    password_hash = hash_password(clean_password)
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="用户不存在")
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, now_utc_iso(), int(user_id)),
            )
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = 0",
                (now_ts(), int(user_id)),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT id, username, is_admin, is_disabled, disabled_at, created_at, updated_at FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
            return auth_user_public(updated)
        finally:
            conn.close()

def change_own_password(user_id: int, old_password: str, new_password: str):
    clean_old = str(old_password or "")
    clean_new = validate_password(new_password)
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            row = conn.execute(
                """
                SELECT id, password_hash, is_disabled
                FROM users
                WHERE id = ?
                LIMIT 1
                """,
                (int(user_id),),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="用户不存在")
            if bool(int(row["is_disabled"] or 0)):
                raise HTTPException(status_code=403, detail="账号已禁用")
            if not verify_password(clean_old, str(row["password_hash"] or "")):
                raise HTTPException(status_code=400, detail="旧密码错误")
            if verify_password(clean_new, str(row["password_hash"] or "")):
                raise HTTPException(status_code=400, detail="新密码不能与旧密码一致")
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(clean_new), now_utc_iso(), int(user_id)),
            )
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = 0",
                (now_ts(), int(user_id)),
            )
            conn.commit()
        finally:
            conn.close()

def create_session_for_user(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)
    created_at = now_ts()
    expires_at = created_at + AUTH_TOKEN_TTL_SECONDS
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute(
                "INSERT INTO sessions (user_id, token_hash, created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, 0)",
                (int(user_id), token_hash, created_at, expires_at),
            )
            conn.commit()
        finally:
            conn.close()
    return token

def revoke_session_token(token: str):
    if not token:
        return
    token_hash = hash_session_token(token)
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at = 0",
                (now_ts(), token_hash),
            )
            conn.commit()
        finally:
            conn.close()

def extract_bearer_token(value: str) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("bearer "):
        return text[7:].strip()
    return ""

def request_session_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    bearer = extract_bearer_token(auth_header)
    if bearer:
        return bearer
    return str(request.cookies.get(AUTH_COOKIE_NAME) or "").strip()

def authenticate_token(token: str):
    text = str(token or "").strip()
    if not text:
        return None
    token_hash = hash_session_token(text)
    now = now_ts()
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.is_admin, u.is_disabled, u.disabled_at, u.created_at, u.updated_at, s.expires_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.revoked_at = 0
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            if int(row["expires_at"] or 0) <= now:
                conn.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ?", (now, token_hash))
                conn.commit()
                return None
            if bool(int(row["is_disabled"] or 0)):
                conn.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at = 0", (now, token_hash))
                conn.commit()
                return None
            return {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "is_admin": bool(row["is_admin"]),
                "is_disabled": bool(int(row["is_disabled"] or 0)),
                "disabled_at": str(row["disabled_at"] or ""),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"] or row["created_at"]),
            }
        finally:
            conn.close()

def require_current_user(request: Request) -> Dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if user:
        return user
    token = request_session_token(request)
    user = authenticate_token(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    request.state.current_user = user
    return user

def project_member_role(project_id: str, user_id: int) -> str:
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            row = conn.execute(
                "SELECT role FROM project_members WHERE project_id = ? AND user_id = ? LIMIT 1",
                (str(project_id or ""), int(user_id)),
            ).fetchone()
            return str(row["role"]) if row and row["role"] else ""
        finally:
            conn.close()

def load_project(project_id: str):
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", project_id or "")
    if not clean_id:
        raise HTTPException(status_code=400, detail="无效的项目 ID")
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            return conn.execute(
                """
                SELECT p.*, u.username AS owner_username, u.is_admin AS owner_is_admin, u.created_at AS owner_created_at
                FROM projects p
                LEFT JOIN users u ON u.id = p.owner_user_id
                WHERE p.id = ?
                LIMIT 1
                """,
                (clean_id,),
            ).fetchone()
        finally:
            conn.close()

def user_can_access_project(user: Dict[str, Any], project_row) -> bool:
    if not user or not project_row:
        return False
    if user.get("is_admin"):
        return True
    if int(project_row["owner_user_id"]) == int(user["id"]):
        return True
    return bool(project_member_role(project_row["id"], int(user["id"])))

def user_can_manage_project(user: Dict[str, Any], project_row) -> bool:
    if not user or not project_row:
        return False
    if user.get("is_admin"):
        return True
    return int(project_row["owner_user_id"]) == int(user["id"])

def login_redirect_response(request: Request) -> RedirectResponse:
    next_path = request.url.path or "/"
    if request.url.query:
        next_path += f"?{request.url.query}"
    target = "/login?next=" + urllib.parse.quote(next_path, safe="")
    return RedirectResponse(url=target, status_code=307)

def is_admin_api_path(path: str, method: str) -> bool:
    method = str(method or "GET").upper()
    if path in ADMIN_API_EXACT_PATHS:
        return True
    if any(path == prefix or path.startswith(prefix + "/") for prefix in ADMIN_API_PREFIXES):
        return True
    if method == "POST" and WORKFLOW_RUN_API_RE.match(path):
        return False
    if any(path == prefix or path.startswith(prefix + "/") for prefix in ADMIN_WRITE_PREFIXES):
        return method != "GET"
    return False

def require_admin_user(request: Request) -> Dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="管理员权限不足")
    return user

def ensure_runtime_config_files():
    """首次运行时提前创建配置目录，避免第一次保存 API Key 时才创建目录/文件。"""
    try:
        os.makedirs(os.path.dirname(API_ENV_FILE), exist_ok=True)
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(API_ENV_FILE):
            with open(API_ENV_FILE, "a", encoding="utf-8"):
                pass
    except Exception as e:
        print(f"初始化 API 配置目录失败: {e}")

def load_env_file():
    if not os.path.exists(API_ENV_FILE):
        return
    try:
        with open(API_ENV_FILE, 'r', encoding='utf-8-sig') as f:
            for raw_line in f.read().splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except Exception as e:
        print(f"加载 API/.env 失败: {e}")
ensure_runtime_config_files()
load_env_file()

COMFYUI_INSTANCES = [s.strip() for s in os.getenv("COMFYUI_INSTANCES", "127.0.0.1:8188").split(",") if s.strip()]
COMFYUI_ADDRESS = COMFYUI_INSTANCES[0]

AI_BASE_URL = os.getenv("COMFLY_BASE_URL", "https://ai.comfly.chat").rstrip("/")
AI_API_KEY = os.getenv("COMFLY_API_KEY", "")
MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
MODELSCOPE_CHAT_BASE_URL = "https://api-inference.modelscope.cn/v1"
MODELSCOPE_DEFAULT_IMAGE_MODELS = [
    "Tongyi-MAI/Z-Image-Turbo",
    "Qwen/Qwen-Image-2512",
    "Qwen/Qwen-Image-Edit-2511",
    "black-forest-labs/FLUX.2-klein-9B",
]
MODELSCOPE_DEFAULT_CHAT_MODELS = [
    "Qwen/Qwen3-235B-A22B",
    "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "MiniMax/MiniMax-M2.7:MiniMax",
]
_MODELSCOPE_CONFIGURED_CHAT_MODELS = [m.strip() for m in os.getenv("MODELSCOPE_CHAT_MODELS", "").split(",") if m.strip()]
MODELSCOPE_CHAT_MODELS = list(dict.fromkeys([m for m in [*MODELSCOPE_DEFAULT_CHAT_MODELS, *_MODELSCOPE_CONFIGURED_CHAT_MODELS] if m]))
MODELSCOPE_DEFAULT_IMAGE_MODEL = MODELSCOPE_DEFAULT_IMAGE_MODELS[0]
MODELSCOPE_DEFAULT_CHAT_MODEL = "Qwen/Qwen3-235B-A22B"
MODELSCOPE_DEFAULT_LORAS = [
    {
        "id": "Daniel8152/film",
        "name": "Z-Image Film",
        "target_model": "Tongyi-MAI/Z-Image-Turbo",
        "strength": 0.8,
        "enabled": True,
        "note": "",
    },
    {
        "id": "Daniel8152/Qwen-Image-2512-Film",
        "name": "Qwen Image 2512 Film",
        "target_model": "Qwen/Qwen-Image-2512",
        "strength": 0.8,
        "enabled": True,
        "note": "",
    },
    {
        "id": "Daniel8152/Klein-enhance",
        "name": "Klein enhance",
        "target_model": "black-forest-labs/FLUX.2-klein-9B",
        "strength": 0.8,
        "enabled": True,
        "note": "",
    },
]
MODELSCOPE_DEFAULTS_VERSION = 3
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "30"))
AI_REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "1800"))
IMAGE_POLL_INTERVAL = float(os.getenv("IMAGE_POLL_INTERVAL", "2"))
IMAGE_TASK_TIMEOUT = float(os.getenv("IMAGE_TASK_TIMEOUT", str(AI_REQUEST_TIMEOUT)))
COMFYUI_HISTORY_TIMEOUT = int(float(os.getenv("COMFYUI_HISTORY_TIMEOUT", "1800")))
APIMART_IMAGE_TASK_TIMEOUT = float(os.getenv("APIMART_IMAGE_TASK_TIMEOUT", "1800"))
APIMART_IMAGE_POLL_INTERVAL = float(os.getenv("APIMART_IMAGE_POLL_INTERVAL", "5"))
APIMART_IMAGE_INITIAL_POLL_DELAY = float(os.getenv("APIMART_IMAGE_INITIAL_POLL_DELAY", "10"))
VIDEO_POLL_TIMEOUT = float(os.getenv("VIDEO_POLL_TIMEOUT", "1800"))
ONLINE_IMAGE_PROMPT_MAX_LENGTH = int(os.getenv("ONLINE_IMAGE_PROMPT_MAX_LENGTH", "20000"))
VIDEO_PROMPT_MAX_LENGTH = int(os.getenv("VIDEO_PROMPT_MAX_LENGTH", "4000"))
LLM_MESSAGE_MAX_LENGTH = int(os.getenv("LLM_MESSAGE_MAX_LENGTH", "20000"))

FIELD_LABELS = {
    "prompt": "提示词",
    "message": "文本",
    "system_prompt": "系统提示词",
}

def friendly_validation_error(errors):
    parts = []
    for err in errors or []:
        loc = [str(item) for item in err.get("loc", []) if item != "body"]
        field = loc[-1] if loc else ""
        label = FIELD_LABELS.get(field, field or "请求参数")
        ctx = err.get("ctx") or {}
        limit = ctx.get("limit_value") or ctx.get("max_length") or ctx.get("min_length")
        err_type = str(err.get("type") or "")
        msg = str(err.get("msg") or "")
        if "max_length" in err_type or "at most" in msg:
            parts.append(f"{label}过长：当前内容超过后端上限 {limit} 个字符。请拆分为多个提示词节点，或先用 LLM 节点压缩后再生成。")
        elif "min_length" in err_type:
            parts.append(f"{label}不能为空。")
        else:
            parts.append(f"{label}格式不正确：{msg}")
    return "\n".join(parts) or "请求参数不正确。"

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": friendly_validation_error(exc.errors()), "errors": exc.errors()},
    )

def model_list(env_name, primary, defaults):
    configured = os.getenv(env_name, "")
    configured_values = [item.strip() for item in configured.split(",") if item.strip()]
    values = configured_values or [primary, *defaults]
    deduped = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped

def reload_env_globals():
    """保存 API 设置后，将 os.environ 里最新的值同步回模块级全局变量，
    避免保存后需要重启才能生效。"""
    global MODELSCOPE_API_KEY, AI_API_KEY, AI_BASE_URL
    global IMAGE_MODELS, CHAT_MODELS, VIDEO_MODELS, MODELSCOPE_CHAT_MODELS
    MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY", "")
    AI_API_KEY = os.getenv("COMFLY_API_KEY", "")
    AI_BASE_URL = os.getenv("COMFLY_BASE_URL", "https://ai.comfly.chat").rstrip("/")
    IMAGE_MODELS = model_list("IMAGE_MODELS", os.getenv("IMAGE_MODEL", IMAGE_MODEL), ["nano-banana-pro"])
    CHAT_MODELS = model_list("CHAT_MODELS", os.getenv("CHAT_MODEL", CHAT_MODEL), ["gpt-4o-mini", "gemini-3.1-flash-image-preview-2k"])
    VIDEO_MODELS = model_list("VIDEO_MODELS", "veo3-fast", [
        "veo2", "veo2-fast", "veo2-pro",
        "veo3", "veo3-fast", "veo3-pro",
        "veo3.1", "veo3.1-fast", "veo3.1-quality", "veo3.1-lite",
        "sora-2", "sora-2-pro",
        "wan2.6-t2v", "wan2.6-i2v",
        "wan2.5-t2v-preview", "wan2.5-i2v-preview",
        "wan2.2-t2v-plus", "wan2.2-i2v-plus", "wan2.2-i2v-flash",
        "doubao-seedance-2-0-260128",
        "doubao-seedance-2-0-fast-260128",
        "doubao-seedance-1-5-pro-251215",
        "doubao-seedance-1-0-pro-250528",
        "doubao-seedance-1-0-lite-t2v-250428",
        "doubao-seedance-1-0-lite-i2v-250428",
    ])
    _configured = [m.strip() for m in os.getenv("MODELSCOPE_CHAT_MODELS", "").split(",") if m.strip()]
    MODELSCOPE_CHAT_MODELS = list(dict.fromkeys([m for m in [*MODELSCOPE_DEFAULT_CHAT_MODELS, *_configured] if m]))

CHAT_MODELS = model_list("CHAT_MODELS", CHAT_MODEL, ["gpt-4o-mini", "gemini-3.1-flash-image-preview-2k"])
IMAGE_MODELS = model_list("IMAGE_MODELS", IMAGE_MODEL, ["nano-banana-pro"])
VIDEO_MODELS = model_list("VIDEO_MODELS", "veo3-fast", [
    # —— Veo 系列 ——
    "veo2", "veo2-fast", "veo2-pro",
    "veo3", "veo3-fast", "veo3-pro",
    "veo3.1", "veo3.1-fast", "veo3.1-quality", "veo3.1-lite",
    # —— Sora ——
    "sora-2", "sora-2-pro",
    # —— 阿里 通义万相 ——
    "wan2.6-t2v", "wan2.6-i2v",
    "wan2.5-t2v-preview", "wan2.5-i2v-preview",
    "wan2.2-t2v-plus", "wan2.2-i2v-plus", "wan2.2-i2v-flash",
    # —— 火山 豆包 Seedance ——
    "doubao-seedance-2-0-260128",
    "doubao-seedance-2-0-fast-260128",
    "doubao-seedance-1-5-pro-251215",
    "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-0-lite-t2v-250428",
    "doubao-seedance-1-0-lite-i2v-250428",
])

def provider_key_env(provider_id):
    if provider_id == "comfly":
        return "COMFLY_API_KEY"
    if provider_id == "modelscope":
        return "MODELSCOPE_API_KEY"
    if provider_id == "runninghub":
        return "RUNNINGHUB_API_KEY"
    return f"API_PROVIDER_{re.sub(r'[^A-Za-z0-9]', '_', provider_id).upper()}_KEY"

def runninghub_wallet_key_env():
    return "RUNNINGHUB_WALLET_API_KEY"

def mask_secret(value):
    if not value:
        return ""
    tail = value[-4:] if len(value) > 4 else value
    return f"••••••••{tail}"

def strip_auth_scheme(value, scheme="Bearer"):
    text = str(value or "").strip()
    if not text:
        return ""
    pattern = rf"^{re.escape(scheme)}\s+"
    return re.sub(pattern, "", text, flags=re.I).strip()

def bearer_auth_value(value):
    token = strip_auth_scheme(value, "Bearer")
    return f"Bearer {token}" if token else ""

def default_api_providers():
    # 只保留 ModelScope 为强制默认平台，其他平台均可自定义增删
    return [
        {
            "id": "modelscope",
            "name": "ModelScope",
            "base_url": MODELSCOPE_CHAT_BASE_URL,
            "protocol": "openai",
            "image_generation_endpoint": "",
            "image_edit_endpoint": "",
            "enabled": True,
            "primary": False,
            "image_models": MODELSCOPE_DEFAULT_IMAGE_MODELS,
            "chat_models": MODELSCOPE_CHAT_MODELS,
            "video_models": [],
            "ms_loras": MODELSCOPE_DEFAULT_LORAS,
            "ms_defaults_version": MODELSCOPE_DEFAULTS_VERSION,
        },
        {
            "id": "runninghub",
            "name": "RunningHub",
            "base_url": RUNNINGHUB_DEFAULT_BASE_URL,
            "protocol": "runninghub",
            "image_generation_endpoint": "",
            "image_edit_endpoint": "",
            "enabled": True,
            "primary": False,
            "image_models": RUNNINGHUB_DEFAULT_IMAGE_MODELS,
            "chat_models": [],
            "video_models": [],
            "ms_loras": [],
            "ms_defaults_version": 0,
            "rh_apps": RUNNINGHUB_DEFAULT_APPS,
            "rh_workflows": RUNNINGHUB_DEFAULT_WORKFLOWS,
        },
    ]

def merge_default_api_providers(providers):
    merged = [dict(item) for item in providers]
    # 强制保留独立入口平台（不再强制 comfly）
    ms_default = next((d for d in default_api_providers() if d["id"] == "modelscope"), None)
    if ms_default:
        current = next((item for item in merged if item.get("id") == "modelscope"), None)
        if not current:
            merged.append(ms_default)
        else:
            if not current.get("base_url"):
                current["base_url"] = ms_default["base_url"]
            seeded_version = int(current.get("ms_defaults_version") or 0)
            if seeded_version < MODELSCOPE_DEFAULTS_VERSION:
                image_models = model_list_from_values([*MODELSCOPE_DEFAULT_IMAGE_MODELS, *(current.get("image_models") or [])])
                chat_models = model_list_from_values([*MODELSCOPE_DEFAULT_CHAT_MODELS, *(current.get("chat_models") or [])])
                loras = normalize_ms_loras([*MODELSCOPE_DEFAULT_LORAS, *(current.get("ms_loras") or [])])
                current["image_models"] = image_models
                current["chat_models"] = chat_models
                current["ms_loras"] = loras
                current["ms_defaults_version"] = MODELSCOPE_DEFAULTS_VERSION
    rh_default = load_static_runninghub_provider() or next((d for d in default_api_providers() if d["id"] == "runninghub"), None)
    if rh_default:
        current = next((item for item in merged if item.get("id") == "runninghub"), None)
        if not current:
            merged.append(rh_default)
        else:
            if not current.get("base_url"):
                current["base_url"] = rh_default["base_url"]
            if not current.get("protocol") or current.get("protocol") == "openai":
                current["protocol"] = "runninghub"
            current["image_models"] = model_list_from_values([*(current.get("image_models") or []), *(rh_default.get("image_models") or [])])
            current["rh_apps"] = merge_runninghub_system_entries(rh_default.get("rh_apps") or [], current.get("rh_apps") or [], "app")
            current["rh_workflows"] = merge_runninghub_system_entries(rh_default.get("rh_workflows") or [], current.get("rh_workflows") or [], "workflow")
    return merged

def normalize_model_list(values):
    return model_list_from_values(values)

def model_list_from_values(values):
    deduped = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in deduped:
            selected_model(item, item)
            deduped.append(item)
    return deduped

def normalize_ms_loras(values):
    normalized = []
    seen = set()
    for raw in values or []:
        if not isinstance(raw, dict):
            continue
        lora_id = str(raw.get("id") or "").strip()
        if not lora_id:
            continue
        target_model = str(raw.get("target_model") or raw.get("model") or "").strip()
        if not target_model:
            continue
        key = (target_model, lora_id)
        if key in seen:
            continue
        seen.add(key)
        try:
            strength = float(raw.get("strength", raw.get("default_strength", 0.8)))
        except Exception:
            strength = 0.8
        strength = max(0.0, min(2.0, strength))
        name = re.sub(r"\s+", " ", str(raw.get("name") or "").strip())[:80]
        normalized.append({
            "id": lora_id[:180],
            "name": name or lora_id,
            "target_model": target_model[:180],
            "strength": strength,
            "enabled": bool(raw.get("enabled", True)),
            "note": str(raw.get("note") or "").strip()[:300],
        })
    return normalized

def normalize_runninghub_entry(raw, kind):
    if not isinstance(raw, dict):
        return None
    raw_id = raw.get("appId") if kind == "app" else raw.get("workflowId")
    entry_id = str(raw_id or raw.get("id") or "").strip()
    match = re.search(r"/run/(ai-app|workflow)/([0-9A-Za-z_-]+)", entry_id)
    if match:
        entry_id = match.group(2)
    if not entry_id:
        return None
    title = re.sub(r"\s+", " ", str(raw.get("title") or raw.get("name") or "").strip())[:80]
    note = str(raw.get("note") or raw.get("description") or "").strip()[:500]
    thumb = str(raw.get("thumbnail") or "").strip()
    if len(thumb) > 1500000:
        thumb = ""
    entry = {
        "id": entry_id[:80],
        "title": title or (f"AI 应用 {entry_id[-6:]}" if kind == "app" else f"工作流 {entry_id[-6:]}"),
        "note": note,
        "thumbnail": thumb,
        "enabled": bool(raw.get("enabled", True)),
    }
    if raw.get("hidden") is True:
        entry["hidden"] = True
    fields = raw.get("fields")
    if isinstance(fields, list):
        entry["fields"] = [runninghub_normalize_field(field) for field in fields if isinstance(field, dict)]
    if kind == "workflow":
        mode = str(raw.get("optionalImageMode") or raw.get("optional_image_mode") or "prune-workflow").strip()
        entry["optionalImageMode"] = mode or "prune-workflow"
        workflow_json = raw.get("workflowJson") or raw.get("workflow_json")
        if isinstance(workflow_json, dict):
            entry["workflowJson"] = workflow_json
    raw_payload = raw.get("raw")
    if isinstance(raw_payload, dict):
        entry["raw"] = raw_payload
    try:
        updated_at = int(raw.get("updatedAt") or raw.get("updated_at") or 0)
        if updated_at > 0:
            entry["updatedAt"] = updated_at
    except Exception:
        pass
    if kind == "app":
        entry["appId"] = entry["id"]
    else:
        entry["workflowId"] = entry["id"]
    return entry

def normalize_runninghub_entries(values, kind):
    normalized = []
    seen = set()
    for raw in values or []:
        entry = normalize_runninghub_entry(raw, kind)
        if not entry or entry["id"] in seen:
            continue
        seen.add(entry["id"])
        normalized.append(entry)
    return normalized

def runninghub_entry_id(entry, kind):
    if not isinstance(entry, dict):
        return ""
    raw_id = entry.get("workflowId") if kind == "workflow" else entry.get("appId")
    return str(raw_id or entry.get("id") or "").strip()

def static_runninghub_thumbnail_url(entry_id, kind):
    entry_id = re.sub(r"[^0-9A-Za-z_-]", "", str(entry_id or "").strip())
    kind_prefix = "workflow" if kind == "workflow" else "app"
    if not entry_id:
        return ""
    candidates = []
    for name in (f"{kind_prefix}-{entry_id}", entry_id):
        for ext in RUNNINGHUB_THUMBNAIL_EXTS:
            candidates.append((STATIC_RUNNINGHUB_THUMBNAIL_DIR, f"{name}{ext}"))
            candidates.append((STATIC_RUNNINGHUB_DIR, f"{name}{ext}"))
    for root, filename in candidates:
        path = os.path.abspath(os.path.join(root, filename))
        if not path.startswith(os.path.abspath(STATIC_RUNNINGHUB_DIR) + os.sep):
            continue
        if os.path.exists(path) and os.path.isfile(path):
            rel = os.path.relpath(path, STATIC_DIR).replace(os.sep, "/")
            return f"/static/{urllib.parse.quote(rel, safe='/._-')}?v={int(os.path.getmtime(path))}"
    return ""

def apply_runninghub_system_thumbnails(entries, kind):
    result = []
    for entry in normalize_runninghub_entries(entries or [], kind):
        if not entry.get("thumbnail"):
            thumb = static_runninghub_thumbnail_url(runninghub_entry_id(entry, kind), kind)
            if thumb:
                entry["thumbnail"] = thumb
        result.append(entry)
    return result

def merge_runninghub_system_entries(system_entries, user_entries, kind):
    merged = []
    index = {}
    hidden_ids = set()
    for entry in apply_runninghub_system_thumbnails(system_entries or [], kind):
        entry_id = runninghub_entry_id(entry, kind)
        if not entry_id:
            continue
        index[entry_id] = len(merged)
        merged.append(entry)
    for entry in apply_runninghub_system_thumbnails(user_entries or [], kind):
        entry_id = runninghub_entry_id(entry, kind)
        if not entry_id:
            continue
        if entry.get("hidden") is True:
            hidden_ids.add(entry_id)
            if entry_id in index:
                merged.pop(index[entry_id])
                index = {runninghub_entry_id(item, kind): idx for idx, item in enumerate(merged)}
            continue
        if entry_id in index:
            merged[index[entry_id]] = entry
        else:
            index[entry_id] = len(merged)
            merged.append(entry)
    return [entry for entry in merged if runninghub_entry_id(entry, kind) not in hidden_ids]

def load_static_runninghub_provider():
    if not os.path.exists(STATIC_RUNNINGHUB_API_PROVIDERS_FILE):
        return None
    try:
        with open(STATIC_RUNNINGHUB_API_PROVIDERS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        candidates = raw if isinstance(raw, list) else raw.get("providers") if isinstance(raw, dict) else []
        if isinstance(raw, dict) and raw.get("id") == "runninghub":
            candidates = [raw]
        for item in candidates or []:
            if isinstance(item, dict) and str(item.get("id") or "").strip().lower() == "runninghub":
                provider = normalize_provider(item)
                provider["rh_apps"] = apply_runninghub_system_thumbnails(provider.get("rh_apps") or [], "app")
                provider["rh_workflows"] = apply_runninghub_system_thumbnails(provider.get("rh_workflows") or [], "workflow")
                return provider
    except Exception as e:
        print(f"加载 static RunningHub 配置失败: {e}")
    return None

def merge_runninghub_provider_with_static(provider):
    static_provider = load_static_runninghub_provider()
    if not static_provider:
        return provider
    if not isinstance(provider, dict):
        return static_provider
    merged = {**static_provider, **provider}
    merged["protocol"] = "runninghub"
    merged["image_models"] = model_list_from_values([*(provider.get("image_models") or []), *(static_provider.get("image_models") or [])])
    merged["rh_apps"] = merge_runninghub_system_entries(static_provider.get("rh_apps") or [], provider.get("rh_apps") or [], "app")
    merged["rh_workflows"] = merge_runninghub_system_entries(static_provider.get("rh_workflows") or [], provider.get("rh_workflows") or [], "workflow")
    return normalize_provider(merged)

def preserve_runninghub_hidden_overrides(provider):
    if not isinstance(provider, dict) or provider.get("id") != "runninghub":
        return provider
    static_provider = load_static_runninghub_provider()
    if not static_provider:
        return provider
    provider = dict(provider)
    for list_key, kind in (("rh_apps", "app"), ("rh_workflows", "workflow")):
        current = normalize_runninghub_entries(provider.get(list_key) or [], kind)
        current_ids = {runninghub_entry_id(item, kind) for item in current}
        for static_entry in static_provider.get(list_key) or []:
            entry_id = runninghub_entry_id(static_entry, kind)
            if entry_id and entry_id not in current_ids:
                tombstone = normalize_runninghub_entry({**static_entry, "enabled": False, "hidden": True}, kind)
                if tombstone:
                    current.append(tombstone)
        provider[list_key] = current
    return provider

def normalize_endpoint_override(value, label):
    endpoint = str(value or "").strip()
    if not endpoint:
        return ""
    if len(endpoint) > 300 or re.search(r"\s", endpoint):
        raise HTTPException(status_code=400, detail=f"{label} 不合法，请填写类似 /v1/images/edits 的路径")
    if re.match(r"^https?://", endpoint, re.I):
        return endpoint.rstrip("/")
    if not endpoint.startswith("/"):
        raise HTTPException(status_code=400, detail=f"{label} 需要以 /v1/... 开头，或填写完整 http(s) 地址")
    return endpoint

def provider_endpoint_url(provider, key, default_path):
    base_url = str((provider or {}).get("base_url") or AI_BASE_URL).strip().rstrip("/")
    override = str((provider or {}).get(key) or "").strip()
    if override:
        if re.match(r"^https?://", override, re.I):
            return override.rstrip("/")
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}{override}"
        return override
    for prefix in ("/api/v3", "/v1beta", "/v1", "/v2"):
        if base_url.endswith(prefix) and default_path.startswith(f"{prefix}/"):
            return f"{base_url}{default_path[len(prefix):]}"
    return f"{base_url}{default_path}"

def runninghub_endpoint_url(provider, path):
    base_url = str((provider or {}).get("base_url") or RUNNINGHUB_DEFAULT_BASE_URL).strip().rstrip("/")
    return f"{base_url}{path}"

def normalize_provider(item):
    provider_id = str(item.get("id") or "").strip().lower()
    if not PROVIDER_ID_RE.fullmatch(provider_id):
        raise HTTPException(status_code=400, detail=f"API 平台 ID 不合法：{provider_id or '(empty)'}")
    name = re.sub(r"\s+", " ", str(item.get("name") or provider_id).strip())[:60] or provider_id
    base_url = str(item.get("base_url") or "").strip().rstrip("/")
    if base_url and not re.match(r"^https?://", base_url):
        raise HTTPException(status_code=400, detail=f"{name} 的 Base URL 需要以 http:// 或 https:// 开头")
    protocol = str(item.get("protocol") or "openai").strip().lower()
    if protocol not in SUPPORTED_PROVIDER_PROTOCOLS:
        protocol = "openai"
    image_generation_endpoint = normalize_endpoint_override(item.get("image_generation_endpoint"), "文生图端口")
    image_edit_endpoint = normalize_endpoint_override(item.get("image_edit_endpoint"), "图生图/编辑端口")
    return {
        "id": provider_id,
        "name": name,
        "base_url": base_url,
        "protocol": protocol,
        "image_generation_endpoint": image_generation_endpoint,
        "image_edit_endpoint": image_edit_endpoint,
        "enabled": bool(item.get("enabled", True)),
        "primary": bool(item.get("primary", False)),
        "image_models": model_list_from_values(item.get("image_models") or []),
        "chat_models": model_list_from_values(item.get("chat_models") or []),
        "video_models": model_list_from_values(item.get("video_models") or []),
        "ms_loras": normalize_ms_loras(item.get("ms_loras") or []),
        "ms_defaults_version": int(item.get("ms_defaults_version") or 0),
        "rh_apps": normalize_runninghub_entries(item.get("rh_apps") or [], "app"),
        "rh_workflows": normalize_runninghub_entries(item.get("rh_workflows") or [], "workflow"),
    }

def load_api_providers():
    defaults = default_api_providers()
    if not os.path.exists(API_PROVIDERS_FILE):
        return merge_default_api_providers(defaults)
    try:
        with open(API_PROVIDERS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        providers = [normalize_provider(item) for item in raw if isinstance(item, dict)]
        return merge_default_api_providers(providers or defaults)
    except Exception as e:
        print(f"加载 API 平台配置失败: {e}")
        return defaults

def save_api_providers(providers):
    os.makedirs(DATA_DIR, exist_ok=True)
    with GLOBAL_CONFIG_LOCK:
        with open(API_PROVIDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(providers, f, ensure_ascii=False, indent=2)

def admin_provider_view(provider):
    if provider.get("id") == "runninghub":
        try:
            provider = runninghub_provider_with_workflow_store(provider)
        except Exception:
            pass
    key = os.getenv(provider_key_env(provider["id"]), "")
    item = {
        **provider,
        "has_key": bool(key),
        "masked_key": mask_secret(key),
    }
    if provider.get("id") == "runninghub":
        wallet_key = os.getenv(runninghub_wallet_key_env(), "")
        item.update({
            "has_wallet_key": bool(wallet_key),
            "masked_wallet_key": mask_secret(wallet_key),
        })
    return item

def provider_config_metadata(provider):
    item = {
        "id": provider.get("id"),
        "name": provider.get("name"),
        "enabled": bool(provider.get("enabled", True)),
        "primary": bool(provider.get("primary", False)),
        "protocol": provider.get("protocol") or "openai",
        "chat_models": list(provider.get("chat_models") or []),
        "image_models": list(provider.get("image_models") or []),
        "video_models": list(provider.get("video_models") or []),
    }
    if provider.get("id") == "modelscope":
        item["ms_loras"] = list(provider.get("ms_loras") or [])
    return item

def get_primary_provider_id(providers=None):
    """返回当前首选 provider 的 id；优先 primary=True 的，否则取第一个非 modelscope 的，再次取第一个。"""
    providers = providers if providers is not None else load_api_providers()
    primary = next((p for p in providers if p.get("primary") and p.get("enabled", True)), None)
    if primary:
        return primary["id"]
    non_ms = next((p for p in providers if p["id"] != "modelscope" and p.get("enabled", True)), None)
    if non_ms:
        return non_ms["id"]
    return providers[0]["id"] if providers else "modelscope"

def get_api_provider(provider_id="comfly"):
    providers = load_api_providers()
    target = (provider_id or "").strip().lower()
    # 兼容旧的 "comfly" 硬编码：若 comfly 不存在或未指定，回退到首选 provider
    if not target or not any(p["id"] == target for p in providers):
        target = get_primary_provider_id(providers)
    provider = next((p for p in providers if p["id"] == target), None)
    if not provider:
        raise HTTPException(status_code=400, detail=f"未找到 API 平台：{target}")
    if not provider.get("enabled", True):
        raise HTTPException(status_code=400, detail=f"API 平台已禁用：{provider.get('name') or target}")
    return provider

def get_api_provider_exact(provider_id: str):
    providers = load_api_providers()
    target = (provider_id or "").strip().lower()
    provider = next((p for p in providers if p["id"] == target), None)
    if not provider:
        raise HTTPException(status_code=400, detail=f"未找到 API 平台：{target or '(empty)'}。新增平台未保存时请使用当前表单拉取模型。")
    if not provider.get("enabled", True):
        raise HTTPException(status_code=400, detail=f"API 平台已禁用：{provider.get('name') or target}")
    return provider

def env_quote(value):
    text = str(value or "")
    if not text or re.search(r"\s|#|['\"]", text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text

def update_env_values(updates):
    os.makedirs(os.path.dirname(API_ENV_FILE), exist_ok=True)
    lines = []
    if os.path.exists(API_ENV_FILE):
        with open(API_ENV_FILE, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    seen = set()
    next_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            next_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            next_lines.append(f"{key}={env_quote(updates[key])}")
            os.environ[key] = str(updates[key] or "")
            seen.add(key)
        else:
            next_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={env_quote(value)}")
            os.environ[key] = str(value or "")
    with open(API_ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(next_lines).rstrip() + "\n")

BACKEND_LOCAL_LOAD = {addr: 0 for addr in COMFYUI_INSTANCES}
BACKEND_OBJECT_INFO_CACHE_TTL = max(5, int(os.getenv("COMFYUI_OBJECT_INFO_CACHE_TTL", "30")))
BACKEND_OBJECT_INFO_CACHE: Dict[str, Dict[str, Any]] = {}

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(OUTPUT_INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_OUTPUT_DIR, exist_ok=True)
os.makedirs(ASSET_LIBRARY_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(WORKFLOW_DIR, exist_ok=True)
os.makedirs(CONVERSATION_DIR, exist_ok=True)
os.makedirs(CANVAS_DIR, exist_ok=True)
AUTH_BOOTSTRAP_SKIPPED = str(os.getenv("AITOOL_SKIP_AUTH_BOOTSTRAP", "")).strip().lower() in {"1", "true", "yes", "on"}
if not AUTH_BOOTSTRAP_SKIPPED:
    init_auth_db()
    ensure_default_admin_user()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# --- Pydantic 模型 ---

def current_app_version():
    version_file = os.path.join(BASE_DIR, "VERSION")
    try:
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                version = (f.read().strip().splitlines() or [""])[0].strip()
                if version:
                    return version
    except Exception:
        pass
    try:
        return time.strftime("%Y.%m.%d", time.localtime())
    except Exception:
        return ""

def versioned_static_html(html: str) -> str:
    version = current_app_version()
    if not version:
        return html
    safe_version = urllib.parse.quote(version, safe="._-")
    pattern = re.compile(r'(?P<prefix>(?:src|href)=["\']|@import\s+url\(["\'])(?P<url>/static/[^"\')?#]+(?:\.(?:js|css|html)))(?:\?v=[^"\')#]*)?', re.I)
    return pattern.sub(lambda m: f"{m.group('prefix')}{m.group('url')}?v={safe_version}", html)

def sync_static_html_versions():
    version = current_app_version()
    if not version:
        return
    safe_version = urllib.parse.quote(version, safe="._-")
    try:
        for name in os.listdir(STATIC_DIR):
            if not name.lower().endswith(".html"):
                continue
            path = os.path.join(STATIC_DIR, name)
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                old = f.read()
            new = re.sub(r'([?&]v=)[^"\'`\s<>)]*', rf'\g<1>{safe_version}', old)
            if new != old:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(new)
    except Exception as e:
        print(f"同步静态页面版本号失败: {e}")

def static_html_response(filename: str):
    path = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(path):
        return Response(
            f"<!DOCTYPE html><html><body style='font-family:sans-serif;padding:40px;text-align:center'>"
            f"<h1>⚠️ 页面文件缺失</h1>"
            f"<p>服务器上缺少静态文件：<code>{filename}</code></p>"
            f"<p>请检查 <code>{path}</code> 是否存在。</p>"
            f"<p style='color:#666;margin-top:20px'>如果这是新功能，请确保相关文件已部署到服务器。</p>"
            f"</body></html>",
            status_code=404,
            media_type="text/html; charset=utf-8",
        )
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    return Response(
        versioned_static_html(html),
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )

@app.get("/api/app-info")
def app_info():
    version = current_app_version()
    return {
        "version": version,
        "repo_url": GITHUB_REPO_URL,
        "version_url": GITHUB_VERSION_URL,
    }

def update_allowed_file(path: str) -> bool:
    path = str(path or "").replace("\\", "/").lstrip("/")
    if not path or any(part in {"", ".", ".."} for part in path.split("/")):
        return False
    return path in {"main.py", "VERSION"} or path.startswith("static/")

# 缓存 GitHub Tree API 响应（含 ETag），减少 60 次/h 限流压力
GITHUB_TREE_CACHE: Dict[str, Any] = {"etag": "", "data": None, "expires_at": 0.0}

def github_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> requests.Response:
    try:
        response = requests.get(
            url,
            headers=headers or {},
            timeout=timeout,
            proxies=urllib.request.getproxies() or None,
        )
    except requests.RequestException as exc:
        raise urllib.error.URLError(str(exc)) from exc
    if response.status_code >= 400 or response.status_code == 304:
        raise urllib.error.HTTPError(url, response.status_code, response.reason, response.headers, None)
    return response

def github_json(url: str, use_etag_cache: bool = False):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Infinite-Canvas-Updater",
    }
    cache_key = url
    if use_etag_cache and cache_key == GITHUB_TREE_URL:
        if GITHUB_TREE_CACHE["data"] and time.time() < GITHUB_TREE_CACHE["expires_at"]:
            return GITHUB_TREE_CACHE["data"]
        if GITHUB_TREE_CACHE["etag"]:
            headers["If-None-Match"] = GITHUB_TREE_CACHE["etag"]
    try:
        resp = github_get(url, headers=headers, timeout=30)
        etag = resp.headers.get("ETag", "")
        payload = json.loads(resp.content.decode("utf-8", errors="replace"))
        if use_etag_cache and cache_key == GITHUB_TREE_URL:
            GITHUB_TREE_CACHE.update({
                "etag": etag,
                "data": payload,
                "expires_at": time.time() + 600,  # 10 分钟内复用
            })
        return payload
    except urllib.error.HTTPError as exc:
        # 304 表示对方树未变，沿用缓存
        if exc.code == 304 and use_etag_cache and GITHUB_TREE_CACHE["data"]:
            GITHUB_TREE_CACHE["expires_at"] = time.time() + 600
            return GITHUB_TREE_CACHE["data"]
        raise

def github_bytes(url: str) -> bytes:
    resp = github_get(url, headers={"User-Agent": "Infinite-Canvas-Updater"}, timeout=60)
    return resp.content

def download_github_update_files(files: List[str], staging_root: str) -> None:
    staging_root_abs = os.path.abspath(staging_root)
    for rel in files:
        safe_update_target(rel)
        raw_url = f"{GITHUB_RAW_ROOT}/{urllib.parse.quote(rel, safe='/')}"
        data = github_bytes(raw_url)
        stage_path = os.path.abspath(os.path.join(staging_root_abs, *rel.split("/")))
        if os.path.commonpath([staging_root_abs, stage_path]) != staging_root_abs:
            raise ValueError(f"更新暂存路径不安全：{rel}")
        os.makedirs(os.path.dirname(stage_path), exist_ok=True)
        with open(stage_path, "wb") as f:
            f.write(data)

def safe_update_target(path: str) -> str:
    rel = str(path or "").replace("\\", "/").lstrip("/")
    if not update_allowed_file(rel):
        raise ValueError(f"更新文件不在允许范围：{rel}")
    target = os.path.abspath(os.path.join(BASE_DIR, *rel.split("/")))
    base = os.path.abspath(BASE_DIR)
    if os.path.commonpath([base, target]) != base:
        raise ValueError(f"更新路径不安全：{rel}")
    return target

def safe_static_dir() -> str:
    target = os.path.abspath(STATIC_DIR)
    expected = os.path.abspath(os.path.join(BASE_DIR, "static"))
    base = os.path.abspath(BASE_DIR)
    if target != expected or os.path.commonpath([base, target]) != base:
        raise RuntimeError(f"static 路径不安全：{target}")
    return target

def schedule_self_restart(delay_seconds: int = 3) -> bool:
    """派生脱离父进程的小脚本，等几秒后启动启动服务脚本，并干掉当前 PID。"""
    delay = max(1, int(delay_seconds or 3))
    pid = os.getpid()
    try:
        if os.name == "nt":
            launcher = os.path.join(BASE_DIR, "启动服务.bat")
            if not os.path.exists(launcher):
                launcher = os.path.join(BASE_DIR, "start.bat")
            bat_path = os.path.join(BASE_DIR, "_self_restart.bat")
            log_path = os.path.join(BASE_DIR, "_self_restart.log")
            script = (
                "@echo off\r\n"
                "chcp 65001 >nul\r\n"
                "setlocal\r\n"
                f"set \"APP_DIR={BASE_DIR}\"\r\n"
                f"set \"LAUNCHER={launcher}\"\r\n"
                f"set \"LOG_FILE={log_path}\"\r\n"
                "echo [%date% %time%] restart scheduled >> \"%LOG_FILE%\"\r\n"
                f"timeout /t {delay} /nobreak >nul\r\n"
                "echo [%date% %time%] stopping old process >> \"%LOG_FILE%\"\r\n"
                f"taskkill /F /PID {pid} >nul 2>&1\r\n"
                "timeout /t 2 /nobreak >nul\r\n"
                "cd /d \"%APP_DIR%\"\r\n"
                "if exist \"%LAUNCHER%\" (\r\n"
                "  echo [%date% %time%] starting launcher: %LAUNCHER% >> \"%LOG_FILE%\"\r\n"
                "  start \"ComfyUI-API-Modelscope\" /D \"%APP_DIR%\" cmd /k call \"%LAUNCHER%\"\r\n"
                ") else (\r\n"
                "  echo [%date% %time%] launcher missing, fallback to python main.py >> \"%LOG_FILE%\"\r\n"
                "  if exist \"%APP_DIR%\\python\\python.exe\" (\r\n"
                "    start \"ComfyUI-API-Modelscope\" /D \"%APP_DIR%\" cmd /k \"\"%APP_DIR%\\python\\python.exe\" main.py\"\r\n"
                "  ) else (\r\n"
                "    start \"ComfyUI-API-Modelscope\" /D \"%APP_DIR%\" cmd /k python main.py\r\n"
                "  )\r\n"
                ")\r\n"
                "del \"%~f0\"\r\n"
            )
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(script)
            subprocess.Popen(
                ["cmd", "/c", bat_path],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
        else:
            launcher = os.path.join(BASE_DIR, "mac-启动服务.command")
            if not os.path.exists(launcher):
                launcher = os.path.join(BASE_DIR, "start.sh")
            sh_path = os.path.join(BASE_DIR, "_self_restart.sh")
            script = (
                "#!/bin/sh\n"
                f"sleep {delay}\n"
                f"kill -9 {pid} 2>/dev/null\n"
                f"cd \"{BASE_DIR}\"\n"
                f"if [ -x \"{launcher}\" ]; then nohup \"{launcher}\" >/dev/null 2>&1 &\n"
                f"elif [ -f \"{launcher}\" ]; then nohup /bin/sh \"{launcher}\" >/dev/null 2>&1 &\n"
                "fi\n"
                "rm -- \"$0\"\n"
            )
            with open(sh_path, "w", encoding="utf-8") as f:
                f.write(script)
            os.chmod(sh_path, 0o755)
            subprocess.Popen(
                ["/bin/sh", sh_path],
                start_new_session=True,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True
    except Exception as exc:
        logging.exception("schedule_self_restart failed: %s", exc)
        return False

class UpdateRequest(BaseModel):
    auto_restart: bool = False
    restart_delay: int = 3

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreateRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False

class UserUpdateRequest(BaseModel):
    is_admin: Optional[bool] = None
    is_disabled: Optional[bool] = None
    disabled: Optional[bool] = None

class UserResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=AUTH_PASSWORD_MIN_LENGTH)

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=AUTH_PASSWORD_MIN_LENGTH)

@app.post("/api/update-from-github")
def update_from_github(request: Request, req: UpdateRequest = UpdateRequest()):
    # 安全加固：默认禁用 GitHub 自更新（它指向上游模板仓库，会整体覆盖 main.py 和 static/），
    # 且必须是管理员才能调用。临时开启需设置环境变量 XY_ENABLE_GITHUB_UPDATE=1。
    require_admin_user(request)
    if os.getenv("XY_ENABLE_GITHUB_UPDATE", "0").strip().lower() not in ("1", "true", "yes"):
        raise HTTPException(
            status_code=403,
            detail="GitHub 自更新已禁用：该功能会用上游模板覆盖本系统代码。如确需使用，请设置 XY_ENABLE_GITHUB_UPDATE=1 后重启服务。",
        )
    if not UPDATE_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="正在更新中，请稍后再试")
    staging_root = ""
    try:
        tree_data = github_json(GITHUB_TREE_URL, use_etag_cache=True)
        entries = tree_data.get("tree") or []
        static_files = []
        root_files = []
        for entry in entries:
            path = str(entry.get("path") or "").replace("\\", "/")
            if entry.get("type") == "blob" and update_allowed_file(path):
                if path.startswith("static/"):
                    static_files.append(path)
                else:
                    root_files.append(path)
        if "main.py" not in root_files:
            root_files.append("main.py")
        if "VERSION" not in root_files:
            root_files.append("VERSION")
        static_files = sorted(set(static_files))
        root_files = sorted(set(root_files))
        files = root_files + static_files
        if not static_files:
            raise RuntimeError("GitHub 未返回 static 文件，已取消更新")

        backup_root = os.path.join(DATA_DIR, "update_backups", time.strftime("%Y%m%d-%H%M%S"))
        staging_root = os.path.join(DATA_DIR, "update_staging", f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
        download_github_update_files(files, staging_root)

        updated = []
        for rel in root_files:
            target = safe_update_target(rel)
            if os.path.exists(target):
                backup_path = os.path.join(backup_root, *rel.split("/"))
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(target, backup_path)

        staged_static_dir = os.path.join(staging_root, "static")
        if not os.path.isdir(staged_static_dir):
            raise RuntimeError("GitHub static 暂存目录不存在，已取消更新")
        static_dir = safe_static_dir()
        backup_static_dir = os.path.join(backup_root, "static")
        if os.path.isdir(static_dir):
            os.makedirs(os.path.dirname(backup_static_dir), exist_ok=True)
            shutil.copytree(static_dir, backup_static_dir)
            shutil.rmtree(static_dir)
        try:
            shutil.copytree(staged_static_dir, static_dir)
        except Exception:
            if os.path.isdir(static_dir):
                shutil.rmtree(static_dir, ignore_errors=True)
            if os.path.isdir(backup_static_dir):
                shutil.copytree(backup_static_dir, static_dir)
            raise
        updated.extend(static_files)

        replaced_root_files = []
        try:
            for rel in root_files:
                target = safe_update_target(rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                temp_path = f"{target}.update_tmp"
                shutil.copy2(os.path.join(staging_root, *rel.split("/")), temp_path)
                os.replace(temp_path, target)
                replaced_root_files.append(rel)
                updated.append(rel)
        except Exception:
            for rel in reversed(replaced_root_files):
                backup_path = os.path.join(backup_root, *rel.split("/"))
                target = safe_update_target(rel)
                if os.path.exists(backup_path):
                    temp_path = f"{target}.rollback_tmp"
                    shutil.copy2(backup_path, temp_path)
                    os.replace(temp_path, target)
            if os.path.isdir(static_dir):
                shutil.rmtree(static_dir, ignore_errors=True)
            if os.path.isdir(backup_static_dir):
                shutil.copytree(backup_static_dir, static_dir)
            raise

        restart_scheduled = False
        if req.auto_restart and updated:
            restart_scheduled = schedule_self_restart(req.restart_delay)
        return {
            "ok": True,
            "updated": updated,
            "count": len(updated),
            "backup_dir": backup_root if os.path.exists(backup_root) else "",
            "restart_required": True,
            "restart_scheduled": restart_scheduled,
        }
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub 下载失败：HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 GitHub：{exc.reason}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新失败：{exc}") from exc
    finally:
        if staging_root and os.path.isdir(staging_root):
            shutil.rmtree(staging_root, ignore_errors=True)
        UPDATE_LOCK.release()

def list_update_backups() -> List[Dict[str, Any]]:
    root = os.path.join(DATA_DIR, "update_backups")
    if not os.path.isdir(root):
        return []
    items = []
    for name in sorted(os.listdir(root), reverse=True):
        bp = os.path.join(root, name)
        if not os.path.isdir(bp):
            continue
        file_count = 0
        for _, _, fs in os.walk(bp):
            file_count += len(fs)
        try:
            created_at = os.path.getmtime(bp)
        except OSError:
            created_at = 0.0
        items.append({
            "name": name,
            "file_count": file_count,
            "created_at": created_at,
        })
    return items

@app.get("/api/update-backups")
def get_update_backups(request: Request):
    require_admin_user(request)
    return {"backups": list_update_backups()}

class RollbackRequest(BaseModel):
    name: str = ""
    auto_restart: bool = False
    restart_delay: int = 3

@app.post("/api/update-rollback")
def rollback_update(request: Request, req: RollbackRequest):
    require_admin_user(request)
    if not req.name:
        raise HTTPException(status_code=400, detail="缺少备份名称")
    if not UPDATE_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="正在更新中，请稍后再试")
    try:
        backup_root_abs = os.path.abspath(os.path.join(DATA_DIR, "update_backups"))
        backup_dir = os.path.abspath(os.path.join(backup_root_abs, req.name))
        if os.path.commonpath([backup_root_abs, backup_dir]) != backup_root_abs:
            raise HTTPException(status_code=400, detail="备份路径不安全")
        if not os.path.isdir(backup_dir):
            raise HTTPException(status_code=404, detail="备份不存在")
        restored = []
        skipped = []
        backup_static_dir = os.path.join(backup_dir, "static")
        if os.path.isdir(backup_static_dir):
            static_dir = safe_static_dir()
            if os.path.isdir(static_dir):
                shutil.rmtree(static_dir)
            try:
                shutil.copytree(backup_static_dir, static_dir)
            except Exception:
                if os.path.isdir(static_dir):
                    shutil.rmtree(static_dir, ignore_errors=True)
                raise
            for dirpath, _, filenames in os.walk(backup_static_dir):
                for fn in filenames:
                    src = os.path.join(dirpath, fn)
                    restored.append(os.path.relpath(src, backup_dir).replace("\\", "/"))
        for dirpath, _, filenames in os.walk(backup_dir):
            for fn in filenames:
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, backup_dir).replace("\\", "/")
                if rel.startswith("static/"):
                    continue
                if not update_allowed_file(rel):
                    skipped.append(rel)
                    continue
                try:
                    target = safe_update_target(rel)
                except ValueError:
                    skipped.append(rel)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                temp_path = f"{target}.rollback_tmp"
                with open(src, "rb") as fin, open(temp_path, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                os.replace(temp_path, target)
                restored.append(rel)
        restart_scheduled = False
        if req.auto_restart and restored:
            restart_scheduled = schedule_self_restart(req.restart_delay)
        return {
            "ok": True,
            "restored": restored,
            "skipped": skipped,
            "count": len(restored),
            "restart_required": True,
            "restart_scheduled": restart_scheduled,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"回滚失败：{exc}") from exc
    finally:
        UPDATE_LOCK.release()

class GenerateRequest(BaseModel):
    prompt: str = ""
    width: int = 1024
    height: int = 1024
    workflow_json: str = "Z-Image.json"
    params: Dict[str, Any] = Field(default_factory=dict)
    type: str = "zimage"
    client_id: str = ""
    convert_to_jpg: bool = False

DIRECT_GENERATE_WORKFLOWS = {"Z-Image.json", "Z-Image-Enhance.json", "Flux2-Klein.json", "upscale.json"}

def ensure_direct_generate_allowed(req: GenerateRequest):
    workflow_name = str(req.workflow_json or "").strip()
    if workflow_name != os.path.basename(workflow_name) or workflow_name not in DIRECT_GENERATE_WORKFLOWS:
        raise HTTPException(status_code=403, detail="自定义工作流必须通过后台配置的运行接口调用")

class DeleteHistoryRequest(BaseModel):
    timestamp: float

class TokenRequest(BaseModel):
    token: str

class CloudGenRequest(BaseModel):
    prompt: str
    api_key: str = ""
    model: str = ""
    resolution: str = "1024x1024"
    type: str = "zimage"
    image_urls: List[str] = []
    loras: Optional[Any] = None
    client_id: Optional[str] = None

class CloudPollRequest(BaseModel):
    task_id: str
    api_key: str = ""
    client_id: Optional[str] = None

class AIReference(BaseModel):
    url: str = ""
    name: str = ""
    role: str = ""

class OnlineImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=ONLINE_IMAGE_PROMPT_MAX_LENGTH)
    provider_id: str = "comfly"
    model: str = ""
    size: str = "1024x1024"
    quality: str = "auto"
    n: int = 1
    reference_images: List[AIReference] = []

CANVAS_TASKS: Dict[str, Dict[str, Any]] = {}
CANVAS_TASK_LOCK = Lock()

class CanvasVideoRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=VIDEO_PROMPT_MAX_LENGTH)
    provider_id: str = "comfly"
    model: str = "veo3-fast"
    duration: int = 5
    aspect_ratio: str = "16:9"
    resolution: str = ""
    size: str = ""
    images: List[AIReference] = []
    videos: List[str] = []
    enhance_prompt: bool = False
    enable_upsample: bool = False
    watermark: bool = False
    seed: Optional[int] = None
    camerafixed: bool = False
    return_last_frame: bool = False
    generate_audio: bool = False

class RunningHubSubmitRequest(BaseModel):
    webappId: str = ""
    nodeInfoList: List[Dict[str, Any]] = []
    instanceType: str = ""
    useWallet: bool = False

class RunningHubWorkflowSubmitRequest(BaseModel):
    workflowId: str = ""
    nodeInfoList: List[Dict[str, Any]] = []
    workflow: Any = None
    useWallet: bool = False

class RunningHubUploadAssetRequest(BaseModel):
    url: str = ""
    useWallet: bool = False

class RunningHubWorkflowConfigField(BaseModel):
    id: str = ""
    nodeId: str = ""
    fieldName: str = ""
    fieldValue: str = ""
    fieldType: str = "TEXT"
    label: str = ""
    enabled: bool = True
    sourceFromUpstream: bool = True
    group: str = ""
    note: str = ""
    options: List[str] = Field(default_factory=list)
    random_enabled: bool = False
    min: Any = ""
    max: Any = ""
    step: Any = ""
    imageOrder: int = 0
    required: bool = False

class RunningHubWorkflowConfig(BaseModel):
    workflowId: str = ""
    title: str = ""
    description: str = ""
    fields: List[RunningHubWorkflowConfigField] = Field(default_factory=list)
    workflowJson: Dict[str, Any] = Field(default_factory=dict)
    optionalImageMode: str = "prune-workflow"
    raw: Dict[str, Any] = Field(default_factory=dict)

class ApiProviderPayload(BaseModel):
    id: str = ""
    name: str = ""
    base_url: str = ""
    protocol: str = "openai"
    image_generation_endpoint: str = ""
    image_edit_endpoint: str = ""
    enabled: bool = True
    primary: bool = False
    image_models: List[str] = []
    chat_models: List[str] = []
    video_models: List[str] = []
    ms_loras: List[Dict[str, Any]] = []
    ms_defaults_version: int = 0
    rh_apps: List[Dict[str, Any]] = []
    rh_workflows: List[Dict[str, Any]] = []
    api_key: Optional[str] = None
    wallet_api_key: Optional[str] = None
    clear_key: bool = False
    clear_wallet_key: bool = False

class ChatRequest(BaseModel):
    conversation_id: str = ""
    message: str = Field(min_length=1, max_length=LLM_MESSAGE_MAX_LENGTH)
    model: str = ""
    image_model: str = ""
    mode: str = "chat"
    size: str = "1024x1024"
    quality: str = "auto"
    reference_images: List[AIReference] = []
    provider: str = "comfly"
    ms_model: str = ""

class MsGenerateRequest(BaseModel):
    prompt: str
    api_key: str = ""
    model: str = "black-forest-labs/FLUX.2-klein-9B"
    image_urls: List[str] = []
    width: int = 0
    height: int = 0
    size: str = ""
    loras: Optional[Any] = None
    client_id: Optional[str] = None

class CanvasLLMRequest(BaseModel):
    message: str = Field(min_length=1, max_length=LLM_MESSAGE_MAX_LENGTH)
    system_prompt: str = ""
    model: str = ""
    messages: List[Dict[str, Any]] = []
    provider: str = "comfly"
    ms_model: str = ""
    images: List[str] = []   # 可以是 /output/*.png、/assets/*.png 本地路径 或 http(s) URL 或 data URL

class ConversationCreateRequest(BaseModel):
    title: str = "新对话"

class CanvasCreateRequest(BaseModel):
    title: str = "未命名画布"
    icon: str = "🧩"
    kind: str = "classic"

class ProjectCreateRequest(BaseModel):
    title: str = "未命名项目"
    thumbnail_url: str = ""
    kind: str = "classic"

class ProjectPatchRequest(BaseModel):
    title: str = ""
    thumbnail_url: str = ""
    icon: str = ""

class CanvasSaveRequest(BaseModel):
    title: str = "未命名画布"
    icon: str = "🧩"
    nodes: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    viewport: Dict[str, Any] = {}
    logs: List[Dict[str, Any]] = []
    settings: Dict[str, Any] = {}
    client_id: str = ""
    base_updated_at: int = 0

class CanvasAssetCheckRequest(BaseModel):
    urls: List[str] = []

class CanvasAssetDownloadRequest(BaseModel):
    urls: List[str] = []
    filename: str = "canvas-output-images.zip"

class SmartCanvasGroupExportItem(BaseModel):
    kind: str = ""
    url: str = ""
    text: str = ""
    name: str = ""

class SmartCanvasGroupExportRequest(BaseModel):
    folder: str = ""
    group_name: str = "group"
    items: List[SmartCanvasGroupExportItem] = []

class LocalImageImportRequest(BaseModel):
    path: str = ""
    paths: List[str] = Field(default_factory=list)

class AssetLibraryCategoryRequest(BaseModel):
    name: str = "新文件夹"
    type: str = "image"

class AssetLibraryAddRequest(BaseModel):
    category_id: str = ""
    url: str = ""
    name: str = ""

class AssetLibraryRenameRequest(BaseModel):
    name: str = ""

# --- 负载均衡 ---

def check_images_exist(backend_addr, images):
    if not images: return True
    for img in images:
        try:
            url = f"http://{backend_addr}/view?filename={urllib.parse.quote(img)}&type=input"
            r = requests.get(url, stream=True, timeout=0.5)
            r.close()
            if r.status_code != 200: return False
        except: return False
    return True

MEDIA_INPUT_KEYS = ("image", "video", "audio", "mask", "filename", "file")
MEDIA_INPUT_EXT_RE = re.compile(r"\.(png|jpe?g|webp|gif|bmp|tiff?|mp4|webm|mov|m4v|avi|mkv|mp3|wav|m4a|aac|ogg|flac)(?:\?|$)", re.I)

class BackendSelectionError(Exception):
    pass

def is_comfy_input_media_value(input_name: str, value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    key = str(input_name or "").lower()
    if any(token in key for token in MEDIA_INPUT_KEYS):
        return True
    return bool(MEDIA_INPUT_EXT_RE.search(value))

def collect_required_comfy_media(params: Dict[str, Any]) -> List[str]:
    required = []
    for node_inputs in (params or {}).values():
        if not isinstance(node_inputs, dict):
            continue
        for input_name, value in node_inputs.items():
            if is_comfy_input_media_value(input_name, value):
                required.append(value)
    return list(dict.fromkeys(required))

def load_workflow_json_payload(workflow_ref: Any) -> Any:
    if isinstance(workflow_ref, (dict, list)):
        return workflow_ref
    if not isinstance(workflow_ref, str):
        return None
    workflow_name = workflow_ref.strip()
    if not workflow_name:
        return None
    if workflow_name.startswith("{") or workflow_name.startswith("["):
        try:
            parsed = json.loads(workflow_name)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass
    if os.path.isabs(workflow_name) or ".." in workflow_name.replace("\\", "/").split("/"):
        return None
    workflow_path = os.path.join(WORKFLOW_DIR, workflow_name)
    if not os.path.exists(workflow_path) and workflow_name == "Z-Image.json":
        workflow_path = WORKFLOW_PATH
    if not os.path.exists(workflow_path):
        return None
    try:
        with open(workflow_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        if isinstance(parsed, (dict, list)):
            return parsed
    except Exception as e:
        print(f"加载 workflow 失败 ({workflow_name}): {e}")
    return None

def iter_workflow_nodes(workflow_json: Any):
    if isinstance(workflow_json, dict):
        workflow_payload = workflow_json.get("workflow_json")
        if isinstance(workflow_payload, (dict, list)):
            yield from iter_workflow_nodes(workflow_payload)
            return
        prompt_payload = workflow_json.get("prompt")
        if isinstance(prompt_payload, (dict, list)):
            yield from iter_workflow_nodes(prompt_payload)
            return
        nodes_payload = workflow_json.get("nodes")
        if isinstance(nodes_payload, list):
            for node in nodes_payload:
                if isinstance(node, dict):
                    yield node
            return
        for node in workflow_json.values():
            if isinstance(node, dict):
                yield node
        return
    if isinstance(workflow_json, list):
        for node in workflow_json:
            if isinstance(node, dict):
                yield node

def collect_required_workflow_class_types(workflow_ref: Any) -> List[str]:
    workflow_json = load_workflow_json_payload(workflow_ref)
    if not isinstance(workflow_json, (dict, list)):
        return []
    required = []
    for node in iter_workflow_nodes(workflow_json):
        class_type = node.get("class_type") or node.get("classType") or node.get("type")
        if isinstance(class_type, str) and class_type.strip():
            required.append(class_type.strip())
    return list(dict.fromkeys(required))

def get_backend_object_classes(addr: str):
    now = time.time()
    with OBJECT_INFO_CACHE_LOCK:
        cached = BACKEND_OBJECT_INFO_CACHE.get(addr)
        if cached and float(cached.get("expires_at") or 0) > now:
            return cached.get("classes"), str(cached.get("error") or "")
    classes = None
    error = ""
    try:
        with urllib.request.urlopen(f"http://{addr}/object_info", timeout=2) as response:
            payload = json.loads(response.read())
        if not isinstance(payload, dict):
            raise ValueError("object_info 响应不是 JSON object")
        classes = set()
        for node_class, node_info in payload.items():
            node_name = str(node_class or "").strip()
            if node_name:
                classes.add(node_name)
            if isinstance(node_info, dict):
                alt_name = str(node_info.get("name") or "").strip()
                if alt_name:
                    classes.add(alt_name)
    except Exception as e:
        classes = None
        error = str(e)[:200]
    with OBJECT_INFO_CACHE_LOCK:
        BACKEND_OBJECT_INFO_CACHE[addr] = {
            "classes": classes,
            "error": error,
            "expires_at": now + BACKEND_OBJECT_INFO_CACHE_TTL,
        }
    return classes, error

def summarize_required_nodes(node_list: List[str], limit: int = 8) -> str:
    if not node_list:
        return "-"
    nodes = list(node_list)
    if len(nodes) <= limit:
        return ", ".join(nodes)
    return ", ".join(nodes[:limit]) + f" ...(+{len(nodes) - limit})"

def build_backend_incompatible_error(required_class_types: List[str], backend_stats: Dict[str, Dict[str, Any]]) -> str:
    lines = []
    for addr in COMFYUI_INSTANCES:
        stat = backend_stats.get(addr) or {}
        if stat.get("queue_error"):
            lines.append(f"{addr}: queue 不可用 ({stat.get('queue_error')})")
            continue
        if stat.get("object_info_error"):
            lines.append(f"{addr}: object_info 不兼容 ({stat.get('object_info_error')})")
            continue
        missing = stat.get("missing_nodes") or []
        if missing:
            lines.append(f"{addr}: 缺少 {len(missing)} 个节点 [{summarize_required_nodes(missing, limit=6)}]")
            continue
        lines.append(f"{addr}: 不兼容（未知原因）")
    summary = "; ".join(lines) if lines else "无可用实例"
    return (
        f"未找到兼容的 ComfyUI 实例。"
        f"workflow 需要 {len(required_class_types)} 个节点：[{summarize_required_nodes(required_class_types)}]。"
        f"实例详情：{summary}"
    )

def get_best_backend(required_images: List[str] = None, workflow_json: Any = None):
    best_backend = COMFYUI_INSTANCES[0]
    min_queue_size = float('inf')
    candidates_with_images = []
    candidates_others = []
    backend_stats = {}
    required_class_types = collect_required_workflow_class_types(workflow_json)
    class_filter_enabled = bool(required_class_types)

    for addr in COMFYUI_INSTANCES:
        stat: Dict[str, Any] = {
            "load": None,
            "has_images": False,
            "missing_nodes": [],
            "queue_error": "",
            "object_info_error": "",
        }
        try:
            with urllib.request.urlopen(f"http://{addr}/queue", timeout=1) as response:
                data = json.loads(response.read())
                remote_load = len(data.get('queue_running', [])) + len(data.get('queue_pending', []))
                with LOAD_LOCK:
                    local_load = BACKEND_LOCAL_LOAD.get(addr, 0)
                effective_load = max(remote_load, local_load)
                has_images = check_images_exist(addr, required_images)
                stat["load"] = effective_load
                stat["has_images"] = has_images
        except Exception as e:
            print(f"Backend {addr} unreachable: {e}")
            stat["queue_error"] = str(e)[:200]
            backend_stats[addr] = stat
            continue

        compatible = True
        if class_filter_enabled:
            classes, object_info_error = get_backend_object_classes(addr)
            if not classes:
                stat["object_info_error"] = object_info_error or "空返回"
                compatible = False
            else:
                missing_nodes = [node for node in required_class_types if node not in classes]
                stat["missing_nodes"] = missing_nodes
                compatible = not missing_nodes
        backend_stats[addr] = stat
        if not compatible:
            continue
        if stat["has_images"]:
            candidates_with_images.append(addr)
        else:
            candidates_others.append(addr)

    target_candidates = candidates_with_images if candidates_with_images else candidates_others
    if not target_candidates:
        if class_filter_enabled:
            raise BackendSelectionError(build_backend_incompatible_error(required_class_types, backend_stats))
        return COMFYUI_INSTANCES[0]

    for addr in target_candidates:
        load = backend_stats[addr]["load"]
        if load < min_queue_size:
            min_queue_size = load
            best_backend = addr

    return best_backend

# --- 辅助工具 ---

def download_image(comfy_address, comfy_url_path, prefix="studio_"):
    filename = f"{prefix}{uuid.uuid4().hex[:10]}.png"
    local_path = output_path_for(filename, "output")
    full_url = f"http://{comfy_address}{comfy_url_path}"
    try:
        with urllib.request.urlopen(full_url) as response, open(local_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        return output_url_for(filename, "output")
    except Exception as e:
        print(f"下载图片失败: {e}")
        if comfy_url_path.startswith("/view"):
            return comfy_url_path.replace("/view", "/api/view", 1)
        return full_url

def comfy_output_extension(item):
    filename = str((item or {}).get("filename") or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext in {
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
        ".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv",
        ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
        ".txt", ".json", ".csv", ".srt", ".vtt", ".md",
    }:
        return ext
    fmt = str((item or {}).get("format") or "").lower()
    if "mpeg" in fmt or "mp3" in fmt:
        return ".mp3"
    if "wav" in fmt or "wave" in fmt:
        return ".wav"
    if "ogg" in fmt:
        return ".ogg"
    if "flac" in fmt:
        return ".flac"
    if "text" in fmt or "plain" in fmt:
        return ".txt"
    if "json" in fmt:
        return ".json"
    if "webm" in fmt:
        return ".webm"
    if "quicktime" in fmt or "mov" in fmt:
        return ".mov"
    if "mp4" in fmt or "h264" in fmt or "video" in fmt:
        return ".mp4"
    return ext or ".bin"

def is_video_output_item(item):
    ext = comfy_output_extension(item)
    fmt = str((item or {}).get("format") or "").lower()
    return ext in {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"} or "video" in fmt

def comfy_output_kind(item):
    ext = comfy_output_extension(item)
    fmt = str((item or {}).get("format") or "").lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"} or "image" in fmt:
        return "image"
    if ext in {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"} or "video" in fmt:
        return "video"
    if ext in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"} or "audio" in fmt or "sound" in fmt:
        return "audio"
    if ext in {".txt", ".json", ".csv", ".srt", ".vtt", ".md"} or "text" in fmt or "json" in fmt:
        return "text"
    return "file"

def download_comfy_output(comfy_address, item, prefix="studio_"):
    ext = comfy_output_extension(item)
    filename = f"{prefix}{uuid.uuid4().hex[:10]}{ext}"
    local_path = output_path_for(filename, "output")
    subfolder = urllib.parse.quote(str(item.get("subfolder") or ""))
    file_type = urllib.parse.quote(str(item.get("type") or "output"))
    comfy_url_path = f"/view?filename={urllib.parse.quote(str(item['filename']))}&subfolder={subfolder}&type={file_type}"
    full_url = f"http://{comfy_address}{comfy_url_path}"
    try:
        with urllib.request.urlopen(full_url) as response, open(local_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        return output_url_for(filename, "output")
    except Exception as e:
        print(f"下载 ComfyUI 输出失败: {e}")
        if comfy_url_path.startswith("/view"):
            return comfy_url_path.replace("/view", "/api/view", 1)
        return full_url

def save_comfy_text_output(value, prefix="studio_", name=""):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    stem = sanitize_export_filename(name or "comfy_text.txt", "comfy_text.txt")
    _, ext = os.path.splitext(stem)
    if ext.lower() not in {".txt", ".json", ".csv", ".srt", ".vtt", ".md"}:
        stem += ".txt"
    filename = f"{prefix}{uuid.uuid4().hex[:10]}_{stem}"
    path = output_path_for(filename, "output")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return output_url_for(filename, "output")

def comfy_text_values_from_output(node_output):
    values = []
    text_keys = ("text", "texts", "prompt", "prompts", "string", "strings", "caption", "captions")
    for key in text_keys:
        if key not in node_output:
            continue
        value = node_output.get(key)
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                text = item.get("text") or item.get("prompt") or item.get("caption") or item.get("value")
                name = item.get("filename") or item.get("name") or f"{key}.txt"
            else:
                text = item
                name = f"{key}.txt"
            if text is None:
                continue
            text = str(text)
            if text.strip():
                values.append((text, name))
    return values

def collect_comfy_file_items(node_output):
    items = []
    for key, value in (node_output or {}).items():
        if key in {"text", "texts", "prompt", "prompts", "string", "strings", "caption", "captions"}:
            continue
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if isinstance(item, dict) and item.get("filename"):
                items.append((key, item))
    return items

def comfy_execution_error_from_history(history_data: Any) -> str:
    if not isinstance(history_data, dict):
        return ""
    status = history_data.get("status")
    if not isinstance(status, dict):
        return ""
    messages = status.get("messages") or []
    for item in messages:
        if not (isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] == "execution_error"):
            continue
        payload = item[1] if isinstance(item[1], dict) else {}
        node_id = str(payload.get("node_id") or "").strip()
        node_type = str(payload.get("node_type") or "").strip()
        exc_type = str(payload.get("exception_type") or "").strip()
        exc_message = str(payload.get("exception_message") or payload.get("error") or "").strip()
        parts = ["ComfyUI 执行失败"]
        if node_id or node_type:
            node_text = f"节点 {node_id}" if node_id else "节点"
            if node_type:
                node_text = f"{node_text} ({node_type})"
            parts.append(node_text)
        if exc_type:
            parts.append(exc_type)
        if exc_message:
            parts.append(exc_message)
        return "：".join([parts[0], " | ".join(parts[1:])]) if len(parts) > 1 else parts[0]
    status_str = str(status.get("status_str") or "").strip().lower()
    if status_str == "error":
        return "ComfyUI 执行失败（未返回详细节点错误）"
    return ""

def normalize_owner_key(owner_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", str(owner_key or "")).strip(".-")

def history_path(owner_key: str):
    clean_owner = normalize_owner_key(owner_key)
    if not clean_owner:
        raise HTTPException(status_code=401, detail="未登录")
    os.makedirs(HISTORY_DIR, exist_ok=True)
    return os.path.join(HISTORY_DIR, f"{clean_owner}.json")

def save_to_history(record, owner_key: str):
    with HISTORY_LOCK:
        history = []
        target_path = history_path(owner_key)
        if os.path.exists(target_path):
            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except: pass
        if "timestamp" not in record:
            record["timestamp"] = time.time()
        history.insert(0, record)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(history[:5000], f, ensure_ascii=False, indent=4)

def get_comfy_history(comfy_address, prompt_id):
    try:
        with urllib.request.urlopen(f"http://{comfy_address}/history/{prompt_id}") as response:
            return json.loads(response.read())
    except Exception as e:
        return {}

def owner_key_from_user(user: Dict[str, Any]) -> str:
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="未登录")
    return normalize_owner_key(f"user-{int(user['id'])}")

def safe_user_id(user_id, request: Request):
    _ = user_id
    user = require_current_user(request)
    return owner_key_from_user(user)

def user_dir(user_id):
    owner_key = normalize_owner_key(user_id)
    if not owner_key:
        raise HTTPException(status_code=400, detail="无效的用户标识")
    path = os.path.join(CONVERSATION_DIR, owner_key)
    os.makedirs(path, exist_ok=True)
    return path

def conversation_path(user_id, conversation_id):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", conversation_id or "")
    if not cleaned:
        raise HTTPException(status_code=400, detail="无效的对话 ID")
    return os.path.join(user_dir(user_id), f"{cleaned}.json")

def now_ms():
    return int(time.time() * 1000)

def save_conversation(user_id, conversation):
    with CONVERSATION_LOCK:
        path = conversation_path(user_id, conversation["id"])
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(conversation, f, ensure_ascii=False, indent=2)

def new_conversation(user_id, title="新对话"):
    timestamp = now_ms()
    conversation = {
        "id": uuid.uuid4().hex,
        "title": (title or "新对话")[:80],
        "created_at": timestamp,
        "updated_at": timestamp,
        "messages": [],
    }
    save_conversation(user_id, conversation)
    return conversation

def load_conversation(user_id, conversation_id):
    path = conversation_path(user_id, conversation_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="对话不存在")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def list_conversations(user_id):
    records = []
    for filename in os.listdir(user_dir(user_id)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(user_dir(user_id), filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        messages = data.get("messages", [])
        last_message = next((m for m in reversed(messages) if m.get("role") != "system"), None)
        records.append({
            "id": data.get("id"),
            "title": data.get("title", "新对话"),
            "created_at": data.get("created_at", 0),
            "updated_at": data.get("updated_at", 0),
            "last_message": (last_message or {}).get("content", ""),
        })
    return sorted(records, key=lambda item: item["updated_at"], reverse=True)

def canvas_path(canvas_id):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", canvas_id or "")
    if not cleaned:
        raise HTTPException(status_code=400, detail="无效的画布 ID")
    return os.path.join(CANVAS_DIR, f"{cleaned}.json")

def save_canvas(canvas):
    canvas["updated_at"] = now_ms()
    with CANVAS_LOCK:
        with open(canvas_path(canvas["id"]), 'w', encoding='utf-8') as f:
            json.dump(canvas, f, ensure_ascii=False, indent=2)

def normalize_canvas_kind(kind="classic"):
    return "smart" if str(kind or "").strip().lower() == "smart" else "classic"

def new_canvas(title="未命名画布", icon="layers", kind="classic", owner_user_id=0, project_id=""):
    timestamp = now_ms()
    canvas_kind = normalize_canvas_kind(kind)
    canvas = {
        "id": uuid.uuid4().hex,
        "title": (title or ("智能画布" if canvas_kind == "smart" else "未命名画布"))[:80],
        "icon": (icon or ("sparkles" if canvas_kind == "smart" else "🧩"))[:32],
        "kind": canvas_kind,
        "created_at": timestamp,
        "updated_at": timestamp,
        "nodes": [],
        "connections": [],
        "viewport": {"x": 0, "y": 0, "scale": 1},
        "owner_user_id": int(owner_user_id or 0),
        "project_id": str(project_id or ""),
    }
    save_canvas(canvas)
    return canvas

def load_canvas(canvas_id):
    path = canvas_path(canvas_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="画布不存在")
    with open(path, 'r', encoding='utf-8') as f:
        canvas = json.load(f)
    if canvas.get("deleted_at"):
        raise HTTPException(status_code=404, detail="画布已在回收站")
    return canvas

def load_canvas_any(canvas_id):
    path = canvas_path(canvas_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="画布不存在")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def canvas_record(data):
    return {
        "id": data.get("id"),
        "title": data.get("title", "未命名画布"),
        "icon": data.get("icon", "🧩"),
        "kind": normalize_canvas_kind(data.get("kind")),
        "created_at": data.get("created_at", 0),
        "updated_at": data.get("updated_at", 0),
        "deleted_at": data.get("deleted_at", 0),
        "node_count": len(data.get("nodes", [])),
        "owner_user_id": int(data.get("owner_user_id") or 0),
        "project_id": str(data.get("project_id") or ""),
    }

def user_can_access_canvas(user: Dict[str, Any], canvas_data: Dict[str, Any]) -> bool:
    if not user or not canvas_data:
        return False
    if user.get("is_admin"):
        return True
    owner_user_id = int(canvas_data.get("owner_user_id") or 0)
    if owner_user_id and owner_user_id == int(user["id"]):
        return True
    project_id = str(canvas_data.get("project_id") or "").strip()
    if not project_id:
        return False
    project_row = load_project(project_id)
    if not project_row:
        return False
    return user_can_access_project(user, project_row)

def ensure_canvas_access(user: Dict[str, Any], canvas_data: Dict[str, Any]):
    if not user_can_access_canvas(user, canvas_data):
        raise HTTPException(status_code=403, detail="无权限访问该画布")

def iter_canvas_records_for_user(user: Dict[str, Any], include_deleted=False, project_id=""):
    cleanup_expired_canvas_trash()
    records = []
    project_filter = str(project_id or "").strip()
    for filename in os.listdir(CANVAS_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(CANVAS_DIR, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        if project_filter and str(data.get("project_id") or "") != project_filter:
            continue
        is_deleted = bool(data.get("deleted_at"))
        if include_deleted != is_deleted:
            continue
        if not user_can_access_canvas(user, data):
            continue
        records.append(canvas_record(data))
    return records

def cleanup_expired_canvas_trash():
    cutoff = now_ms() - CANVAS_TRASH_RETENTION_MS
    with CANVAS_LOCK:
        for filename in os.listdir(CANVAS_DIR):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(CANVAS_DIR, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                deleted_at = int(data.get("deleted_at") or 0)
                if deleted_at and deleted_at < cutoff:
                    os.remove(path)
            except Exception:
                continue

def iter_canvas_records(include_deleted=False):
    cleanup_expired_canvas_trash()
    records = []
    for filename in os.listdir(CANVAS_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(CANVAS_DIR, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        is_deleted = bool(data.get("deleted_at"))
        if include_deleted != is_deleted:
            continue
        records.append(canvas_record(data))
    return records

def list_canvases():
    records = iter_canvas_records(include_deleted=False)
    return sorted(records, key=lambda item: item["updated_at"], reverse=True)

def list_deleted_canvases():
    records = iter_canvas_records(include_deleted=True)
    return sorted(records, key=lambda item: item["deleted_at"], reverse=True)

def project_row_to_dict(row) -> Dict[str, Any]:
    owner = None
    if row and row["owner_username"] is not None:
        owner = {
            "id": int(row["owner_user_id"]),
            "username": str(row["owner_username"]),
            "is_admin": bool(row["owner_is_admin"]),
            "created_at": str(row["owner_created_at"] or ""),
        }
    default_canvas = {}
    default_canvas_id = str(row["default_canvas_id"] or "")
    if default_canvas_id:
        try:
            default_canvas = canvas_record(load_canvas_any(default_canvas_id))
        except Exception:
            default_canvas = {"id": default_canvas_id}
    project_updated_at = int(row["updated_at"] or 0)
    canvas_updated_at = int(default_canvas.get("updated_at") or 0)
    return {
        "id": str(row["id"]),
        "title": str(row["title"] or "未命名项目"),
        "owner_user_id": int(row["owner_user_id"]),
        "owner": owner,
        "default_canvas_id": default_canvas_id,
        "default_canvas": default_canvas,
        "icon": str(default_canvas.get("icon") or "layers"),
        "kind": normalize_canvas_kind(default_canvas.get("kind")),
        "node_count": int(default_canvas.get("node_count") or 0),
        "thumbnail_url": str(row["thumbnail_url"] or ""),
        "status": str(row["status"] or "active"),
        "created_at": int(row["created_at"] or 0),
        "updated_at": max(project_updated_at, canvas_updated_at),
        "archived_at": int(row["archived_at"] or 0),
    }

def list_projects_for_user(user: Dict[str, Any], status: str = "active") -> List[Dict[str, Any]]:
    desired_status = "archived" if status == "archived" else "active"
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            if user.get("is_admin"):
                rows = conn.execute(
                    """
                    SELECT p.*, u.username AS owner_username, u.is_admin AS owner_is_admin, u.created_at AS owner_created_at
                    FROM projects p
                    LEFT JOIN users u ON u.id = p.owner_user_id
                    WHERE p.status = ?
                    ORDER BY p.updated_at DESC
                    """,
                    (desired_status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT p.*, u.username AS owner_username, u.is_admin AS owner_is_admin, u.created_at AS owner_created_at
                    FROM projects p
                    LEFT JOIN users u ON u.id = p.owner_user_id
                    LEFT JOIN project_members pm ON pm.project_id = p.id AND pm.user_id = ?
                    WHERE p.status = ? AND (p.owner_user_id = ? OR pm.user_id IS NOT NULL)
                    ORDER BY p.updated_at DESC
                    """,
                    (int(user["id"]), desired_status, int(user["id"])),
                ).fetchall()
            return [project_row_to_dict(row) for row in rows]
        finally:
            conn.close()

def touch_project(project_id: str, timestamp: Optional[int] = None):
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", project_id or "")
    if not clean_id:
        return
    updated_at = int(timestamp or now_ms())
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (updated_at, clean_id))
            conn.commit()
        finally:
            conn.close()

def display_title(text):
    title = re.sub(r"\s+", " ", text or "").strip()
    return title[:24] or "新对话"

def resolve_chat_provider(provider: str, model: str, ms_model: str):
    if provider == "modelscope":
        if not MODELSCOPE_API_KEY:
            raise HTTPException(status_code=400, detail="未配置 MODELSCOPE_API_KEY，请在 API/.env 中填写。")
        base = MODELSCOPE_CHAT_BASE_URL
        hdrs = {"Authorization": bearer_auth_value(MODELSCOPE_API_KEY), "Content-Type": "application/json"}
        mdl = selected_model(ms_model or model, MODELSCOPE_CHAT_MODELS[0] if MODELSCOPE_CHAT_MODELS else "MiniMax/MiniMax-M2.7")
        return base, hdrs, mdl
    api_provider = get_api_provider(provider or "")
    base_root = (api_provider.get("base_url") or AI_BASE_URL).rstrip("/")
    if not base_root:
        raise HTTPException(status_code=400, detail=f"{api_provider.get('name') or api_provider['id']} 未配置 Base URL")
    protocol = provider_protocol(api_provider)
    if protocol == "gemini":
        base = base_root if base_root.endswith("/v1beta") else base_root + "/v1beta"
    elif protocol == "volcengine":
        base = base_root if base_root.endswith("/api/v3") else base_root + "/api/v3"
    else:
        base = base_root if base_root.endswith("/v1") else base_root + "/v1"
    hdrs = api_headers(provider=api_provider)
    default_model = preferred_chat_model(api_provider)
    mdl = selected_model(model, default_model)
    return base, hdrs, mdl

def api_headers(json_body=True, provider=None):
    if provider:
        key_env = provider_key_env(provider["id"])
        api_key = os.getenv(key_env, "")
        provider_name = provider.get("name") or provider["id"]
        if not api_key:
            raise HTTPException(status_code=400, detail=f"未配置 {provider_name} 的 API Key，请在 API 平台管理中填写。")
    else:
        api_key = AI_API_KEY
        if not api_key:
            raise HTTPException(status_code=400, detail="未配置 COMFLY_API_KEY，请在 API/.env 中填写。")
    if provider and provider_protocol(provider) == "gemini":
        headers = {"Accept": "application/json", "x-goog-api-key": api_key}
    else:
        headers = {"Accept": "application/json", "Authorization": bearer_auth_value(api_key)}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers

def selected_model(requested, fallback):
    model = (requested or fallback).strip()
    if not model:
        raise HTTPException(status_code=400, detail="模型名称不能为空")
    if len(model) > 240 or any(ord(ch) < 32 or ord(ch) == 127 for ch in model):
        raise HTTPException(status_code=400, detail=f"模型名称不合法：{model}")
    return model

def looks_like_vision_chat_model(model):
    lc = str(model or "").strip().lower()
    if not lc:
        return False
    vision_keys = [
        "vision", "vl-", "-vl-", "internvl", "qvq", "qwen-vl",
        "doubao-vision", "glm-4v", "minicpm-v",
    ]
    return any(key in lc for key in vision_keys)

def preferred_chat_model(provider):
    values = [str(item or "").strip() for item in (provider.get("chat_models") or [CHAT_MODEL])]
    models = [item for item in values if item]
    if not models:
        return CHAT_MODEL
    if is_volcengine_provider(provider):
        endpoint_models = [item for item in models if item.lower().startswith("ep-")]
        if endpoint_models:
            return endpoint_models[0]
        text_like_models = [item for item in models if not looks_like_vision_chat_model(item)]
        if text_like_models:
            return text_like_models[0]
    return models[0]

def modelscope_size(value, fallback="1024x1024"):
    size = str(value or fallback).strip().lower().replace("*", "x")
    if re.fullmatch(r"\d{2,5}x\d{2,5}", size):
        return size
    raise HTTPException(status_code=400, detail=f"ModelScope size 格式不正确：{value or fallback}，应为 WxH，例如 1024x1024")

def unwrap_apimart_response(raw):
    """APIMart 将标准 OpenAI 响应包在 {"code":200,"data":{...}} 里；如果检测到就解包。"""
    if isinstance(raw, dict) and "data" in raw and isinstance(raw.get("data"), dict) and "choices" not in raw:
        return raw["data"]
    return raw

def text_from_chat_response(data):
    data = unwrap_apimart_response(data)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("content") or "")
        return "\n".join(part for part in parts if part)
    return str(content)

def text_delta_from_chat_chunk(data):
    choices = data.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("content") or "")
        return "".join(parts)
    return str(content) if content else ""

def sse_event(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

def extract_image(data):
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            parts = content.get("parts") if isinstance(content, dict) else None
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if not isinstance(inline, dict):
                    continue
                value = inline.get("data")
                if value:
                    return {
                        "type": "b64",
                        "value": value,
                        "mime_type": inline.get("mimeType") or inline.get("mime_type") or "image/png",
                    }
    if isinstance(data.get("data"), dict) and isinstance(data["data"].get("result"), dict):
        data = data["data"]
    if isinstance(data.get("result"), dict):
        result_images = data["result"].get("images") or []
        if result_images:
            first = result_images[0]
            url = first.get("url")
            if isinstance(url, list) and url:
                return {"type": "url", "value": url[0]}
            if isinstance(url, str) and url:
                return {"type": "url", "value": url}
    if isinstance(data.get("data"), dict) and isinstance(data["data"].get("data"), dict):
        data = data["data"]["data"]
    images = data.get("data") or []
    if not isinstance(images, list) or not images:
        raise HTTPException(status_code=502, detail="生图接口没有返回图片数据")
    first = images[0]
    if first.get("url"):
        return {"type": "url", "value": first["url"]}
    if first.get("b64_json"):
        return {"type": "b64", "value": first["b64_json"]}
    raise HTTPException(status_code=502, detail="无法识别生图接口返回格式")

def extract_task_id(data):
    if data.get("task_id"):
        return str(data["task_id"])
    if data.get("id") and str(data.get("id", "")).startswith("task"):
        return str(data["id"])
    nested = data.get("data")
    if isinstance(nested, list) and nested:
        first = nested[0]
        if isinstance(first, dict):
            return extract_task_id(first)
    if isinstance(nested, dict):
        return extract_task_id(nested)
    return None

def images_api_unsupported(response):
    text = str(getattr(response, "text", "") or "").lower()
    return "images api is not supported" in text or "not supported for this platform" in text

def provider_protocol(provider):
    return str((provider or {}).get("protocol") or "openai").strip().lower()

def is_apimart_provider(provider):
    base_url = str((provider or {}).get("base_url") or "").lower()
    return provider_protocol(provider) == "apimart" or "apimart.ai" in base_url

def is_gemini_provider(provider):
    return provider_protocol(provider) == "gemini"

def is_volcengine_provider(provider):
    return provider_protocol(provider) == "volcengine"

def is_runninghub_provider(provider):
    return provider_protocol(provider) == "runninghub" or str((provider or {}).get("id") or "").strip().lower() == "runninghub"

async def wait_for_image_task(client, task_id, provider=None):
    base_url = (provider.get("base_url") if provider else AI_BASE_URL).rstrip("/")
    is_apimart = is_apimart_provider(provider)
    if is_apimart:
        task_url = f"{base_url}/tasks/{task_id}" if base_url.endswith("/v1") else f"{base_url}/v1/tasks/{task_id}"
    else:
        task_url = f"{base_url}/images/tasks/{task_id}" if base_url.endswith("/v1") else f"{base_url}/v1/images/tasks/{task_id}"
    timeout = APIMART_IMAGE_TASK_TIMEOUT if is_apimart else IMAGE_TASK_TIMEOUT
    interval = APIMART_IMAGE_POLL_INTERVAL if is_apimart else IMAGE_POLL_INTERVAL
    initial_delay = APIMART_IMAGE_INITIAL_POLL_DELAY if is_apimart else 0
    deadline = time.monotonic() + timeout
    last_payload = {}
    while time.monotonic() < deadline:
        if initial_delay:
            await asyncio.sleep(min(initial_delay, max(0.0, deadline - time.monotonic())))
            initial_delay = 0
            if time.monotonic() >= deadline:
                break
        response = await client.get(task_url, headers=api_headers(provider=provider))
        response.raise_for_status()
        last_payload = response.json()
        task_data = last_payload.get("data") if isinstance(last_payload.get("data"), dict) else last_payload
        status = str(task_data.get("status") or task_data.get("task_status") or "").upper()
        if status in {"SUCCESS", "SUCCEED", "SUCCEEDED", "COMPLETED", "COMPLETE", "DONE", "FINISHED", "OK", "READY"}:
            return last_payload
        if status in {"FAILURE", "FAILED", "FAIL", "ERROR", "ERRORED", "CANCELED", "CANCELLED", "TIMEOUT", "REJECTED", "EXPIRED"}:
            error = task_data.get("error") if isinstance(task_data.get("error"), dict) else {}
            reason = task_data.get("fail_reason") or task_data.get("message") or error.get("message") or last_payload.get("message") or "生图任务失败"
            raise HTTPException(status_code=502, detail=f"生图任务失败：{reason}")
        await asyncio.sleep(min(interval, max(0.0, deadline - time.monotonic())))
    raise HTTPException(status_code=504, detail=f"生图任务超时（已等待 {int(timeout)} 秒），task_id={task_id}")

def output_storage(category="output"):
    return (OUTPUT_INPUT_DIR, "input") if category == "input" else (OUTPUT_OUTPUT_DIR, "output")

def output_url_for(filename, category="output"):
    _, subdir = output_storage(category)
    return f"/assets/{subdir}/{filename}"

def output_path_for(filename, category="output"):
    folder, _ = output_storage(category)
    return os.path.join(folder, filename)

def output_file_from_url(url):
    if isinstance(url, dict):
        url = url.get("url", "")
    if not url or not (url.startswith("/output/") or url.startswith("/assets/")):
        return None
    clean = urllib.parse.unquote(url.split("?", 1)[0]).replace("\\", "/")
    if clean.startswith("/assets/"):
        root = ASSETS_DIR
        rel = clean[len("/assets/"):]
    else:
        root = OUTPUT_DIR
        rel = clean[len("/output/"):]
    rel = rel.lstrip("/")
    if not rel:
        return None
    path = os.path.abspath(os.path.join(root, rel))
    output_root = os.path.abspath(root)
    if os.path.commonpath([output_root, path]) != output_root or not os.path.exists(path):
        return None
    return path

def origin_from_url(value):
    parsed = urllib.parse.urlparse(str(value or ""))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".lower()

def ensure_same_origin_request(request: Request):
    host = str(request.headers.get("host") or "").lower()
    expected = f"{request.url.scheme}://{host}".lower() if host else ""
    origin = origin_from_url(request.headers.get("origin", ""))
    referer = origin_from_url(request.headers.get("referer", ""))
    actual = origin or referer
    if expected and actual != expected:
        raise HTTPException(status_code=403, detail="只允许从当前页面导入本地图片")

def normalize_local_image_path(value):
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        raise HTTPException(status_code=400, detail="本地图片路径为空")
    if text.lower().startswith("file:"):
        parsed = urllib.parse.urlparse(text)
        if parsed.scheme.lower() != "file":
            raise HTTPException(status_code=400, detail="只支持本地图片路径")
        if parsed.netloc and re.match(r"^[a-zA-Z]:$", parsed.netloc) and os.name == "nt":
            path = f"{parsed.netloc}{urllib.request.url2pathname(parsed.path or '')}"
        elif parsed.netloc and parsed.netloc.lower() not in ("localhost",):
            raise HTTPException(status_code=400, detail="只支持本机图片路径")
        else:
            path = urllib.request.url2pathname(parsed.path or "")
    else:
        path = text
    path = path.strip().strip('"').strip("'")
    if re.match(r"^/[a-zA-Z]:[\\/]", path):
        path = path[1:]
    if re.match(r"^[a-zA-Z]:[\\/]", path):
        return os.path.abspath(path)
    if path.startswith("/") and os.name != "nt":
        return os.path.abspath(path)
    raise HTTPException(status_code=400, detail="只支持本机绝对图片路径")

def import_local_image_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in LOCAL_IMAGE_IMPORT_EXTS:
        raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、JPEG、WEBP、GIF 图片")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="本地图片不存在或无法读取")
    try:
        size = os.path.getsize(path)
    except OSError:
        raise HTTPException(status_code=404, detail="本地图片不存在或无法读取")
    if size <= 0:
        raise HTTPException(status_code=400, detail="本地图片为空")
    if size > LOCAL_IMAGE_IMPORT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="本地图片过大，请使用 50MB 以内的图片")
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="文件不是可识别的图片")
    filename = f"ai_ref_{uuid.uuid4().hex[:12]}{ext}"
    dest = output_path_for(filename, "input")
    try:
        shutil.copyfile(path, dest)
    except OSError:
        raise HTTPException(status_code=500, detail="导入本地图片失败")
    return {"url": output_url_for(filename, "input"), "name": os.path.basename(path) or filename, "kind": "image"}

def default_asset_library():
    return {
        "categories": [
            {"id": "characters", "name": "角色", "type": "image", "items": []},
            {"id": "scenes", "name": "场景", "type": "image", "items": []},
            {"id": "workflows", "name": "工作流", "type": "workflow", "items": []},
        ],
        "updated_at": now_ms(),
    }

def load_asset_library():
    if not os.path.exists(ASSET_LIBRARY_PATH):
        lib = default_asset_library()
        save_asset_library(lib)
        return lib
    try:
        with open(ASSET_LIBRARY_PATH, "r", encoding="utf-8") as f:
            lib = json.load(f)
    except Exception:
        lib = default_asset_library()
    cats = lib.get("categories") if isinstance(lib.get("categories"), list) else []
    if not any(c.get("type") == "workflow" for c in cats):
        cats.append({"id": "workflows", "name": "工作流", "type": "workflow", "items": []})
    lib["categories"] = cats
    lib["updated_at"] = int(lib.get("updated_at") or now_ms())
    sort_asset_library_items(lib)
    return lib

def sort_asset_library_items(lib):
    for cat in lib.get("categories", []):
        items = cat.get("items")
        if isinstance(items, list):
            def created_at_key(item):
                if not isinstance(item, dict):
                    return 0
                try:
                    return int(float(item.get("created_at") or 0))
                except (TypeError, ValueError):
                    return 0
            items.sort(key=created_at_key, reverse=True)
    return lib

def save_asset_library(lib):
    sort_asset_library_items(lib)
    lib["updated_at"] = now_ms()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ASSET_LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)

def find_asset_category(lib, category_id):
    for cat in lib.get("categories", []):
        if cat.get("id") == category_id:
            return cat
    return None

def sanitize_asset_name(name, fallback="asset"):
    name = re.sub(r'[\\/:*?"<>|]+', "_", str(name or fallback)).strip()
    return name[:120] or fallback

def content_type_for_path(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in [".mp4", ".m4v"]:
        return "video/mp4"
    if ext == ".webm":
        return "video/webm"
    if ext == ".mov":
        return "video/quicktime"
    if ext == ".mp3":
        return "audio/mpeg"
    if ext == ".wav":
        return "audio/wav"
    if ext == ".m4a":
        return "audio/mp4"
    if ext == ".aac":
        return "audio/aac"
    if ext == ".ogg":
        return "audio/ogg"
    if ext == ".flac":
        return "audio/flac"
    if ext == ".gif":
        return "image/gif"
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".txt":
        return "text/plain; charset=utf-8"
    if ext == ".json":
        return "application/json; charset=utf-8"
    if ext == ".csv":
        return "text/csv; charset=utf-8"
    if ext == ".md":
        return "text/markdown; charset=utf-8"
    if ext == ".srt":
        return "application/x-subrip; charset=utf-8"
    if ext == ".vtt":
        return "text/vtt; charset=utf-8"
    if ext == ".png":
        return "image/png"
    return "application/octet-stream"

def is_image_reference_value(value):
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("data:image/"):
        return True
    if value.startswith("data:"):
        return False
    if value.startswith("/output/") or value.startswith("/assets/"):
        path = output_file_from_url(value)
        return bool(path and content_type_for_path(path).startswith("image/"))
    clean = value.split("?", 1)[0].lower()
    if re.search(r"\.(mp4|webm|mov|m4v|mp3|wav|m4a|aac|ogg|flac)$", clean):
        return False
    return True

def convert_output_to_jpg(url, quality=88):
    path = output_file_from_url(url)
    if not path:
        return url
    root, ext = os.path.splitext(path)
    if ext.lower() in [".jpg", ".jpeg"]:
        return url
    jpg_path = f"{root}.jpg"
    try:
        with Image.open(path) as img:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
                img = bg
            else:
                img = img.convert("RGB")
            img.save(jpg_path, "JPEG", quality=quality, optimize=True)
        try:
            root = ASSETS_DIR if os.path.commonpath([os.path.abspath(ASSETS_DIR), os.path.abspath(jpg_path)]) == os.path.abspath(ASSETS_DIR) else OUTPUT_DIR
        except ValueError:
            root = OUTPUT_DIR
        rel = os.path.relpath(jpg_path, root).replace("\\", "/")
        prefix = "/assets" if root == ASSETS_DIR else "/output"
        return f"{prefix}/{rel}"
    except Exception as e:
        print(f"转换 JPG 失败: {e}")
        return url

def reference_to_data_url(ref, max_size=None):
    """把本地输出文件转为 data URL（base64）。max_size 限制最长边像素，避免 payload 过大。"""
    path = output_file_from_url(ref.get("url", ""))
    if not path:
        return ref.get("url", "")
    if max_size:
        try:
            with Image.open(path) as img:
                img.load()
                w, h = img.size
                if max(w, h) > max_size:
                    img.thumbnail((max_size, max_size), Image.LANCZOS)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                buf = BytesIO()
                fmt = "PNG" if img.mode == "RGBA" else "JPEG"
                img.save(buf, format=fmt, quality=88 if fmt == "JPEG" else None)
                encoded = base64.b64encode(buf.getvalue()).decode("ascii")
                mime = "image/png" if fmt == "PNG" else "image/jpeg"
                return f"data:{mime};base64,{encoded}"
        except Exception as e:
            print(f"reference resize failed, fallback to raw: {e}")
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{content_type_for_path(path)};base64,{encoded}"

def compress_data_url_image(value, max_size=1536, jpeg_quality=88):
    if not isinstance(value, str) or not value.startswith("data:image/") or ";base64," not in value:
        return value
    header, encoded = value.split(";base64,", 1)
    try:
        raw = base64.b64decode(encoded)
        with Image.open(BytesIO(raw)) as img:
            img.load()
            if max_size and max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.LANCZOS)
            has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
            if has_alpha:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                fmt, mime = "PNG", "image/png"
            else:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                fmt, mime = "JPEG", "image/jpeg"
            buf = BytesIO()
            if fmt == "JPEG":
                img.save(buf, format=fmt, quality=jpeg_quality, optimize=True)
            else:
                img.save(buf, format=fmt, optimize=True)
            return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
    except Exception as e:
        print(f"data url image compress failed, fallback to raw: {e}")
        return value

def modelscope_image_url(value, max_size=1536):
    if not value:
        return value
    if isinstance(value, str) and (value.startswith("/output/") or value.startswith("/assets/")):
        return reference_to_data_url({"url": value}, max_size=max_size)
    if isinstance(value, str) and value.startswith("data:image/"):
        return compress_data_url_image(value, max_size=max_size)
    return value

def valid_video_image_input(value: str) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    return (
        value.startswith("http://") or
        value.startswith("https://") or
        value.startswith("asset://") or
        (value.startswith("data:image/") and ";base64," in value)
    )

def valid_apimart_video_image_input(value: str) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    return value.startswith("http://") or value.startswith("https://") or value.startswith("asset://")

def is_apimart_veo31_model(model: str) -> bool:
    return str(model or "").strip().lower().startswith("veo3.1")

def apimart_veo31_model(model: str) -> str:
    value = str(model or "").strip().lower()
    aliases = {
        "veo3.1": "veo3.1-fast",
        "veo3.1-pro": "veo3.1-quality",
        "veo3.1-preview": "veo3.1-fast",
    }
    value = aliases.get(value, value or "veo3.1-fast")
    allowed = {"veo3.1-fast", "veo3.1-quality", "veo3.1-lite"}
    return value if value in allowed else "veo3.1-fast"

def apimart_veo31_aspect(aspect: str) -> str:
    value = str(aspect or "16:9").strip()
    return value if value in {"16:9", "9:16"} else "16:9"

def apimart_veo31_resolution(resolution: str) -> str:
    value = str(resolution or "").strip().lower()
    aliases = {"": "720p", "auto": "720p", "480p": "720p", "780p": "720p", "1080": "1080p", "4k": "4k"}
    value = aliases.get(value, value)
    return value if value in {"720p", "1080p", "4k"} else "720p"

def apimart_upload_file_payload(path: str):
    """Return (filename, bytes, content_type), keeping APIMart VEO images under the documented 10MB limit."""
    max_bytes = 9_500_000
    size = os.path.getsize(path)
    if size <= max_bytes:
        with open(path, "rb") as fh:
            return os.path.basename(path), fh.read(), content_type_for_path(path)
    with Image.open(path) as img:
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        quality = 92
        while quality >= 62:
            buf = BytesIO()
            bg.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                name = os.path.splitext(os.path.basename(path))[0] + ".jpg"
                return name, data, "image/jpeg"
            quality -= 8
    raise ValueError("图片超过 10MB，且压缩后仍无法满足 VEO3.1 图片限制")

def invalid_video_image_preview(value: str) -> str:
    text = str(value or "")
    if text.startswith("data:"):
        return text.split(";base64,", 1)[0] + ";base64,..."
    return text[:120]

def extract_apimart_asset_url(payload):
    if isinstance(payload, list):
        for item in payload:
            found = extract_apimart_asset_url(item)
            if found:
                return found
        return ""
    if not isinstance(payload, dict):
        return ""
    url_keys = ("url", "asset_url", "assetUrl", "uri", "file_url", "fileUrl")
    for key in url_keys:
        value = str(payload.get(key) or "").strip()
        if valid_apimart_video_image_input(value):
            return value
    id_keys = ("asset_id", "assetId", "file_id", "fileId", "id")
    for key in id_keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value if value.startswith("asset://") else f"asset://{value}"
    for key in ("data", "file", "asset", "result"):
        found = extract_apimart_asset_url(payload.get(key))
        if found:
            return found
    return ""

def apimart_upload_payload_from_bytes(data: bytes, mime: str, name_hint: str = "image"):
    """把内存中的图片字节按 APIMart 的 10MB 限制压缩为可上传 payload。"""
    max_bytes = 9_500_000
    ext = mimetypes.guess_extension(mime or "image/png") or ".png"
    if len(data) <= max_bytes and (mime or "").lower() in ("image/png", "image/jpeg", "image/webp"):
        return f"{name_hint}{ext}", data, (mime or "image/png")
    with Image.open(BytesIO(data)) as img:
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        if has_alpha:
            base = img.convert("RGBA")
            bg = Image.new("RGB", base.size, (255, 255, 255))
            bg.paste(base, mask=base.split()[-1])
            target = bg
        else:
            target = img.convert("RGB")
        quality = 92
        while quality >= 62:
            buf = BytesIO()
            target.save(buf, format="JPEG", quality=quality, optimize=True)
            payload = buf.getvalue()
            if len(payload) <= max_bytes:
                return f"{name_hint}.jpg", payload, "image/jpeg"
            quality -= 8
    raise ValueError("data URL 图片超过 10MB，且压缩后仍无法满足 APIMart 限制")

async def upload_image_for_apimart(client, provider, ref_url: str) -> str:
    """把本地图片转成上游可接受的输入。
    按 APIMart 文档上传到 /v1/uploads/images，拿到可用于生成接口的 http/https URL。
    绝不把 /output/* 或 /assets/* 这类本地路径直接传给上游。
    返回上游可用 URL；返回值以 "ERR:" 开头表示具体失败原因（供前端展示）。"""
    ref_url = str(ref_url or "").strip()
    if not ref_url:
        return "ERR:空地址"
    # 已经是网络 URL 或 asset:// → 直接可用，无需上传
    if ref_url.startswith("http://") or ref_url.startswith("https://") or ref_url.startswith("asset://"):
        return ref_url
    base_url = video_api_root(provider)
    upload_url = f"{base_url}/v1/uploads/images"
    # data URL: 解码后直接上传到 APIMart
    if ref_url.startswith("data:"):
        try:
            if ";base64," not in ref_url:
                return "ERR:不支持的 data URL（缺少 base64 段）"
            header, encoded = ref_url.split(";base64,", 1)
            mime = header.split(":", 1)[1].split(";", 1)[0] if ":" in header else "image/png"
            raw = base64.b64decode(encoded)
            filename, content, ct = apimart_upload_payload_from_bytes(raw, mime, name_hint="canvas_image")
            files = {"file": (filename, content, ct)}
            resp = await client.post(upload_url, headers=api_headers(json_body=False, provider=provider), files=files, timeout=60)
            if resp.status_code in (200, 201):
                rj = resp.json()
                url = extract_apimart_asset_url(rj)
                if valid_apimart_video_image_input(url):
                    return url
                print(f"APIMart 上传 data URL 返回中未找到可用 asset/url: {str(rj)[:300]}")
                return "ERR:APIMart 上传响应未包含可用 URL"
            print(f"APIMart 上传 data URL 失败 ({resp.status_code}): {resp.text[:300]}")
            return f"ERR:APIMart 上传失败({resp.status_code})"
        except ValueError as e:
            return f"ERR:{e}"
        except Exception as e:
            print(f"APIMart 上传 data URL 异常: {e}")
            return f"ERR:上传异常 {e}"
    # 本地 /output/ 或 /assets/ 路径：先确认文件存在再上传
    if ref_url.startswith("/output/") or ref_url.startswith("/assets/"):
        path = output_file_from_url(ref_url)
        if not path:
            print(f"APIMart 上传跳过：本地文件不存在 {ref_url}")
            return "ERR:本地文件不存在或已被删除"
        try:
            filename, content, ct = apimart_upload_file_payload(path)
            files = {"file": (filename, content, ct)}
            resp = await client.post(upload_url, headers=api_headers(json_body=False, provider=provider), files=files, timeout=60)
            if resp.status_code in (200, 201):
                rj = resp.json()
                url = extract_apimart_asset_url(rj)
                if valid_apimart_video_image_input(url):
                    return url
                print(f"APIMart 文件上传返回中未找到可用 asset/url: {str(rj)[:300]}")
                return "ERR:APIMart 上传响应未包含可用 URL"
            print(f"APIMart 文件上传失败 ({resp.status_code}): {resp.text[:300]}")
            return f"ERR:APIMart 上传失败({resp.status_code})"
        except ValueError as e:
            return f"ERR:{e}"
        except Exception as e:
            print(f"APIMart 文件上传异常: {e}")
            return f"ERR:上传异常 {e}"
    return "ERR:不支持的图片来源（仅支持 http/https/asset/data 或本地 /output/ /assets/ 路径）"

async def save_ai_image_to_output(image_data, prefix="online_", category="output"):
    filename = f"{prefix}{uuid.uuid4().hex[:10]}.png"
    path = output_path_for(filename, category)
    if image_data["type"] == "b64":
        mime_type = str(image_data.get("mime_type") or "").lower()
        if "jpeg" in mime_type or "jpg" in mime_type:
            filename = filename[:-4] + ".jpg"
            path = output_path_for(filename, category)
        elif "webp" in mime_type:
            filename = filename[:-4] + ".webp"
            path = output_path_for(filename, category)
        with open(path, "wb") as f:
            f.write(base64.b64decode(image_data["value"]))
        return output_url_for(filename, category)
    value = image_data["value"]
    if value.startswith("/output/") or value.startswith("/assets/"):
        return value
    try:
        timeout = httpx.Timeout(connect=20.0, read=300.0, write=60.0, pool=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(value)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "jpeg" in content_type or "jpg" in content_type:
                filename = filename[:-4] + ".jpg"
                path = output_path_for(filename, category)
            elif "webp" in content_type:
                filename = filename[:-4] + ".webp"
                path = output_path_for(filename, category)
            with open(path, "wb") as f:
                f.write(response.content)
            return output_url_for(filename, category)
    except Exception as e:
        print(f"保存上游图片失败: {e}")
        return value

async def save_remote_video_to_output(url, prefix="video_", category="output"):
    if not url:
        return ""
    if url.startswith("/output/") or url.startswith("/assets/"):
        return url
    filename = f"{prefix}{uuid.uuid4().hex[:10]}.mp4"
    path = output_path_for(filename, category)
    try:
        async with httpx.AsyncClient(timeout=VIDEO_POLL_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            clean_path = urllib.parse.urlparse(url).path
            ext = os.path.splitext(clean_path)[1].lower()
            if ext in {".mp4", ".webm", ".mov"}:
                filename = filename[:-4] + ext
                path = output_path_for(filename, category)
            elif "webm" in content_type:
                filename = filename[:-4] + ".webm"
                path = output_path_for(filename, category)
            elif "quicktime" in content_type or "mov" in content_type:
                filename = filename[:-4] + ".mov"
                path = output_path_for(filename, category)
            with open(path, "wb") as f:
                f.write(response.content)
            return output_url_for(filename, category)
    except Exception as e:
        print(f"保存上游视频失败: {e}")
        return url

def parse_size_pair(size):
    match = re.fullmatch(r"\s*(\d+)\s*[xX*]\s*(\d+)\s*", str(size or ""))
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))

GPT_IMAGE2_MAX_EDGE = 3840
GPT_IMAGE2_MAX_PIXELS = 8_294_400
GPT_IMAGE2_MIN_PIXELS = 655_360

def is_gpt_image_2_model(model):
    return str(model or "").strip().lower() == "gpt-image-2"

def normalize_gpt_image_2_size(size):
    width, height = parse_size_pair(size)
    if not width or not height:
        return size or "auto"
    if width == height and (width > 2048 or width * height > 4_194_304):
        return "3840x2160"
    ratio = width / height
    if ratio > 3:
        width = height * 3
    elif ratio < 1 / 3:
        height = width * 3
    scale = min(
        1.0,
        GPT_IMAGE2_MAX_EDGE / max(width, height),
        (GPT_IMAGE2_MAX_PIXELS / max(1, width * height)) ** 0.5,
    )
    width = max(16, int((width * scale) // 16) * 16)
    height = max(16, int((height * scale) // 16) * 16)
    if width * height < GPT_IMAGE2_MIN_PIXELS:
        grow = (GPT_IMAGE2_MIN_PIXELS / max(1, width * height)) ** 0.5
        width = int((width * grow + 15) // 16) * 16
        height = int((height * grow + 15) // 16) * 16
    return f"{width}x{height}"

def apimart_size_resolution(size):
    width, height = parse_size_pair(size)
    if not width or not height:
        raw = str(size or "").strip().lower()
        if raw in {"1k", "2k", "4k"}:
            return "1:1", raw
        if re.fullmatch(r"(auto|\d+\s*:\s*\d+)", raw):
            return raw.replace(" ", ""), "1k"
        return "1:1", "1k"
    long_edge = max(width, height)
    pixels = width * height
    if long_edge >= 3000 or pixels > 4_500_000:
        resolution = "4k"
    elif long_edge >= 1800 or pixels > 1_800_000:
        resolution = "2k"
    else:
        resolution = "1k"
    common = [
        (1, 1, "1:1"), (3, 2, "3:2"), (2, 3, "2:3"), (4, 3, "4:3"), (3, 4, "3:4"),
        (5, 4, "5:4"), (4, 5, "4:5"), (16, 9, "16:9"), (9, 16, "9:16"),
        (2, 1, "2:1"), (1, 2, "1:2"), (3, 1, "3:1"), (1, 3, "1:3"),
        (21, 9, "21:9"), (9, 21, "9:21"),
    ]
    ratio = width / height
    best = min(common, key=lambda item: abs(ratio - item[0] / item[1]))
    return best[2], resolution

VOLCENGINE_MIN_PIXELS = 3_686_400
VOLCENGINE_MIN_EDGE = 1536
VOLCENGINE_MAX_EDGE = 4096
VOLCENGINE_RATIO_CHOICES = [
    (1, 1, "1:1"),
    (4, 3, "4:3"),
    (3, 4, "3:4"),
    (16, 9, "16:9"),
    (9, 16, "9:16"),
    (21, 9, "21:9"),
    (9, 21, "9:21"),
    (3, 2, "3:2"),
    (2, 3, "2:3"),
    (5, 4, "5:4"),
    (4, 5, "4:5"),
]

def is_volcengine_seedream_model(model):
    value = str(model or "").strip().lower()
    return "seedream" in value or "doubao-seedream" in value

def normalize_volcengine_size(size, model=""):
    width, height = parse_size_pair(size)
    raw = str(size or "").strip().lower()
    if not width or not height:
        if raw == "4k":
            return "4096x4096"
        if raw == "2k":
            return "2048x2048"
        return "2048x2048" if is_volcengine_seedream_model(model) else (size or "1024x1024")
    if not is_volcengine_seedream_model(model):
        return f"{width}x{height}"
    ratio = width / max(1, height)
    best_ratio = min(VOLCENGINE_RATIO_CHOICES, key=lambda item: abs(ratio - item[0] / item[1]))
    rw, rh = best_ratio[0], best_ratio[1]
    scale = max(
        (VOLCENGINE_MIN_PIXELS / max(1, rw * rh)) ** 0.5,
        VOLCENGINE_MIN_EDGE / max(1, min(rw, rh)),
    )
    target_w = rw * scale
    target_h = rh * scale
    cap = min(1.0, VOLCENGINE_MAX_EDGE / max(target_w, target_h))
    target_w *= cap
    target_h *= cap
    snapped_w = max(64, int(target_w // 16) * 16)
    snapped_h = max(64, int(target_h // 16) * 16)
    while snapped_w * snapped_h < VOLCENGINE_MIN_PIXELS:
        if snapped_w <= snapped_h:
            snapped_w += 16
        else:
            snapped_h += 16
        if max(snapped_w, snapped_h) > VOLCENGINE_MAX_EDGE:
            break
    return f"{snapped_w}x{snapped_h}"

def friendly_image_error_detail(text, size="", model=""):
    text = str(text or "")
    lower_text = text.lower()
    m = re.search(r"longest edge must be less than or equal to (\d+)", text)
    if m:
        limit = m.group(1)
        return f"该模型不支持当前分辨率：最长边超过 {limit}px。请把图片分辨率调低（例如换到 2K 或更小），或更换支持高分辨率的模型。"
    if "image size must be at least" in lower_text:
        pixel_match = re.search(r"at least (\d+) pixels", lower_text)
        pixels = pixel_match.group(1) if pixel_match else "3686400"
        return f"该模型要求更高分辨率，当前尺寸 {size or '过小'} 不满足最低像素要求（至少 {pixels} 像素）。火山 Seedream 5.0 建议从 2K 起步。"
    if "invalid size" in lower_text or "invalid_value" in lower_text:
        return f"该模型不支持当前尺寸：{size or '未指定'}。请尝试更换分辨率或模型。"
    if "inputtextsensitivecontentdetected" in lower_text or "policyviolation" in lower_text or "copyright restrictions" in lower_text:
        return "上游内容安全拦截了这段提示词，原因偏向版权/敏感内容限制。请改写提示词，避免直接出现具体 IP、角色名、品牌名、影视/动漫作品名，改成风格特征描述再试。"
    if "rate limit" in lower_text or "429" in lower_text:
        return "请求过于频繁，已被上游限流，请稍后再试。"
    if "unauthorized" in lower_text or "401" in lower_text:
        return "API Key 无效或已过期，请到「API 设置」检查 Key。"
    if "model_not_found" in lower_text or "channel not found" in lower_text:
        return f"上游平台找不到模型「{model}」可用通道。可能该模型未在此账号开通，请换一个已开通的模型。"
    return ""

def parse_error_payload_text(text):
    body = str(text or "").strip()
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}

def friendly_chat_error_detail(text, model="", provider=None):
    raw_text = str(text or "")
    lower_text = raw_text.lower()
    payload = parse_error_payload_text(raw_text)
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = str(error.get("code") or payload.get("code") or "").strip()
    message = str(error.get("message") or payload.get("message") or "").strip()
    code_lc = code.lower()
    message_lc = message.lower()
    model_name = str(model or "").strip()

    if is_volcengine_provider(provider):
        if code_lc in {"invalidendpointormodel.notfound", "invalidendpointormodel.modelidaccessdisabled"}:
            provider_name = provider.get("name") or provider.get("id") or "火山方舟"
            return (
                f"{provider_name} 当前不接受模型名「{model_name or '未指定'}」直接调用聊天接口，"
                f"请在火山方舟控制台创建并使用推理接入点 ID（形如 `ep-...`）作为聊天模型。\n\n"
                f"补充说明：`/api/v3/models` 能拉到公开模型列表，但你的账号未必能直接用这些模型名调用 `/chat/completions`；"
                f"很多账号只允许传自己已开通的 `ep-...` 接入点。"
            )
        if "does not exist or you do not have access to it" in message_lc:
            return (
                f"火山方舟找不到或无权访问聊天模型「{model_name or '未指定'}」。"
                f"如果你现在填的是模型名，请改成已开通的推理接入点 ID（`ep-...`）；"
                f"如果已经是 `ep-...`，请检查这个接入点是否绑定了聊天模型、区域是否正确、以及账号是否有调用权限。"
            )
    if "unauthorized" in lower_text or "401" in lower_text:
        return "API Key 无效或已过期，请到「API 设置」检查 Key。"
    if "rate limit" in lower_text or "429" in lower_text:
        return "请求过于频繁，已被上游限流，请稍后再试。"
    return ""

async def generate_modelscope_provider_image(prompt, size, model, reference_images=None, provider=None):
    clean_token = MODELSCOPE_API_KEY.strip()
    if not clean_token:
        raise HTTPException(status_code=400, detail="未配置 ModelScope API Key，请在 API 设置中填写。")
    width, height = parse_size_pair(size)
    refs = []
    for ref in (reference_images or [])[:4]:
        if not ref.get("url"):
            continue
        # 把参考图压缩为 data URL，避免 base64 payload 过大导致 MS 内部任务失败
        refs.append(modelscope_image_url(ref.get("url", ""), max_size=1536))
    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true",
    }
    payload = {
        "model": selected_model(model, "Tongyi-MAI/Z-Image-Turbo"),
        "prompt": prompt.strip(),
    }
    if width and height:
        payload["width"] = width
        payload["height"] = height
        payload["size"] = f"{width}x{height}"
    if refs:
        payload["image_url"] = refs

    base_root = ((provider or {}).get("base_url") or MODELSCOPE_CHAT_BASE_URL).rstrip("/")
    api_root = base_root if base_root.endswith("/v1") else f"{base_root}/v1"
    async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT) as client:
        submit_res = await client.post(f"{api_root}/images/generations", headers=headers, json=payload)
        submit_res.raise_for_status()
        raw = submit_res.json()
        task_id = raw.get("task_id")
        if not task_id:
            try:
                return extract_image(raw), raw
            except HTTPException:
                raise HTTPException(status_code=502, detail=f"ModelScope 未返回 task_id：{raw}")

        deadline = time.monotonic() + AI_REQUEST_TIMEOUT
        last_payload = raw
        while time.monotonic() < deadline:
            await asyncio.sleep(IMAGE_POLL_INTERVAL)
            result = await client.get(
                f"{api_root}/tasks/{task_id}",
                headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
            )
            result.raise_for_status()
            data = result.json()
            last_payload = data
            status = str(data.get("task_status") or "").upper()
            if status == "SUCCEED":
                images = data.get("output_images") or []
                if not images:
                    raise HTTPException(status_code=502, detail=f"ModelScope 成功但没有返回图片：{data}")
                return {"type": "url", "value": images[0]}, data
            if status in {"FAILED", "FAIL", "ERROR", "CANCELED", "CANCELLED", "TIMEOUT", "REVOKED"}:
                detail = data.get("error_info") or data.get("message") or data.get("detail") or str(data)
                raise HTTPException(status_code=502, detail=f"ModelScope 任务失败：{detail}")
        raise HTTPException(status_code=504, detail=f"ModelScope 生图任务超时：{last_payload}")

def gemini_model_name(model):
    value = selected_model(model, "gemini-3-pro-image-preview").strip()
    return value[len("models/"):] if value.startswith("models/") else value

def gemini_endpoint_url(provider, model):
    model_name = urllib.parse.quote(gemini_model_name(model), safe="")
    return provider_endpoint_url(provider, "image_generation_endpoint", f"/v1beta/models/{model_name}:generateContent")

def gemini_image_config(size):
    width, height = parse_size_pair(size)
    if not width or not height:
        raw = str(size or "").strip().upper()
        if raw in {"1K", "2K", "4K"}:
            return {"aspectRatio": "1:1", "imageSize": raw}
        if re.fullmatch(r"\d+\s*:\s*\d+", raw):
            return {"aspectRatio": raw.replace(" ", ""), "imageSize": "1K"}
        return {"aspectRatio": "1:1", "imageSize": "2K"}
    aspect_ratio, resolution = apimart_size_resolution(size)
    return {"aspectRatio": aspect_ratio, "imageSize": resolution.upper()}

def gemini_reference_part(ref):
    value = reference_to_data_url(ref, max_size=1536)
    if not value:
        return None
    if isinstance(value, str) and value.startswith("data:image/") and ";base64," in value:
        header, encoded = value.split(";base64,", 1)
        mime_type = header.replace("data:", "", 1) or "image/png"
        return {"inlineData": {"mimeType": mime_type, "data": encoded}}
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return {"fileData": {"mimeType": "image/png", "fileUri": value}}
    return None

async def generate_gemini_provider_image(prompt, size, model, reference_images=None, provider=None):
    model_name = gemini_model_name(model)
    endpoint = gemini_endpoint_url(provider, model_name)
    parts = [{"text": prompt.strip()}]
    for ref in (reference_images or [])[:16]:
        part = gemini_reference_part(ref)
        if part:
            parts.append(part)
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": gemini_image_config(size),
        },
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=1800.0, write=120.0, pool=20.0)) as client:
        response = await client.post(endpoint, headers=api_headers(provider=provider), json=body)
        response.raise_for_status()
        raw = response.json()
        return extract_image(raw), raw

def volcengine_endpoint_url(provider):
    return provider_endpoint_url(provider, "image_generation_endpoint", "/api/v3/images/generations")

def volcengine_image_payload(ref):
    value = reference_to_data_url(ref, max_size=1536)
    if not value:
        return None
    return value

async def generate_volcengine_provider_image(prompt, size, model, reference_images=None, provider=None):
    endpoint = volcengine_endpoint_url(provider)
    size = normalize_volcengine_size(size, model)
    body = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
    }
    images = [volcengine_image_payload(ref) for ref in (reference_images or [])[:10]]
    images = [value for value in images if value]
    if images:
        body["image"] = images
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=1800.0, write=120.0, pool=20.0)) as client:
        response = await client.post(endpoint, headers=api_headers(provider=provider), json=body)
        response.raise_for_status()
        raw = response.json()
        return extract_image(raw), raw

def runninghub_api_headers(provider):
    api_key = runninghub_api_key(provider)
    if not api_key:
        raise HTTPException(status_code=400, detail="未配置 RunningHub API Key，请在 API 设置中填写。")
    return {"Authorization": bearer_auth_value(api_key), "Accept": "application/json", "Content-Type": "application/json"}

def runninghub_provider():
    return get_api_provider_exact("runninghub")

def runninghub_api_key(provider=None, use_wallet=False, prefer_wallet=False):
    provider = provider or runninghub_provider()
    free_key = os.getenv(provider_key_env(provider["id"]), "")
    wallet_key = os.getenv(runninghub_wallet_key_env(), "")
    api_key = wallet_key if (use_wallet or prefer_wallet) and wallet_key else free_key
    if not api_key:
        raise HTTPException(status_code=400, detail="未配置 RunningHub API Key，请在 RH 设置中填写。")
    return api_key

def runninghub_app_headers(json_body=True, use_wallet=False):
    headers = {"Host": "www.runninghub.cn"}
    provider = runninghub_provider()
    if provider:
        free_key = os.getenv(provider_key_env(provider["id"]), "")
        wallet_key = os.getenv(runninghub_wallet_key_env(), "")
        api_key = wallet_key if use_wallet and wallet_key else free_key
        if api_key:
            headers["Authorization"] = bearer_auth_value(api_key)
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers

def runninghub_local_asset_path(url):
    text = str(url or "").strip()
    if not text:
        return None
    if text.startswith("/assets/input/") or text.startswith("/input/"):
        clean = urllib.parse.unquote(text.split("?", 1)[0]).replace("\\", "/")
        rel = clean[len("/assets/input/"):] if clean.startswith("/assets/input/") else clean[len("/input/"):]
        root = OUTPUT_INPUT_DIR
    elif text.startswith("/assets/output/"):
        clean = urllib.parse.unquote(text.split("?", 1)[0]).replace("\\", "/")
        rel = clean[len("/assets/output/"):]
        root = OUTPUT_OUTPUT_DIR
    elif text.startswith("/output/") or text.startswith("/assets/"):
        return output_file_from_url(text)
    else:
        return None
    rel = rel.lstrip("/")
    if not rel:
        return None
    path = os.path.abspath(os.path.join(root, rel))
    root_abs = os.path.abspath(root)
    if os.path.commonpath([root_abs, path]) != root_abs or not os.path.exists(path):
        return None
    return path

def runninghub_output_ext(remote, content_type=""):
    tail = str(remote or "").split("?", 1)[0].split("#", 1)[0]
    ext = os.path.splitext(tail)[1].lower().strip(".")
    allowed = {"png","jpg","jpeg","webp","gif","bmp","mp4","webm","mov","m4v","mkv","mp3","wav","ogg","m4a","flac","aac"}
    if ext in allowed:
        return ext
    ct = str(content_type or "").lower()
    if "mp4" in ct:
        return "mp4"
    if "webm" in ct:
        return "webm"
    if "quicktime" in ct:
        return "mov"
    if "mpeg" in ct:
        return "mp3"
    if "wav" in ct:
        return "wav"
    if "ogg" in ct:
        return "ogg"
    if "webp" in ct:
        return "webp"
    if "jpeg" in ct:
        return "jpg"
    return "png"

def runninghub_extract_outputs(data):
    arr = []
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        for key in ("outputs", "results", "files", "data"):
            value = data.get(key)
            if isinstance(value, list):
                arr = value
                break
        if not arr and (data.get("fileUrl") or data.get("url")):
            arr = [data]
    outputs = []
    for item in arr:
        if isinstance(item, str):
            outputs.append(item)
        elif isinstance(item, dict):
            url = item.get("fileUrl") or item.get("file_url") or item.get("url") or item.get("downloadUrl") or item.get("download_url")
            if isinstance(url, list):
                outputs.extend([str(u) for u in url if u])
            elif url:
                outputs.append(str(url))
    return outputs

async def runninghub_store_remote_output(client, remote):
    if not str(remote or "").startswith(("http://", "https://")):
        return remote
    response = await client.get(remote, follow_redirects=True)
    if not response.is_success:
        return remote
    ext = runninghub_output_ext(remote, response.headers.get("content-type", ""))
    filename = f"rh_{uuid.uuid4().hex[:12]}.{ext}"
    path = output_path_for(filename, "output")
    with open(path, "wb") as f:
        f.write(response.content)
    return output_url_for(filename, "output")

def runninghub_fail_reason(raw):
    data = raw.get("data") if isinstance(raw, dict) else None
    values = []
    if isinstance(data, dict):
        values.extend([data.get("failedReason"), data.get("failReason"), data.get("message"), data.get("error")])
    if isinstance(raw, dict):
        values.extend([raw.get("msg"), raw.get("message"), raw.get("error")])
    for value in values:
        if not value:
            continue
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("exception_message") or value.get("message") or json.dumps(value, ensure_ascii=False)
        return str(value)
    return ""

def runninghub_infer_workflow_field_type(field_name, field_value):
    key = f"{field_name or ''} {field_value or ''}".lower()
    if re.search(r"\b(image|img|mask|photo|picture)\b", key) or re.search(r"\.(png|jpe?g|webp|gif|bmp)(\?|$)", key, re.I):
        return "IMAGE"
    if re.search(r"\b(video|movie|mp4)\b", key) or re.search(r"\.(mp4|webm|mov|m4v|mkv)(\?|$)", key, re.I):
        return "VIDEO"
    if re.search(r"\b(audio|sound|music|voice)\b", key) or re.search(r"\.(mp3|wav|ogg|m4a|flac|aac)(\?|$)", key, re.I):
        return "AUDIO"
    text = str(field_value or "").strip()
    if text.lower() in {"true", "false"}:
        return "BOOLEAN"
    try:
        if text:
            float(text)
            return "NUMBER"
    except Exception:
        pass
    return "TEXT"

def runninghub_is_workflow_link_value(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
    )

def runninghub_workflow_node_info_list(workflow_json):
    result = []
    if not isinstance(workflow_json, dict):
        return result
    for node_id, node_content in workflow_json.items():
        inputs = node_content.get("inputs") if isinstance(node_content, dict) else None
        if not isinstance(inputs, dict):
            continue
        for field_name, raw_value in inputs.items():
            if runninghub_is_workflow_link_value(raw_value):
                continue
            if isinstance(raw_value, (dict, list)):
                field_value = json.dumps(raw_value, ensure_ascii=False)
            elif raw_value is None:
                field_value = ""
            else:
                field_value = str(raw_value)
            result.append({
                "nodeId": str(node_id),
                "fieldName": str(field_name),
                "fieldValue": field_value,
                "fieldType": runninghub_infer_workflow_field_type(field_name, field_value),
                "source": "workflow",
            })
    return result

def runninghub_task_endpoint(provider, model):
    model_path = str(model or "").strip().strip("/")
    if not model_path:
        model_path = RUNNINGHUB_DEFAULT_IMAGE_MODELS[0]
    if model_path.startswith("/openapi/"):
        return runninghub_endpoint_url(provider, model_path)
    if model_path.startswith("openapi/"):
        return runninghub_endpoint_url(provider, f"/{model_path}")
    return runninghub_endpoint_url(provider, f"/openapi/v2/{model_path}")

def runninghub_query_status(raw):
    if not isinstance(raw, dict):
        return ""
    values = [
        raw.get("status"),
        raw.get("state"),
        raw.get("taskStatus"),
        raw.get("task_status"),
    ]
    data = raw.get("data")
    if isinstance(data, dict):
        values.extend([data.get("status"), data.get("state"), data.get("taskStatus"), data.get("task_status")])
    for value in values:
        if value is not None:
            return str(value).lower()
    return ""

def runninghub_extract_task_id(raw):
    if not isinstance(raw, dict):
        return ""
    for key in ("taskId", "task_id", "id"):
        if raw.get(key):
            return str(raw[key])
    data = raw.get("data")
    if isinstance(data, dict):
        for key in ("taskId", "task_id", "id"):
            if data.get(key):
                return str(data[key])
    return ""

def runninghub_extract_image(raw):
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="RunningHub 返回格式不是 JSON 对象")
    containers = [raw]
    data = raw.get("data")
    if isinstance(data, dict):
        containers.append(data)
    for container in containers:
        results = container.get("results") or container.get("result") or container.get("outputs") or container.get("output")
        if isinstance(results, dict):
            results = [results]
        if isinstance(results, list):
            for item in results:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    return {"type": "url", "value": item}
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "url" and item.get("value"):
                    return {"type": "url", "value": item["value"]}
                if item.get("type") == "b64" and item.get("value"):
                    return {"type": "b64", "value": item["value"], "mime_type": item.get("mime_type") or "image/png"}
                url = item.get("url") or item.get("fileUrl") or item.get("file_url") or item.get("download_url") or item.get("imageUrl") or item.get("image_url")
                if isinstance(url, list) and url:
                    url = url[0]
                if isinstance(url, str) and url:
                    return {"type": "url", "value": url}
    return extract_image(raw)

async def runninghub_upload_reference(client, provider, ref):
    path = output_file_from_url(ref.get("url", ""))
    if not path:
        value = ref.get("url", "")
        return value if str(value).startswith(("http://", "https://")) else ""
    upload_url = runninghub_endpoint_url(provider, "/openapi/v2/media/upload/binary")
    api_key = os.getenv(provider_key_env(provider["id"]), "")
    headers = {"Authorization": bearer_auth_value(api_key), "Accept": "application/json"}
    with open(path, "rb") as fh:
        files = {"file": (os.path.basename(path), fh, content_type_for_path(path))}
        response = await client.post(upload_url, headers=headers, files=files, timeout=120)
    response.raise_for_status()
    raw = response.json()
    data = raw.get("data") if isinstance(raw, dict) else None
    candidates = [raw, data] if isinstance(data, dict) else [raw]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        value = item.get("download_url") or item.get("downloadUrl") or item.get("url") or item.get("fileUrl") or item.get("file_url")
        if value:
            return str(value)
    raise HTTPException(status_code=502, detail=f"RunningHub 上传图片未返回 download_url：{raw}")

async def wait_for_runninghub_image_task(client, provider, task_id):
    query_url = runninghub_endpoint_url(provider, "/openapi/v2/query")
    deadline = time.monotonic() + 1800
    last_payload = None
    while time.monotonic() < deadline:
        await asyncio.sleep(2)
        response = await client.post(query_url, headers=runninghub_api_headers(provider), json={"taskId": task_id})
        response.raise_for_status()
        raw = response.json()
        last_payload = raw
        status = runninghub_query_status(raw)
        if status in {"success", "succeeded", "completed", "complete", "finished", "finish", "done", "3"}:
            return raw
        if status in {"failed", "fail", "error", "canceled", "cancelled", "4"}:
            raise HTTPException(status_code=502, detail=f"RunningHub 任务失败：{raw}")
        try:
            return {"data": {"results": [runninghub_extract_image(raw)]}}
        except HTTPException:
            pass
    raise HTTPException(status_code=504, detail=f"RunningHub 生图任务超时：{last_payload}")

async def generate_runninghub_provider_image(prompt, size, model, reference_images=None, provider=None):
    endpoint = runninghub_task_endpoint(provider, model)
    width, height = parse_size_pair(size)
    body = {"prompt": prompt}
    if width and height:
        body.update({"width": width, "height": height})
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=1800.0, write=180.0, pool=20.0)) as client:
        image_urls = []
        for ref in (reference_images or [])[:10]:
            url = await runninghub_upload_reference(client, provider, ref)
            if url:
                image_urls.append(url)
        if image_urls:
            body["imageUrls"] = image_urls
        response = await client.post(endpoint, headers=runninghub_api_headers(provider), json=body)
        response.raise_for_status()
        raw = response.json()
        try:
            return runninghub_extract_image(raw), raw
        except HTTPException:
            task_id = runninghub_extract_task_id(raw)
            if not task_id:
                raise HTTPException(status_code=502, detail=f"RunningHub 未返回 taskId 或图片结果：{raw}")
        result = await wait_for_runninghub_image_task(client, provider, task_id)
        return runninghub_extract_image(result), result

async def generate_ai_image(prompt, size, quality, model, reference_images=None, provider_id="comfly"):
    provider = get_api_provider(provider_id)
    if provider["id"] == "modelscope":
        return await generate_modelscope_provider_image(prompt, size, model, reference_images, provider)
    if is_runninghub_provider(provider):
        return await generate_runninghub_provider_image(prompt, size, model, reference_images, provider)
    if is_gemini_provider(provider):
        return await generate_gemini_provider_image(prompt, size, model, reference_images, provider)
    if is_volcengine_provider(provider):
        return await generate_volcengine_provider_image(prompt, size, model, reference_images, provider)
    is_gpt2 = is_gpt_image_2_model(model)
    is_apimart = is_apimart_provider(provider)
    quality = str(quality or "").strip().lower()
    if quality not in {"low", "medium", "high"}:
        quality = ""
    if is_gpt_image_2_model(model) and not is_apimart:
        size = normalize_gpt_image_2_size(size)
    base_url = (provider.get("base_url") or AI_BASE_URL).rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail=f"{provider.get('name') or provider['id']} 未配置 Base URL")
    gen_url = provider_endpoint_url(provider, "image_generation_endpoint", "/v1/images/generations")
    edit_url = provider_endpoint_url(provider, "image_edit_endpoint", "/v1/images/edits")
    refs = [ref for ref in (reference_images or []) if ref.get("url")]
    mask_refs = [ref for ref in refs if str(ref.get("role") or "").strip().lower() == "mask" or str(ref.get("name") or "").lower().endswith("_mask.png")]
    image_refs = [ref for ref in refs if ref not in mask_refs]
    request_timeout = httpx.Timeout(connect=20.0, read=1800.0, write=120.0, pool=20.0) if (is_gpt2 or is_apimart) else AI_REQUEST_TIMEOUT
    async with httpx.AsyncClient(timeout=request_timeout) as client:
        response = None
        async def post_openai_edits(edit_files=None):
            data = {"model": model, "prompt": prompt, "size": size}
            if quality:
                data["quality"] = quality
            return await client.post(
                edit_url,
                headers=api_headers(json_body=False, provider=provider),
                data=data,
                files=edit_files if edit_files is not None else {},
            )

        if is_apimart:
            apimart_size, resolution = apimart_size_resolution(size)
            # APIMart 的 GPT-Image-2 图生图仍走 /images/generations，
            # 通过 image_urls 传参考图，不使用 OpenAI multipart /images/edits。
            body = {
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": apimart_size,
                "resolution": resolution,
                "official_fallback": False,
            }
            if image_refs:
                body["image_urls"] = [reference_to_data_url(ref, max_size=1536) for ref in image_refs[:16]]
            response = await client.post(gen_url, headers=api_headers(provider=provider), json=body)
        elif is_gpt2 and not image_refs and not mask_refs:
            body = {"model": model, "prompt": prompt, "size": size}
            if quality:
                body["quality"] = quality
            response = await client.post(gen_url, headers=api_headers(provider=provider), json=body)
            if response.status_code >= 400 and images_api_unsupported(response):
                response = await post_openai_edits()
        elif image_refs:
            # 1) OpenAI 协议的图生图/编辑用 multipart 提交到 /images/edits；
            # GPT-Image-2 参考图不能走 /images/generations JSON，否则部分平台会忽略原图或报 Images API unsupported。
            files = []
            opened = []
            edit_failed_status = None
            edit_failed_text = ""
            try:
                for ref in image_refs[:4]:
                    path = output_file_from_url(ref.get("url", ""))
                    if not path:
                        continue
                    fh = open(path, "rb")
                    opened.append(fh)
                    files.append(("image", (os.path.basename(path), fh, content_type_for_path(path))))
                if mask_refs:
                    mask_path = output_file_from_url(mask_refs[0].get("url", ""))
                    if mask_path:
                        fh = open(mask_path, "rb")
                        opened.append(fh)
                        files.append(("mask", (os.path.basename(mask_path), fh, content_type_for_path(mask_path))))
                try:
                    response = await post_openai_edits(files)
                    if response.status_code >= 400:
                        edit_failed_status = response.status_code
                        edit_failed_text = response.text[:500]
                        response = None
                except httpx.HTTPError as e:
                    edit_failed_status = -1
                    edit_failed_text = str(e)
                    response = None
            finally:
                for fh in opened:
                    fh.close()
            # 2) edits 失败 → 非 GPT-Image-2 可回退到 /images/generations + JSON image:[urls/base64]（grsai 风格）
            if response is None:
                if is_gpt2:
                    raise HTTPException(
                        status_code=502,
                        detail=f"GPT-Image-2 编辑接口 /images/edits 调用失败：{edit_failed_text[:300] or edit_failed_status}。已停止自动重试，避免上游可能已扣费后再次请求。"
                    )
                print(f"/images/edits failed ({edit_failed_status}): {edit_failed_text[:200]} → 回退到 /images/generations + image:[] JSON")
                image_payload = [reference_to_data_url(ref, max_size=1536) for ref in image_refs[:4]]
                body = {
                    "model": model, "prompt": prompt, "size": size,
                    "response_format": "url", "n": 1,
                    "image": image_payload,
                }
                if quality:
                    body["quality"] = quality
                response = await client.post(gen_url, headers=api_headers(provider=provider), json=body)
                if response.status_code >= 400 and images_api_unsupported(response):
                    raise HTTPException(
                        status_code=502,
                        detail=f"编辑接口 /images/edits 调用失败，且该平台不支持 /images/generations：{edit_failed_text[:300] or edit_failed_status}"
                    )
        else:
            body = {"model": model, "prompt": prompt, "size": size, "response_format": "url", "n": 1}
            if quality:
                body["quality"] = quality
            response = await client.post(
                gen_url,
                headers=api_headers(provider=provider),
                json=body,
            )
            if response.status_code >= 400 and images_api_unsupported(response):
                response = await post_openai_edits()
        response.raise_for_status()
        raw = response.json()
        try:
            return extract_image(raw), raw
        except HTTPException:
            task_id = extract_task_id(raw)
            if not task_id:
                raise
        task_result = await wait_for_image_task(client, task_id, provider)
        return extract_image(task_result), task_result

def upstream_message_from_record(item):
    role = item.get("role")
    if role not in {"user", "assistant"} or item.get("type") == "image":
        return None
    refs = item.get("attachments") or []
    if refs and role == "user":
        content = [{"type": "text", "text": item.get("content", "")}]
        for ref in refs[:4]:
            url = reference_to_data_url(ref)
            if url:
                content.append({"type": "image_url", "image_url": {"url": url}})
        return {"role": role, "content": content}
    return {"role": role, "content": item.get("content", "")}

# --- 路由接口 ---

@app.get("/login")
async def login_page(request: Request):
    existing = authenticate_token(request_session_token(request))
    if existing:
        next_path = str(request.query_params.get("next") or "/").strip()
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/"
        return RedirectResponse(url=next_path, status_code=307)
    return static_html_response("login.html")

@app.post("/api/auth/login")
async def auth_login(payload: LoginRequest, request: Request):
    username = validate_username(payload.username)
    password = validate_password(payload.password)
    row = find_user_by_username(username)
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if bool(int(row["is_disabled"] or 0)):
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
    user = auth_user_public(row)
    token = create_session_for_user(user["id"])
    response = JSONResponse({
        "ok": True,
        "token": token,
        "token_type": "bearer",
        "expires_in": AUTH_TOKEN_TTL_SECONDS,
        "user": user,
    })
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=AUTH_TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    return response

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = request_session_token(request)
    if token:
        revoke_session_token(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return response

@app.get("/api/auth/me")
async def auth_me(request: Request):
    user = getattr(request.state, "current_user", None)
    if not user:
        token = request_session_token(request)
        user = authenticate_token(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {"user": user}

@app.post("/api/auth/users")
async def auth_create_user(payload: UserCreateRequest, request: Request):
    require_admin_user(request)
    user = create_user(payload.username, payload.password, bool(payload.is_admin))
    return {"user": user}

@app.get("/api/auth/users")
async def auth_list_users(request: Request):
    require_admin_user(request)
    return {"users": list_users()}

@app.patch("/api/auth/users/{user_id}")
async def auth_update_user(user_id: int, payload: UserUpdateRequest, request: Request):
    require_admin_user(request)
    desired_disabled = payload.is_disabled if payload.is_disabled is not None else payload.disabled
    user = update_user_admin_state(user_id, payload.is_admin, desired_disabled)
    return {"user": user}

@app.put("/api/auth/users/{user_id}")
async def auth_update_user_put(user_id: int, payload: UserUpdateRequest, request: Request):
    return await auth_update_user(user_id, payload, request)

@app.post("/api/auth/users/{user_id}/reset-password")
async def auth_reset_user_password(user_id: int, payload: UserResetPasswordRequest, request: Request):
    require_admin_user(request)
    user = reset_user_password(user_id, payload.new_password)
    return {"ok": True, "user": user}

@app.post("/api/auth/change-password")
async def auth_change_password(payload: ChangePasswordRequest, request: Request):
    user = require_current_user(request)
    change_own_password(int(user["id"]), payload.old_password, payload.new_password)
    response = JSONResponse({"ok": True, "relogin": True})
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return response

@app.get("/")
async def index():
    # 平台唯一入口：旧壳 XY AI（2026-06-12 决策：浅色项目主页下架，只保留一套画布入口）
    return RedirectResponse(url="/static/index.html", status_code=307)

@app.get("/projects")
async def projects_page():
    return RedirectResponse(url="/static/index.html", status_code=307)

@app.get("/studio")
async def studio_page():
    return static_html_response("index.html")

@app.get("/admin")
async def admin_page():
    return static_html_response("admin-dashboard.html")

@app.get("/admin/users")
async def admin_users_page():
    return static_html_response("admin-users.html")

@app.get("/smart-canvas")
async def smart_canvas_page():
    # 智能画布已下架（2026-06-12）：统一使用经典 xy-canvas，旧链接一律回主入口
    return RedirectResponse(url="/static/index.html", status_code=307)

@app.get("/canvas")
async def canvas_page():
    return static_html_response("canvas.html")

@app.get("/api-settings")
async def api_settings_page():
    return static_html_response("api-settings.html")

@app.get("/comfyui-settings")
async def comfyui_settings_page():
    return static_html_response("comfyui-settings.html")

@app.get("/comfyui-workbench")
async def comfyui_workbench_page():
    return static_html_response("comfyui-workbench.html")

@app.get("/api/view")
def view_image(filename: str, type: str = "input", subfolder: str = ""):
    # 先按原逻辑去各 ComfyUI 后端找
    for addr in COMFYUI_INSTANCES:
        try:
            url = f"http://{addr}/view"
            params = {"filename": filename, "type": type, "subfolder": subfolder}
            r = requests.get(url, params=params, timeout=1)
            if r.status_code == 200:
                return Response(content=r.content, media_type=r.headers.get('Content-Type'))
        except Exception:
            continue
    # 后端都拿不到时回退本地 assets/<input|output>/
    # 适用场景：画布通过 /api/ai/upload 把参考图直接落到本地 assets/input/，
    # 但 ComfyUI 的 input 可能因为重启/清理而丢失，导致 enhance/klein 等页面预览对比图 404
    if not subfolder and type in ("input", "output"):
        safe_name = os.path.basename(filename or "")
        if safe_name:
            local_path = output_path_for(safe_name, "input" if type == "input" else "output")
            if os.path.isfile(local_path):
                return FileResponse(local_path, media_type=content_type_for_path(local_path))
    raise HTTPException(status_code=404, detail="Image not found on any available backend")

@app.get("/api/download-output")
def download_output(url: str, name: str = ""):
    path = output_file_from_url(url)
    if not path:
        raise HTTPException(status_code=404, detail="文件不存在")
    filename = os.path.basename(name) if name else os.path.basename(path)
    return FileResponse(path, media_type=content_type_for_path(path), filename=filename)

@app.post("/api/upload")
async def upload_image(files: List[UploadFile] = File(...)):
    uploaded_files = []
    files_content = []
    for file in files:
        content = await file.read()
        files_content.append((file, content))

    for file, content in files_content:
        success_count = 0
        last_result = None
        for addr in COMFYUI_INSTANCES:
            try:
                files_data = {'image': (file.filename, content, file.content_type)}
                response = requests.post(f"http://{addr}/upload/image", files=files_data, timeout=5)
                if response.status_code == 200:
                    last_result = response.json()
                    success_count += 1
            except Exception as e:
                print(f"Upload error for {addr}: {e}")

        if success_count > 0 and last_result:
            uploaded_files.append({"comfy_name": last_result.get("name", file.filename)})
        else:
            raise HTTPException(status_code=500, detail="Failed to upload to any backend")

    return {"files": uploaded_files}

@app.post("/api/ai/upload")
async def upload_ai_reference(files: List[UploadFile] = File(...)):
    uploaded = []
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    video_exts = {".mp4", ".webm", ".mov", ".m4v"}
    audio_exts = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
    for file in files:
        content = await file.read()
        if not content:
            continue
        ext = os.path.splitext(file.filename or "")[1].lower()
        content_type = (file.content_type or "").lower()
        kind = "image"
        if ext in video_exts or content_type.startswith("video/"):
            kind = "video"
            if ext not in video_exts:
                ext = ".webm" if "webm" in content_type else ".mov" if "quicktime" in content_type else ".mp4"
        elif ext in audio_exts or content_type.startswith("audio/"):
            kind = "audio"
            if ext not in audio_exts:
                ext = ".wav" if "wav" in content_type else ".ogg" if "ogg" in content_type else ".m4a" if "mp4" in content_type else ".mp3"
        elif ext in image_exts or content_type.startswith("image/"):
            kind = "image"
            if ext not in image_exts:
                ext = ".jpg" if "jpeg" in content_type else ".webp" if "webp" in content_type else ".gif" if "gif" in content_type else ".png"
        else:
            continue
        filename = f"ai_ref_{uuid.uuid4().hex[:12]}{ext}"
        path = output_path_for(filename, "input")
        with open(path, "wb") as f:
            f.write(content)
        uploaded.append({"url": output_url_for(filename, "input"), "name": file.filename or filename, "kind": kind})
    return {"files": uploaded}

@app.post("/api/ai/import-local-image")
async def import_local_ai_reference(payload: LocalImageImportRequest, request: Request):
    ensure_same_origin_request(request)
    requested = [payload.path] if payload.path else []
    requested.extend(payload.paths or [])
    requested = [p for p in requested if str(p or "").strip()][:20]
    if not requested:
        raise HTTPException(status_code=400, detail="没有可导入的本地图片")
    return {"files": [import_local_image_file(normalize_local_image_path(path)) for path in requested]}

@app.get("/api/runninghub/app-info")
async def runninghub_app_info(webappId: str = ""):
    webapp_id = str(webappId or "").strip()
    if not webapp_id:
        raise HTTPException(status_code=400, detail="webappId 必填")
    provider = runninghub_provider()
    api_key = runninghub_api_key(provider)
    url = runninghub_endpoint_url(provider, f"/api/webapp/apiCallDemo?apiKey={urllib.parse.quote(api_key)}&webappId={urllib.parse.quote(webapp_id)}")
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=120.0, write=30.0, pool=20.0)) as client:
        try:
            response = await client.get(url, headers=runninghub_app_headers(False))
            raw = response.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text[:500]) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"请求 RunningHub 应用信息失败：{exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=json.dumps(raw, ensure_ascii=False)[:500])
    if isinstance(raw, dict) and raw.get("code") not in (0, "0", None):
        raise HTTPException(status_code=400, detail=raw.get("msg") or f"RunningHub 查询失败 code={raw.get('code')}")
    data = raw.get("data") if isinstance(raw, dict) else {}
    return {"success": True, "data": data or {}}

@app.post("/api/runninghub/submit")
async def runninghub_submit(payload: RunningHubSubmitRequest):
    webapp_id = str(payload.webappId or "").strip()
    if not webapp_id:
        raise HTTPException(status_code=400, detail="webappId 必填")
    provider = runninghub_provider()
    api_key = runninghub_api_key(provider, use_wallet=payload.useWallet)
    body = {
        "apiKey": api_key,
        "webappId": webapp_id,
        "nodeInfoList": payload.nodeInfoList or [],
    }
    instance_type = str(payload.instanceType or "").strip()
    if instance_type:
        body["instanceType"] = instance_type
    url = runninghub_endpoint_url(provider, "/task/openapi/ai-app/run")
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=180.0, write=120.0, pool=20.0)) as client:
        try:
            response = await client.post(url, headers=runninghub_app_headers(True, payload.useWallet), json=body)
            raw = response.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"提交 RunningHub 任务失败：{exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=json.dumps(raw, ensure_ascii=False)[:800])
    if isinstance(raw, dict) and raw.get("code") in (0, "0"):
        task_id = raw.get("data", {}).get("taskId") if isinstance(raw.get("data"), dict) else ""
        if not task_id:
            raise HTTPException(status_code=502, detail=f"RunningHub 未返回 taskId：{raw}")
        return {"success": True, "data": {"taskId": task_id, "raw": raw}}
    raise HTTPException(status_code=400, detail=(raw.get("msg") if isinstance(raw, dict) else "") or f"RunningHub 提交失败：{raw}")

@app.post("/api/runninghub/workflow-submit")
async def runninghub_workflow_submit(payload: RunningHubWorkflowSubmitRequest):
    workflow_id = str(payload.workflowId or "").strip()
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflowId 必填")
    provider = runninghub_provider()
    api_key = runninghub_api_key(provider, use_wallet=payload.useWallet)
    body = {
        "apiKey": api_key,
        "workflowId": workflow_id,
        "addMetadata": True,
    }
    if payload.nodeInfoList:
        body["nodeInfoList"] = payload.nodeInfoList
    workflow_payload = payload.workflow
    if workflow_payload:
        if isinstance(workflow_payload, (dict, list)):
            body["workflow"] = json.dumps(workflow_payload, ensure_ascii=False)
        else:
            body["workflow"] = str(workflow_payload)
    url = runninghub_endpoint_url(provider, "/task/openapi/create")
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=180.0, write=120.0, pool=20.0)) as client:
        try:
            response = await client.post(url, headers=runninghub_app_headers(True, payload.useWallet), json=body)
            raw = response.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"提交 RunningHub 工作流失败：{exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=json.dumps(raw, ensure_ascii=False)[:800])
    if isinstance(raw, dict) and raw.get("code") in (0, "0"):
        task_id = raw.get("data", {}).get("taskId") if isinstance(raw.get("data"), dict) else ""
        if not task_id:
            raise HTTPException(status_code=502, detail=f"RunningHub 工作流未返回 taskId：{raw}")
        return {"success": True, "data": {"taskId": task_id, "raw": raw}}
    raise HTTPException(status_code=400, detail=(raw.get("msg") if isinstance(raw, dict) else "") or f"RunningHub 工作流提交失败：{raw}")

@app.get("/api/runninghub/workflow-info")
async def runninghub_workflow_info(workflowId: str = ""):
    workflow_id = str(workflowId or "").strip()
    if not workflow_id:
        raise HTTPException(status_code=400, detail="workflowId 必填")
    provider = runninghub_provider()
    api_key = runninghub_api_key(provider)
    url = runninghub_endpoint_url(provider, "/api/openapi/getJsonApiFormat")
    body = {"apiKey": api_key, "workflowId": workflow_id}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=180.0, write=60.0, pool=20.0)) as client:
        try:
            response = await client.post(url, headers=runninghub_app_headers(True), json=body)
            raw = response.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"拉取 RunningHub 工作流参数失败：{exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=json.dumps(raw, ensure_ascii=False)[:800])
    if not isinstance(raw, dict) or raw.get("code") not in (0, "0"):
        raise HTTPException(status_code=400, detail=(raw.get("msg") if isinstance(raw, dict) else "") or f"RunningHub 工作流参数拉取失败：{raw}")
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    prompt = data.get("prompt")
    workflow_json = {}
    if isinstance(prompt, str) and prompt.strip():
        try:
            workflow_json = json.loads(prompt)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"RunningHub 工作流 JSON 解析失败：{exc}") from exc
    elif isinstance(prompt, dict):
        workflow_json = prompt
    node_info_list = runninghub_workflow_node_info_list(workflow_json)
    return {"success": True, "data": {"workflowId": workflow_id, "nodeInfoList": node_info_list, "raw": raw}}

@app.get("/api/runninghub/workflows")
def list_runninghub_workflows():
    with RUNNINGHUB_WORKFLOW_LOCK:
        store = load_runninghub_workflow_store()
    merged = {workflow_id: cfg for workflow_id, cfg in store.items() if isinstance(cfg, dict)}
    for provider in load_api_providers():
        if provider.get("id") != "runninghub":
            continue
        for entry in provider.get("rh_workflows") or []:
            workflow_id = runninghub_workflow_store_key(entry.get("workflowId") or entry.get("id"))
            if not workflow_id:
                continue
            provider_cfg = runninghub_provider_workflow_config(workflow_id)
            if provider_cfg:
                merged[workflow_id] = runninghub_select_workflow_config(merged.get(workflow_id), provider_cfg)
    items = []
    for workflow_id, cfg in merged.items():
        if not isinstance(cfg, dict):
            continue
        items.append({
            "workflowId": workflow_id,
            "title": cfg.get("title") or workflow_id,
            "fieldCount": len(cfg.get("fields") or []),
            "updatedAt": cfg.get("updatedAt"),
            "description": cfg.get("description") or "",
        })
    items.sort(key=lambda item: item["title"])
    return {"workflows": items}

@app.get("/api/runninghub/workflows/{workflow_id:path}")
def get_runninghub_workflow(workflow_id: str):
    key = runninghub_workflow_store_key(workflow_id)
    if not key:
        raise HTTPException(status_code=400, detail="workflowId 必填")
    with RUNNINGHUB_WORKFLOW_LOCK:
        store = load_runninghub_workflow_store()
    cfg = store.get(key)
    provider_cfg = runninghub_provider_workflow_config(key)
    cfg = runninghub_select_workflow_config(cfg, provider_cfg)
    if not isinstance(cfg, dict):
        raise HTTPException(status_code=404, detail="RunningHub 工作流未找到")
    return {"workflow": cfg}

@app.post("/api/runninghub/workflows/fetch")
async def fetch_runninghub_workflow(payload: RunningHubWorkflowConfig):
    workflow_id, workflow_json, raw = await fetch_runninghub_workflow_json_by_id(payload.workflowId)
    fields = runninghub_collect_workflow_fields(workflow_json)
    return {"success": True, "data": {"workflowId": workflow_id, "title": payload.title or workflow_id, "description": payload.description or "", "fields": fields, "workflowJson": workflow_json, "raw": raw}}

@app.put("/api/runninghub/workflows/{workflow_id:path}")
def save_runninghub_workflow(workflow_id: str, payload: RunningHubWorkflowConfig):
    key = runninghub_workflow_store_key(workflow_id)
    if not key:
        raise HTTPException(status_code=400, detail="workflowId 必填")
    fields = [
        field for field in (runninghub_normalize_field(item) for item in (payload.fields or []))
        if not runninghub_is_saved_link_field(field)
    ]
    cfg = {
        "workflowId": key,
        "title": (payload.title or key).strip() or key,
        "description": payload.description or "",
        "fields": fields,
        "workflowJson": payload.workflowJson or {},
        "optionalImageMode": payload.optionalImageMode or "prune-workflow",
        "raw": payload.raw or {},
        "updatedAt": now_ms(),
    }
    with RUNNINGHUB_WORKFLOW_LOCK:
        store = load_runninghub_workflow_store()
        store[key] = cfg
        save_runninghub_workflow_store(store)
    sync_runninghub_workflow_to_provider(cfg)
    return {"success": True, "workflow": cfg}

@app.delete("/api/runninghub/workflows/{workflow_id:path}")
def delete_runninghub_workflow(workflow_id: str):
    key = runninghub_workflow_store_key(workflow_id)
    if not key:
        raise HTTPException(status_code=400, detail="workflowId 必填")
    with RUNNINGHUB_WORKFLOW_LOCK:
        store = load_runninghub_workflow_store()
        provider_cfg = runninghub_provider_workflow_config(key)
        if key not in store and not provider_cfg:
            raise HTTPException(status_code=404, detail="RunningHub 工作流未找到")
        store.pop(key, None)
        save_runninghub_workflow_store(store)
    remove_runninghub_workflow_from_provider(key)
    return {"success": True}

@app.get("/api/runninghub/query")
async def runninghub_query(taskId: str = ""):
    task_id = str(taskId or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="taskId 必填")
    provider = runninghub_provider()
    api_key = runninghub_api_key(provider)
    url = runninghub_endpoint_url(provider, "/task/openapi/outputs")
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=240.0, write=30.0, pool=20.0)) as client:
        try:
            response = await client.post(url, headers=runninghub_app_headers(True), json={"apiKey": api_key, "taskId": task_id})
            raw = response.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"查询 RunningHub 任务失败：{exc}") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=json.dumps(raw, ensure_ascii=False)[:800])
        code = raw.get("code") if isinstance(raw, dict) else None
        status = "PENDING"
        urls = []
        if code in (0, "0"):
            status = "SUCCESS"
            for remote in runninghub_extract_outputs(raw.get("data")):
                try:
                    urls.append(await runninghub_store_remote_output(client, remote))
                except Exception:
                    urls.append(remote)
        elif code in (804, "804"):
            status = "RUNNING"
        elif code in (813, "813"):
            status = "QUEUED"
        elif code in (805, "805"):
            status = "FAILED"
        else:
            status = "UNKNOWN"
        return {"success": True, "data": {"status": status, "urls": urls, "failReason": runninghub_fail_reason(raw), "code": code, "raw": raw}}

@app.post("/api/runninghub/upload-asset")
async def runninghub_upload_asset(payload: RunningHubUploadAssetRequest):
    source_url = str(payload.url or "").strip()
    if not source_url:
        raise HTTPException(status_code=400, detail="url 必填")
    provider = runninghub_provider()
    api_key = runninghub_api_key(provider, use_wallet=payload.useWallet)
    filename = "asset.bin"
    content_type = "application/octet-stream"
    content = b""
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=240.0, write=240.0, pool=20.0), follow_redirects=True) as client:
        path = runninghub_local_asset_path(source_url)
        if path:
            filename = os.path.basename(path)
            content_type = content_type_for_path(path)
            with open(path, "rb") as f:
                content = f.read()
        elif source_url.startswith(("http://", "https://")):
            response = await client.get(source_url)
            if not response.is_success:
                raise HTTPException(status_code=400, detail=f"下载素材失败 HTTP {response.status_code}")
            content = response.content
            content_type = response.headers.get("content-type") or content_type
            filename = os.path.basename(urllib.parse.urlsplit(source_url).path) or filename
        else:
            raise HTTPException(status_code=400, detail=f"不支持的素材地址：{source_url}")
        if not content:
            raise HTTPException(status_code=400, detail="素材为空，无法上传到 RunningHub")
        upload_url = runninghub_endpoint_url(provider, "/task/openapi/upload")
        files = {"file": (filename, content, content_type)}
        data = {"apiKey": api_key, "fileType": "input"}
        try:
            response = await client.post(upload_url, headers=runninghub_app_headers(False, payload.useWallet), data=data, files=files)
            raw = response.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"上传素材到 RunningHub 失败：{exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=json.dumps(raw, ensure_ascii=False)[:800])
    if isinstance(raw, dict) and raw.get("code") in (0, "0") and isinstance(raw.get("data"), dict) and raw["data"].get("fileName"):
        return {"success": True, "data": {"fileName": raw["data"]["fileName"], "fileType": raw["data"].get("fileType") or content_type}}
    raise HTTPException(status_code=400, detail=(raw.get("msg") if isinstance(raw, dict) else "") or f"RunningHub 上传失败：{raw}")

@app.get("/api/config")
async def ai_config():
    preferred_chat_model = next((m for m in CHAT_MODELS if m == "gpt-5.5"), CHAT_MODELS[0] if CHAT_MODELS else CHAT_MODEL)
    providers = [provider_config_metadata(p) for p in load_api_providers()]
    return {
        "chat_model": preferred_chat_model,
        "image_model": IMAGE_MODEL,
        "chat_models": CHAT_MODELS,
        "image_models": IMAGE_MODELS,
        "video_models": VIDEO_MODELS,
        "api_providers": providers,
        "ms_chat_models": MODELSCOPE_CHAT_MODELS,
    }

@app.get("/api/models")
async def ai_models():
    return {"chat_models": CHAT_MODELS, "image_models": IMAGE_MODELS, "video_models": VIDEO_MODELS}

@app.get("/api/providers")
async def api_providers(request: Request):
    require_admin_user(request)
    return {"providers": [admin_provider_view(p) for p in load_api_providers()]}

@app.put("/api/providers")
async def save_providers(payload: List[ApiProviderPayload], request: Request):
    require_admin_user(request)
    providers = []
    env_updates = {}
    # 收集每个 item 的 primary 字段
    raw_primary_flags = [bool(getattr(item, "primary", False)) for item in payload]
    for item in payload:
        provider = normalize_provider(item.dict(exclude={"api_key"}))
        if provider["id"] == "runninghub":
            provider = preserve_runninghub_hidden_overrides(provider)
        if any(existing["id"] == provider["id"] for existing in providers):
            raise HTTPException(status_code=400, detail=f"API 平台 ID 重复：{provider['id']}")
        providers.append(provider)
        key_env = provider_key_env(provider["id"])
        if item.clear_key:
            env_updates[key_env] = ""
        elif item.api_key is not None and item.api_key.strip():
            env_updates[key_env] = item.api_key.strip()
        if provider["id"] == "runninghub":
            wallet_env = runninghub_wallet_key_env()
            if item.clear_wallet_key:
                env_updates[wallet_env] = ""
            elif item.wallet_api_key is not None and item.wallet_api_key.strip():
                env_updates[wallet_env] = item.wallet_api_key.strip()
        if provider["id"] == "comfly":
            env_updates["COMFLY_BASE_URL"] = provider["base_url"]
            env_updates["IMAGE_MODELS"] = ",".join(provider["image_models"])
            env_updates["CHAT_MODELS"] = ",".join(provider["chat_models"])
            env_updates["VIDEO_MODELS"] = ",".join(provider.get("video_models") or [])
        if provider["id"] == "modelscope":
            env_updates["MODELSCOPE_CHAT_MODELS"] = ",".join(provider["chat_models"])
        if provider["id"] == "runninghub":
            provider["protocol"] = "runninghub"
    if not providers:
        raise HTTPException(status_code=400, detail="至少保留一个 API 平台")
    # 强制最多一个 primary（取最后被标记的；都没标记则保持原样不强制）
    primary_indices = [i for i, flag in enumerate(raw_primary_flags) if flag]
    if primary_indices:
        winner = primary_indices[-1]
        for i, p in enumerate(providers):
            p["primary"] = (i == winner)
    save_api_providers(providers)
    if env_updates:
        update_env_values(env_updates)
        reload_env_globals()   # 立即将最新 env 值同步回模块全局变量，无需重启
    return {"providers": [admin_provider_view(p) for p in providers]}

# --- ModelScope Token (从 env 读取，不再支持通过 UI 修改) ---

@app.get("/api/config/token")
async def get_global_token(request: Request):
    require_admin_user(request)
    # 优先读 env，回退到 global_config.json（兼容旧数据）
    if MODELSCOPE_API_KEY:
        return {"token": MODELSCOPE_API_KEY}
    if os.path.exists(GLOBAL_CONFIG_FILE):
        try:
            with open(GLOBAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return {"token": config.get("modelscope_token", "")}
        except:
            pass
    return {"token": ""}

# --- 在线生图 (COMFLY) ---

class TestConnectionPayload(BaseModel):
    base_url: str = ""
    api_key: str = ""
    provider_id: str = ""
    protocol: str = "openai"

def protocol_from_payload(payload):
    protocol = str(getattr(payload, "protocol", "") or "openai").strip().lower()
    return protocol if protocol in SUPPORTED_PROVIDER_PROTOCOLS else "openai"

def upstream_models_url(base_url: str, protocol: str):
    if protocol == "gemini":
        return f"{base_url}/models" if base_url.endswith("/v1beta") else f"{base_url}/v1beta/models"
    if protocol == "volcengine":
        return f"{base_url}/models" if base_url.endswith("/api/v3") else f"{base_url}/api/v3/models"
    if protocol == "runninghub":
        return f"{base_url}/openapi/v2/models"
    return f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"

def upstream_model_headers(api_key: str, protocol: str):
    if protocol == "gemini":
        return {"x-goog-api-key": api_key, "Accept": "application/json"}
    if protocol == "runninghub":
        return {"Authorization": strip_auth_scheme(api_key, "Bearer"), "Accept": "application/json"}
    return {"Authorization": bearer_auth_value(api_key), "Accept": "application/json"}

def classify_upstream_model(mid):
    lc = str(mid or "").lower()
    video_keys = ["veo", "sora", "wan2", "wanx", "doubao-seedance", "doubao-1", "kling", "hailuo", "video", "t2v-", "i2v-", "s2v"]
    if any(k in lc for k in video_keys):
        return "video"
    image_keys = ["banana", "image", "dalle", "dall-e", "imagen", "flux", "stable", "sdxl", "midjourney", "nano-banana", "ideogram", "fal-ai", "z-image", "qwen-image", "klein", "seedream", "doubao-seedream", "text-to-image", "image-to-image"]
    if any(k in lc for k in image_keys):
        return "image"
    return "chat"

def parse_upstream_models(raw, protocol="openai"):
    items = raw.get("data") if isinstance(raw, dict) else None
    if not items and isinstance(raw, dict):
        items = raw.get("models") or raw.get("list") or []
    if not isinstance(items, list):
        items = []
    ids = []
    for it in items:
        if isinstance(it, str):
            mid = it
        elif isinstance(it, dict):
            mid = it.get("id") or it.get("name") or it.get("model")
        else:
            mid = ""
        if mid:
            mid = str(mid)
            if protocol == "gemini" and mid.startswith("models/"):
                mid = mid[len("models/"):]
            ids.append(mid)
    ids = sorted(set(ids))
    grouped = {"image": [], "chat": [], "video": []}
    for mid in ids:
        grouped[classify_upstream_model(mid)].append(mid)
    return grouped, ids

@app.post("/api/providers/test-connection")
async def test_provider_connection(payload: TestConnectionPayload):
    """测试请求地址是否可用：调上游 /v1/models。验证通过时同时把模型清单按类别返回，避免再调一次拉取接口。"""
    base_url = (payload.base_url or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="请先填写请求地址")
    if not re.match(r"^https?://", base_url):
        raise HTTPException(status_code=400, detail="请求地址必须以 http:// 或 https:// 开头")
    api_key = (payload.api_key or "").strip()
    if not api_key and payload.provider_id:
        api_key = os.getenv(runninghub_wallet_key_env(), "") if payload.provider_id == "runninghub" else ""
        if not api_key:
            api_key = os.getenv(provider_key_env(payload.provider_id), "")
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写或保存 API Key")
    protocol = protocol_from_payload(payload)
    url = upstream_models_url(base_url, protocol)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=upstream_model_headers(api_key, protocol))
        if resp.status_code >= 400:
            return {"ok": False, "status": resp.status_code, "message": resp.text[:300]}
        data = resp.json() if resp.text else {}
        grouped, ids = parse_upstream_models(data, protocol)
        return {"ok": True, "status": resp.status_code, "model_count": len(ids), "image_models": grouped["image"], "chat_models": grouped["chat"], "video_models": grouped["video"], "all": ids}
    except httpx.HTTPError as e:
        return {"ok": False, "status": 0, "message": str(e)[:300]}

@app.post("/api/providers/probe-async")
async def probe_async_endpoint(payload: TestConnectionPayload):
    """验证异步协议：用假 task_id 请求 GET /v1/tasks/{fake_id}。
    收到 400 Invalid task ID = 端点存在且 Key 有效；401/403 = Key 无效；404/连接失败 = 不支持异步端点。"""
    base_url = (payload.base_url or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="请先填写请求地址")
    api_key = (payload.api_key or "").strip()
    if not api_key and payload.provider_id:
        api_key = os.getenv(runninghub_wallet_key_env(), "") if payload.provider_id == "runninghub" else ""
        if not api_key:
            api_key = os.getenv(provider_key_env(payload.provider_id), "")
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写或保存 API Key")
    tasks_base = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    probe_url = f"{tasks_base}/tasks/healthcheck_probe_do_not_submit"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(probe_url, headers={"Authorization": bearer_auth_value(api_key), "Accept": "application/json"})
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        sc = resp.status_code
        # 判断结果
        err_msg = ""
        if isinstance(body, dict):
            err = body.get("error") or {}
            if isinstance(err, dict):
                err_msg = str(err.get("message") or "").lower()
            else:
                err_msg = str(err).lower()
        # 400 + "invalid task id" → 端点存在，Key 有效
        if sc == 400 and "invalid task id" in err_msg:
            return {"ok": True, "status_code": sc, "message": "异步任务端点可用，API Key 已通过认证", "raw": body}
        # 401 / 403 → Key 无效
        if sc in (401, 403):
            return {"ok": False, "status_code": sc, "message": "API Key 无效或无权限", "raw": body}
        # 404 + 没有结构化错误 → 平台不支持此端点
        if sc == 404:
            return {"ok": False, "status_code": sc, "message": "平台不支持 /v1/tasks/ 端点，可能不是 APIMart 异步协议", "raw": body}
        # 其他 400 系 → 返回原始信息供参考
        if 400 <= sc < 500:
            return {"ok": None, "status_code": sc, "message": f"端点返回 {sc}，请查看原始响应判断", "raw": body}
        # 2xx → 意外成功（不太可能）
        if sc < 300:
            return {"ok": True, "status_code": sc, "message": f"端点返回 {sc}（意外成功）", "raw": body}
        return {"ok": False, "status_code": sc, "message": f"服务端错误 {sc}", "raw": body}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e)[:300])

async def fetch_models_from_upstream(base_url: str, api_key: str, protocol: str = "openai"):
    """从上游模型列表端点拉取模型，并按名称做轻量分类。"""
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(status_code=400, detail="请先填写请求地址")
    if not re.match(r"^https?://", base_url):
        raise HTTPException(status_code=400, detail="请求地址必须以 http:// 或 https:// 开头")
    api_key = (api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写或保存 API Key")
    protocol = protocol if protocol in SUPPORTED_PROVIDER_PROTOCOLS else "openai"
    url = upstream_models_url(base_url, protocol)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=upstream_model_headers(api_key, protocol))
            if resp.status_code >= 400:
                endpoint_label = "/v1beta/models" if protocol == "gemini" else "/api/v3/models" if protocol == "volcengine" else "/openapi/v2/models" if protocol == "runninghub" else "/v1/models"
                raise HTTPException(status_code=resp.status_code, detail=f"上游 {endpoint_label} 失败：{resp.text[:300]}")
            raw = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"请求上游模型列表失败：{e}")
    grouped, ids = parse_upstream_models(raw, protocol)
    return {"total": len(ids), "image_models": grouped["image"], "chat_models": grouped["chat"], "video_models": grouped["video"], "all": ids}

@app.post("/api/providers/fetch-models")
async def fetch_upstream_models_from_payload(payload: TestConnectionPayload):
    """按页面当前表单值拉取模型，支持新增平台未保存时直接使用临时 Base URL / Key。"""
    api_key = (payload.api_key or "").strip()
    if not api_key and payload.provider_id:
        api_key = os.getenv(runninghub_wallet_key_env(), "") if payload.provider_id == "runninghub" else ""
        if not api_key:
            api_key = os.getenv(provider_key_env(payload.provider_id), "")
    return await fetch_models_from_upstream(payload.base_url, api_key, protocol_from_payload(payload))

@app.get("/api/providers/{provider_id}/fetch-models")
async def fetch_upstream_models(provider_id: str):
    """从已保存的上游 OpenAI 兼容接口拉取 /v1/models 列表，按名称智能分类为 image/chat/video。"""
    provider = get_api_provider_exact(provider_id)
    api_key = os.getenv(runninghub_wallet_key_env(), "") if provider["id"] == "runninghub" else ""
    if not api_key:
        api_key = os.getenv(provider_key_env(provider["id"]), "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"{provider.get('name') or provider_id} 未配置 API Key")
    return await fetch_models_from_upstream(provider.get("base_url") or "", api_key, provider_protocol(provider))

async def build_online_image_result(payload: OnlineImageRequest, owner_key: str = ""):
    provider = get_api_provider(payload.provider_id)
    default_model = (provider.get("image_models") or [IMAGE_MODEL])[0]
    model = selected_model(payload.model, default_model)
    refs = [ref.dict() for ref in payload.reference_images if ref.url]
    count = max(1, min(8, int(payload.n or 1)))
    async def generate_one():
        image_data, raw_item = await generate_ai_image(payload.prompt, payload.size, payload.quality, model, refs, provider["id"])
        local_url = await save_ai_image_to_output(image_data, prefix="online_")
        return local_url, raw_item
    try:
        generated = await asyncio.gather(*(generate_one() for _ in range(count)))
    except httpx.HTTPStatusError as exc:
        text = exc.response.text or ''
        friendly = friendly_image_error_detail(text, payload.size, model)
        detail = friendly or f"上游生图接口错误：{text[:300]}"
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"请求上游生图接口失败：{exc}") from exc

    local_urls = [url for url, _raw in generated if url]
    raw = generated[0][1] if generated else {}
    result = {
        "prompt": payload.prompt,
        "images": local_urls,
        "timestamp": time.time(),
        "type": "online",
        "model": model,
        "provider_id": provider["id"],
        "provider_name": provider.get("name") or provider["id"],
        "task_id": extract_task_id(raw) if isinstance(raw, dict) else None,
        "request_id": raw.get("id") if isinstance(raw, dict) else None,
        "params": {"provider_id": provider["id"], "model": model, "size": payload.size, "quality": payload.quality, "n": count, "reference_images": refs},
        "raw_usage": raw.get("usage") if isinstance(raw, dict) else None,
    }
    save_to_history(result, owner_key=owner_key)
    if GLOBAL_LOOP:
        asyncio.run_coroutine_threadsafe(manager.broadcast_new_image(result), GLOBAL_LOOP)
    return result

@app.post("/api/online-image")
async def online_image(payload: OnlineImageRequest, request: Request):
    user = require_current_user(request)
    return await build_online_image_result(payload, owner_key=owner_key_from_user(user))

async def run_canvas_image_task(task_id: str, payload: OnlineImageRequest, owner_key: str):
    with CANVAS_TASK_LOCK:
        if task_id in CANVAS_TASKS:
            CANVAS_TASKS[task_id]["status"] = "running"
            CANVAS_TASKS[task_id]["updated_at"] = time.time()
    try:
        result = await build_online_image_result(payload, owner_key=owner_key)
        with CANVAS_TASK_LOCK:
            CANVAS_TASKS[task_id].update({
                "status": "succeeded",
                "result": result,
                "error": "",
                "updated_at": time.time(),
            })
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        status_code = getattr(exc, "status_code", 500)
        with CANVAS_TASK_LOCK:
            CANVAS_TASKS[task_id].update({
                "status": "failed",
                "error": str(detail),
                "status_code": status_code,
                "updated_at": time.time(),
            })

@app.post("/api/canvas-image-tasks")
async def create_canvas_image_task(payload: OnlineImageRequest, request: Request):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    task_id = f"canvas_img_{uuid.uuid4().hex}"
    with CANVAS_TASK_LOCK:
        CANVAS_TASKS[task_id] = {
            "id": task_id,
            "type": "online-image",
            "owner_key": owner_key,
            "status": "queued",
            "created_at": time.time(),
            "updated_at": time.time(),
            "result": None,
            "error": "",
        }
    asyncio.create_task(run_canvas_image_task(task_id, payload, owner_key=owner_key))
    return {"task_id": task_id, "status": "queued"}

@app.get("/api/canvas-image-tasks/{task_id}")
async def get_canvas_image_task(task_id: str, request: Request):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    with CANVAS_TASK_LOCK:
        task = dict(CANVAS_TASKS.get(task_id) or {})
    if not task:
        raise HTTPException(status_code=404, detail="画布任务不存在，可能服务已重启或任务已过期")
    if task.get("owner_key") and task.get("owner_key") != owner_key:
        raise HTTPException(status_code=404, detail="画布任务不存在，可能服务已重启或任务已过期")
    return task

# --- Canvas Video ---

VIDEO_URL_KEYS = (
    "url", "video_url", "videoUrl", "mp4_url", "mp4Url",
    "output", "output_url", "outputUrl", "download_url", "downloadUrl",
    "video", "src", "uri", "preview_url", "previewUrl", "path",
    "last_frame_url", "lastFrameUrl",
)

def _collect_video_url(value, urls):
    if not value:
        return
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://") or value.startswith("/output/") or value.startswith("/assets/"):
            urls.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_video_url(item, urls)
        return
    if isinstance(value, dict):
        for key in ("videos", "outputs", "data", "result", "content"):
            if key in value:
                _collect_video_url(value.get(key), urls)
        for key in VIDEO_URL_KEYS:
            if key in value:
                _collect_video_url(value.get(key), urls)

def video_output_urls(raw):
    urls = []
    if not isinstance(raw, dict):
        return urls
    candidates = [raw]
    data = raw.get("data")
    content = raw.get("content")
    if isinstance(data, dict):
        candidates.append(data)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                candidates.append(item)
    if isinstance(content, dict):
        candidates.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                candidates.append(item)
    for node in list(candidates):
        result = node.get("result") if isinstance(node, dict) else None
        if isinstance(result, dict):
            candidates.append(result)
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    candidates.append(item)
    for node in candidates:
        if not isinstance(node, dict):
            continue
        for key in ("videos", "outputs", "content"):
            value = node.get(key)
            if value:
                _collect_video_url(value, urls)
        for key in VIDEO_URL_KEYS:
            if key in node:
                _collect_video_url(node.get(key), urls)
    deduped = []
    for url in urls:
        if isinstance(url, str) and url and url not in deduped:
            deduped.append(url)
    return deduped

def video_api_root(provider):
    base_url = (provider.get("base_url") or AI_BASE_URL).rstrip("/")
    if is_volcengine_provider(provider):
        if base_url.endswith("/api/v3"):
            base_url = base_url[: -len("/api/v3")]
        return base_url
    if base_url.endswith("/v1") or base_url.endswith("/v2"):
        base_url = base_url.rsplit("/", 1)[0]
    return base_url

VIDEO_TASK_SUCCESS_STATUSES = {
    "SUCCESS", "SUCCEED", "SUCCEEDED", "COMPLETED", "COMPLETE",
    "DONE", "FINISHED", "FINISH", "OK", "READY",
}
VIDEO_TASK_FAILURE_STATUSES = {
    "FAILURE", "FAILED", "FAIL", "ERROR", "ERRORED",
    "CANCELED", "CANCELLED", "TIMEOUT", "TIMEDOUT", "REJECTED", "EXPIRED",
}

async def wait_for_video_task(client, provider, task_id):
    base_url = video_api_root(provider)
    if not base_url:
        raise HTTPException(status_code=400, detail=f"{provider.get('name') or provider['id']} 未配置 Base URL")
    if is_apimart_provider(provider):
        task_path = f"{base_url}/tasks/{task_id}" if base_url.endswith("/v1") else f"{base_url}/v1/tasks/{task_id}"
        task_url = f"{task_path}?language=zh"
    elif is_volcengine_provider(provider):
        task_url = f"{base_url}/api/v3/contents/generations/tasks/{task_id}"
    else:
        task_url = f"{base_url}/v2/videos/generations/{task_id}"
    deadline = time.monotonic() + VIDEO_POLL_TIMEOUT
    delay = max(2.0, IMAGE_POLL_INTERVAL)
    last_payload = {}
    while time.monotonic() < deadline:
        await asyncio.sleep(delay)
        response = await client.get(task_url, headers=api_headers(provider=provider))
        response.raise_for_status()
        raw = response.json()
        last_payload = raw
        task_data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        status = str(task_data.get("status") or task_data.get("task_status") or raw.get("status") or raw.get("task_status") or "").upper()
        if status in VIDEO_TASK_SUCCESS_STATUSES:
            return raw
        # 部分上游不返回标准 status 字段，但已经返回了视频 URL —— 直接当成功处理
        if not status and video_output_urls(raw):
            return raw
        if status in VIDEO_TASK_FAILURE_STATUSES:
            error = task_data.get("error") if isinstance(task_data.get("error"), dict) else {}
            reason = task_data.get("fail_reason") or task_data.get("message") or error.get("message") or raw.get("error") or raw.get("message") or str(raw)
            raise HTTPException(status_code=502, detail=f"视频生成任务失败：{reason}")
        delay = min(delay * 1.6, 12)
    raise HTTPException(status_code=504, detail=f"视频生成任务超时：{last_payload or task_id}")

def apimart_video_size(size):
    value = str(size or "16:9").strip()
    if value == "keep_ratio":
        return "adaptive"
    allowed = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"}
    return value if value in allowed else "16:9"

def volcengine_video_prompt_text(prompt, aspect_ratio="", duration=None):
    text = str(prompt or "").strip()
    suffixes = []
    ratio = str(aspect_ratio or "").strip()
    if ratio:
        suffixes.append(f"--ratio {ratio}")
    if not suffixes:
        return text
    suffix_text = " ".join(suffixes)
    return f"{text} {suffix_text}".strip() if text else suffix_text

@app.post("/api/canvas-video")
async def canvas_video(payload: CanvasVideoRequest):
    provider = get_api_provider(payload.provider_id)
    base_url = video_api_root(provider)
    if not base_url:
        raise HTTPException(status_code=400, detail=f"{provider.get('name') or provider['id']} 未配置 Base URL")
    api_key = os.getenv(provider_key_env(provider["id"]), "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"未配置 {provider.get('name') or provider['id']} 的 API Key，请在 API 设置中填写。")
    is_apimart = is_apimart_provider(provider)
    is_volcengine = is_volcengine_provider(provider)
    submit_url = (
        f"{base_url}/videos/generations" if is_apimart and base_url.endswith("/v1")
        else f"{base_url}/v1/videos/generations" if is_apimart
        else f"{base_url}/api/v3/contents/generations/tasks" if is_volcengine
        else f"{base_url}/v2/videos/generations"
    )
    requested_model = selected_model(payload.model, "veo3-fast")
    is_veo31 = is_apimart and is_apimart_veo31_model(requested_model)
    try:
        async with httpx.AsyncClient(timeout=VIDEO_POLL_TIMEOUT) as client:
            # --- 构造图片载荷 ---
            if is_apimart:
                # APIMart 只接受 http/https 或 asset:// URL，先上传本地图片取回网络 URL
                image_with_roles = []
                invalid_images = []  # 每项为 (原始 URL, 失败原因)
                apimart_model = apimart_veo31_model(requested_model) if is_veo31 else ""
                if apimart_model == "veo3.1-lite" and payload.images:
                    raise HTTPException(status_code=400, detail="veo3.1-lite 不支持图片输入，请改用 veo3.1-fast 或 veo3.1-quality。")
                image_limit = 0 if apimart_model == "veo3.1-lite" else (3 if is_veo31 else 9)
                for ref in payload.images[:image_limit]:
                    if not ref.url:
                        continue
                    role = str(ref.role or "").strip()
                    if not is_veo31 and role in {"first_frame", "last_frame", "reference_image"}:
                        up_url = await upload_image_for_apimart(client, provider, ref.url)
                        if valid_apimart_video_image_input(up_url):
                            image_with_roles.append({"url": up_url, "role": role})
                        else:
                            reason = up_url[4:] if isinstance(up_url, str) and up_url.startswith("ERR:") else "未知错误"
                            invalid_images.append((ref.url, reason))
                image_payload = []
                if not image_with_roles:
                    for ref in payload.images[:image_limit]:
                        if not ref.url:
                            continue
                        up_url = await upload_image_for_apimart(client, provider, ref.url)
                        if valid_apimart_video_image_input(up_url):
                            image_payload.append(up_url)
                        else:
                            reason = up_url[4:] if isinstance(up_url, str) and up_url.startswith("ERR:") else "未知错误"
                            invalid_images.append((ref.url, reason))
                if payload.images and not image_with_roles and not image_payload:
                    first_url, first_reason = invalid_images[0] if invalid_images else ("", "未知错误")
                    sample = invalid_video_image_preview(first_url)
                    raise HTTPException(status_code=400, detail=f"输入图片无法转换为视频接口支持的格式：{sample}\n原因：{first_reason}\n请确认本地文件存在且不超过 10MB；VEO3.1 需要图片是 APIMart 可访问的 http/https / asset:// / data URL。")
                # --- APIMart 请求体 ---
                if is_veo31:
                    model = apimart_model
                    body = {
                        "prompt": payload.prompt,
                        "model": model,
                        "duration": 8,
                        "aspect_ratio": apimart_veo31_aspect(payload.aspect_ratio),
                        "resolution": apimart_veo31_resolution(payload.resolution),
                    }
                    if image_payload and model != "veo3.1-lite":
                        video_images = image_payload[:3]
                        if model == "veo3.1-quality" and len(video_images) > 2:
                            video_images = video_images[:2]
                        body["image_urls"] = video_images
                        if len(video_images) == 2:
                            body["generation_type"] = "frame"
                        elif len(video_images) >= 3 and model != "veo3.1-quality":
                            body["generation_type"] = "reference"
                    if model != "veo3.1-lite":
                        body["official_fallback"] = False
                else:
                    body = {
                        "prompt": payload.prompt,
                        "model": selected_model(payload.model, "doubao-seedance-2.0"),
                        "duration": payload.duration,
                        "size": apimart_video_size(payload.aspect_ratio or payload.size),
                        "resolution": payload.resolution or "480p",
                    }
                    if image_with_roles:
                        body["image_with_roles"] = image_with_roles
                    elif image_payload:
                        body["image_urls"] = image_payload[:9]
                    if payload.videos:
                        body["video_urls"] = [v for v in payload.videos if v][:3]
                    if payload.seed is not None:
                        body["seed"] = payload.seed
                    if payload.return_last_frame:
                        body["return_last_frame"] = True
                    if payload.generate_audio:
                        body["generate_audio"] = True
            else:
                # 非 APIMart：data URL 方式（OpenAI / ComflyAI 接口）
                image_payload = []
                for ref in payload.images[:4]:
                    if ref.url:
                        image_payload.append(reference_to_data_url(ref.dict(), max_size=1536))
                if is_volcengine:
                    text = volcengine_video_prompt_text(payload.prompt, payload.aspect_ratio, payload.duration)
                    body = {
                        "model": selected_model(payload.model, "doubao-seedance-2-0-fast-260128"),
                        "content": [
                            {
                                "type": "text",
                                "text": text,
                            }
                        ],
                    }
                    if image_payload:
                        body["content"].append({
                            "type": "image_url",
                            "image_url": {"url": image_payload[0]},
                        })
                    if payload.seed is not None:
                        body["seed"] = payload.seed
                else:
                    body = {
                        "prompt": payload.prompt,
                        "model": selected_model(payload.model, "veo3-fast"),
                        "duration": payload.duration,
                        "watermark": payload.watermark,
                    }
                    if payload.aspect_ratio:
                        body["aspect_ratio"] = payload.aspect_ratio
                        body["ratio"] = payload.aspect_ratio
                    if payload.size:
                        body["size"] = payload.size
                    if payload.resolution:
                        body["resolution"] = payload.resolution
                    if image_payload:
                        body["images"] = image_payload
                    if payload.videos:
                        body["videos"] = [v for v in payload.videos if v]
                    if payload.enhance_prompt:
                        body["enhance_prompt"] = True
                    if payload.enable_upsample:
                        body["enable_upsample"] = True
                    if payload.seed is not None:
                        body["seed"] = payload.seed
                    if payload.camerafixed:
                        body["camerafixed"] = True
                    if payload.return_last_frame:
                        body["return_last_frame"] = True
                    if payload.generate_audio:
                        body["generate_audio"] = True
            # --- 发起视频生成请求 ---
            response = await client.post(submit_url, headers=api_headers(provider=provider), json=body)
            response.raise_for_status()
            try:
                raw = response.json()
            except Exception:
                # 上游返回了 HTML 错误页面或非 JSON 响应
                resp_text = response.text[:500]
                raise HTTPException(status_code=502, detail=f"上游视频接口返回非 JSON 响应（状态 {response.status_code}）：{resp_text}")
            task_id = extract_task_id(raw) or raw.get("task_id") or raw.get("id")
            result = raw
            if task_id and not video_output_urls(raw):
                result = await wait_for_video_task(client, provider, task_id)
            urls = video_output_urls(result)
            if not urls:
                raise HTTPException(status_code=502, detail=f"视频生成成功但没有返回视频：{result}")
            local_urls = [await save_remote_video_to_output(url) for url in urls]
            return {"videos": local_urls, "task_id": task_id, "raw": result}
    except httpx.HTTPStatusError as exc:
        text = exc.response.text
        try:
            requested_model = body.get("model", "") or payload.model or ""
        except NameError:
            requested_model = payload.model or ""
        provider_name = provider.get('name') or provider['id']
        # 1) 模型名不在上游支持范围 → 从错误信息里抽取合法列表展示
        valid_models_match = re.search(r"not in\s*\[([^\]]+)\]", text)
        if valid_models_match:
            valid_models = [m.strip() for m in valid_models_match.group(1).split(",") if m.strip()]
            sample = valid_models[:30]
            more = f"（共 {len(valid_models)} 个，仅显示前 {len(sample)} 个）" if len(valid_models) > len(sample) else ""
            hint = (
                f"上游「{provider_name}」不识别模型「{requested_model}」。\n\n"
                f"上游支持的视频模型清单{more}：\n  {', '.join(sample)}\n\n"
                f"请到「API 设置」里把视频模型改成上面列表中的一个。"
            )
            raise HTTPException(status_code=exc.response.status_code, detail=hint) from exc
        # 2) 模型名合法但账号没开通通道
        if "channel not found" in text or "model_not_found" in text:
            hint = (
                f"上游「{provider_name}」识别了模型「{requested_model}」，但你的 API Key 账号下**没有该模型的可用通道**。\n\n"
                f"原因：你的账号没开通这个模型的访问权限（付费/订阅相关）。\n\n"
                f"解决方法：\n"
                f"  1. 登录 {provider.get('base_url') or '上游平台'} 控制台，开通该模型 / 充值；\n"
                f"  2. 或在「API 设置」里把视频模型改成你账号已开通的型号（如 veo3-fast / veo2-fast / sora-2 等）。"
            )
            raise HTTPException(status_code=exc.response.status_code, detail=hint) from exc
        if "text.duration" in text or "specified duration is not supported" in text:
            hint = (
                f"上游「{provider_name}」模型「{requested_model}」不支持当前时长参数。\n\n"
                f"我方已改为不主动给火山 Seedance fast 传 duration；如果仍报这个错误，请把视频时长先切回默认值再试，"
                f"或改用该账号已开通的其他视频模型。"
            )
            raise HTTPException(status_code=exc.response.status_code, detail=hint) from exc
        if "inputimagesensitivecontentdetected" in text.lower() or "privacyinformation" in text.lower() or "may contain real person" in text.lower():
            hint = (
                f"上游「{provider_name}」拦截了输入参考图，原因是图片里可能包含真人身份/隐私信息。\n\n"
                f"这不是代码协议错误，而是火山视频模型的内容安全策略。\n\n"
                f"建议你这样处理：\n"
                f"  1. 改用非真人参考图，例如插画、AI 头像、商品图、场景图；\n"
                f"  2. 先把真人脸做模糊、遮挡、裁掉，或转成明显的二次元/插画风；\n"
                f"  3. 如果只是想做文生视频，先去掉参考图只保留文字提示词测试。"
            )
            raise HTTPException(status_code=exc.response.status_code, detail=hint) from exc
        raise HTTPException(status_code=exc.response.status_code, detail=f"上游视频接口错误：{text}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"请求上游视频接口失败：{exc}") from exc

# --- Canvas LLM ---

@app.post("/api/canvas-llm")
async def canvas_llm(payload: CanvasLLMRequest):
    chat_base, chat_hdrs, model = resolve_chat_provider(payload.provider, payload.model, payload.ms_model)
    # 判断协议：APIMart 异步 vs 标准 OpenAI
    _llm_provider = get_api_provider(payload.provider) if payload.provider not in ("modelscope",) else {}
    _is_apimart = is_apimart_provider(_llm_provider)
    system_prompt = (payload.system_prompt or "").strip()
    upstream_messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
    for item in payload.messages[-MAX_HISTORY_MESSAGES:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            upstream_messages.append({"role": role, "content": content})
    # 构造用户消息：有图片时用 OpenAI vision 多模态格式
    image_inputs = [img for img in (payload.images or []) if is_image_reference_value(img)]
    if image_inputs:
        content_parts = [{"type": "text", "text": payload.message}]
        ok_imgs = 0
        for img in image_inputs[:8]:
            if not img or not isinstance(img, str):
                continue
            # 本地 /output/* 或 /assets/* 路径转为 data URL；http(s) 或 data URL 直接用
            if img.startswith("/output/") or img.startswith("/assets/"):
                ref_url = reference_to_data_url({"url": img}, max_size=1024)
            else:
                ref_url = img
            if not ref_url:
                continue
            content_parts.append({"type": "image_url", "image_url": {"url": ref_url}})
            ok_imgs += 1
        print(f"[canvas-llm] model={model} provider={payload.provider} text_len={len(payload.message)} images={ok_imgs}/{len(payload.images)}")
        upstream_messages.append({"role": "user", "content": content_parts})
    else:
        upstream_messages.append({"role": "user", "content": payload.message})
    raw = None
    try:
        async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT) as client:
            req_body = {"model": model, "messages": upstream_messages}
            if _is_apimart:
                req_body["stream"] = False   # APIMart 默认流式，强制关闭
            response = await client.post(
                f"{chat_base}/chat/completions",
                headers=chat_hdrs,
                json=req_body,
            )
            response.raise_for_status()
            if not response.content:
                raise HTTPException(status_code=502, detail="上游接口返回了空响应")
            raw = response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text or ""
        friendly = friendly_chat_error_detail(body, model, _llm_provider)
        raise HTTPException(status_code=exc.response.status_code, detail=friendly or f"上游接口错误：{body}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"请求上游接口失败：{exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"解析上游响应失败：{exc}") from exc
    try:
        text = text_from_chat_response(raw).strip() if isinstance(raw, dict) else ""
        text = text or "接口返回了空回复。"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"解析回复内容失败：{exc}") from exc
    raw_data = unwrap_apimart_response(raw) if isinstance(raw, dict) else {}
    return {"text": text, "model": model, "raw_usage": raw_data.get("usage")}

# --- 对话管理 ---

@app.get("/api/conversations")
async def conversations(request: Request, x_user_id: str = Header(default="")):
    _ = x_user_id
    user = require_current_user(request)
    user_id = owner_key_from_user(user)
    return {"user_id": user_id, "conversations": list_conversations(user_id)}

@app.post("/api/conversations")
async def create_conversation(payload: ConversationCreateRequest, request: Request, x_user_id: str = Header(default="")):
    _ = x_user_id
    user = require_current_user(request)
    user_id = owner_key_from_user(user)
    return {"conversation": new_conversation(user_id, payload.title)}

@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request, x_user_id: str = Header(default="")):
    _ = x_user_id
    user = require_current_user(request)
    user_id = owner_key_from_user(user)
    return {"conversation": load_conversation(user_id, conversation_id)}

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request, x_user_id: str = Header(default="")):
    _ = x_user_id
    user = require_current_user(request)
    user_id = owner_key_from_user(user)
    path = conversation_path(user_id, conversation_id)
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True}

# --- 画布管理 ---

@app.get("/api/projects")
async def projects(request: Request):
    user = require_current_user(request)
    return {"projects": list_projects_for_user(user, status="active")}

@app.get("/api/projects/trash")
async def trashed_projects(request: Request):
    user = require_current_user(request)
    return {"projects": list_projects_for_user(user, status="archived")}

@app.post("/api/projects")
async def create_project(payload: ProjectCreateRequest, request: Request):
    user = require_current_user(request)
    timestamp = now_ms()
    project_id = uuid.uuid4().hex
    default_icon = "sparkles" if normalize_canvas_kind(payload.kind) == "smart" else "🧩"
    canvas = new_canvas(
        title=(payload.title or "未命名项目")[:80],
        icon=default_icon,
        kind=payload.kind,
        owner_user_id=int(user["id"]),
        project_id=project_id,
    )
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute(
                """
                INSERT INTO projects
                (id, title, owner_user_id, default_canvas_id, thumbnail_url, status, created_at, updated_at, archived_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, 0)
                """,
                (
                    project_id,
                    (payload.title or "未命名项目")[:120],
                    int(user["id"]),
                    str(canvas["id"]),
                    str(payload.thumbnail_url or "")[:500],
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    row = load_project(project_id)
    return {"project": project_row_to_dict(row), "canvas": canvas}

@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request):
    user = require_current_user(request)
    row = load_project(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not user_can_access_project(user, row):
        raise HTTPException(status_code=403, detail="无权限访问该项目")
    return {"project": project_row_to_dict(row)}

@app.patch("/api/projects/{project_id}")
async def patch_project(project_id: str, payload: ProjectPatchRequest, request: Request):
    user = require_current_user(request)
    row = load_project(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not user_can_manage_project(user, row):
        raise HTTPException(status_code=403, detail="无权限修改该项目")
    next_title = (payload.title or row["title"] or "未命名项目")[:120]
    next_thumbnail = (payload.thumbnail_url or row["thumbnail_url"] or "")[:500]
    timestamp = now_ms()
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute(
                "UPDATE projects SET title = ?, thumbnail_url = ?, updated_at = ? WHERE id = ?",
                (next_title, next_thumbnail, timestamp, str(row["id"])),
            )
            conn.commit()
        finally:
            conn.close()
    default_canvas_id = str(row["default_canvas_id"] or "")
    if default_canvas_id:
        try:
            canvas = load_canvas_any(default_canvas_id)
            if user_can_access_canvas(user, canvas):
                canvas["title"] = next_title[:80]
                if payload.icon:
                    canvas["icon"] = str(payload.icon)[:32]
                save_canvas(canvas)
        except HTTPException:
            pass
        except Exception:
            pass
    updated = load_project(project_id)
    return {"project": project_row_to_dict(updated)}

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, request: Request):
    user = require_current_user(request)
    row = load_project(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not user_can_manage_project(user, row):
        raise HTTPException(status_code=403, detail="无权限归档该项目")
    timestamp = now_ms()
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute(
                "UPDATE projects SET status = 'archived', archived_at = ?, updated_at = ? WHERE id = ?",
                (timestamp, timestamp, str(row["id"])),
            )
            conn.commit()
        finally:
            conn.close()
    default_canvas_id = str(row["default_canvas_id"] or "")
    if default_canvas_id:
        try:
            canvas = load_canvas_any(default_canvas_id)
            if not canvas.get("deleted_at"):
                canvas["deleted_at"] = timestamp
                save_canvas(canvas)
        except HTTPException:
            pass
    return {"ok": True}

@app.post("/api/projects/{project_id}/restore")
async def restore_project(project_id: str, request: Request):
    user = require_current_user(request)
    row = load_project(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not user_can_manage_project(user, row):
        raise HTTPException(status_code=403, detail="无权限恢复该项目")
    timestamp = now_ms()
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute(
                "UPDATE projects SET status = 'active', archived_at = 0, updated_at = ? WHERE id = ?",
                (timestamp, str(row["id"])),
            )
            conn.commit()
        finally:
            conn.close()
    default_canvas_id = str(row["default_canvas_id"] or "")
    if default_canvas_id:
        try:
            canvas = load_canvas_any(default_canvas_id)
            if canvas.get("deleted_at"):
                canvas.pop("deleted_at", None)
                save_canvas(canvas)
        except HTTPException:
            pass
    updated = load_project(project_id)
    return {"project": project_row_to_dict(updated)}

@app.delete("/api/projects/{project_id}/purge")
async def purge_project(project_id: str, request: Request):
    user = require_current_user(request)
    row = load_project(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not user_can_manage_project(user, row):
        raise HTTPException(status_code=403, detail="无权限删除该项目")
    default_canvas_id = str(row["default_canvas_id"] or "")
    with AUTH_LOCK:
        conn = auth_db_conn()
        try:
            conn.execute("DELETE FROM projects WHERE id = ?", (str(row["id"]),))
            conn.commit()
        finally:
            conn.close()
    if default_canvas_id:
        path = canvas_path(default_canvas_id)
        if os.path.exists(path):
            os.remove(path)
    return {"ok": True}

@app.get("/api/canvases")
async def canvases(request: Request, project_id: str = ""):
    user = require_current_user(request)
    project_filter = str(project_id or "").strip()
    if project_filter:
        row = load_project(project_filter)
        if not row:
            raise HTTPException(status_code=404, detail="项目不存在")
        if not user_can_access_project(user, row):
            raise HTTPException(status_code=403, detail="无权限访问该项目")
    records = iter_canvas_records_for_user(user, include_deleted=False, project_id=project_filter)
    return {"canvases": sorted(records, key=lambda item: item["updated_at"], reverse=True)}

@app.get("/api/canvases/trash")
async def trashed_canvases(request: Request, project_id: str = ""):
    user = require_current_user(request)
    project_filter = str(project_id or "").strip()
    if project_filter:
        row = load_project(project_filter)
        if not row:
            raise HTTPException(status_code=404, detail="项目不存在")
        if not user_can_access_project(user, row):
            raise HTTPException(status_code=403, detail="无权限访问该项目")
    records = iter_canvas_records_for_user(user, include_deleted=True, project_id=project_filter)
    return {"canvases": sorted(records, key=lambda item: item["deleted_at"], reverse=True), "retention_days": 30}

@app.post("/api/canvases")
async def create_canvas(payload: CanvasCreateRequest, request: Request):
    user = require_current_user(request)
    return {"canvas": new_canvas(payload.title, payload.icon, payload.kind, owner_user_id=int(user["id"]))}

@app.get("/api/canvases/{canvas_id}/meta")
async def get_canvas_meta(canvas_id: str, request: Request):
    user = require_current_user(request)
    canvas = load_canvas(canvas_id)
    ensure_canvas_access(user, canvas)
    return {
        "id": canvas.get("id"),
        "updated_at": canvas.get("updated_at", 0),
        "title": canvas.get("title", "未命名画布"),
        "icon": canvas.get("icon", "layers"),
        "kind": normalize_canvas_kind(canvas.get("kind")),
        "owner_user_id": int(canvas.get("owner_user_id") or 0),
        "project_id": str(canvas.get("project_id") or ""),
    }

@app.get("/api/canvases/{canvas_id}")
async def get_canvas(canvas_id: str, request: Request):
    user = require_current_user(request)
    canvas = load_canvas(canvas_id)
    ensure_canvas_access(user, canvas)
    return {"canvas": canvas}

@app.post("/api/canvas-assets/check")
async def check_canvas_assets(payload: CanvasAssetCheckRequest):
    result = {}
    for url in payload.urls[:3000]:
        text = str(url or "").strip()
        if not text:
            continue
        if text.startswith("/output/") or text.startswith("/assets/"):
            result[text] = bool(output_file_from_url(text))
        else:
            result[text] = True
    return {"exists": result}

@app.post("/api/canvas-assets/download")
async def download_canvas_assets(payload: CanvasAssetDownloadRequest):
    buffer = BytesIO()
    used_names = set()
    count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for url in payload.urls[:1000]:
            text = str(url or "").strip()
            if not text or not (text.startswith("/output/") or text.startswith("/assets/")):
                continue
            path = output_file_from_url(text)
            if not path or not os.path.isfile(path):
                continue
            base = os.path.basename(path) or f"image-{count + 1}.png"
            name, ext = os.path.splitext(base)
            archive_name = base
            suffix = 2
            while archive_name in used_names:
                archive_name = f"{name}-{suffix}{ext}"
                suffix += 1
            used_names.add(archive_name)
            zf.write(path, archive_name)
            count += 1
    if count <= 0:
        raise HTTPException(status_code=404, detail="没有可下载的本地图片")
    buffer.seek(0)
    filename = re.sub(r'[\\/:*?"<>|]+', "_", payload.filename or "canvas-output-images.zip")
    if not filename.lower().endswith(".zip"):
        filename += ".zip"
    encoded = urllib.parse.quote(filename)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
    return Response(buffer.getvalue(), media_type="application/zip", headers=headers)

def sanitize_export_filename(name: str, fallback: str) -> str:
    base = os.path.basename(str(name or "").strip()) or fallback
    base = re.sub(r'[\\/:*?"<>|]+', "_", base)
    return base or fallback

def smart_group_export_folder(folder: str, group_name: str) -> str:
    text = str(folder or "").strip()
    if text:
        path = os.path.abspath(os.path.expanduser(text))
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe_group = sanitize_export_filename(group_name or "group", "group")
        path = os.path.abspath(os.path.join(OUTPUT_DIR, "smart-groups", f"{safe_group}-{stamp}"))
    os.makedirs(path, exist_ok=True)
    return path

@app.post("/api/smart-canvas/group-export")
async def export_smart_canvas_group(payload: SmartCanvasGroupExportRequest):
    target_dir = smart_group_export_folder(payload.folder, payload.group_name)
    used_names = set()
    count = 0
    text_index = 1
    for item in payload.items[:2000]:
        kind = str(item.kind or "").lower()
        if kind == "text":
            text = str(item.text or "")
            if not text.strip():
                continue
            base = sanitize_export_filename(item.name or f"{text_index}.txt", f"{text_index}.txt")
            if not base.lower().endswith(".txt"):
                base += ".txt"
            text_index += 1
            name, ext = os.path.splitext(base)
            out_name = base
            suffix = 2
            while out_name in used_names:
                out_name = f"{name}-{suffix}{ext}"
                suffix += 1
            used_names.add(out_name)
            with open(os.path.join(target_dir, out_name), "w", encoding="utf-8") as f:
                f.write(text)
            count += 1
            continue
        src = output_file_from_url(item.url)
        if not src or not os.path.isfile(src):
            continue
        base = sanitize_export_filename(item.name or os.path.basename(src), os.path.basename(src) or f"asset-{count + 1}")
        name, ext = os.path.splitext(base)
        if not ext:
            _, src_ext = os.path.splitext(src)
            ext = src_ext or ".bin"
            base = name + ext
        out_name = base
        suffix = 2
        while out_name in used_names:
            out_name = f"{name}-{suffix}{ext}"
            suffix += 1
        used_names.add(out_name)
        shutil.copy2(src, os.path.join(target_dir, out_name))
        count += 1
    if count <= 0:
        raise HTTPException(status_code=404, detail="没有可导出的内容")
    return {"ok": True, "folder": target_dir, "count": count}

@app.get("/api/asset-library")
async def get_asset_library():
    return {"library": load_asset_library()}

@app.post("/api/asset-library/categories")
async def create_asset_library_category(payload: AssetLibraryCategoryRequest):
    lib = load_asset_library()
    cat_type = "workflow" if str(payload.type or "").lower() == "workflow" else "image"
    category = {"id": f"cat_{uuid.uuid4().hex[:12]}", "name": sanitize_asset_name(payload.name, "新文件夹"), "type": cat_type, "items": []}
    lib.setdefault("categories", []).append(category)
    save_asset_library(lib)
    return {"library": lib, "category": category}

@app.patch("/api/asset-library/categories/{category_id}")
async def rename_asset_library_category(category_id: str, payload: AssetLibraryRenameRequest):
    lib = load_asset_library()
    cat = find_asset_category(lib, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    cat["name"] = sanitize_asset_name(payload.name, cat.get("name") or "新文件夹")
    save_asset_library(lib)
    return {"library": lib, "category": cat}

@app.delete("/api/asset-library/categories/{category_id}")
async def delete_asset_library_category(category_id: str):
    lib = load_asset_library()
    cat = find_asset_category(lib, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    if cat.get("type") == "workflow" and category_id == "workflows":
        raise HTTPException(status_code=400, detail="默认工作流分类不能删除")
    lib["categories"] = [c for c in lib.get("categories", []) if c.get("id") != category_id]
    save_asset_library(lib)
    return {"library": lib}

@app.post("/api/asset-library/items")
async def add_asset_library_item(payload: AssetLibraryAddRequest):
    lib = load_asset_library()
    cat = find_asset_category(lib, payload.category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    if cat.get("type") != "image":
        raise HTTPException(status_code=400, detail="该分类暂不支持添加图片")
    src = output_file_from_url(payload.url)
    if not src:
        raise HTTPException(status_code=400, detail="只支持保存本地 /assets 或 /output 图片")
    ext = os.path.splitext(src)[1].lower() or ".png"
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
        ext = ".png"
    safe_name = sanitize_asset_name(payload.name or os.path.basename(src), "asset")
    if not os.path.splitext(safe_name)[1]:
        safe_name += ext
    dest_name = f"lib_{uuid.uuid4().hex[:12]}_{safe_name}"
    dest_path = os.path.join(ASSET_LIBRARY_DIR, dest_name)
    shutil.copy2(src, dest_path)
    item = {"id": f"asset_{uuid.uuid4().hex[:12]}", "name": os.path.splitext(safe_name)[0][:120], "url": f"/assets/library/{dest_name}", "created_at": now_ms()}
    cat.setdefault("items", []).append(item)
    save_asset_library(lib)
    return {"library": lib, "item": item}

@app.patch("/api/asset-library/items/{item_id}")
async def rename_asset_library_item(item_id: str, payload: AssetLibraryRenameRequest):
    lib = load_asset_library()
    for cat in lib.get("categories", []):
        for item in cat.get("items", []):
            if item.get("id") == item_id:
                item["name"] = sanitize_asset_name(payload.name, item.get("name") or "asset")
                save_asset_library(lib)
                return {"library": lib, "item": item}
    raise HTTPException(status_code=404, detail="资产不存在")

@app.delete("/api/asset-library/items/{item_id}")
async def delete_asset_library_item(item_id: str):
    lib = load_asset_library()
    removed = None
    for cat in lib.get("categories", []):
        keep = []
        for item in cat.get("items", []):
            if item.get("id") == item_id:
                removed = item
            else:
                keep.append(item)
        cat["items"] = keep
    if not removed:
        raise HTTPException(status_code=404, detail="资产不存在")
    save_asset_library(lib)
    return {"library": lib}

@app.put("/api/canvases/{canvas_id}")
async def update_canvas(canvas_id: str, payload: CanvasSaveRequest, request: Request):
    user = require_current_user(request)
    canvas = load_canvas(canvas_id)
    ensure_canvas_access(user, canvas)
    current_updated_at = int(canvas.get("updated_at") or 0)
    if payload.base_updated_at and current_updated_at and int(payload.base_updated_at) < current_updated_at:
        raise HTTPException(status_code=409, detail={
            "message": "画布已被其他页面更新，已拒绝旧版本覆盖。",
            "canvas": canvas,
            "updated_at": current_updated_at,
        })
    canvas["title"] = (payload.title or canvas.get("title") or "未命名画布")[:80]
    canvas["icon"] = (payload.icon or canvas.get("icon") or "layers")[:32]
    canvas["kind"] = normalize_canvas_kind(canvas.get("kind"))
    canvas["nodes"] = payload.nodes
    canvas["connections"] = payload.connections
    canvas["viewport"] = payload.viewport
    canvas["logs"] = payload.logs[-500:]
    canvas["settings"] = payload.settings or {}
    save_canvas(canvas)
    if canvas.get("project_id"):
        touch_project(str(canvas.get("project_id")), int(canvas.get("updated_at") or now_ms()))
    await manager.broadcast_canvas_updated(canvas_id, int(canvas.get("updated_at") or now_ms()), payload.client_id)
    return {"canvas": canvas}

@app.delete("/api/canvases/{canvas_id}")
async def delete_canvas(canvas_id: str, request: Request):
    user = require_current_user(request)
    canvas = load_canvas_any(canvas_id)
    ensure_canvas_access(user, canvas)
    if not canvas.get("deleted_at"):
        canvas["deleted_at"] = now_ms()
        save_canvas(canvas)
    return {"ok": True}

@app.post("/api/canvases/{canvas_id}/restore")
async def restore_canvas(canvas_id: str, request: Request):
    user = require_current_user(request)
    canvas = load_canvas_any(canvas_id)
    ensure_canvas_access(user, canvas)
    if canvas.get("deleted_at"):
        canvas.pop("deleted_at", None)
        save_canvas(canvas)
    return {"canvas": canvas}

@app.delete("/api/canvases/{canvas_id}/purge")
async def purge_canvas(canvas_id: str, request: Request):
    user = require_current_user(request)
    canvas = load_canvas_any(canvas_id)
    ensure_canvas_access(user, canvas)
    path = canvas_path(canvas_id)
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True}

# --- GPT 对话 ---

@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request, x_user_id: str = Header(default="")):
    _ = x_user_id
    user = require_current_user(request)
    user_id = owner_key_from_user(user)
    conversation = (
        load_conversation(user_id, payload.conversation_id)
        if payload.conversation_id
        else new_conversation(user_id, display_title(payload.message))
    )
    if not conversation.get("messages"):
        conversation["title"] = display_title(payload.message)

    refs = [ref.dict() for ref in payload.reference_images if ref.url]
    user_message = {
        "id": uuid.uuid4().hex,
        "role": "user",
        "content": payload.message,
        "created_at": now_ms(),
        "attachments": refs,
        "mode": payload.mode,
    }
    conversation["messages"].append(user_message)
    conversation["updated_at"] = now_ms()
    save_conversation(user_id, conversation)

    if payload.mode == "image":
        image_provider_id = payload.provider if payload.provider not in {"modelscope"} else "comfly"
        provider = get_api_provider(image_provider_id)
        default_model = (provider.get("image_models") or [IMAGE_MODEL])[0]
        model = selected_model(payload.image_model or payload.model, default_model)
        try:
            image_data, raw = await generate_ai_image(payload.message, payload.size, payload.quality, model, refs, provider["id"])
            local_url = await save_ai_image_to_output(image_data, prefix="chat_")
        except httpx.HTTPStatusError as exc:
            text = exc.response.text or ""
            detail = friendly_image_error_detail(text, payload.size, model) or f"上游生图接口错误：{text[:300]}"
            raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"请求上游生图接口失败：{exc}") from exc
        assistant_message = {
            "id": uuid.uuid4().hex,
            "role": "assistant",
            "type": "image",
            "content": payload.message,
            "image_url": local_url,
            "created_at": now_ms(),
            "model": model,
            "raw_usage": raw.get("usage") if isinstance(raw, dict) else None,
        }
    else:
        chat_base, chat_hdrs, model = resolve_chat_provider(payload.provider, payload.model, payload.ms_model)
        _conv_provider = get_api_provider(payload.provider) if payload.provider not in ("modelscope",) else {}
        _conv_is_apimart = is_apimart_provider(_conv_provider)
        history = conversation["messages"][-MAX_HISTORY_MESSAGES:]
        upstream_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in history:
            msg = upstream_message_from_record(item)
            if msg:
                upstream_messages.append(msg)
        try:
            async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT) as client:
                conv_req_body = {"model": model, "messages": upstream_messages}
                if _conv_is_apimart:
                    conv_req_body["stream"] = False
                response = await client.post(
                    f"{chat_base}/chat/completions",
                    headers=chat_hdrs,
                    json=conv_req_body,
                )
                response.raise_for_status()
                raw = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text or ""
            friendly = friendly_chat_error_detail(body, model, _conv_provider)
            raise HTTPException(status_code=exc.response.status_code, detail=friendly or f"上游接口错误：{body}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"请求上游接口失败：{exc}") from exc
        raw_data = unwrap_apimart_response(raw) if isinstance(raw, dict) else raw
        assistant_message = {
            "id": uuid.uuid4().hex,
            "role": "assistant",
            "content": text_from_chat_response(raw).strip() or "接口返回了空回复。",
            "created_at": now_ms(),
            "model": model,
            "raw_usage": raw_data.get("usage") if isinstance(raw_data, dict) else None,
        }

    conversation["messages"].append(assistant_message)
    conversation["updated_at"] = now_ms()
    save_conversation(user_id, conversation)
    return {"conversation": conversation, "message": assistant_message}

@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request, x_user_id: str = Header(default="")):
    if payload.mode == "image":
        raise HTTPException(status_code=400, detail="图片模式请使用 /api/chat")

    _ = x_user_id
    user = require_current_user(request)
    user_id = owner_key_from_user(user)
    conversation = (
        load_conversation(user_id, payload.conversation_id)
        if payload.conversation_id
        else new_conversation(user_id, display_title(payload.message))
    )
    if not conversation.get("messages"):
        conversation["title"] = display_title(payload.message)

    refs = [ref.dict() for ref in payload.reference_images if ref.url]
    user_message = {
        "id": uuid.uuid4().hex,
        "role": "user",
        "content": payload.message,
        "created_at": now_ms(),
        "attachments": refs,
        "mode": payload.mode,
    }
    conversation["messages"].append(user_message)
    conversation["updated_at"] = now_ms()
    save_conversation(user_id, conversation)

    chat_base, chat_hdrs, model = resolve_chat_provider(payload.provider, payload.model, payload.ms_model)
    _stream_provider = get_api_provider(payload.provider) if payload.provider not in ("modelscope",) else {}
    history = conversation["messages"][-MAX_HISTORY_MESSAGES:]
    upstream_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history:
        msg = upstream_message_from_record(item)
        if msg:
            upstream_messages.append(msg)

    async def stream():
        content_parts = []
        raw_usage = None
        yield sse_event({"type": "meta", "conversation": conversation})
        try:
            async with httpx.AsyncClient(timeout=AI_REQUEST_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{chat_base}/chat/completions",
                    headers=chat_hdrs,
                    json={"model": model, "messages": upstream_messages, "stream": True},
                ) as response:
                    if response.status_code >= 400:
                        detail = await response.aread()
                        body = detail.decode("utf-8", errors="ignore")
                        friendly = friendly_chat_error_detail(body, model, _stream_provider)
                        yield sse_event({"type": "error", "detail": friendly or f"上游接口错误：{body}"})
                        return
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(chunk, dict) and chunk.get("usage"):
                            raw_usage = chunk.get("usage")
                        delta = text_delta_from_chat_chunk(chunk)
                        if delta:
                            content_parts.append(delta)
                            yield sse_event({"type": "delta", "delta": delta})
        except httpx.HTTPError as exc:
            yield sse_event({"type": "error", "detail": f"请求上游接口失败：{exc}"})
            return

        assistant_message = {
            "id": uuid.uuid4().hex,
            "role": "assistant",
            "content": "".join(content_parts).strip() or "接口返回了空回复。",
            "created_at": now_ms(),
            "model": model,
            "raw_usage": raw_usage,
        }
        conversation["messages"].append(assistant_message)
        conversation["updated_at"] = now_ms()
        save_conversation(user_id, conversation)
        yield sse_event({"type": "done", "conversation": conversation, "message": assistant_message})

    return StreamingResponse(stream(), media_type="text/event-stream")

# --- 历史记录 ---

@app.get("/api/history")
async def get_history_api(request: Request, type: str = None):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    owner_history_file = history_path(owner_key)
    if os.path.exists(owner_history_file):
        try:
            with open(owner_history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if type:
                    data = [item for item in data if item.get("type", "zimage") == type]
                data = [item for item in data if item.get("images") and len(item["images"]) > 0]

                def sort_key(item):
                    ts = item.get("timestamp", 0)
                    if isinstance(ts, (int, float)):
                        return float(ts)
                    return 0

                data.sort(key=sort_key, reverse=True)
                return data
        except Exception as e:
            print(f"读取历史文件失败: {e}")
            return []
    return []

@app.get("/api/queue_status")
async def get_queue_status(client_id: str):
    with QUEUE_LOCK:
        total = len(QUEUE)
        positions = [i + 1 for i, t in enumerate(QUEUE) if t["client_id"] == client_id]
        position = positions[0] if positions else 0
    return {"total": total, "position": position}

@app.post("/api/history/delete")
async def delete_history(req: DeleteHistoryRequest, request: Request):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    owner_history_file = history_path(owner_key)
    if not os.path.exists(owner_history_file):
        return {"success": False, "message": "History file not found"}
    try:
        with HISTORY_LOCK:
            with open(owner_history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            target_record = None
            new_history = []
            for item in history:
                is_match = False
                item_ts = item.get("timestamp", 0)
                if isinstance(req.timestamp, (int, float)) and isinstance(item_ts, (int, float)):
                    if abs(float(item_ts) - float(req.timestamp)) < 0.001:
                        is_match = True
                elif str(item_ts) == str(req.timestamp):
                    is_match = True
                if is_match:
                    target_record = item
                else:
                    new_history.append(item)
            if target_record:
                with open(owner_history_file, 'w', encoding='utf-8') as f:
                    json.dump(new_history, f, ensure_ascii=False, indent=4)

        if target_record:
            for img_url in target_record.get("images", []):
                file_path = output_file_from_url(img_url)
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Failed to delete file {file_path}: {e}")
            return {"success": True}
        else:
            return {"success": False, "message": "Record not found"}
    except Exception as e:
        print(f"Delete history error: {e}")
        return {"success": False, "message": str(e)}

# --- ModelScope 角度控制 ---

@app.post("/api/angle/poll_status")
async def poll_angle_cloud(req: CloudPollRequest, request: Request):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    base_url = 'https://api-inference.modelscope.cn/'
    clean_token = (req.api_key or MODELSCOPE_API_KEY).strip()
    if not clean_token:
        raise HTTPException(status_code=400, detail="未提供 ModelScope API Key")

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true"
    }
    task_id = req.task_id
    print(f"Resuming polling for Angle Task: {task_id}")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(300):
                await asyncio.sleep(2)
                try:
                    result = await client.get(
                        f"{base_url}v1/tasks/{task_id}",
                        headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
                    )
                    data = result.json()
                    status = data.get("task_status")

                    if status == "SUCCEED":
                        img_url = data["output_images"][0]
                        local_path = ""
                        try:
                            async with httpx.AsyncClient() as dl_client:
                                img_res = await dl_client.get(img_url)
                                if img_res.status_code == 200:
                                    filename = f"cloud_angle_{int(time.time())}.png"
                                    file_path = output_path_for(filename, "output")
                                    with open(file_path, "wb") as f:
                                        f.write(img_res.content)
                                    local_path = output_url_for(filename, "output")
                                else:
                                    local_path = img_url
                        except Exception:
                            local_path = img_url

                        record = {"timestamp": time.time(), "prompt": f"Resumed {task_id}", "images": [local_path], "type": "angle"}
                        save_to_history(record, owner_key=owner_key)
                        if req.client_id:
                            await manager.send_personal_message({"type": "cloud_status", "status": "SUCCEED", "task_id": task_id}, req.client_id)
                        return {"url": local_path}

                    elif status == "FAILED":
                        if req.client_id:
                            await manager.send_personal_message({"type": "cloud_status", "status": "FAILED", "task_id": task_id}, req.client_id)
                        raise Exception(f"ModelScope task failed: {data}")

                    if i % 5 == 0 and req.client_id:
                        await manager.send_personal_message({
                            "type": "cloud_status", "status": f"{status} ({i}/300)",
                            "task_id": task_id, "progress": i, "total": 300
                        }, req.client_id)

                except Exception as loop_e:
                    print(f"Angle polling error: {loop_e}")
                    continue

            if req.client_id:
                await manager.send_personal_message({"type": "cloud_status", "status": "TIMEOUT", "task_id": task_id}, req.client_id)
            return {"status": "timeout", "task_id": task_id, "message": "Task still pending"}

    except Exception as e:
        print(f"Angle polling error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/angle/generate")
async def generate_angle_cloud(req: CloudGenRequest, request: Request):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    base_url = 'https://api-inference.modelscope.cn/'
    clean_token = (req.api_key or MODELSCOPE_API_KEY).strip()
    if not clean_token:
        raise HTTPException(status_code=400, detail="未提供 ModelScope API Key")

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true"
    }
    model = selected_model(req.model, "Qwen/Qwen-Image-Edit-2511")
    payload = {
        "model": model,
        "prompt": req.prompt.strip(),
        "image_url": [modelscope_image_url(url, max_size=1536) for url in req.image_urls]
    }
    if req.resolution:
        payload["size"] = modelscope_size(req.resolution)
    if req.loras is not None:
        payload["loras"] = req.loras

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            submit_res = await client.post(f"{base_url}v1/images/generations", headers=headers, json=payload)
            if submit_res.status_code != 200:
                try:
                    detail = submit_res.json()
                except:
                    detail = submit_res.text
                raise HTTPException(status_code=submit_res.status_code, detail=detail)

            task_id = submit_res.json().get("task_id")
            print(f"Angle Task submitted, ID: {task_id}")

            for i in range(300):
                await asyncio.sleep(2)
                try:
                    result = await client.get(
                        f"{base_url}v1/tasks/{task_id}",
                        headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
                    )
                    data = result.json()
                    status = data.get("task_status")

                    if status == "SUCCEED":
                        img_url = data["output_images"][0]
                        local_path = ""
                        try:
                            async with httpx.AsyncClient() as dl_client:
                                img_res = await dl_client.get(img_url)
                                if img_res.status_code == 200:
                                    filename = f"cloud_angle_{int(time.time())}.png"
                                    file_path = output_path_for(filename, "output")
                                    with open(file_path, "wb") as f:
                                        f.write(img_res.content)
                                    local_path = output_url_for(filename, "output")
                                else:
                                    local_path = img_url
                        except Exception:
                            local_path = img_url

                        record = {"timestamp": time.time(), "prompt": req.prompt, "images": [local_path], "type": "angle"}
                        save_to_history(record, owner_key=owner_key)
                        if req.client_id:
                            await manager.send_personal_message({"type": "cloud_status", "status": "SUCCEED", "task_id": task_id}, req.client_id)
                        if GLOBAL_LOOP:
                            asyncio.run_coroutine_threadsafe(manager.broadcast_new_image(record), GLOBAL_LOOP)
                        return {"url": local_path, "task_id": task_id}

                    elif status == "FAILED":
                        if req.client_id:
                            await manager.send_personal_message({"type": "cloud_status", "status": "FAILED", "task_id": task_id}, req.client_id)
                        raise Exception(f"ModelScope task failed: {data}")

                    if i % 5 == 0 and req.client_id:
                        await manager.send_personal_message({
                            "type": "cloud_status", "status": f"{status} ({i}/300)",
                            "task_id": task_id, "progress": i, "total": 300
                        }, req.client_id)

                except Exception as loop_e:
                    print(f"Angle polling error: {loop_e}")
                    continue

            if req.client_id:
                await manager.send_personal_message({"type": "cloud_status", "status": "TIMEOUT", "task_id": task_id}, req.client_id)
            return {"status": "timeout", "task_id": task_id, "message": "Task still pending"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Angle generation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# --- ModelScope Z-Image 云端生图 ---

@app.post("/generate")
async def generate_cloud(req: CloudGenRequest, request: Request):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    base_url = 'https://api-inference.modelscope.cn/'
    clean_token = (req.api_key or MODELSCOPE_API_KEY).strip()
    if not clean_token:
        raise HTTPException(status_code=400, detail="未提供 ModelScope API Key")

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "Tongyi-MAI/Z-Image-Turbo",
        "prompt": req.prompt.strip(),
        "size": modelscope_size(req.resolution),
        "n": 1
    }
    if req.loras is not None:
        payload["loras"] = req.loras

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            submit_res = await client.post(
                f"{base_url}v1/images/generations",
                headers={**headers, "X-ModelScope-Async-Mode": "true"},
                json=payload
            )
            if submit_res.status_code != 200:
                try:
                    detail = submit_res.json()
                except:
                    detail = submit_res.text
                raise HTTPException(status_code=submit_res.status_code, detail=detail)

            task_id = submit_res.json().get("task_id")
            print(f"Z-Image Task submitted, ID: {task_id}")

            for i in range(200):
                await asyncio.sleep(3)
                try:
                    result = await client.get(
                        f"{base_url}v1/tasks/{task_id}",
                        headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
                    )
                    data = result.json()
                    status = data.get("task_status")

                    if i % 5 == 0:
                        print(f"Task {task_id} status check {i}: {status}")

                    if status == "SUCCEED":
                        img_url = data["output_images"][0]
                        local_path = ""
                        try:
                            async with httpx.AsyncClient() as dl_client:
                                img_res = await dl_client.get(img_url)
                                if img_res.status_code == 200:
                                    filename = f"cloud_{int(time.time())}.png"
                                    file_path = output_path_for(filename, "output")
                                    with open(file_path, "wb") as f:
                                        f.write(img_res.content)
                                    local_path = output_url_for(filename, "output")
                                else:
                                    local_path = img_url
                        except Exception as dl_e:
                            print(f"Download error: {dl_e}")
                            local_path = img_url

                        record = {"timestamp": time.time(), "prompt": req.prompt, "images": [local_path], "type": "cloud"}
                        save_to_history(record, owner_key=owner_key)
                        try:
                            await manager.broadcast_new_image(record)
                        except Exception:
                            pass
                        return {"url": local_path}

                    elif status == "FAILED":
                        raise Exception(f"ModelScope task failed: {data}")

                except Exception as loop_e:
                    print(f"Polling error (retrying): {loop_e}")
                    continue

            raise Exception("Cloud generation timeout")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Cloud generation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# --- ModelScope 通用图片生成（支持图生图） ---

@app.post("/api/ms/generate")
async def ms_generate(req: MsGenerateRequest, request: Request):
    user = require_current_user(request)
    owner_key = owner_key_from_user(user)
    base_url = 'https://api-inference.modelscope.cn/'
    clean_token = (req.api_key or MODELSCOPE_API_KEY).strip()
    if not clean_token:
        raise HTTPException(status_code=400, detail="未配置 ModelScope API Key，请在 API 设置中填写，或重新保存 ModelScope Token。")

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true"
    }
    payload = {
        "model": req.model,
        "prompt": req.prompt.strip(),
    }
    if req.width and req.height:
        payload["width"] = req.width
        payload["height"] = req.height
        payload["size"] = modelscope_size(req.size or f"{req.width}x{req.height}")
    elif req.size:
        payload["size"] = modelscope_size(req.size)
    if req.image_urls:
        payload["image_url"] = [modelscope_image_url(url, max_size=1536) for url in req.image_urls]
    if req.loras is not None:
        payload["loras"] = req.loras

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            submit_res = await client.post(
                f"{base_url}v1/images/generations",
                headers=headers,
                json=payload
            )
            if submit_res.status_code != 200:
                try:
                    detail = submit_res.json()
                except:
                    detail = submit_res.text
                raise HTTPException(status_code=submit_res.status_code, detail=detail)

            task_id = submit_res.json().get("task_id")
            print(f"MS Generate Task submitted ({req.model}), ID: {task_id}")

            TERMINAL_FAILED_STATUSES = {"FAILED", "FAIL", "ERROR", "CANCELED", "CANCELLED", "TIMEOUT", "REVOKED"}

            for i in range(300):
                await asyncio.sleep(2)
                try:
                    result = await client.get(
                        f"{base_url}v1/tasks/{task_id}",
                        headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
                    )
                    data = result.json()
                    status = data.get("task_status")
                    print(f"MS Task {task_id} poll {i}: status={status}")

                    if status == "SUCCEED":
                        img_url = data["output_images"][0]
                        local_path = ""
                        try:
                            async with httpx.AsyncClient() as dl_client:
                                img_res = await dl_client.get(img_url)
                                if img_res.status_code == 200:
                                    filename = f"ms_{req.model.replace('/', '_').replace(':', '_')}_{int(time.time())}.png"
                                    file_path = output_path_for(filename, "output")
                                    with open(file_path, "wb") as f:
                                        f.write(img_res.content)
                                    local_path = output_url_for(filename, "output")
                                else:
                                    local_path = img_url
                        except Exception:
                            local_path = img_url

                        record = {
                            "timestamp": time.time(),
                            "prompt": req.prompt,
                            "images": [local_path],
                            "type": "klein",
                            "model": req.model,
                        }
                        save_to_history(record, owner_key=owner_key)
                        if GLOBAL_LOOP:
                            asyncio.run_coroutine_threadsafe(manager.broadcast_new_image(record), GLOBAL_LOOP)
                        return {"url": local_path, "task_id": task_id}

                    elif status in TERMINAL_FAILED_STATUSES:
                        error_info = data.get("error_info") or data.get("message") or data.get("detail") or str(data)
                        raise HTTPException(status_code=502, detail=f"MS task {status}: {error_info}")

                except HTTPException:
                    raise
                except Exception as loop_e:
                    print(f"MS polling error: {loop_e}")
                    continue

            raise HTTPException(status_code=504, detail="MS 生图超时")

    except HTTPException:
        raise
    except Exception as e:
        print(f"MS generate error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# --- 本地 ComfyUI 生图 ---

@app.post("/api/generate")
def generate(req: GenerateRequest, request: Request):
    user = require_current_user(request)
    ensure_direct_generate_allowed(req)
    return run_comfy_generate(req, owner_key=owner_key_from_user(user))

def normalize_seed_value(existing: Any, seed: int) -> int:
    if isinstance(existing, bool):
        return int(seed)
    if isinstance(existing, int) and existing >= 0 and existing <= 4294967295:
        mod = seed % 4294967295
        return mod if mod > 0 else 1
    return int(seed)

def apply_workflow_random_seed(workflow: Dict[str, Any], seed: int, params: Dict[str, Dict[str, Any]]):
    explicit_fields = set()
    for raw_node_id, raw_inputs in (params or {}).items():
        node_id = str(raw_node_id)
        if not isinstance(raw_inputs, dict):
            continue
        for raw_input_name in raw_inputs.keys():
            explicit_fields.add((node_id, str(raw_input_name).lower()))
    for raw_node_id, node in (workflow or {}).items():
        node_id = str(raw_node_id)
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name in list(inputs.keys()):
            input_name_lc = str(input_name).lower()
            if input_name_lc not in {"seed", "noise_seed"}:
                continue
            if (node_id, input_name_lc) in explicit_fields:
                continue
            inputs[input_name] = normalize_seed_value(inputs.get(input_name), seed)

AIDEN_WORKFLOW_BASENAME = "1-Aiden-极致真实摄影人像工作流-文生图-小白福音.json"
AIDEN_MAIN_PROMPT_NODE_ID = "25"
AIDEN_STAGE1_PROMPT_NODE_ID = "97"
AIDEN_STAGE2_PROMPT_NODE_ID = "110"
AIDEN_CAMERA_ASSIST_PROMPT = "<sks> front view eye-level shot medium shot"

def apply_aiden_prompt_mapping(workflow_name: str, workflow: Dict[str, Any], req: GenerateRequest):
    if os.path.basename(str(workflow_name or "")) != AIDEN_WORKFLOW_BASENAME:
        return

    user_prompt = ""
    node_inputs = (req.params or {}).get(AIDEN_MAIN_PROMPT_NODE_ID)
    if isinstance(node_inputs, dict):
        raw_prompt = node_inputs.get("prompt")
        if isinstance(raw_prompt, str):
            user_prompt = raw_prompt.strip()
    if not user_prompt and isinstance(req.prompt, str):
        user_prompt = req.prompt.strip()
    if not user_prompt:
        return

    main_node = workflow.get(AIDEN_MAIN_PROMPT_NODE_ID)
    if isinstance(main_node, dict):
        main_inputs = main_node.setdefault("inputs", {})
        if isinstance(main_inputs, dict):
            main_inputs["prompt"] = user_prompt

    stage1_node = workflow.get(AIDEN_STAGE1_PROMPT_NODE_ID)
    if isinstance(stage1_node, dict):
        stage1_inputs = stage1_node.setdefault("inputs", {})
        if isinstance(stage1_inputs, dict):
            stage1_inputs["prompt"] = user_prompt

    stage2_node = workflow.get(AIDEN_STAGE2_PROMPT_NODE_ID)
    if isinstance(stage2_node, dict):
        stage2_inputs = stage2_node.setdefault("inputs", {})
        if isinstance(stage2_inputs, dict):
            if AIDEN_CAMERA_ASSIST_PROMPT.lower() in user_prompt.lower():
                stage2_inputs["prompt"] = user_prompt
            else:
                stage2_inputs["prompt"] = f"{user_prompt}\n{AIDEN_CAMERA_ASSIST_PROMPT}"

def resolve_instance_override(instance: str, workflow_ref: Any) -> str:
    """校验管理员指定的试跑 worker：必须在 COMFYUI_INSTANCES 内，且不缺该 workflow 所需节点。"""
    addr = re.sub(r"^https?://", "", str(instance or "").strip()).rstrip("/")
    if not addr:
        raise HTTPException(status_code=400, detail="instance 不能为空")
    if addr not in COMFYUI_INSTANCES:
        raise HTTPException(status_code=400, detail=f"指定的 worker 不在已配置实例中：{addr}")
    required_class_types = collect_required_workflow_class_types(workflow_ref)
    if required_class_types:
        classes, object_info_error = get_backend_object_classes(addr)
        if classes is None:
            raise HTTPException(status_code=502, detail=f"worker {addr} 的 object_info 不可用：{object_info_error or '未知错误'}")
        missing = [node for node in required_class_types if node not in classes]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"worker {addr} 缺少该 workflow 所需节点：{summarize_required_nodes(missing)}",
            )
    return addr

def run_comfy_generate(req: GenerateRequest, owner_key: str = "", instance_override: str = ""):
    global NEXT_TASK_ID
    current_task = None
    target_backend = None
    with QUEUE_LOCK:
        task_id = NEXT_TASK_ID
        NEXT_TASK_ID += 1
        current_task = {"task_id": task_id, "client_id": req.client_id}
        QUEUE.append(current_task)

    try:
        required_images = collect_required_comfy_media(req.params)

        if instance_override:
            target_backend = resolve_instance_override(instance_override, req.workflow_json)
        else:
            target_backend = get_best_backend(required_images, req.workflow_json)
        with LOAD_LOCK:
            BACKEND_LOCAL_LOAD[target_backend] += 1

        for image_name in required_images:
            need_sync = False
            try:
                check_url = f"http://{target_backend}/view?filename={urllib.parse.quote(image_name)}&type=input"
                resp = requests.get(check_url, stream=True, timeout=0.5)
                resp.close()
                if resp.status_code != 200:
                    need_sync = True
            except:
                need_sync = True

            if need_sync:
                image_content = None
                image_type = "image/png"
                for addr in COMFYUI_INSTANCES:
                    if addr == target_backend: continue
                    try:
                        src_url = f"http://{addr}/view?filename={urllib.parse.quote(image_name)}&type=input"
                        r = requests.get(src_url, timeout=5)
                        if r.status_code == 200:
                            image_content = r.content
                            image_type = r.headers.get("Content-Type", "image/png")
                            break
                    except: continue

                if image_content:
                    try:
                        files = {'image': (image_name, image_content, image_type)}
                        requests.post(f"http://{target_backend}/upload/image", files=files, timeout=10)
                    except Exception as e:
                        print(f"Sync upload failed: {e}")

        workflow_name = str(req.workflow_json or "").strip()
        if os.path.isabs(workflow_name) or ".." in workflow_name.replace("\\", "/").split("/"):
            raise Exception(f"Invalid workflow file: {req.workflow_json}")
        workflow_path = os.path.join(WORKFLOW_DIR, workflow_name)
        if not os.path.exists(workflow_path) and req.workflow_json == "Z-Image.json":
            workflow_path = WORKFLOW_PATH
        if not os.path.exists(workflow_path):
            raise Exception(f"Workflow file not found: {req.workflow_json}")

        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
        # 过滤非节点的顶层键（如导出工具塞的 "_meta"）：ComfyUI 会把它们当节点而整单拒收
        workflow = {k: v for k, v in workflow.items() if isinstance(v, dict) and v.get('class_type')}

        seed = random.randint(1, 10**15)

        if "23" in workflow and req.prompt:
            workflow["23"]["inputs"]["text"] = req.prompt
        if "144" in workflow:
            workflow["144"]["inputs"]["width"] = req.width
            workflow["144"]["inputs"]["height"] = req.height

        apply_workflow_random_seed(workflow, seed, req.params)

        for node_id, node_inputs in req.params.items():
            if node_id in workflow:
                if "inputs" not in workflow[node_id]:
                    workflow[node_id]["inputs"] = {}
                for input_name, value in node_inputs.items():
                    workflow[node_id]["inputs"][input_name] = value
        apply_aiden_prompt_mapping(workflow_name, workflow, req)

        p = {"prompt": workflow, "client_id": req.client_id or CLIENT_ID}
        data = json.dumps(p).encode('utf-8')
        try:
            post_req = urllib.request.Request(f"http://{target_backend}/prompt", data=data)
            prompt_id = json.loads(urllib.request.urlopen(post_req, timeout=10).read())['prompt_id']
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"HTTP Error {e.code}: {error_body}")

        history_data = None
        for i in range(COMFYUI_HISTORY_TIMEOUT):
            try:
                res = get_comfy_history(target_backend, prompt_id)
                if prompt_id in res:
                    history_data = res[prompt_id]
                    break
            except Exception:
                pass
            time.sleep(1)

        if not history_data:
            raise Exception("ComfyUI 渲染超时")
        comfy_error = comfy_execution_error_from_history(history_data)
        if comfy_error:
            raise Exception(comfy_error)

        local_images = []
        local_videos = []
        local_audios = []
        local_texts = []
        local_files = []
        local_items = []
        local_urls = []
        current_timestamp = time.time()
        if 'outputs' in history_data:
            for node_id in history_data['outputs']:
                node_output = history_data['outputs'][node_id]
                for output_key, item in collect_comfy_file_items(node_output):
                    prefix = f"{req.type}_{int(current_timestamp)}_"
                    kind = comfy_output_kind(item)
                    local_path = download_comfy_output(target_backend, item, prefix=prefix)
                    if kind == "image" and req.convert_to_jpg:
                        local_path = convert_output_to_jpg(local_path)
                    name = os.path.basename(str(item.get("filename") or "")) or os.path.basename(str(local_path).split("?", 1)[0])
                    entry = {
                        "url": local_path,
                        "kind": kind,
                        "name": name,
                        "node_id": str(node_id),
                        "output_key": str(output_key),
                    }
                    if kind == "image":
                        local_images.append(local_path)
                    elif kind == "video":
                        local_videos.append(local_path)
                    elif kind == "audio":
                        local_audios.append(local_path)
                    elif kind == "text":
                        local_texts.append(local_path)
                    else:
                        local_files.append(local_path)
                    local_items.append(entry)
                    local_urls.append(local_path)
                for text, name in comfy_text_values_from_output(node_output):
                    prefix = f"{req.type}_{int(current_timestamp)}_"
                    local_path = save_comfy_text_output(text, prefix=prefix, name=name)
                    entry = {
                        "url": local_path,
                        "kind": "text",
                        "name": os.path.basename(str(local_path).split("?", 1)[0]),
                        "node_id": str(node_id),
                        "output_key": "text",
                    }
                    local_texts.append(local_path)
                    local_items.append(entry)
                    local_urls.append(local_path)

        result = {
            "prompt": req.prompt if req.prompt else "Detail Enhance",
            "images": local_images,
            "videos": local_videos,
            "audios": local_audios,
            "texts": local_texts,
            "files": local_files,
            "items": local_items,
            "outputs": local_urls,
            "seed": seed,
            "timestamp": current_timestamp,
            "type": req.type,
            "workflow_json": req.workflow_json,
            "task_id": task_id,
            "prompt_id": prompt_id,
            "backend": target_backend,
            "params": req.params
        }
        save_to_history(result, owner_key=owner_key)
        if GLOBAL_LOOP:
            asyncio.run_coroutine_threadsafe(manager.broadcast_new_image(result), GLOBAL_LOOP)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        if target_backend:
            with LOAD_LOCK:
                if BACKEND_LOCAL_LOAD.get(target_backend, 0) > 0:
                    BACKEND_LOCAL_LOAD[target_backend] -= 1
        if current_task:
            with QUEUE_LOCK:
                if current_task in QUEUE:
                    QUEUE.remove(current_task)

# --- ComfyUI 工作流管理 ---

BUILTIN_WORKFLOWS = {"Z-Image.json", "Z-Image-Enhance.json", "2511.json", "klein-enhance.json", "Flux2-Klein.json", "upscale.json"}
CUSTOM_WORKFLOW_FOLDER = "custom"
LEGACY_CUSTOM_WORKFLOW_FOLDER = "自定义"
# 60 盘共享 workflow 目录（compose 把 SMB 盘只读挂载到 workflows/shared）：
# 只读来源，配置/跑通记录写到 data/workflow-configs/shared/，平台内不可删除
SHARED_WORKFLOW_FOLDER = "shared"
WORKFLOW_NAME_RE = re.compile(rf"^(?:(?:{CUSTOM_WORKFLOW_FOLDER}|{LEGACY_CUSTOM_WORKFLOW_FOLDER}|{SHARED_WORKFLOW_FOLDER})/)?[a-zA-Z0-9_一-龥\.\-]+\.json$")
LTX_PUBLIC_WORKFLOW_NAME = "LTXDirectorv2-API.json"
LTX_PUBLIC_NODE_ID = "46"

class WorkflowField(BaseModel):
    id: str
    node: str = ""
    input: str = ""
    name: str = ""
    type: str = "text"
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: List[str] = Field(default_factory=list)
    random_enabled: bool = False
    required: bool = False
    enabled: bool = True
    hidden: bool = False

class WorkflowConfig(BaseModel):
    title: str = ""
    description: str = ""
    category: str = ""
    thumbnail: str = ""
    enabled: bool = True
    fields: List[WorkflowField] = Field(default_factory=list)
    mini_cards: Dict[str, Any] = Field(default_factory=dict)
    # 最近一次成功运行记录（时间/worker/参数快照），由后端在 run 成功后自动写入；
    # 客户端 PUT config 不带该字段时保留旧值
    last_test: Optional[Dict[str, Any]] = None

class WorkflowUploadRequest(BaseModel):
    name: str
    workflow: Dict[str, Any]

class WorkflowImportPlanRequest(BaseModel):
    source_type: str = "workflow_json"  # workflow_json | runninghub_ref
    source_value: str = ""
    workflow_json: Dict[str, Any] = Field(default_factory=dict)
    workflow_name: str = ""
    save_workflow: bool = True

class WorkflowInstallTaskRequest(BaseModel):
    actions: List[Dict[str, Any]] = Field(default_factory=list)

class WorkflowAutoModelDownloadsRequest(BaseModel):
    actions: List[Dict[str, Any]] = Field(default_factory=list)

class WorkflowModelCandidatesRequest(BaseModel):
    action: Dict[str, Any] = Field(default_factory=dict)
    model_name: str = ""
    value: str = ""
    category: str = ""

    class Config:
        extra = "allow"

class WorkflowRunRequest(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)
    config: Optional[WorkflowConfig] = None
    client_id: str = ""
    # 管理员试跑时可指定目标 worker（host:port，须在 COMFYUI_INSTANCES 内）；普通用户忽略该字段走自动调度
    instance: str = ""

def workflow_path_from_name(name: str) -> str:
    if not WORKFLOW_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid workflow name")
    path = os.path.abspath(os.path.join(WORKFLOW_DIR, *name.split("/")))
    workflow_root = os.path.abspath(WORKFLOW_DIR)
    if os.path.commonpath([workflow_root, path]) != workflow_root:
        raise HTTPException(status_code=400, detail="Invalid workflow name")
    return path

def is_shared_workflow(name: str) -> bool:
    return str(name or "").startswith(f"{SHARED_WORKFLOW_FOLDER}/")

def workflow_config_path(name: str) -> str:
    path = workflow_path_from_name(name)
    if is_shared_workflow(name):
        # 共享目录是只读 SMB 挂载，配置写到平台 data/ 下
        cfg_name = os.path.basename(path).replace(".json", ".config.json")
        return os.path.join(DATA_DIR, "workflow-configs", SHARED_WORKFLOW_FOLDER, cfg_name)
    return path.replace(".json", ".config.json")

def is_builtin_workflow(name: str) -> bool:
    return "/" not in name and os.path.basename(name) in BUILTIN_WORKFLOWS

def workflow_default_title(name: str) -> str:
    return os.path.basename(name).replace(".json", "")

def is_admin_request(request: Request) -> bool:
    user = getattr(request.state, "current_user", None)
    return bool(user and user.get("is_admin"))

def workflow_field_from_raw(raw) -> Optional[WorkflowField]:
    if hasattr(raw, "dict"):
        raw = raw.dict()
    if not isinstance(raw, dict):
        return None
    try:
        data = dict(raw)
        data["id"] = str(data.get("id") or data.get("fieldId") or data.get("key") or "").strip()
        if not data["id"]:
            node = str(data.get("node") or data.get("nodeId") or data.get("node_id") or "").strip()
            input_name = str(data.get("input") or data.get("fieldName") or data.get("inputName") or "").strip()
            data["id"] = f"{node}::{input_name}" if node or input_name else f"f_{uuid.uuid4().hex[:8]}"
        data["node"] = str(data.get("node") or data.get("nodeId") or data.get("node_id") or "").strip()
        data["input"] = str(data.get("input") or data.get("fieldName") or data.get("inputName") or "").strip()
        data["name"] = str(data.get("name") or data.get("label") or data["input"] or data["id"]).strip()
        data["type"] = str(data.get("type") or data.get("fieldType") or "text").strip().lower()
        if data["type"] == "switch":
            data["type"] = "boolean"
        if data["type"] not in {"text", "textarea", "number", "slider", "dropdown", "image", "video", "audio", "boolean"}:
            data["type"] = "text"
        options = data.get("options") or []
        if isinstance(options, str):
            options = [item.strip() for item in re.split(r"[\r\n,]+", options) if item.strip()]
        elif isinstance(options, list):
            options = [str(item).strip() for item in options if str(item).strip()]
        else:
            options = []
        data["options"] = options
        return WorkflowField(**data)
    except Exception:
        return None

def workflow_config_from_raw(name: str, raw=None) -> WorkflowConfig:
    raw = raw if isinstance(raw, dict) else {}
    # 共享盘 workflow 未配置时默认停用：必须经管理员确认参数并发布后才进画布
    default_enabled = not is_shared_workflow(name)
    enabled_value = raw.get("enabled", default_enabled)
    if enabled_value is None:
        enabled_value = default_enabled
    fields = [
        field for field in (workflow_field_from_raw(item) for item in (raw.get("fields") or []))
        if field is not None
    ]
    cfg = WorkflowConfig(
        title=str(raw.get("title") or workflow_default_title(name)),
        description=str(raw.get("description") or ""),
        category=str(raw.get("category") or ""),
        thumbnail=str(raw.get("thumbnail") or ""),
        enabled=bool(enabled_value),
        fields=fields,
        mini_cards=raw.get("mini_cards") if isinstance(raw.get("mini_cards"), dict) else {},
        last_test=raw.get("last_test") if isinstance(raw.get("last_test"), dict) else None,
    )
    return cfg

def load_workflow_config(name: str) -> WorkflowConfig:
    cfg_path = workflow_config_path(name)
    if not os.path.exists(cfg_path):
        return workflow_config_from_raw(name)
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw = json.load(f) or {}
        return workflow_config_from_raw(name, raw)
    except Exception:
        return workflow_config_from_raw(name)

def save_workflow_config_data(name: str, cfg: WorkflowConfig):
    cfg_path = workflow_config_path(name)
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg.dict(), f, ensure_ascii=False, indent=2)

def record_workflow_last_test(name: str, user: Dict[str, Any], result: Dict[str, Any], run_fields: Dict[str, Any]):
    """workflow 运行成功后记录「最近跑通」信息，供 ComfyTV 工作台显示。失败不影响主流程。"""
    try:
        fields_snapshot: Dict[str, Any] = {}
        for key, value in (run_fields or {}).items():
            if isinstance(value, (int, float, bool)) or value is None:
                fields_snapshot[str(key)] = value
            else:
                fields_snapshot[str(key)] = str(value)[:300]
        cfg = load_workflow_config(name)
        cfg.last_test = {
            "ok": True,
            "at": now_ts(),
            "by": str(user.get("username") or ""),
            "backend": str(result.get("backend") or ""),
            "output_count": len(result.get("outputs") or []),
            "fields": fields_snapshot,
        }
        save_workflow_config_data(name, cfg)
    except Exception as e:
        print(f"记录 workflow last_test 失败 [{name}]: {e}")

def comfy_is_link_value(value) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)

def comfy_guess_field_type(value, input_name: str) -> str:
    lc = str(input_name or "").lower()
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "slider" if re.search(r"strength|cfg|denoise", lc) else "number"
    if isinstance(value, str):
        if re.search(r"prompt|text|description", lc) or len(value) > 60:
            return "textarea"
        if re.search(r"video|movie|mp4|webm|mov|m4v|vhs", lc) or re.search(r"\.(mp4|webm|mov|m4v|avi|mkv)(\?|$)", value, re.I):
            return "video"
        if re.search(r"audio|sound|music|voice|wav|mp3", lc) or re.search(r"\.(mp3|wav|m4a|aac|ogg|flac)(\?|$)", value, re.I):
            return "audio"
        if re.search(r"image|img|mask|filename|file", lc) or re.search(r"\.(png|jpe?g|webp|gif|bmp|tiff?)(\?|$)", value, re.I):
            return "image"
    return "text"

MODEL_DEPENDENCY_EXACT_KEYS = {
    "model",
    "vae",
    "clip",
    "unet",
    "controlnet",
    "ckpt_name",
    "lora_name",
    "vae_name",
    "control_net_name",
    "controlnet_name",
    "unet_name",
    "clip_name",
    "clip_name1",
    "clip_name2",
    "model_name",
    "diffusion_model",
    "diffusion_model_name",
    "checkpoint",
    "checkpoint_name",
}
MODEL_DEPENDENCY_EXCLUDED_KEYS = {
    "filename_prefix",
    "sampler_name",
    "scheduler",
    "upscale_method",
    "crop",
    "device",
    "type",
    "strength_model",
    "strength_clip",
    "strength",
}
MODEL_DEPENDENCY_KEY_RE = re.compile(r"(?:^|[_-])(model|checkpoint|ckpt|lora|vae|control[_-]?net|unet|clip)(?:$|[_-])", re.I)
MODEL_DEPENDENCY_STATUS_PENDING = "待确认"
MODEL_DEPENDENCY_STATUS_EXISTS = "exists"
MODEL_DEPENDENCY_STATUS_MISSING = "missing"
MODEL_DEPENDENCY_STATUS_UNKNOWN = "unknown"
MODEL_DEPENDENCY_FILE_EXTS = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".bin",
    ".gguf",
}
MODELSCOPE_MODEL_HOSTS = {"modelscope.cn", "www.modelscope.cn"}
MODEL_CANDIDATE_SOURCE_PRIORITY = {
    "modelscope": 0,
    "huggingface": 1,
    "ai": 2,
}
MODEL_DEPENDENCY_CATEGORY_DIRS = {
    "checkpoints": ["checkpoints"],
    "loras": ["loras"],
    "vae": ["vae"],
    "clip": ["clip"],
    "unet": ["unet"],
    "controlnet": ["controlnet"],
    "upscale_models": ["upscale_models"],
}
WORKFLOW_INSTALL_TASK_LOCK = Lock()
WORKFLOW_INSTALL_TASKS: Dict[str, Dict[str, Any]] = {}
WORKFLOW_INSTALL_ACTION_STATUSES = {"ready", "running", "needs_url", "needs_repo", "blocked", "skipped", "done", "failed"}
CUSTOM_NODES_ENV_KEYS = ("AITOOL_COMFYUI_CUSTOM_NODES_DIR", "COMFYUI_CUSTOM_NODES_DIR")
GITHUB_REPO_RE = re.compile(r"^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$")
RUNNINGHUB_POST_RE = re.compile(r"/post/([0-9A-Za-z_-]+)", re.I)
RUNNINGHUB_WORKFLOW_RUN_RE = re.compile(r"/run/workflow/([0-9A-Za-z_-]+)", re.I)
RUNNINGHUB_NUMERIC_ID_RE = re.compile(r"^[0-9]{8,}$")

def normalize_resource_root_path(value: Any) -> str:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    expanded = os.path.expanduser(text)
    return os.path.abspath(expanded)

def get_resource_root_config() -> Dict[str, Any]:
    for key in RESOURCE_ROOT_ENV_KEYS:
        raw = str(os.getenv(key, "") or "").strip()
        if raw:
            return {
                "resource_root": normalize_resource_root_path(raw),
                "source": key,
                "configured": True,
            }
    return {"resource_root": "", "source": "", "configured": False}

def resource_root_safe_join(root_abs: str, relative_path: str) -> str:
    rel = str(relative_path or "").replace("\\", "/").strip().strip("/")
    target = os.path.abspath(os.path.join(root_abs, *rel.split("/"))) if rel else root_abs
    if os.path.commonpath([root_abs, target]) != root_abs:
        raise ValueError(f"路径越界：{relative_path}")
    return target

def inspect_resource_root(resource_root: str, create_missing: bool = False) -> Dict[str, Any]:
    root_abs = normalize_resource_root_path(resource_root)
    result: Dict[str, Any] = {
        "resource_root": root_abs,
        "configured": bool(root_abs),
        "exists": False,
        "is_dir": False,
        "readable": False,
        "writable": False,
        "available": False,
        "status": "unconfigured",
        "message": "资源盘未配置",
        "disk": {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0},
        "suggested_subdirs": [],
    }
    if not root_abs:
        return result

    exists = os.path.exists(root_abs)
    is_dir = os.path.isdir(root_abs)
    readable = bool(exists and is_dir and os.access(root_abs, os.R_OK))
    writable = bool(exists and is_dir and os.access(root_abs, os.W_OK))
    result.update({
        "exists": exists,
        "is_dir": is_dir,
        "readable": readable,
        "writable": writable,
        "available": bool(exists and is_dir and readable),
    })
    if not exists:
        result["status"] = "missing"
        result["message"] = "资源盘路径不存在"
    elif not is_dir:
        result["status"] = "invalid"
        result["message"] = "资源盘路径不是目录"
    elif not readable:
        result["status"] = "unreadable"
        result["message"] = "资源盘不可读"
    else:
        result["status"] = "ok"
        result["message"] = "资源盘可访问"
        try:
            usage = shutil.disk_usage(root_abs)
            result["disk"] = {
                "total_bytes": int(usage.total),
                "used_bytes": int(usage.used),
                "free_bytes": int(usage.free),
            }
        except Exception as exc:
            result["disk_error"] = str(exc)[:180]

    created_count = 0
    missing_count = 0
    for rel in RESOURCE_ROOT_SUGGESTED_SUBDIRS:
        abs_path = resource_root_safe_join(root_abs, rel)
        entry = {
            "relative_path": rel,
            "path": abs_path,
            "exists": False,
            "is_dir": False,
            "readable": False,
            "writable": False,
            "status": "missing",
            "created": False,
            "error": "",
        }
        if create_missing and result["available"] and writable and not os.path.exists(abs_path):
            try:
                os.makedirs(abs_path, exist_ok=True)
                entry["created"] = True
                created_count += 1
            except Exception as exc:
                entry["error"] = str(exc)[:180]
                entry["status"] = "error"
        exists_sub = os.path.exists(abs_path)
        is_dir_sub = os.path.isdir(abs_path)
        readable_sub = bool(exists_sub and is_dir_sub and os.access(abs_path, os.R_OK))
        writable_sub = bool(exists_sub and is_dir_sub and os.access(abs_path, os.W_OK))
        entry.update({
            "exists": exists_sub,
            "is_dir": is_dir_sub,
            "readable": readable_sub,
            "writable": writable_sub,
        })
        if entry["status"] != "error":
            if not exists_sub:
                entry["status"] = "missing"
                missing_count += 1
            elif not is_dir_sub:
                entry["status"] = "invalid"
            elif readable_sub:
                entry["status"] = "ok"
            else:
                entry["status"] = "unreadable"
        result["suggested_subdirs"].append(entry)

    result["summary"] = {
        "subdir_total": len(result["suggested_subdirs"]),
        "subdir_missing": missing_count,
        "subdir_created": created_count,
    }
    return result

def infer_model_dependency_category(input_key: str) -> str:
    key = str(input_key or "").lower()
    if "lora" in key:
        return "loras"
    if "vae" in key:
        return "vae"
    if "control_net" in key or "controlnet" in key:
        return "controlnet"
    if "unet" in key or "diffusion_model" in key:
        return "unet"
    if "clip" in key:
        return "clip"
    if "upscale" in key:
        return "upscale_models"
    return "checkpoints"

def normalize_model_lookup_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/").split("?")[0].split("#")[0]
    return os.path.basename(text).strip()

def build_resource_model_file_index(resource_root: str) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    root_abs = normalize_resource_root_path(resource_root)
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    by_stem: Dict[str, List[Dict[str, Any]]] = {}
    for category, subdirs in MODEL_DEPENDENCY_CATEGORY_DIRS.items():
        for subdir in subdirs:
            base_dir = resource_root_safe_join(root_abs, f"models/{subdir}")
            if not os.path.isdir(base_dir):
                continue
            for walk_root, _, files in os.walk(base_dir):
                for filename in files:
                    if os.path.splitext(filename)[1].lower() not in MODEL_DEPENDENCY_FILE_EXTS:
                        continue
                    full_path = os.path.join(walk_root, filename)
                    rel_path = os.path.relpath(full_path, root_abs).replace("\\", "/")
                    item = {
                        "path": full_path,
                        "relative_path": rel_path,
                        "category": category,
                        "filename": filename,
                    }
                    key = filename.lower()
                    by_name.setdefault(key, []).append(item)
                    stem = os.path.splitext(filename)[0].lower()
                    if stem:
                        by_stem.setdefault(stem, []).append(item)
    return {"by_name": by_name, "by_stem": by_stem}

def detect_model_dependencies_in_resource_root(
    model_dependencies: List[Dict[str, Any]],
    resource_root_state: Dict[str, Any],
) -> Dict[str, Any]:
    dependencies = [dict(item or {}) for item in (model_dependencies or [])]
    if not dependencies:
        return {"items": [], "summary": {"total": 0, "exists": 0, "missing": 0, "unknown": 0}}

    if not resource_root_state.get("configured"):
        reason = "资源盘未配置"
        items = []
        for dep in dependencies:
            dep.update({
                "status": MODEL_DEPENDENCY_STATUS_UNKNOWN,
                "exists": False,
                "path": "",
                "category": dep.get("category") or infer_model_dependency_category(dep.get("input_key")),
                "note": reason,
            })
            items.append(dep)
        return {"items": items, "summary": {"total": len(items), "exists": 0, "missing": 0, "unknown": len(items), "reason": reason}}

    if not resource_root_state.get("available"):
        reason = "资源盘不可访问"
        items = []
        for dep in dependencies:
            dep.update({
                "status": MODEL_DEPENDENCY_STATUS_UNKNOWN,
                "exists": False,
                "path": "",
                "category": dep.get("category") or infer_model_dependency_category(dep.get("input_key")),
                "note": reason,
            })
            items.append(dep)
        return {"items": items, "summary": {"total": len(items), "exists": 0, "missing": 0, "unknown": len(items), "reason": reason}}

    root_abs = str(resource_root_state.get("resource_root") or "").strip()
    index = build_resource_model_file_index(root_abs)
    by_name = index["by_name"]
    by_stem = index["by_stem"]
    counts = {"exists": 0, "missing": 0, "unknown": 0}
    detected_items = []
    for dep in dependencies:
        input_key = dep.get("input_key")
        category = dep.get("category") or infer_model_dependency_category(input_key)
        lookup_name = normalize_model_lookup_name(dep.get("value"))
        dep["category"] = category
        dep["lookup_name"] = lookup_name
        if not lookup_name:
            dep.update({
                "status": MODEL_DEPENDENCY_STATUS_UNKNOWN,
                "exists": False,
                "path": "",
                "note": "模型值为空或无法解析文件名",
            })
            counts["unknown"] += 1
            detected_items.append(dep)
            continue
        candidates = list(by_name.get(lookup_name.lower(), []))
        if not candidates:
            stem = os.path.splitext(lookup_name)[0].lower()
            if stem:
                candidates = list(by_stem.get(stem, []))
        if candidates:
            preferred = next((item for item in candidates if item.get("category") == category), candidates[0])
            dep.update({
                "status": MODEL_DEPENDENCY_STATUS_EXISTS,
                "exists": True,
                "path": preferred.get("path") or "",
                "relative_path": preferred.get("relative_path") or "",
                "note": "已在 60 盘找到同名模型",
            })
            counts["exists"] += 1
        else:
            dep.update({
                "status": MODEL_DEPENDENCY_STATUS_MISSING,
                "exists": False,
                "path": "",
                "note": "60 盘未找到同名模型",
            })
            counts["missing"] += 1
        detected_items.append(dep)
    return {
        "items": detected_items,
        "summary": {
            "total": len(detected_items),
            "exists": counts["exists"],
            "missing": counts["missing"],
            "unknown": counts["unknown"],
        },
    }

def looks_like_comfy_api_workflow(workflow_json: Any) -> bool:
    if not isinstance(workflow_json, dict) or not workflow_json:
        return False
    sample = next(iter(workflow_json.values()), None)
    if not isinstance(sample, dict):
        return False
    return bool(sample.get("class_type") or sample.get("classType") or sample.get("type"))

COMFY_UI_SEED_CONTROL_VALUES = {"fixed", "randomize", "increment", "decrement"}

def looks_like_comfy_ui_workflow(workflow_json: Any) -> bool:
    if not isinstance(workflow_json, dict):
        return False
    nodes = workflow_json.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return False
    return any(isinstance(node, dict) and node.get("id") is not None and node.get("type") for node in nodes)

def comfy_ui_link_key(value: Any) -> str:
    return str(value)

def comfy_ui_link_from_raw(raw_link: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw_link, dict):
        link_id = raw_link.get("id")
        origin_id = raw_link.get("origin_id", raw_link.get("from_node_id", raw_link.get("source_node_id")))
        origin_slot = raw_link.get("origin_slot", raw_link.get("from_socket", raw_link.get("source_slot", 0)))
        target_id = raw_link.get("target_id", raw_link.get("to_node_id"))
        target_slot = raw_link.get("target_slot", raw_link.get("to_socket"))
    elif isinstance(raw_link, list) and len(raw_link) >= 5:
        link_id, origin_id, origin_slot, target_id, target_slot = raw_link[:5]
    else:
        return None
    if link_id is None or origin_id is None:
        return None
    return {
        "id": link_id,
        "origin_id": origin_id,
        "origin_slot": origin_slot if origin_slot is not None else 0,
        "target_id": target_id,
        "target_slot": target_slot,
    }

def comfy_ui_node_id(node: Dict[str, Any]) -> str:
    return str(node.get("id"))

def comfy_ui_input_name(input_def: Dict[str, Any]) -> str:
    widget = input_def.get("widget")
    if isinstance(widget, dict) and widget.get("name"):
        return str(widget.get("name"))
    return str(input_def.get("name") or "")

def comfy_ui_input_link(input_def: Dict[str, Any]) -> Any:
    link = input_def.get("link")
    if link is None:
        link = input_def.get("links")
    if isinstance(link, list):
        return link[0] if link else None
    return link

def comfy_ui_resolve_link_value(
    link_id: Any,
    link_by_id: Dict[str, Dict[str, Any]],
    node_by_id: Dict[str, Dict[str, Any]],
    visited: Optional[set] = None,
) -> Optional[List[Any]]:
    key = comfy_ui_link_key(link_id)
    if key in (visited or set()):
        return None
    visited = set(visited or set())
    visited.add(key)
    link = link_by_id.get(key)
    if not link:
        return None
    origin_node_id = str(link.get("origin_id"))
    origin_slot = link.get("origin_slot", 0)
    origin_node = node_by_id.get(origin_node_id)
    if isinstance(origin_node, dict) and str(origin_node.get("type") or "").lower() == "reroute":
        for input_def in origin_node.get("inputs") or []:
            if not isinstance(input_def, dict):
                continue
            upstream_link_id = comfy_ui_input_link(input_def)
            if upstream_link_id is None:
                continue
            resolved = comfy_ui_resolve_link_value(upstream_link_id, link_by_id, node_by_id, visited)
            if resolved:
                return resolved
        return None
    return [origin_node_id, origin_slot]

def comfy_ui_should_skip_seed_control(widget_name: str, next_value: Any, next_widget_name: str) -> bool:
    if str(widget_name or "").lower() not in {"seed", "noise_seed"}:
        return False
    if str(next_widget_name or "").lower() == "control_after_generate":
        return False
    return isinstance(next_value, str) and next_value.lower() in COMFY_UI_SEED_CONTROL_VALUES

def comfy_ui_workflow_to_api_prompt(workflow_json: Any) -> Optional[Dict[str, Any]]:
    if not looks_like_comfy_ui_workflow(workflow_json):
        return None

    nodes = [node for node in workflow_json.get("nodes") or [] if isinstance(node, dict)]
    node_by_id = {comfy_ui_node_id(node): node for node in nodes if node.get("id") is not None}
    link_by_id: Dict[str, Dict[str, Any]] = {}
    for raw_link in workflow_json.get("links") or []:
        link = comfy_ui_link_from_raw(raw_link)
        if link:
            link_by_id[comfy_ui_link_key(link.get("id"))] = link

    prompt: Dict[str, Any] = {}
    for node in nodes:
        node_id = comfy_ui_node_id(node)
        class_type = node.get("type")
        if not node_id or not class_type or str(class_type).lower() == "reroute":
            continue

        inputs: Dict[str, Any] = {}
        input_defs = [item for item in (node.get("inputs") or []) if isinstance(item, dict)]
        widget_values = node.get("widgets_values")
        if not isinstance(widget_values, list):
            widget_values = []
        widget_input_names = [
            comfy_ui_input_name(input_def)
            for input_def in input_defs
            if isinstance(input_def.get("widget"), dict) and comfy_ui_input_name(input_def)
        ]
        widget_input_index = 0
        widget_value_index = 0

        for input_def in input_defs:
            input_name = comfy_ui_input_name(input_def)
            if not input_name:
                continue

            has_widget = isinstance(input_def.get("widget"), dict) and bool(input_name)
            widget_value = None
            widget_value_available = False
            next_widget_name = ""
            if has_widget:
                if widget_value_index < len(widget_values):
                    widget_value = widget_values[widget_value_index]
                    widget_value_available = True
                    widget_value_index += 1
                    if widget_input_index + 1 < len(widget_input_names):
                        next_widget_name = widget_input_names[widget_input_index + 1]
                    if (
                        widget_value_index < len(widget_values)
                        and comfy_ui_should_skip_seed_control(input_name, widget_values[widget_value_index], next_widget_name)
                    ):
                        widget_value_index += 1
                widget_input_index += 1

            link_id = comfy_ui_input_link(input_def)
            if link_id is not None:
                resolved_link = comfy_ui_resolve_link_value(link_id, link_by_id, node_by_id)
                if resolved_link:
                    inputs[input_name] = resolved_link
                continue
            if widget_value_available:
                inputs[input_name] = widget_value

        title = node.get("title") or class_type
        prompt[node_id] = {
            "class_type": class_type,
            "inputs": inputs,
            "_meta": {"title": str(title)},
        }

    return prompt or None

def normalize_comfy_api_workflow_payload(workflow_json: Any) -> Optional[Dict[str, Any]]:
    if looks_like_comfy_api_workflow(workflow_json):
        return workflow_json
    ui_prompt = comfy_ui_workflow_to_api_prompt(workflow_json)
    if ui_prompt:
        return ui_prompt
    if isinstance(workflow_json, dict):
        prompt_payload = workflow_json.get("prompt")
        if looks_like_comfy_api_workflow(prompt_payload):
            return prompt_payload
        ui_prompt = comfy_ui_workflow_to_api_prompt(prompt_payload)
        if ui_prompt:
            return ui_prompt
        workflow_payload = workflow_json.get("workflow_json")
        if looks_like_comfy_api_workflow(workflow_payload):
            return workflow_payload
        ui_prompt = comfy_ui_workflow_to_api_prompt(workflow_payload)
        if ui_prompt:
            return ui_prompt
        workflow_payload = workflow_json.get("workflow")
        if looks_like_comfy_api_workflow(workflow_payload):
            return workflow_payload
        ui_prompt = comfy_ui_workflow_to_api_prompt(workflow_payload)
        if ui_prompt:
            return ui_prompt
    return None

def normalize_custom_workflow_filename(raw_name: str, fallback: str = "imported-workflow") -> str:
    value = os.path.basename(str(raw_name or "").strip())
    value = re.sub(r"\.json$", "", value, flags=re.I)
    value = re.sub(r"[^a-zA-Z0-9_一-龥\.\-]+", "-", value).strip(" .-_")
    value = value or fallback
    if len(value) > 80:
        value = value[:80].rstrip(" .-_")
    return f"{value}.json"

def parse_runninghub_workflow_ref(value: str) -> Dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {"ok": False, "kind": "empty", "message": "请输入 RunningHub URL 或 workflowId"}
    post_match = RUNNINGHUB_POST_RE.search(text)
    if post_match:
        return {"ok": True, "kind": "post", "post_id": post_match.group(1), "raw": text}
    run_match = RUNNINGHUB_WORKFLOW_RUN_RE.search(text)
    if run_match:
        return {"ok": True, "kind": "workflow", "workflow_id": run_match.group(1), "raw": text}
    if RUNNINGHUB_NUMERIC_ID_RE.match(text):
        return {"ok": True, "kind": "workflow", "workflow_id": text, "raw": text}
    try:
        parsed = urllib.parse.urlparse(text)
    except Exception:
        parsed = None
    if parsed and parsed.path:
        run_match = RUNNINGHUB_WORKFLOW_RUN_RE.search(parsed.path)
        if run_match:
            return {"ok": True, "kind": "workflow", "workflow_id": run_match.group(1), "raw": text}
        post_match = RUNNINGHUB_POST_RE.search(parsed.path)
        if post_match:
            return {"ok": True, "kind": "post", "post_id": post_match.group(1), "raw": text}
        path = parsed.path.strip("/").strip()
        if RUNNINGHUB_NUMERIC_ID_RE.match(path):
            return {"ok": True, "kind": "workflow", "workflow_id": path, "raw": text}
    return {"ok": False, "kind": "unknown", "raw": text, "message": "仅支持 /post/{id}、/run/workflow/{id} 或纯数字 workflowId"}

async def fetch_runninghub_workflow_json_by_id(workflow_id: str):
    key = runninghub_workflow_store_key(workflow_id)
    if not key:
        raise HTTPException(status_code=400, detail="workflowId 必填")
    provider = runninghub_provider()
    api_key = runninghub_api_key(provider)
    url = runninghub_endpoint_url(provider, "/api/openapi/getJsonApiFormat")
    body = {"apiKey": api_key, "workflowId": key}
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=180.0, write=60.0, pool=20.0)) as client:
        try:
            response = await client.post(url, headers=runninghub_app_headers(True), json=body)
            raw = response.json()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"拉取 RunningHub 工作流参数失败：{exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=json.dumps(raw, ensure_ascii=False)[:800])
    if not isinstance(raw, dict) or raw.get("code") not in (0, "0"):
        raise HTTPException(status_code=400, detail=(raw.get("msg") if isinstance(raw, dict) else "") or f"RunningHub 工作流参数拉取失败：{raw}")
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    prompt = data.get("prompt")
    workflow_json = {}
    if isinstance(prompt, str) and prompt.strip():
        try:
            workflow_json = json.loads(prompt)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"RunningHub 工作流 JSON 解析失败：{exc}") from exc
    elif isinstance(prompt, dict):
        workflow_json = prompt
    payload = normalize_comfy_api_workflow_payload(workflow_json)
    if not payload:
        raise HTTPException(status_code=400, detail="RunningHub 返回的 workflow 不是有效的 ComfyUI API 工作流（缺少 class_type）")
    return key, payload, raw

def collect_workflow_model_dependencies(workflow_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    dependencies: Dict[tuple, Dict[str, Any]] = {}
    for node_id, node_content in (workflow_json or {}).items():
        if not isinstance(node_content, dict):
            continue
        inputs = node_content.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name, raw_value in inputs.items():
            if comfy_is_link_value(raw_value):
                continue
            input_key = str(input_name or "")
            input_key_lc = input_key.lower()
            if input_key_lc in MODEL_DEPENDENCY_EXCLUDED_KEYS:
                continue
            if input_key_lc not in MODEL_DEPENDENCY_EXACT_KEYS and not MODEL_DEPENDENCY_KEY_RE.search(input_key_lc):
                continue
            if raw_value is None:
                continue
            if isinstance(raw_value, (dict, list)):
                value = json.dumps(raw_value, ensure_ascii=False)
            else:
                value = str(raw_value).strip()
            if not value:
                continue
            dep_key = (input_key_lc, value)
            if dep_key not in dependencies:
                dependencies[dep_key] = {
                    "input_key": input_key,
                    "value": value,
                    "category": infer_model_dependency_category(input_key),
                    "status": MODEL_DEPENDENCY_STATUS_PENDING,
                    "exists": None,
                    "path": "",
                    "note": "待检测 60 盘资源中心",
                    "nodes": [],
                }
            dependencies[dep_key]["nodes"].append(str(node_id))
    items = list(dependencies.values())
    items.sort(key=lambda item: (item["input_key"].lower(), item["value"]))
    return items

def collect_instance_node_compatibility(required_class_types: List[str]) -> List[Dict[str, Any]]:
    results = []
    for addr in COMFYUI_INSTANCES:
        classes, object_info_error = get_backend_object_classes(addr)
        if not classes:
            results.append({
                "address": addr,
                "compatible": False,
                "available": False,
                "missing_nodes": required_class_types,
                "object_info_error": object_info_error or "object_info 返回为空",
            })
            continue
        missing_nodes = [node for node in required_class_types if node not in classes]
        results.append({
            "address": addr,
            "compatible": not missing_nodes,
            "available": True,
            "missing_nodes": missing_nodes,
            "object_info_error": "",
        })
    return results

def build_workflow_import_plan_items(
    saved_name: str,
    compatibility: List[Dict[str, Any]],
    model_dependencies: List[Dict[str, Any]],
    resource_root_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    steps = []
    if saved_name:
        steps.append(f"已保存工作流：{saved_name}（默认未启用）")
    else:
        steps.append("本次仅做预检分析，未写入工作流文件")
    compatible_instances = [item for item in compatibility if item.get("compatible")]
    if compatible_instances:
        steps.append(f"节点兼容：{len(compatible_instances)}/{len(compatibility)} 台实例可直接运行")
    else:
        steps.append("节点兼容：暂无实例完全兼容，请先补齐缺失自定义节点")
    if model_dependencies:
        if resource_root_state and resource_root_state.get("available"):
            exists_items = [item for item in model_dependencies if item.get("status") == MODEL_DEPENDENCY_STATUS_EXISTS]
            missing_items = [item for item in model_dependencies if item.get("status") == MODEL_DEPENDENCY_STATUS_MISSING]
            unknown_items = [item for item in model_dependencies if item.get("status") == MODEL_DEPENDENCY_STATUS_UNKNOWN]
            steps.append(f"模型依赖：共 {len(model_dependencies)} 项（已存在 {len(exists_items)}，缺失 {len(missing_items)}，未知 {len(unknown_items)}）")
            if exists_items:
                sample = "、".join([str(item.get("value") or "") for item in exists_items[:3]])
                steps.append(f"60 盘已存在：{sample}" + (" 等" if len(exists_items) > 3 else ""))
            if missing_items:
                sample = "、".join([str(item.get("value") or "") for item in missing_items[:3]])
                steps.append(f"60 盘缺失：{sample}" + (" 等" if len(missing_items) > 3 else ""))
            if unknown_items:
                steps.append("部分模型状态未知：请检查模型字段值是否为有效文件名")
        elif resource_root_state and resource_root_state.get("configured"):
            steps.append(f"模型依赖：识别到 {len(model_dependencies)} 项（资源盘不可访问，暂无法检测存在性）")
            steps.append("人工事项：先确认 60 盘挂载可读，再重新执行导入预检")
        else:
            steps.append(f"模型依赖：识别到 {len(model_dependencies)} 项，状态均为“待确认”")
            steps.append("人工事项：先配置 60 盘资源根目录，再重新执行导入预检")
    else:
        steps.append("模型依赖：未识别到常见模型字段，建议人工复查")
    steps.append("安全边界：不会执行任意 shell 命令；仅在安装计划中按白名单动作下载模型或 git clone")
    return steps

def workflow_install_task_snapshot(task_id: str) -> Dict[str, Any]:
    with WORKFLOW_INSTALL_TASK_LOCK:
        task = WORKFLOW_INSTALL_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="安装任务不存在")
        return json.loads(json.dumps(task, ensure_ascii=False))

def workflow_install_update_task(task_id: str, **updates):
    with WORKFLOW_INSTALL_TASK_LOCK:
        task = WORKFLOW_INSTALL_TASKS.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at"] = now_utc_iso()

def workflow_install_log(task_id: str, message: str):
    with WORKFLOW_INSTALL_TASK_LOCK:
        task = WORKFLOW_INSTALL_TASKS.get(task_id)
        if not task:
            return
        task.setdefault("logs", []).append({"time": now_utc_iso(), "message": str(message or "")})
        task["updated_at"] = now_utc_iso()

def workflow_install_append_result(task_id: str, result: Dict[str, Any]):
    with WORKFLOW_INSTALL_TASK_LOCK:
        task = WORKFLOW_INSTALL_TASKS.get(task_id)
        if not task:
            return
        task.setdefault("results", []).append(result)
        task["updated_at"] = now_utc_iso()

def workflow_install_update_action(task_id: str, action_id: str, **updates):
    if not action_id:
        return
    with WORKFLOW_INSTALL_TASK_LOCK:
        task = WORKFLOW_INSTALL_TASKS.get(task_id)
        if not task:
            return
        for item in task.get("actions") or []:
            if str(item.get("id") or "") == str(action_id):
                item.update(updates)
                break
        task["updated_at"] = now_utc_iso()

def workflow_install_update_action_progress(
    task_id: str,
    action_id: str,
    progress: Dict[str, Any],
    action_status: str = "",
    note: str = "",
):
    if not action_id:
        return
    safe_progress = dict(progress or {})
    safe_progress.setdefault("downloaded_bytes", 0)
    safe_progress.setdefault("total_bytes", None)
    safe_progress.setdefault("percent", None)
    safe_progress.setdefault("speed_bytes_per_sec", 0)
    safe_progress.setdefault("phase", safe_progress.get("status") or "")
    safe_progress.setdefault("status", safe_progress.get("phase") or action_status or "")
    safe_progress.setdefault("target_relative_path", "")
    safe_progress["updated_at"] = now_utc_iso()
    with WORKFLOW_INSTALL_TASK_LOCK:
        task = WORKFLOW_INSTALL_TASKS.get(task_id)
        if not task:
            return
        task.setdefault("progress", {})[str(action_id)] = safe_progress
        for item in task.get("actions") or []:
            if str(item.get("id") or "") == str(action_id):
                item["progress"] = safe_progress
                if action_status:
                    item["status"] = action_status
                if note:
                    item["note"] = note
                break
        task["updated_at"] = safe_progress["updated_at"]

def workflow_install_action_id(prefix: str, value: Any) -> str:
    raw = str(value or "")
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{prefix}_{digest}"

def inspect_custom_nodes_dir() -> Dict[str, Any]:
    selected_source = ""
    selected_path = ""
    for key in CUSTOM_NODES_ENV_KEYS:
        raw = str(os.getenv(key, "") or "").strip()
        if raw:
            selected_source = key
            selected_path = normalize_resource_root_path(raw)
            break
    state = {
        "path": selected_path,
        "source": selected_source,
        "configured": bool(selected_path),
        "exists": False,
        "is_dir": False,
        "writable": False,
        "available": False,
        "message": "custom_nodes 目录未配置",
    }
    if not selected_path:
        return state
    exists = os.path.exists(selected_path)
    is_dir = os.path.isdir(selected_path)
    writable = bool(exists and is_dir and os.access(selected_path, os.W_OK))
    state.update({
        "exists": exists,
        "is_dir": is_dir,
        "writable": writable,
        "available": writable,
    })
    if not exists:
        state["message"] = "custom_nodes 目录不存在"
    elif not is_dir:
        state["message"] = "custom_nodes 路径不是目录"
    elif not writable:
        state["message"] = "custom_nodes 目录不可写"
    else:
        state["message"] = "custom_nodes 目录可写"
    return state

def workflow_model_target_from_dependency(dep: Dict[str, Any], resource_root: str) -> Dict[str, str]:
    category = str(dep.get("category") or "").strip()
    if category not in MODEL_DEPENDENCY_CATEGORY_DIRS:
        raise ValueError(f"模型分类不支持：{category or '-'}")
    filename = normalize_model_lookup_name(dep.get("lookup_name") or dep.get("value") or "")
    if not filename or filename in {".", ".."}:
        raise ValueError("模型文件名为空或不合法")
    if "/" in filename or "\\" in filename:
        raise ValueError("模型文件名不允许包含路径分隔符")
    category_dir = MODEL_DEPENDENCY_CATEGORY_DIRS[category][0]
    relative_path = f"models/{category_dir}/{filename}"
    target_path = resource_root_safe_join(resource_root, relative_path)
    return {"target_path": target_path, "target_relative_path": relative_path, "filename": filename}

def build_workflow_install_plan(
    compatibility: List[Dict[str, Any]],
    model_dependencies: List[Dict[str, Any]],
    resource_root_state: Dict[str, Any],
) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    resource_root = str(resource_root_state.get("resource_root") or "").strip()
    resource_ready = bool(resource_root_state.get("available") and resource_root_state.get("writable"))
    for dep in model_dependencies or []:
        dep_status = str(dep.get("status") or "")
        if dep_status not in {MODEL_DEPENDENCY_STATUS_MISSING, MODEL_DEPENDENCY_STATUS_UNKNOWN, MODEL_DEPENDENCY_STATUS_EXISTS}:
            continue
        action = {
            "id": workflow_install_action_id("model", f"{dep.get('category')}:{dep.get('input_key')}:{dep.get('value')}"),
            "type": "model_download",
            "title": str(dep.get("value") or dep.get("lookup_name") or dep.get("input_key") or "模型文件"),
            "status": "needs_url",
            "executable": False,
            "source_url": "",
            "target_path": "",
            "target_relative_path": "",
            "category": str(dep.get("category") or infer_model_dependency_category(dep.get("input_key"))),
            "value": str(dep.get("value") or ""),
            "note": str(dep.get("note") or ""),
        }
        if dep_status == MODEL_DEPENDENCY_STATUS_EXISTS:
            action.update({
                "status": "skipped",
                "target_path": str(dep.get("path") or ""),
                "target_relative_path": str(dep.get("relative_path") or ""),
                "note": "模型已存在，无需下载",
            })
            actions.append(action)
            continue
        if not resource_ready:
            action.update({
                "status": "blocked",
                "note": resource_root_state.get("message") or "资源根目录未配置或不可写",
            })
            actions.append(action)
            continue
        try:
            target = workflow_model_target_from_dependency(action, resource_root)
            action.update({
                "target_path": target["target_path"],
                "target_relative_path": target["target_relative_path"],
            })
            if os.path.exists(target["target_path"]):
                action.update({"status": "skipped", "note": "目标文件已存在，无需下载"})
        except Exception as exc:
            action.update({"status": "blocked", "note": str(exc)})
        actions.append(action)

    missing_class_types = sorted({
        str(class_type or "").strip()
        for item in compatibility or []
        for class_type in (item.get("missing_nodes") or [])
        if str(class_type or "").strip()
    })
    custom_nodes_state = inspect_custom_nodes_dir()
    for class_type in missing_class_types:
        note = "填写对应 GitHub 仓库 URL 后，可克隆到 custom_nodes"
        if not custom_nodes_state.get("available"):
            note = f"{note}；当前{custom_nodes_state.get('message') or 'custom_nodes 不可用'}"
        actions.append({
            "id": workflow_install_action_id("custom", class_type),
            "type": "custom_node_install",
            "title": class_type,
            "status": "needs_repo",
            "executable": False,
            "repo_url": "",
            "target_path": "",
            "class_type": class_type,
            "note": note,
        })

    summary = {
        "action_count": len(actions),
        "model_download_count": sum(1 for item in actions if item.get("type") == "model_download"),
        "custom_node_install_count": sum(1 for item in actions if item.get("type") == "custom_node_install"),
    }
    return {
        "actions": actions,
        "summary": summary,
        "resource_root": resource_root_state,
        "custom_nodes": custom_nodes_state,
    }

def validate_http_download_url(url: Any) -> str:
    text = str(url or "").strip()
    try:
        parsed = urllib.parse.urlparse(text)
    except Exception:
        parsed = None
    if not parsed or parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("下载 URL 仅支持 http/https")
    if parsed.username or parsed.password:
        raise ValueError("下载 URL 不允许包含用户名或密码")
    return text

def is_modelscope_model_host(hostname: str) -> bool:
    return str(hostname or "").lower() in MODELSCOPE_MODEL_HOSTS

def modelscope_api_repo_file_path(parsed: urllib.parse.ParseResult) -> str:
    query = urllib.parse.parse_qs(parsed.query or "", keep_blank_values=True)
    values = query.get("FilePath") or query.get("filepath") or []
    return urllib.parse.unquote(str(values[0] or "")).strip() if values else ""

def model_candidate_download_filename(url: Any) -> str:
    text = str(url or "").strip()
    try:
        parsed = urllib.parse.urlparse(text)
    except Exception:
        parsed = None
    if parsed and is_modelscope_model_host(parsed.hostname or ""):
        path = urllib.parse.unquote(parsed.path or "")
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 6 and parts[:3] == ["api", "v1", "models"] and parts[5] == "repo":
            file_path = modelscope_api_repo_file_path(parsed)
            return os.path.basename(file_path.rstrip("/")).strip()
    return normalize_model_lookup_name(text)

def model_candidate_source_from_url(url: Any, default_source: str = "ai") -> str:
    try:
        parsed = urllib.parse.urlparse(str(url or "").strip())
    except Exception:
        parsed = None
    if parsed and is_modelscope_model_host(parsed.hostname or ""):
        return "modelscope"
    return default_source

def model_download_candidate_score(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0

def model_download_candidate_sort_key(item: Dict[str, Any]):
    source = str((item or {}).get("source") or "").strip().lower()
    priority = MODEL_CANDIDATE_SOURCE_PRIORITY.get(source, 9)
    score = model_download_candidate_score((item or {}).get("score"))
    title = str((item or {}).get("title") or (item or {}).get("filename") or "").lower()
    return (priority, -score, title)

def validate_model_candidate_download_url(url: Any, target_filename: str = "") -> str:
    text = validate_http_download_url(url)
    parsed = urllib.parse.urlparse(text)
    path = urllib.parse.unquote(parsed.path or "")
    host = (parsed.hostname or "").lower()
    basename = model_candidate_download_filename(text)
    ext = os.path.splitext(basename.lower())[1]
    target_name = normalize_model_lookup_name(target_filename)
    if not basename or ext not in MODEL_DEPENDENCY_FILE_EXTS:
        raise ValueError(f"候选 URL 不是支持的模型文件下载链接：{target_name or basename or '-'}")

    if host == "huggingface.co":
        parts = [part for part in path.split("/") if part]
        if len(parts) < 5 or parts[2] != "resolve":
            raise ValueError("Hugging Face 候选 URL 必须指向 resolve 文件下载路径")
        if not parts[0] or not parts[1] or not parts[3]:
            raise ValueError("Hugging Face 候选 URL 缺少仓库或 revision")
        if not "/".join(parts[4:]).strip():
            raise ValueError("Hugging Face 候选 URL 缺少模型文件路径")
    elif is_modelscope_model_host(host):
        parts = [part for part in path.split("/") if part]
        is_resolve_file = (
            len(parts) >= 6
            and parts[0] == "models"
            and parts[3] == "resolve"
            and bool(parts[1])
            and bool(parts[2])
            and bool(parts[4])
            and bool("/".join(parts[5:]).strip())
        )
        is_repo_api_file = (
            len(parts) == 6
            and parts[:3] == ["api", "v1", "models"]
            and bool(parts[3])
            and bool(parts[4])
            and parts[5] == "repo"
            and bool(modelscope_api_repo_file_path(parsed))
        )
        if not is_resolve_file and not is_repo_api_file:
            raise ValueError("ModelScope 候选 URL 必须指向 resolve 文件路径或 repo FilePath 下载接口")
    return text

def workflow_model_candidate_filename(action: Dict[str, Any]) -> str:
    for key in ("model_name", "value", "title", "lookup_name", "target_relative_path"):
        filename = normalize_model_lookup_name(action.get(key))
        if filename:
            return filename
    return ""

def workflow_model_candidate_query(action: Dict[str, Any]) -> str:
    filename = workflow_model_candidate_filename(action)
    if filename:
        return os.path.splitext(filename)[0] or filename
    for key in ("model_name", "value", "title"):
        text = str(action.get(key) or "").strip()
        if text:
            return text[:120]
    return ""

def workflow_model_candidate_request_action(payload: WorkflowModelCandidatesRequest) -> Dict[str, Any]:
    raw = payload.dict() if hasattr(payload, "dict") else {}
    action = dict(raw.get("action") or {})
    for key in ("id", "type", "title", "value", "category", "lookup_name", "model_name"):
        if key in raw and raw.get(key) not in (None, "") and key not in action:
            action[key] = raw.get(key)
    if payload.model_name:
        action["model_name"] = payload.model_name
    if payload.value:
        action["value"] = payload.value
    if payload.category:
        action["category"] = payload.category
    return action

def workflow_model_action_target_filename(action: Dict[str, Any]) -> str:
    for key in ("target_relative_path", "model_name", "value", "title", "lookup_name"):
        filename = normalize_model_lookup_name((action or {}).get(key))
        if filename and os.path.splitext(filename.lower())[1] in MODEL_DEPENDENCY_FILE_EXTS:
            return filename
    return workflow_model_candidate_filename(action)

def workflow_auto_model_target_skip_reason(action: Dict[str, Any], target_filename: str) -> str:
    raw = target_filename or workflow_model_candidate_filename(action)
    if not raw:
        return "无法解析目标模型文件名"
    ext = os.path.splitext(str(raw).lower())[1]
    if ext not in MODEL_DEPENDENCY_FILE_EXTS:
        return "目标名不是支持的模型文件后缀，已跳过一键下载"
    return ""

def workflow_install_find_model_candidates_for_action(action: Dict[str, Any]) -> Dict[str, Any]:
    target_filename = workflow_model_action_target_filename(action)
    query = workflow_model_candidate_query({**(action or {}), "model_name": target_filename or (action or {}).get("model_name")})
    errors: List[str] = []
    candidates: List[Dict[str, Any]] = []
    try:
        ms_candidates, ms_errors = find_modelscope_model_candidates(query, target_filename)
        candidates.extend(ms_candidates)
        errors.extend(ms_errors)
    except Exception as exc:
        errors.append(f"ModelScope 候选处理失败：{exc}")
    try:
        hf_candidates, hf_errors = find_huggingface_model_candidates(query, target_filename)
        candidates.extend(hf_candidates)
        errors.extend(hf_errors)
    except Exception as exc:
        errors.append(f"Hugging Face 候选处理失败：{exc}")
    if not candidates:
        try:
            ai_candidates, ai_errors = find_ai_model_candidates(action, query, target_filename)
            candidates.extend(ai_candidates)
            errors.extend(ai_errors)
        except Exception as exc:
            errors.append(f"AI 候选处理失败：{exc}")

    safe_candidates = []
    seen_urls = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        try:
            url = validate_model_candidate_download_url(item.get("url"), target_filename)
        except Exception:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            score = int(item.get("score") or 0)
        except Exception:
            score = 0
        safe_candidates.append({
            "source": str(item.get("source") or "unknown")[:40],
            "title": str(item.get("title") or item.get("filename") or target_filename or url)[:180],
            "url": url,
            "repo": str(item.get("repo") or "")[:180],
            "filename": str(item.get("filename") or model_candidate_download_filename(url) or "")[:180],
            "score": score,
            "note": str(item.get("note") or "")[:300],
        })
    safe_candidates.sort(key=model_download_candidate_sort_key)
    message = "找到候选下载链接" if safe_candidates else "未找到候选下载链接，请手动填写 URL"
    return {
        "candidates": safe_candidates[:8],
        "query": query,
        "target_filename": target_filename,
        "errors": errors,
        "message": message,
    }

def select_high_confidence_model_candidate(
    candidates: List[Dict[str, Any]],
    target_filename: str,
) -> Optional[Dict[str, Any]]:
    target = os.path.basename(str(target_filename or "")).strip().lower()
    if not target or os.path.splitext(target)[1] not in MODEL_DEPENDENCY_FILE_EXTS:
        return None
    exact_candidates = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        if model_download_candidate_score(item.get("score")) < 100:
            continue
        try:
            url = validate_model_candidate_download_url(item.get("url"), target_filename)
        except Exception:
            continue
        url_filename = os.path.basename(model_candidate_download_filename(url)).strip().lower()
        candidate_filename = os.path.basename(
            normalize_model_lookup_name(item.get("filename")) or model_candidate_download_filename(url)
        ).strip().lower()
        if url_filename != target or candidate_filename != target:
            continue
        exact_candidates.append({**item, "url": url})
    exact_candidates.sort(key=model_download_candidate_sort_key)
    return exact_candidates[0] if exact_candidates else None

def model_file_candidate_score(filename: str, target_filename: str) -> int:
    name = os.path.basename(str(filename or "")).strip()
    target = os.path.basename(str(target_filename or "")).strip()
    name_lc = name.lower()
    target_lc = target.lower()
    if not name_lc or os.path.splitext(name_lc)[1] not in MODEL_DEPENDENCY_FILE_EXTS:
        return 0
    if target_lc and name_lc == target_lc:
        return 100
    stem = os.path.splitext(target_lc)[0]
    name_stem = os.path.splitext(name_lc)[0]
    if stem and name_stem == stem:
        return 88
    if stem and (stem in name_stem or name_stem in stem):
        return 72
    if target_lc and os.path.splitext(name_lc)[1] == os.path.splitext(target_lc)[1]:
        return 45
    return 35

def hf_model_file_candidate_score(filename: str, target_filename: str) -> int:
    return model_file_candidate_score(filename, target_filename)

def modelscope_model_file_candidate_score(filename: str, target_filename: str) -> int:
    return model_file_candidate_score(filename, target_filename)

def modelscope_repo_id_from_item(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("id", "model_id", "ModelId", "ModelID", "modelId", "RepoId", "repo"):
        value = str(item.get(key) or "").strip().strip("/")
        if "/" in value:
            return value
    backend = item.get("BackendSupport")
    if isinstance(backend, dict):
        value = str(backend.get("model_id") or "").strip().strip("/")
        if "/" in value:
            return value
    owner = str(item.get("Path") or item.get("Owner") or item.get("owner") or item.get("path") or "").strip().strip("/")
    name = str(item.get("Name") or item.get("name") or "").strip().strip("/")
    if owner and name:
        return f"{owner}/{name}"
    return ""

def modelscope_repo_revision_from_item(repo_item: Dict[str, Any]) -> str:
    if isinstance(repo_item, dict):
        for key in ("Revision", "revision", "DefaultRevision", "default_revision", "DefaultBranch", "default_branch"):
            value = str(repo_item.get(key) or "").strip().strip("/")
            if value:
                return value
    return "master"

def modelscope_files_from_payload(payload: Any) -> List[Dict[str, Any]]:
    data = payload
    if isinstance(data, dict) and "Data" in data:
        data = data.get("Data")
    if isinstance(data, dict):
        for key in ("Files", "files", "RepoFiles", "repo_files"):
            files = data.get(key)
            if isinstance(files, list):
                return [item for item in files if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []

def modelscope_model_download_candidates_from_api(
    repos: List[Dict[str, Any]],
    repo_files: Dict[str, Any],
    target_filename: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    candidates = []
    seen = set()
    for repo_item in repos or []:
        repo_id = modelscope_repo_id_from_item(repo_item)
        if not repo_id:
            continue
        revision = modelscope_repo_revision_from_item(repo_item)
        files = modelscope_files_from_payload((repo_files or {}).get(repo_id))
        for file_item in files:
            file_path = str(
                file_item.get("Path")
                or file_item.get("path")
                or file_item.get("FilePath")
                or file_item.get("rfilename")
                or file_item.get("Name")
                or file_item.get("name")
                or ""
            ).strip().lstrip("/")
            if not file_path:
                continue
            if str(file_item.get("Type") or file_item.get("type") or "").lower() == "tree":
                continue
            filename = os.path.basename(file_path.rstrip("/")).strip()
            score = modelscope_model_file_candidate_score(filename, target_filename)
            if score <= 0:
                continue
            quoted_repo = urllib.parse.quote(repo_id, safe="/")
            quoted_revision = urllib.parse.quote(revision or "master", safe="")
            quoted_file = urllib.parse.quote(file_path, safe="/")
            url = f"https://www.modelscope.cn/models/{quoted_repo}/resolve/{quoted_revision}/{quoted_file}"
            try:
                url = validate_model_candidate_download_url(url, target_filename)
            except Exception:
                continue
            key = (repo_id.lower(), file_path.lower())
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "source": "modelscope",
                "title": filename,
                "url": url,
                "repo": repo_id,
                "filename": filename,
                "score": score,
                "note": "ModelScope 仓库文件匹配",
            })
    candidates.sort(key=model_download_candidate_sort_key)
    return candidates[:limit]

def modelscope_repo_ids_from_query(query: str) -> List[str]:
    seen = set()
    repo_ids = []
    text = str(query or "")

    def add_repo_id(value: str):
        repo_id = str(value or "").strip().strip("/")
        if repo_id and repo_id.lower() not in seen:
            seen.add(repo_id.lower())
            repo_ids.append(repo_id)

    for url in re.findall(r"https?://[^\s\"'<>，。)）]+", text):
        try:
            parsed = urllib.parse.urlparse(url.rstrip(".,;"))
        except Exception:
            parsed = None
        if not parsed or not is_modelscope_model_host(parsed.hostname or ""):
            continue
        parts = [part for part in urllib.parse.unquote(parsed.path or "").split("/") if part]
        if len(parts) >= 3 and parts[0] == "models":
            add_repo_id(f"{parts[1]}/{parts[2]}")
            text = text.replace(url, " ")
        elif len(parts) >= 5 and parts[:3] == ["api", "v1", "models"]:
            add_repo_id(f"{parts[3]}/{parts[4]}")
            text = text.replace(url, " ")

    for match in re.findall(r"(?<![\w.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?![\w.-])", text):
        add_repo_id(match)
    return repo_ids

def modelscope_search_repos(query: str, limit: int = 8) -> (List[Dict[str, Any]], List[str]):
    if not query:
        return [], ["模型名称为空，无法搜索 ModelScope"]
    try:
        response = requests.put(
            "https://www.modelscope.cn/api/v1/models/",
            data=json.dumps({"Name": query, "PageNumber": 1, "PageSize": limit}),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=(8, 20),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("Data") if isinstance(payload, dict) else None
        repos = data.get("Models") if isinstance(data, dict) else None
        if not isinstance(repos, list):
            return [], ["ModelScope 搜索响应格式不是模型列表"]
        return [item for item in repos if isinstance(item, dict)], []
    except Exception as exc:
        return [], [f"ModelScope 搜索失败：{exc}"]

def modelscope_fetch_repo_detail(repo_id: str) -> Dict[str, Any]:
    detail_response = requests.get(
        f"https://www.modelscope.cn/api/v1/models/{urllib.parse.quote(repo_id, safe='/')}",
        headers={"Accept": "application/json"},
        timeout=(8, 20),
    )
    detail_response.raise_for_status()
    detail_payload = detail_response.json()
    if isinstance(detail_payload, dict) and isinstance(detail_payload.get("Data"), dict):
        return detail_payload["Data"]
    return {}

def modelscope_fetch_repo_files(repo_id: str, revision: str, root: str = "") -> List[Dict[str, Any]]:
    params = {"Revision": revision or "master"}
    if root:
        params["Root"] = root
    files_response = requests.get(
        f"https://www.modelscope.cn/api/v1/models/{urllib.parse.quote(repo_id, safe='/')}/repo/files",
        params=params,
        headers={"Accept": "application/json"},
        timeout=(8, 20),
    )
    files_response.raise_for_status()
    return modelscope_files_from_payload(files_response.json())

def find_modelscope_model_candidates(query: str, target_filename: str) -> (List[Dict[str, Any]], List[str]):
    errors = []
    if not query:
        return [], ["模型名称为空，无法搜索 ModelScope"]

    repos: List[Dict[str, Any]] = []
    seen_repos = set()
    for repo_id in modelscope_repo_ids_from_query(query):
        try:
            detail = modelscope_fetch_repo_detail(repo_id)
            detail.setdefault("id", repo_id)
            repos.append(detail)
            seen_repos.add(repo_id.lower())
        except Exception as exc:
            errors.append(f"ModelScope 仓库读取失败 {repo_id}：{exc}")

    search_repos, search_errors = modelscope_search_repos(query, limit=8)
    errors.extend(search_errors)
    for item in search_repos:
        repo_id = modelscope_repo_id_from_item(item)
        if not repo_id or repo_id.lower() in seen_repos:
            continue
        repos.append(item)
        seen_repos.add(repo_id.lower())

    if not repos:
        if not errors:
            errors.append("ModelScope 未找到可用仓库候选")
        return [], errors

    repo_files: Dict[str, Any] = {}
    hydrated_repos: List[Dict[str, Any]] = []
    for item in repos[:8]:
        repo_id = modelscope_repo_id_from_item(item)
        if not repo_id:
            continue
        repo_item = dict(item)
        try:
            detail = modelscope_fetch_repo_detail(repo_id)
            if detail:
                repo_item.update(detail)
                repo_item.setdefault("id", repo_id)
        except Exception as exc:
            errors.append(f"ModelScope 仓库读取失败 {repo_id}：{exc}")
        revision = modelscope_repo_revision_from_item(repo_item)
        try:
            files = modelscope_fetch_repo_files(repo_id, revision)
            tree_roots = [
                str(file_item.get("Path") or file_item.get("Name") or "").strip().strip("/")
                for file_item in files
                if str(file_item.get("Type") or "").lower() == "tree"
            ]
            for root in [root for root in tree_roots if root][:12]:
                try:
                    files.extend(modelscope_fetch_repo_files(repo_id, revision, root=root))
                except Exception as exc:
                    errors.append(f"ModelScope 仓库目录读取失败 {repo_id}/{root}：{exc}")
            repo_files[repo_id] = files
            hydrated_repos.append(repo_item)
        except Exception as exc:
            errors.append(f"ModelScope 仓库文件读取失败 {repo_id}：{exc}")

    return modelscope_model_download_candidates_from_api(hydrated_repos, repo_files, target_filename), errors

def hf_model_download_candidates_from_api(
    repos: List[Dict[str, Any]],
    repo_details: Dict[str, Dict[str, Any]],
    target_filename: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    candidates = []
    seen = set()
    for repo_item in repos or []:
        repo_id = str(repo_item.get("id") or repo_item.get("modelId") or "").strip()
        if not repo_id:
            continue
        detail = repo_details.get(repo_id) or {}
        siblings = detail.get("siblings") if isinstance(detail, dict) else []
        for sibling in siblings or []:
            filename = str((sibling or {}).get("rfilename") or (sibling or {}).get("name") or "").strip()
            score = hf_model_file_candidate_score(filename, target_filename)
            if score <= 0:
                continue
            quoted_repo = urllib.parse.quote(repo_id, safe="/")
            quoted_file = urllib.parse.quote(filename, safe="/")
            url = f"https://huggingface.co/{quoted_repo}/resolve/main/{quoted_file}?download=true"
            try:
                url = validate_model_candidate_download_url(url, target_filename)
            except Exception:
                continue
            key = (repo_id.lower(), filename.lower())
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "source": "huggingface",
                "title": filename,
                "url": url,
                "repo": repo_id,
                "filename": filename,
                "score": score,
                "note": "Hugging Face 仓库文件匹配",
            })
    candidates.sort(key=model_download_candidate_sort_key)
    return candidates[:limit]

def find_huggingface_model_candidates(query: str, target_filename: str) -> (List[Dict[str, Any]], List[str]):
    errors = []
    if not query:
        return [], ["模型名称为空，无法搜索 Hugging Face"]
    try:
        response = requests.get(
            "https://huggingface.co/api/models",
            params={"search": query, "limit": 8, "full": "false"},
            headers={"Accept": "application/json"},
            timeout=(8, 20),
        )
        response.raise_for_status()
        repos = response.json()
        if not isinstance(repos, list):
            return [], ["Hugging Face 搜索响应格式不是列表"]
    except Exception as exc:
        return [], [f"Hugging Face 搜索失败：{exc}"]

    repo_details: Dict[str, Dict[str, Any]] = {}
    for item in repos[:8]:
        repo_id = str((item or {}).get("id") or (item or {}).get("modelId") or "").strip()
        if not repo_id:
            continue
        try:
            detail_response = requests.get(
                f"https://huggingface.co/api/models/{urllib.parse.quote(repo_id, safe='/')}",
                headers={"Accept": "application/json"},
                timeout=(8, 20),
            )
            detail_response.raise_for_status()
            detail = detail_response.json()
            if isinstance(detail, dict):
                repo_details[repo_id] = detail
        except Exception as exc:
            errors.append(f"Hugging Face 仓库读取失败 {repo_id}：{exc}")
    return hf_model_download_candidates_from_api(repos, repo_details, target_filename), errors

def parse_ai_model_candidate_urls(text: str, target_filename: str) -> List[Dict[str, Any]]:
    candidates = []
    seen = set()
    raw_text = str(text or "")
    json_payload = None
    json_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw_text, re.S)
    json_text = json_match.group(1) if json_match else raw_text.strip()
    try:
        json_payload = json.loads(json_text)
    except Exception:
        json_payload = None
    items = []
    if isinstance(json_payload, dict):
        items = json_payload.get("candidates") or json_payload.get("urls") or []
    elif isinstance(json_payload, list):
        items = json_payload
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                parsed_item = {"url": item}
            elif isinstance(item, dict):
                parsed_item = item
            else:
                continue
            url = str(parsed_item.get("url") or "").strip()
            try:
                url = validate_model_candidate_download_url(url, target_filename)
            except Exception:
                continue
            if url in seen:
                continue
            seen.add(url)
            filename = normalize_model_lookup_name(parsed_item.get("filename")) or model_candidate_download_filename(url)
            source = model_candidate_source_from_url(url, "ai")
            candidates.append({
                "source": source,
                "title": str(parsed_item.get("title") or filename or target_filename or "AI 候选链接").strip()[:160],
                "url": url,
                "repo": str(parsed_item.get("repo") or "").strip()[:160],
                "filename": filename,
                "score": int(parsed_item.get("score") or 20) if str(parsed_item.get("score") or "").isdigit() else 20,
                "note": "ModelScope 直链候选（AI 建议，需确认）" if source == "modelscope" else "AI 建议，需确认",
            })
    for url in re.findall(r"https?://[^\s\"'<>，。)）]+", raw_text):
        try:
            url = validate_model_candidate_download_url(url.rstrip(".,;"), target_filename)
        except Exception:
            continue
        if url in seen:
            continue
        seen.add(url)
        filename = model_candidate_download_filename(url)
        source = model_candidate_source_from_url(url, "ai")
        candidates.append({
            "source": source,
            "title": filename or target_filename or "AI 候选链接",
            "url": url,
            "repo": "",
            "filename": filename,
            "score": 20,
            "note": "ModelScope 直链候选（AI 建议，需确认）" if source == "modelscope" else "AI 建议，需确认",
        })
    return candidates[:5]

def find_ai_model_candidates(action: Dict[str, Any], query: str, target_filename: str) -> (List[Dict[str, Any]], List[str]):
    errors = []
    providers = load_api_providers()
    providers = [item for item in providers if item.get("enabled", True) and item.get("chat_models")]
    providers.sort(key=lambda item: (not bool(item.get("primary")), item.get("id") != "modelscope"))
    prompt = (
        "Find likely public direct download URLs for this ComfyUI model dependency. "
        "Return JSON only: {\"candidates\":[{\"title\":\"\",\"url\":\"https://...\",\"repo\":\"\",\"filename\":\"\",\"score\":20}]}. "
        "Only include http or https URLs. Do not invent local paths.\n"
        f"Model filename: {target_filename or query}\n"
        f"Category: {action.get('category') or '-'}\n"
    )
    for provider in providers[:3]:
        provider_id = provider.get("id") or ""
        try:
            chat_base, chat_hdrs, model = resolve_chat_provider(provider_id, "", "")
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You return concise JSON for model download URL candidates."},
                    {"role": "user", "content": prompt},
                ],
            }
            if provider_id != "modelscope" and is_apimart_provider(provider):
                body["stream"] = False
            response = requests.post(
                f"{chat_base}/chat/completions",
                headers=chat_hdrs,
                json=body,
                timeout=(8, 30),
            )
            response.raise_for_status()
            text = text_from_chat_response(response.json())
            candidates = parse_ai_model_candidate_urls(text, target_filename)
            if candidates:
                return candidates, errors
            errors.append(f"{provider.get('name') or provider_id} 未返回可解析候选")
        except Exception as exc:
            errors.append(f"{provider.get('name') or provider_id} AI 候选失败：{exc}")
    if not providers:
        errors.append("未配置可用的 LLM chat provider，已跳过 AI 候选")
    return [], errors

def validate_github_repo_url(url: Any) -> str:
    text = str(url or "").strip()
    try:
        parsed = urllib.parse.urlparse(text)
    except Exception:
        parsed = None
    if not parsed or parsed.scheme.lower() != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("自定义节点仓库仅支持 https://github.com/owner/repo")
    if parsed.username or parsed.password:
        raise ValueError("GitHub URL 不允许包含用户名或密码")
    if not GITHUB_REPO_RE.match(parsed.path or ""):
        raise ValueError("GitHub 仓库 URL 格式不合法")
    owner, repo = [part for part in parsed.path.strip("/").split("/")[:2]]
    repo = re.sub(r"\.git$", "", repo, flags=re.I)
    return f"https://github.com/{owner}/{repo}.git"

def github_repo_safe_dir_name(repo_url: str) -> str:
    parsed = urllib.parse.urlparse(repo_url)
    repo = os.path.basename(parsed.path or "").strip()
    repo = re.sub(r"\.git$", "", repo, flags=re.I)
    repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", repo).strip(".-")
    if not repo:
        raise ValueError("无法从 GitHub URL 解析仓库目录名")
    return repo[:100]

def execute_model_download_action(action: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    cfg = get_resource_root_config()
    state = inspect_resource_root(cfg.get("resource_root") or "", create_missing=False)
    if not state.get("available") or not state.get("writable"):
        raise ValueError(state.get("message") or "资源根目录未配置或不可写")
    root_abs = str(state.get("resource_root") or "").strip()
    dep = {
        "category": action.get("category"),
        "value": action.get("value") or action.get("title"),
        "lookup_name": action.get("lookup_name") or action.get("target_relative_path"),
    }
    target = workflow_model_target_from_dependency(dep, root_abs)
    target_path = target["target_path"]
    target_relative_path = target["target_relative_path"]
    action_id = str(action.get("id") or "")
    source_url = validate_model_candidate_download_url(action.get("source_url"), target["filename"])
    if os.path.exists(target_path):
        progress = {
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "percent": 100,
            "speed_bytes_per_sec": 0,
            "phase": "skipped",
            "status": "skipped",
            "target_relative_path": target_relative_path,
        }
        workflow_install_update_action_progress(task_id, action_id, progress, action_status="skipped", note="目标文件已存在")
        workflow_install_log(task_id, f"模型已存在，跳过：{target_relative_path}")
        return {
            **action,
            "status": "skipped",
            "executable": False,
            "target_path": target_path,
            "target_relative_path": target_relative_path,
            "note": "目标文件已存在",
            "progress": progress,
        }
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    cache_dir = resource_root_safe_join(root_abs, "downloads/cache")
    os.makedirs(cache_dir, exist_ok=True)
    temp_path = os.path.join(cache_dir, f"{uuid.uuid4().hex}.part")
    downloaded = 0
    total_bytes: Optional[int] = None
    started_monotonic = time.monotonic()
    last_update_monotonic = started_monotonic
    last_update_downloaded = 0
    workflow_install_update_action_progress(
        task_id,
        action_id,
        {
            "downloaded_bytes": 0,
            "total_bytes": None,
            "percent": 0,
            "speed_bytes_per_sec": 0,
            "phase": "starting",
            "status": "running",
            "target_relative_path": target_relative_path,
        },
        action_status="running",
        note="准备下载",
    )
    workflow_install_log(task_id, f"开始下载模型：{target_relative_path}")
    try:
        with requests.get(source_url, stream=True, timeout=(10, 300)) as response:
            response.raise_for_status()
            try:
                header_total = int(response.headers.get("Content-Length") or 0)
                total_bytes = header_total if header_total > 0 else None
            except Exception:
                total_bytes = None
            workflow_install_update_action_progress(
                task_id,
                action_id,
                {
                    "downloaded_bytes": 0,
                    "total_bytes": total_bytes,
                    "percent": 0 if total_bytes else None,
                    "speed_bytes_per_sec": 0,
                    "phase": "downloading",
                    "status": "running",
                    "target_relative_path": target_relative_path,
                },
                action_status="running",
                note="下载中",
            )
            with open(temp_path, "wb") as out_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    now_mono = time.monotonic()
                    if now_mono - last_update_monotonic >= 1 or downloaded - last_update_downloaded >= 5 * 1024 * 1024:
                        elapsed = max(now_mono - started_monotonic, 0.001)
                        percent = round((downloaded / total_bytes) * 100, 2) if total_bytes else None
                        workflow_install_update_action_progress(
                            task_id,
                            action_id,
                            {
                                "downloaded_bytes": downloaded,
                                "total_bytes": total_bytes,
                                "percent": min(percent, 99.99) if percent is not None else None,
                                "speed_bytes_per_sec": int(downloaded / elapsed),
                                "phase": "downloading",
                                "status": "running",
                                "target_relative_path": target_relative_path,
                            },
                            action_status="running",
                            note="下载中",
                        )
                        last_update_monotonic = now_mono
                        last_update_downloaded = downloaded
        os.replace(temp_path, target_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    elapsed = max(time.monotonic() - started_monotonic, 0.001)
    final_total = total_bytes or downloaded
    progress = {
        "downloaded_bytes": downloaded,
        "total_bytes": final_total,
        "percent": 100,
        "speed_bytes_per_sec": int(downloaded / elapsed),
        "phase": "done",
        "status": "done",
        "target_relative_path": target_relative_path,
    }
    workflow_install_update_action_progress(task_id, action_id, progress, action_status="done", note="下载完成")
    workflow_install_log(task_id, f"模型下载完成：{target_relative_path}（{downloaded} bytes）")
    return {
        **action,
        "status": "done",
        "executable": False,
        "target_path": target_path,
        "target_relative_path": target_relative_path,
        "note": "下载完成",
        "bytes": downloaded,
        "progress": progress,
    }

def execute_custom_node_install_action(action: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    repo_url = validate_github_repo_url(action.get("repo_url"))
    custom_state = inspect_custom_nodes_dir()
    if not custom_state.get("available"):
        raise ValueError(custom_state.get("message") or "custom_nodes 目录未配置或不可写")
    custom_root = str(custom_state.get("path") or "")
    safe_dir = github_repo_safe_dir_name(repo_url)
    target_path = os.path.abspath(os.path.join(custom_root, safe_dir))
    if os.path.commonpath([custom_root, target_path]) != custom_root:
        raise ValueError("custom_nodes 目标路径越界")
    if os.path.exists(target_path):
        workflow_install_log(task_id, f"自定义节点已存在，跳过：{safe_dir}")
        return {
            **action,
            "status": "skipped",
            "executable": False,
            "repo_url": repo_url,
            "target_path": target_path,
            "note": "目标目录已存在",
        }
    workflow_install_log(task_id, f"开始克隆自定义节点：{repo_url}")
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, target_path],
        shell=False,
        text=True,
        capture_output=True,
        timeout=1800,
    )
    if proc.stdout.strip():
        workflow_install_log(task_id, proc.stdout.strip()[-1200:])
    if proc.stderr.strip():
        workflow_install_log(task_id, proc.stderr.strip()[-1200:])
    if proc.returncode != 0:
        raise ValueError(f"git clone 失败（exit {proc.returncode}）")
    workflow_install_log(task_id, "已克隆，requirements 请人工确认后安装")
    return {
        **action,
        "status": "done",
        "executable": False,
        "repo_url": repo_url,
        "target_path": target_path,
        "note": "已克隆，requirements 请人工确认后安装",
    }

def execute_workflow_install_task(task_id: str):
    workflow_install_update_task(task_id, status="running", started_at=now_utc_iso())
    failed_count = 0
    task = workflow_install_task_snapshot(task_id)
    actions = task.get("actions") or []
    workflow_install_log(task_id, f"安装任务开始，共 {len(actions)} 个动作")
    for raw_action in actions:
        action = dict(raw_action or {})
        action_type = str(action.get("type") or "")
        title = str(action.get("title") or action.get("id") or action_type)
        try:
            if action_type == "model_download":
                result = execute_model_download_action(action, task_id)
            elif action_type == "custom_node_install":
                result = execute_custom_node_install_action(action, task_id)
            else:
                raise ValueError(f"不支持的安装动作类型：{action_type or '-'}")
            workflow_install_update_action(
                task_id,
                str(action.get("id") or ""),
                status=result.get("status") or "done",
                executable=False,
                note=result.get("note") or "",
            )
            workflow_install_append_result(task_id, result)
        except Exception as exc:
            failed_count += 1
            message = str(exc)
            workflow_install_log(task_id, f"{title} 失败：{message}")
            try:
                current_task = workflow_install_task_snapshot(task_id)
                progress = dict((current_task.get("progress") or {}).get(str(action.get("id") or "")) or {})
            except Exception:
                progress = dict(action.get("progress") or {})
            progress.update({
                "phase": "failed",
                "status": "failed",
                "error": message,
                "target_relative_path": progress.get("target_relative_path") or action.get("target_relative_path") or "",
            })
            workflow_install_update_action_progress(
                task_id,
                str(action.get("id") or ""),
                progress,
                action_status="failed",
                note=message,
            )
            workflow_install_append_result(task_id, {**action, "status": "failed", "executable": False, "note": message})
    final_status = "failed" if failed_count else "done"
    workflow_install_log(task_id, f"安装任务结束：{final_status}")
    workflow_install_update_task(task_id, status=final_status, finished_at=now_utc_iso())

def normalize_workflow_install_task_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for raw in actions or []:
        if not isinstance(raw, dict):
            continue
        action_type = str(raw.get("type") or "").strip()
        if action_type not in {"model_download", "custom_node_install"}:
            continue
        if action_type == "model_download" and not str(raw.get("source_url") or "").strip():
            continue
        if action_type == "custom_node_install" and not str(raw.get("repo_url") or "").strip():
            continue
        action = dict(raw)
        action["id"] = str(action.get("id") or workflow_install_action_id("action", json.dumps(action, ensure_ascii=False, sort_keys=True)))
        action["title"] = str(action.get("title") or action.get("value") or action.get("class_type") or action["id"])
        action["status"] = "ready"
        action["executable"] = True
        normalized.append(action)
    return normalized

def start_workflow_install_task(actions: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not actions:
        raise HTTPException(status_code=400, detail="没有可执行的安装动作")
    task_id = f"wf_install_{uuid.uuid4().hex}"
    task = {
        "task_id": task_id,
        "status": "queued",
        "created_at": now_utc_iso(),
        "updated_at": now_utc_iso(),
        "started_at": "",
        "finished_at": "",
        "actions": actions,
        "progress": {},
        "logs": [],
        "results": [],
    }
    if metadata:
        task.update(metadata)
    with WORKFLOW_INSTALL_TASK_LOCK:
        WORKFLOW_INSTALL_TASKS[task_id] = task
    thread = Thread(target=execute_workflow_install_task, args=(task_id,), daemon=True)
    thread.start()
    return workflow_install_task_snapshot(task_id)

def build_auto_model_downloads_response(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    selected_actions: List[Dict[str, Any]] = []
    selected: List[Dict[str, Any]] = []
    manual_required: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[str] = []
    selected_targets = set()

    for raw_action in actions or []:
        if not isinstance(raw_action, dict):
            continue
        action = dict(raw_action)
        action_id = str(action.get("id") or "")
        action_title = str(action.get("title") or action.get("value") or action_id or "-")
        action_type = str(action.get("type") or "")
        action_status = str(action.get("status") or "")
        if action_type != "model_download":
            if action_type:
                skipped.append({
                    "id": action_id,
                    "title": action_title,
                    "type": action_type,
                    "reason": "一键下载仅处理模型文件，不处理自定义节点",
                })
            continue
        if action_status in {"done", "skipped", "blocked"}:
            skipped.append({
                "id": action_id,
                "title": action_title,
                "type": action_type,
                "status": action_status,
                "reason": action.get("note") or "该动作当前不可自动下载",
            })
            continue

        target_filename = workflow_model_action_target_filename(action)
        skip_reason = workflow_auto_model_target_skip_reason(action, target_filename)
        if skip_reason:
            manual_required.append({
                "id": action_id,
                "title": action_title,
                "type": action_type,
                "target_filename": target_filename or workflow_model_candidate_filename(action),
                "reason": skip_reason,
                "candidates": [],
                "errors": [],
            })
            continue
        target_key = target_filename.lower()
        if target_key in selected_targets:
            skipped.append({
                "id": action_id,
                "title": action_title,
                "type": action_type,
                "target_filename": target_filename,
                "reason": "同名模型已在本次一键任务中选择，避免重复下载",
            })
            continue

        lookup = workflow_install_find_model_candidates_for_action({**action, "model_name": target_filename})
        candidates = lookup.get("candidates") or []
        chosen = select_high_confidence_model_candidate(candidates, target_filename)
        if not chosen:
            manual_required.append({
                "id": action_id,
                "title": action_title,
                "type": action_type,
                "target_filename": target_filename,
                "reason": "未找到 score>=100 且文件名完全同名的候选，请人工确认 URL",
                "query": lookup.get("query") or "",
                "candidates": candidates[:3],
                "errors": (lookup.get("errors") or [])[:5],
            })
            continue

        selected_targets.add(target_key)
        selected_actions.append({
            **action,
            "source_url": chosen.get("url") or "",
            "status": "ready",
            "executable": True,
            "note": f"一键高置信候选：{chosen.get('source') or 'unknown'} · score {chosen.get('score') or 0}",
        })
        selected.append({
            "id": action_id,
            "title": action_title,
            "type": action_type,
            "target_filename": target_filename,
            "target_relative_path": action.get("target_relative_path") or "",
            "source": chosen.get("source") or "",
            "score": model_download_candidate_score(chosen.get("score")),
            "repo": chosen.get("repo") or "",
            "filename": chosen.get("filename") or model_candidate_download_filename(chosen.get("url")),
            "url": chosen.get("url") or "",
        })

    normalized_actions = normalize_workflow_install_task_actions(selected_actions)
    if selected_actions and not normalized_actions:
        errors.append("已选择候选，但没有生成可执行下载动作")
    auto_summary = {
        "selected": selected,
        "manual_required": manual_required,
        "skipped": skipped,
        "errors": errors,
        "summary": {
            "selected_count": len(selected),
            "manual_required_count": len(manual_required),
            "skipped_count": len(skipped),
        },
        "message": f"已选择 {len(selected)} 个高置信同名模型；{len(manual_required)} 个需要人工确认",
    }
    task = None
    if normalized_actions:
        task = start_workflow_install_task(normalized_actions, {"auto_model_downloads": auto_summary})
    return {
        "task_id": task.get("task_id") if task else "",
        "task": task,
        "selected": selected,
        "manual_required": manual_required,
        "skipped": skipped,
        "errors": errors,
        "summary": auto_summary["summary"],
        "message": auto_summary["message"],
    }

def save_custom_workflow_with_candidates(
    raw_name: str,
    workflow_json: Dict[str, Any],
    suggested_title: str = "",
    default_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    name = normalize_custom_workflow_filename(raw_name, fallback="imported-workflow")
    if not WORKFLOW_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="工作流名称不合法，请使用中文/英文/数字/_-.")
    payload = normalize_comfy_api_workflow_payload(workflow_json)
    if not payload:
        raise HTTPException(status_code=400, detail="不是有效的 ComfyUI API 工作流 JSON（需包含 class_type）")
    custom_dir = os.path.join(WORKFLOW_DIR, CUSTOM_WORKFLOW_FOLDER)
    os.makedirs(custom_dir, exist_ok=True)
    stored_name = f"{CUSTOM_WORKFLOW_FOLDER}/{name}"
    path = workflow_path_from_name(stored_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    cfg_path = workflow_config_path(stored_name)
    cfg_exists = os.path.exists(cfg_path)
    cfg = load_workflow_config(stored_name)
    if default_enabled is not None:
        cfg.enabled = bool(default_enabled)
    if not cfg_exists:
        cfg.title = (suggested_title or workflow_default_title(name)).strip() or workflow_default_title(name)
    cfg.fields = merge_workflow_field_candidates(cfg.fields, collect_comfy_workflow_fields(payload))
    save_workflow_config_data(stored_name, cfg)
    return {
        "name": stored_name,
        "title": cfg.title or workflow_default_title(name),
        "enabled": cfg.enabled,
        "field_count": len(cfg.fields or []),
        "created": not cfg_exists,
    }

def collect_comfy_workflow_fields(workflow_json: Dict[str, Any]) -> List[WorkflowField]:
    fields: List[WorkflowField] = []
    if not isinstance(workflow_json, dict):
        return fields
    for node_id, node_content in workflow_json.items():
        if not isinstance(node_content, dict):
            continue
        inputs = node_content.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name, raw_value in inputs.items():
            if comfy_is_link_value(raw_value):
                continue
            field_type = comfy_guess_field_type(raw_value, input_name)
            default = raw_value if not isinstance(raw_value, (dict, list)) else None
            min_value = max_value = step_value = None
            if field_type in {"number", "slider"} and isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                min_value = 0
                max_value = max(float(raw_value) * 2, 10)
                step_value = 0.1 if 0 < float(raw_value) < 5 else 1
            fields.append(WorkflowField(
                id=f"{node_id}::{input_name}",
                node=str(node_id),
                input=str(input_name),
                name=str(input_name),
                type=field_type,
                default=default,
                min=min_value,
                max=max_value,
                step=step_value,
                enabled=False,
                hidden=False,
                required=field_type in {"image", "video", "audio"},
            ))
    return fields

def merge_workflow_field_candidates(existing: List[WorkflowField], candidates: List[WorkflowField]) -> List[WorkflowField]:
    merged = list(existing or [])
    keys = {
        (str(field.node), str(field.input))
        for field in merged
        if field.node or field.input
    }
    ids = {str(field.id) for field in merged}
    for candidate in candidates:
        key = (str(candidate.node), str(candidate.input))
        if key in keys or str(candidate.id) in ids:
            continue
        merged.append(candidate)
        keys.add(key)
        ids.add(str(candidate.id))
    return merged

def workflow_field_is_public(field: WorkflowField) -> bool:
    return bool(field.enabled) and not bool(field.hidden)

def workflow_public_fields(cfg: WorkflowConfig) -> List[Dict[str, Any]]:
    public_fields = []
    for field in cfg.fields or []:
        if not workflow_field_is_public(field):
            continue
        public_fields.append({
            "id": field.id,
            "input": field.input,
            "name": field.name,
            "type": field.type,
            "default": field.default,
            "min": field.min,
            "max": field.max,
            "step": field.step,
            "options": field.options or [],
            "random_enabled": field.random_enabled,
            "required": field.required,
        })
    return public_fields

def workflow_public_config(cfg: WorkflowConfig) -> Dict[str, Any]:
    return {
        "title": cfg.title,
        "description": cfg.description,
        "category": cfg.category,
        "thumbnail": cfg.thumbnail,
        "enabled": cfg.enabled,
        "fields": workflow_public_fields(cfg),
    }

def workflow_list_items(public_only: bool = False) -> List[Dict[str, Any]]:
    if not os.path.isdir(WORKFLOW_DIR):
        return []
    items = []
    for root, dirs, files in os.walk(WORKFLOW_DIR):
        if os.path.abspath(root) == os.path.abspath(WORKFLOW_DIR):
            dirs[:] = [d for d in dirs if d in {CUSTOM_WORKFLOW_FOLDER, LEGACY_CUSTOM_WORKFLOW_FOLDER, SHARED_WORKFLOW_FOLDER}]
        for fn in sorted(files):
            if not fn.endswith(".json") or fn.endswith(".config.json"):
                continue
            # SMB 共享盘上的 macOS 元数据文件（._xxx / .DS_Store 同类），不是有效 workflow
            if fn.startswith("._"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), WORKFLOW_DIR).replace("\\", "/")
            # 文件名不符合命名规则（如全角标点）时跳过，避免一个坏文件让整个列表接口 400
            if not WORKFLOW_NAME_RE.match(rel):
                print(f"跳过命名不合法的 workflow 文件: {rel}")
                continue
            builtin = is_builtin_workflow(rel)
            cfg = load_workflow_config(rel)
            if public_only and not cfg.enabled:
                continue
            public_count = len(workflow_public_fields(cfg))
            item = {
                "name": rel,
                "title": cfg.title or workflow_default_title(rel),
                "description": cfg.description,
                "category": cfg.category,
                "thumbnail": cfg.thumbnail,
                "enabled": cfg.enabled,
                "builtin": builtin,
                "shared": is_shared_workflow(rel),
                "field_count": public_count,
            }
            if not public_only:
                item["total_field_count"] = len(cfg.fields or [])
                item["last_test"] = cfg.last_test if isinstance(cfg.last_test, dict) else None
            items.append(item)
    items.sort(key=lambda item: (0 if item["name"].startswith(f"{CUSTOM_WORKFLOW_FOLDER}/") else 1, item.get("category") or "", item["title"]))
    return items

def parse_positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(float(value))
        return parsed if parsed > 0 else None
    except Exception:
        return None

def load_workflow_node_inputs(workflow_name: str, node_id: str) -> Dict[str, Any]:
    try:
        with open(workflow_path_from_name(workflow_name), "r", encoding="utf-8") as f:
            workflow_json = json.load(f) or {}
        node = workflow_json.get(str(node_id))
        if not isinstance(node, dict):
            return {}
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            return {}
        return inputs
    except Exception:
        return {}

def apply_ltx_public_run_defaults(workflow_name: str, params: Dict[str, Dict[str, Any]]):
    if os.path.basename(workflow_name) != LTX_PUBLIC_WORKFLOW_NAME:
        return
    node_params = params.setdefault(LTX_PUBLIC_NODE_ID, {})
    if not isinstance(node_params, dict):
        return
    workflow_inputs = load_workflow_node_inputs(workflow_name, LTX_PUBLIC_NODE_ID)

    if "segment_lengths" not in node_params:
        duration_frames = parse_positive_int(node_params.get("duration_frames"))
        if duration_frames is None:
            duration_frames = parse_positive_int(workflow_inputs.get("duration_frames"))
        if duration_frames is not None:
            node_params["segment_lengths"] = str(duration_frames)

    local_prompts = node_params.get("local_prompts")
    if isinstance(local_prompts, str) and local_prompts.strip():
        return
    global_prompt = node_params.get("global_prompt")
    if isinstance(global_prompt, str) and global_prompt.strip():
        node_params["local_prompts"] = global_prompt.strip()
        return
    local_default = workflow_inputs.get("local_prompts")
    if isinstance(local_default, str) and local_default.strip():
        node_params["local_prompts"] = local_default.strip()
        return
    global_default = workflow_inputs.get("global_prompt")
    if isinstance(global_default, str) and global_default.strip():
        node_params["local_prompts"] = global_default.strip()
        return
    node_params["local_prompts"] = "cinematic scene"

def runninghub_workflow_store_path() -> str:
    return RUNNINGHUB_WORKFLOW_STORE_FILE

def load_runninghub_workflow_store():
    if not os.path.exists(RUNNINGHUB_WORKFLOW_STORE_FILE):
        return {}
    try:
        with open(RUNNINGHUB_WORKFLOW_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_runninghub_workflow_store(store):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RUNNINGHUB_WORKFLOW_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

def runninghub_workflow_config_has_payload(cfg):
    if not isinstance(cfg, dict):
        return False
    return bool(cfg.get("fields") or cfg.get("workflowJson") or cfg.get("raw"))

def runninghub_workflow_entry_from_config(cfg, fallback=None):
    fallback = fallback if isinstance(fallback, dict) else {}
    key = runninghub_workflow_store_key((cfg or {}).get("workflowId") or fallback.get("workflowId") or fallback.get("id"))
    if not key:
        return None
    return normalize_runninghub_entry({
        "id": key,
        "workflowId": key,
        "title": (cfg or {}).get("title") or fallback.get("title") or fallback.get("name") or f"工作流 {key[-6:]}",
        "note": (cfg or {}).get("description") or fallback.get("note") or fallback.get("description") or "",
        "thumbnail": fallback.get("thumbnail") or "",
        "enabled": fallback.get("enabled", True),
        "fields": (cfg or {}).get("fields") or fallback.get("fields") or [],
        "workflowJson": (cfg or {}).get("workflowJson") if isinstance((cfg or {}).get("workflowJson"), dict) else fallback.get("workflowJson") or {},
        "optionalImageMode": (cfg or {}).get("optionalImageMode") or fallback.get("optionalImageMode") or "prune-workflow",
        "raw": (cfg or {}).get("raw") if isinstance((cfg or {}).get("raw"), dict) else fallback.get("raw") or {},
        "updatedAt": (cfg or {}).get("updatedAt") or fallback.get("updatedAt") or 0,
    }, "workflow")

def runninghub_provider_with_workflow_store(provider):
    if not isinstance(provider, dict) or provider.get("id") != "runninghub":
        return provider
    store = load_runninghub_workflow_store()
    if not store:
        return provider
    merged = dict(provider)
    workflows = [dict(item) for item in (merged.get("rh_workflows") or []) if isinstance(item, dict)]
    by_id = {
        runninghub_workflow_store_key(item.get("workflowId") or item.get("id")): item
        for item in workflows
        if runninghub_workflow_store_key(item.get("workflowId") or item.get("id"))
    }
    for workflow_id, cfg in store.items():
        if not isinstance(cfg, dict) or not runninghub_workflow_config_has_payload(cfg):
            continue
        existing = by_id.get(workflow_id)
        selected = runninghub_select_workflow_config(existing, cfg)
        entry = runninghub_workflow_entry_from_config(selected, existing)
        if not entry:
            continue
        if existing is None:
            workflows.append(entry)
        else:
            existing.update(entry)
    merged["rh_workflows"] = normalize_runninghub_entries(workflows, "workflow")
    return merged

def runninghub_provider_workflow_config(workflow_id: str):
    key = runninghub_workflow_store_key(workflow_id)
    if not key:
        return None
    providers = load_api_providers()
    provider = next((item for item in providers if item.get("id") == "runninghub"), None)
    if not provider:
        return None
    for entry in provider.get("rh_workflows") or []:
        entry_key = runninghub_workflow_store_key(entry.get("workflowId") or entry.get("id"))
        if entry_key != key:
            continue
        cfg = {
            "workflowId": key,
            "title": entry.get("title") or key,
            "description": entry.get("note") or entry.get("description") or "",
            "fields": [
                field for field in (runninghub_normalize_field(item) for item in (entry.get("fields") or []))
                if not runninghub_is_saved_link_field(field)
            ],
            "workflowJson": entry.get("workflowJson") if isinstance(entry.get("workflowJson"), dict) else {},
            "optionalImageMode": entry.get("optionalImageMode") or "prune-workflow",
            "raw": entry.get("raw") if isinstance(entry.get("raw"), dict) else {},
            "updatedAt": entry.get("updatedAt") or 0,
            "source": "api_providers",
        }
        return cfg if runninghub_workflow_config_has_payload(cfg) else None
    return None

def runninghub_select_workflow_config(local_cfg, provider_cfg):
    if isinstance(local_cfg, dict) and isinstance(provider_cfg, dict):
        try:
            local_updated = int(local_cfg.get("updatedAt") or 0)
        except Exception:
            local_updated = 0
        try:
            provider_updated = int(provider_cfg.get("updatedAt") or 0)
        except Exception:
            provider_updated = 0
        return provider_cfg if provider_updated > local_updated else local_cfg
    if isinstance(local_cfg, dict):
        return local_cfg
    if isinstance(provider_cfg, dict):
        return provider_cfg
    return None

def sync_runninghub_workflow_to_provider(cfg):
    if not isinstance(cfg, dict):
        return
    key = runninghub_workflow_store_key(cfg.get("workflowId"))
    if not key:
        return
    providers = load_api_providers()
    provider = next((item for item in providers if item.get("id") == "runninghub"), None)
    if not provider:
        provider = {
            "id": "runninghub",
            "name": "RunningHub",
            "base_url": RUNNINGHUB_DEFAULT_BASE_URL,
            "protocol": "runninghub",
            "image_generation_endpoint": "",
            "image_edit_endpoint": "",
            "enabled": True,
            "primary": False,
            "image_models": RUNNINGHUB_DEFAULT_IMAGE_MODELS,
            "chat_models": [],
            "video_models": [],
            "ms_loras": [],
            "ms_defaults_version": 0,
            "rh_apps": RUNNINGHUB_DEFAULT_APPS,
            "rh_workflows": [],
        }
        providers.append(provider)
    workflows = provider.setdefault("rh_workflows", [])
    entry = None
    for item in workflows:
        item_key = runninghub_workflow_store_key(item.get("workflowId") or item.get("id"))
        if item_key == key:
            entry = item
            break
    if entry is None:
        entry = {
            "id": key,
            "workflowId": key,
            "title": cfg.get("title") or f"工作流 {key[-6:]}",
            "note": cfg.get("description") or "",
            "thumbnail": "",
            "enabled": True,
        }
        workflows.append(entry)
    entry.update({
        "id": key,
        "workflowId": key,
        "title": cfg.get("title") or entry.get("title") or f"工作流 {key[-6:]}",
        "note": cfg.get("description") or "",
        "fields": [
            field for field in (runninghub_normalize_field(item) for item in (cfg.get("fields") or []))
            if not runninghub_is_saved_link_field(field)
        ],
        "workflowJson": cfg.get("workflowJson") if isinstance(cfg.get("workflowJson"), dict) else {},
        "optionalImageMode": cfg.get("optionalImageMode") or "prune-workflow",
        "raw": cfg.get("raw") if isinstance(cfg.get("raw"), dict) else {},
        "updatedAt": cfg.get("updatedAt") or now_ms(),
    })
    if "enabled" not in entry:
        entry["enabled"] = True
    if "thumbnail" not in entry:
        entry["thumbnail"] = ""
    save_api_providers([normalize_provider(item) for item in providers])

def remove_runninghub_workflow_from_provider(workflow_id: str):
    key = runninghub_workflow_store_key(workflow_id)
    if not key:
        return
    providers = load_api_providers()
    changed = False
    for provider in providers:
        if provider.get("id") != "runninghub":
            continue
        workflows = provider.get("rh_workflows") or []
        removed = next((
            item for item in workflows
            if runninghub_workflow_store_key(item.get("workflowId") or item.get("id")) == key
        ), None)
        kept = [
            item for item in workflows
            if runninghub_workflow_store_key(item.get("workflowId") or item.get("id")) != key
        ]
        static_provider = load_static_runninghub_provider()
        static_workflow = next((
            item for item in (static_provider or {}).get("rh_workflows", [])
            if runninghub_workflow_store_key(item.get("workflowId") or item.get("id")) == key
        ), None)
        if static_workflow:
            tombstone = normalize_runninghub_entry({**static_workflow, **(removed or {}), "enabled": False, "hidden": True}, "workflow")
            if tombstone:
                kept.append(tombstone)
        if static_workflow or len(kept) != len(workflows):
            provider["rh_workflows"] = kept
            changed = True
    if changed:
        save_api_providers([normalize_provider(item) for item in providers])

def runninghub_workflow_store_key(workflow_id: str) -> str:
    return str(workflow_id or "").strip()

def runninghub_normalize_field(raw, fallback=None):
    fallback = fallback or {}
    if hasattr(raw, "dict"):
        raw = raw.dict()
    if not isinstance(raw, dict):
        raw = {}
    options = raw.get("options", fallback.get("options", []))
    if isinstance(options, str):
        options = [item.strip() for item in re.split(r"[\r\n,]+", options) if item.strip()]
    elif isinstance(options, list):
        options = [str(item).strip() for item in options if str(item).strip()]
    else:
        options = []
    field_id = str(raw.get("id") or raw.get("fieldId") or raw.get("key") or raw.get("nodeId") or fallback.get("id") or "").strip()
    node_id = str(raw.get("nodeId") or fallback.get("nodeId") or raw.get("node_id") or "").strip()
    field_name = str(raw.get("fieldName") or raw.get("inputName") or raw.get("name") or fallback.get("fieldName") or "").strip()
    field_value = raw.get("fieldValue")
    if field_value is None:
        field_value = raw.get("defaultValue")
    if field_value is None:
        field_value = raw.get("value")
    if field_value is None:
        field_value = fallback.get("fieldValue", "")
    if isinstance(field_value, (dict, list)):
        field_value = json.dumps(field_value, ensure_ascii=False)
    elif field_value is None:
        field_value = ""
    else:
        field_value = str(field_value)
    return {
        "id": field_id or f"{node_id}::{field_name}",
        "nodeId": node_id,
        "fieldName": field_name,
        "fieldValue": field_value,
        "fieldType": str(raw.get("fieldType") or fallback.get("fieldType") or "TEXT"),
        "label": str(raw.get("label") or raw.get("title") or field_name or fallback.get("label") or ""),
        "enabled": bool(raw.get("enabled", fallback.get("enabled", True))),
        "sourceFromUpstream": bool(raw.get("sourceFromUpstream", fallback.get("sourceFromUpstream", True))),
        "group": str(raw.get("group") or fallback.get("group") or ""),
        "note": str(raw.get("note") or fallback.get("note") or ""),
        "options": options,
        "random_enabled": bool(raw.get("random_enabled", fallback.get("random_enabled", False))),
        "min": raw.get("min", fallback.get("min", "")),
        "max": raw.get("max", fallback.get("max", "")),
        "step": raw.get("step", fallback.get("step", "")),
        "imageOrder": int(raw.get("imageOrder") or raw.get("image_order") or fallback.get("imageOrder") or 0),
        "required": bool(raw.get("required", fallback.get("required", False))),
    }

def runninghub_is_saved_link_field(field):
    if not isinstance(field, dict):
        return False
    value = field.get("fieldValue")
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return False
    try:
        parsed = json.loads(text)
    except Exception:
        return False
    return runninghub_is_workflow_link_value(parsed)

def runninghub_collect_workflow_fields(workflow_json):
    fields = []
    if not isinstance(workflow_json, dict):
        return fields
    for node_id, node_content in workflow_json.items():
        if not isinstance(node_content, dict):
            continue
        inputs = node_content.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for field_name, raw_value in inputs.items():
            if runninghub_is_workflow_link_value(raw_value):
                continue
            if isinstance(raw_value, (dict, list)):
                field_value = json.dumps(raw_value, ensure_ascii=False)
            elif raw_value is None:
                field_value = ""
            else:
                field_value = str(raw_value)
            field_type = runninghub_infer_workflow_field_type(field_name, field_value)
            fields.append({
                "id": f"{node_id}::{field_name}",
                "nodeId": str(node_id),
                "fieldName": str(field_name),
                "fieldValue": field_value,
                "fieldType": field_type,
                "label": str(field_name),
                "enabled": False,
                "sourceFromUpstream": True,
                "group": str(
                    (node_content.get("_meta") or {}).get("title")
                    or node_content.get("class_type")
                    or node_content.get("_class")
                    or node_content.get("type")
                    or ""
                ),
                "note": "",
                "imageOrder": 0,
                "required": field_type == "IMAGE",
            })
    return fields

class ComfyInstancesPayload(BaseModel):
    instances: List[str] = []

class ResourceRootPayload(BaseModel):
    resource_root: str = ""
    create_missing: bool = False

class ResourceRootDetectPayload(BaseModel):
    create_missing: bool = False

class ResourceRootModelCheckPayload(BaseModel):
    model_dependencies: List[Dict[str, Any]] = Field(default_factory=list)

def comfy_instance_base_url(addr: str) -> str:
    value = str(addr or "").strip().rstrip("/")
    if not value:
        return ""
    return value if re.match(r"^https?://", value, re.I) else f"http://{value}"

def comfy_vram_mb(value: Any) -> Optional[int]:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 1024 * 1024:
        return int(round(n / 1024 / 1024))
    return int(round(n))

def comfy_queue_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0

def comfy_device_summary(stats_data: Any) -> Dict[str, Any]:
    if not isinstance(stats_data, dict):
        return {}
    devices = stats_data.get("devices")
    if not isinstance(devices, list):
        return {}

    normalized = []
    for raw in devices:
        if not isinstance(raw, dict):
            continue
        total = comfy_vram_mb(raw.get("vram_total") or raw.get("torch_vram_total"))
        free = comfy_vram_mb(raw.get("vram_free") or raw.get("torch_vram_free"))
        used = total - free if total is not None and free is not None else None
        normalized.append({
            "name": str(raw.get("name") or raw.get("device_name") or raw.get("type") or "Device"),
            "type": str(raw.get("type") or ""),
            "index": raw.get("index"),
            "vram_total_mb": total,
            "vram_free_mb": free,
            "vram_used_mb": used,
        })

    if not normalized:
        return {}
    first = normalized[0]
    return {
        "device_name": first.get("name") or "",
        "gpu": first.get("name") or "",
        "vram_total_mb": first.get("vram_total_mb"),
        "vram_free_mb": first.get("vram_free_mb"),
        "vram_used_mb": first.get("vram_used_mb"),
        "devices": normalized,
    }

def probe_comfy_instance(addr: str) -> Dict[str, Any]:
    base_url = comfy_instance_base_url(addr)
    item: Dict[str, Any] = {
        "address": str(addr or "").strip(),
        "base_url": base_url,
        "ok": False,
        "reason": "地址为空" if not base_url else "",
        "latency_ms": None,
        "queue_running": 0,
        "queue_pending": 0,
    }
    if not base_url:
        return item
    try:
        started = time.time()
        stats = requests.get(f"{base_url}/system_stats", timeout=4.5)
        if stats.status_code >= 400:
            item["reason"] = f"system_stats HTTP {stats.status_code}"
            return item
        queue = requests.get(f"{base_url}/queue", timeout=4.5)
        if queue.status_code >= 400:
            item["reason"] = f"queue HTTP {queue.status_code}"
            return item
        item.update({
            "ok": True,
            "reason": "可连接",
            "latency_ms": int((time.time() - started) * 1000),
        })
        try:
            stats_data = stats.json()
            item.update(comfy_device_summary(stats_data))
        except Exception:
            pass
        try:
            queue_data = queue.json()
            item["queue_running"] = comfy_queue_count(queue_data.get("queue_running"))
            item["queue_pending"] = comfy_queue_count(queue_data.get("queue_pending"))
        except Exception:
            pass
    except requests.RequestException as exc:
        item["reason"] = str(exc)[:180] or "无法连接"
    return item

@app.get("/api/comfyui/instances")
def get_comfyui_instances(request: Request):
    require_admin_user(request)
    return {
        "instances": COMFYUI_INSTANCES,
        "source": "COMFYUI_INSTANCES",
        "platform_origin": str(request.base_url).rstrip("/"),
    }

@app.get("/api/comfyui/status")
def get_comfyui_status(request: Request):
    require_admin_user(request)
    return {"instances": [probe_comfy_instance(addr) for addr in COMFYUI_INSTANCES]}

@app.get("/api/comfyui/workbench-status")
def get_comfyui_workbench_status(request: Request):
    user = require_current_user(request)
    return {
        "instances": [probe_comfy_instance(addr) for addr in COMFYUI_INSTANCES],
        "updated_at": now_ts(),
        "user": {
            "username": user.get("username") or "",
            "is_admin": bool(user.get("is_admin")),
        },
    }

def normalize_known_instance(instance: str) -> str:
    addr = re.sub(r"^https?://", "", str(instance or "").strip()).rstrip("/")
    if not addr:
        raise HTTPException(status_code=400, detail="instance 不能为空")
    if addr not in COMFYUI_INSTANCES:
        raise HTTPException(status_code=400, detail=f"指定的 worker 不在已配置实例中：{addr}")
    return addr

def comfy_history_entry_summary(addr: str, prompt_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    prompt = entry.get("prompt")
    api_workflow = {}
    number = 0
    if isinstance(prompt, list) and len(prompt) >= 3:
        try:
            number = int(prompt[0])
        except Exception:
            number = 0
        if isinstance(prompt[2], dict):
            api_workflow = prompt[2]
    status = entry.get("status") or {}
    status_str = str(status.get("status_str") or "")
    completed = bool(status.get("completed"))
    started_at_ms = 0
    for msg in (status.get("messages") or []):
        if isinstance(msg, list) and len(msg) >= 2 and isinstance(msg[1], dict):
            ts = msg[1].get("timestamp")
            if ts:
                try:
                    started_at_ms = int(ts)
                    break
                except Exception:
                    pass
    images = []
    for node_output in (entry.get("outputs") or {}).values():
        if not isinstance(node_output, dict):
            continue
        for im in (node_output.get("images") or []):
            if not isinstance(im, dict) or not im.get("filename"):
                continue
            images.append(
                f"http://{addr}/view?filename={urllib.parse.quote(str(im['filename']))}"
                f"&subfolder={urllib.parse.quote(str(im.get('subfolder') or ''))}"
                f"&type={urllib.parse.quote(str(im.get('type') or 'output'))}"
            )
    class_types = list(dict.fromkeys(
        str(node.get("class_type") or "").strip()
        for node in api_workflow.values()
        if isinstance(node, dict) and node.get("class_type")
    ))
    return {
        "prompt_id": str(prompt_id),
        "number": number,
        "success": status_str == "success" and completed,
        "status_str": status_str or ("success" if completed else "unknown"),
        "started_at_ms": started_at_ms,
        "node_count": len(api_workflow),
        "class_types": class_types[:10],
        "class_type_count": len(class_types),
        "images": images[:4],
        "image_count": len(images),
        "has_api_workflow": bool(api_workflow),
    }

@app.get("/api/comfyui/worker-history")
def get_comfyui_worker_history(request: Request, instance: str = "", limit: int = 20):
    """ComfyTV 导入源：读取指定 worker（ComfyUI）的运行历史，含 API workflow 与输出图。"""
    require_admin_user(request)
    addr = normalize_known_instance(instance)
    limit = max(1, min(int(limit or 20), 50))
    try:
        with urllib.request.urlopen(f"http://{addr}/history?max_items={limit}", timeout=5) as response:
            data = json.loads(response.read())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"读取 worker {addr} 历史失败：{str(e)[:200]}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail=f"worker {addr} 历史响应格式异常")
    items = [comfy_history_entry_summary(addr, pid, entry) for pid, entry in data.items() if isinstance(entry, dict)]
    items.sort(key=lambda item: item.get("number") or 0, reverse=True)
    return {"instance": addr, "items": items, "updated_at": now_ts()}

class ComfyHistoryImportRequest(BaseModel):
    instance: str = ""
    prompt_id: str = ""
    name: str = ""

@app.post("/api/comfyui/import-from-history")
def import_workflow_from_history(payload: ComfyHistoryImportRequest, request: Request):
    """把 worker（ComfyUI）里已跑通的一次运行导入为平台 workflow：history 自带 API 格式 prompt。"""
    user = require_admin_user(request)
    addr = normalize_known_instance(payload.instance)
    prompt_id = str(payload.prompt_id or "").strip()
    if not prompt_id:
        raise HTTPException(status_code=400, detail="缺少 prompt_id")
    try:
        with urllib.request.urlopen(f"http://{addr}/history/{urllib.parse.quote(prompt_id)}", timeout=5) as response:
            data = json.loads(response.read())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"读取 worker {addr} 历史失败：{str(e)[:200]}")
    entry = data.get(prompt_id) if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail=f"worker {addr} 上没有找到该运行记录：{prompt_id}")
    summary = comfy_history_entry_summary(addr, prompt_id, entry)
    if not summary["has_api_workflow"]:
        raise HTTPException(status_code=400, detail="该运行记录中没有可用的 API workflow")
    api_workflow = entry["prompt"][2]
    suggested_name = str(payload.name or "").strip() or f"comfytv-{prompt_id[:8]}"
    saved = save_custom_workflow_with_candidates(
        suggested_name,
        api_workflow,
        suggested_title=suggested_name,
        default_enabled=False,
    )
    # 它在 worker 上已经跑通过，直接预填 last_test（来源标记为 comfyui-history）
    try:
        cfg = load_workflow_config(saved["name"])
        cfg.last_test = {
            "ok": bool(summary["success"]),
            "at": int(summary["started_at_ms"] / 1000) if summary["started_at_ms"] else now_ts(),
            "by": str(user.get("username") or ""),
            "backend": addr,
            "output_count": summary["image_count"],
            "source": "comfyui-history",
            "prompt_id": prompt_id,
        }
        save_workflow_config_data(saved["name"], cfg)
    except Exception as e:
        print(f"导入预填 last_test 失败 [{saved.get('name')}]: {e}")
    return {
        "name": saved["name"],
        "title": saved.get("title") or suggested_name,
        "success_run": bool(summary["success"]),
        "node_count": summary["node_count"],
        "image_count": summary["image_count"],
    }

# ===== AI-CanvasPro 本地桥（APIMart 兼容协议）=====
# 在 CanvasPro 的 APIMart provider 里把 apiUrl 配成 http://<本机>:3000/bridge/apimart、
# apiKey 配成 AIC_BRIDGE_KEY，它的图像节点即可在本地 ComfyUI worker 上出图。
AIC_BRIDGE_KEY = (os.getenv("AIC_BRIDGE_KEY", "aitool-local") or "").strip()
AIC_BRIDGE_DEFAULT_WORKFLOW = (os.getenv("AIC_BRIDGE_DEFAULT_WORKFLOW", "Z-Image.json") or "").strip()

def _bridge_auth_ok(request: Request) -> bool:
    raw = request.headers.get("Authorization", "")
    key = re.sub(r"^Bearer\s+", "", raw, flags=re.IGNORECASE).strip()
    return bool(AIC_BRIDGE_KEY) and key == AIC_BRIDGE_KEY

def _bridge_error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": "invalid_request_error"}})

def _bridge_resolve_workflow(model: str) -> str:
    published = workflow_list_items(public_only=True)
    by_name = {w["name"]: w for w in published}
    if model in by_name:
        return model
    for w in published:
        if w.get("title") == model:
            return w["name"]
    if AIC_BRIDGE_DEFAULT_WORKFLOW in by_name:
        return AIC_BRIDGE_DEFAULT_WORKFLOW
    return published[0]["name"] if published else ""

@app.get("/bridge/apimart/v1/models")
def bridge_apimart_models(request: Request):
    if not _bridge_auth_ok(request):
        return _bridge_error(401, "无效的本地桥 API Key")
    data = [
        {"id": w["name"], "object": "model", "owned_by": "aitoolstudio-local", "name": w.get("title") or w["name"]}
        for w in workflow_list_items(public_only=True)
    ]
    return {"object": "list", "data": data}

@app.get("/bridge/apimart/v1/balance")
def bridge_apimart_balance(request: Request):
    # 本地算力不计费，返回大额余额避免前端弹「余额不足」
    return {"code": 0, "balance": 999999, "data": {"balance": 999999, "currency": "LOCAL"}}

@app.post("/bridge/apimart/v1/images/generations")
def bridge_apimart_images(payload: Dict[str, Any], request: Request):
    if not _bridge_auth_ok(request):
        return _bridge_error(401, "无效的本地桥 API Key")
    prompt = str(payload.get("prompt") or "").strip()
    model = str(payload.get("model") or "").strip()
    name = _bridge_resolve_workflow(model)
    if not name:
        return _bridge_error(400, "平台没有已发布的工作流，请先在 ComfyUI 工作台发布")
    cfg = load_workflow_config(name)
    params: Dict[str, Dict[str, Any]] = {}
    prompt_field = None
    for f in cfg.fields:
        if not f.enabled or f.hidden or f.type not in ("text", "textarea"):
            continue
        haystack = f"{f.input} {f.name}".lower()
        if "prompt" in haystack or "提示" in haystack or f.required:
            prompt_field = f
            break
    if prompt_field is None:
        prompt_field = next((f for f in cfg.fields if f.enabled and f.type in ("text", "textarea")), None)
    if prompt_field and prompt and prompt_field.node and prompt_field.input:
        params.setdefault(prompt_field.node, {})[prompt_field.input] = prompt
    req_g = GenerateRequest(
        prompt="",
        workflow_json=name,
        params=params,
        type="canvaspro-bridge",
        client_id=str(uuid.uuid4()),
    )
    result = run_comfy_generate(req_g, owner_key="canvaspro-bridge")
    record_workflow_last_test(name, {"username": "canvaspro-bridge"}, result, {prompt_field.id if prompt_field else "prompt": prompt})
    host = request.headers.get("host") or "192.168.1.60:3000"
    base = f"{request.url.scheme}://{host}"
    urls = [(base + u) if str(u).startswith("/") else str(u) for u in (result.get("images") or [])]
    if not urls:
        return _bridge_error(502, "工作流执行成功但没有图像输出")
    return {"created": now_ts(), "data": [{"url": u} for u in urls]}

@app.get("/api/comfyui/workbench-workflows")
def get_comfyui_workbench_workflows(request: Request):
    """ComfyTV 工作流面板：全部 workflow（含未启用草稿）+ 各 worker 节点兼容性 + 最近跑通记录。"""
    require_admin_user(request)
    items = workflow_list_items(public_only=False)
    backend_classes: Dict[str, Any] = {}
    backend_errors: Dict[str, str] = {}
    for addr in COMFYUI_INSTANCES:
        classes, err = get_backend_object_classes(addr)
        backend_classes[addr] = classes
        backend_errors[addr] = err or ""
    for item in items:
        try:
            required = collect_required_workflow_class_types(item["name"])
        except Exception:
            required = []
        instances = []
        compatible_count = 0
        for addr in COMFYUI_INSTANCES:
            classes = backend_classes.get(addr)
            if classes is None:
                instances.append({
                    "address": addr,
                    "reachable": False,
                    "error": backend_errors.get(addr) or "object_info 不可用",
                    "missing_nodes": [],
                    "compatible": False,
                })
                continue
            missing = [node for node in required if node not in classes]
            compatible = not missing
            if compatible:
                compatible_count += 1
            instances.append({
                "address": addr,
                "reachable": True,
                "error": "",
                "missing_nodes": missing,
                "compatible": compatible,
            })
        item["required_class_count"] = len(required)
        item["instances"] = instances
        item["compatible_count"] = compatible_count
    return {
        "workflows": items,
        "instance_addresses": list(COMFYUI_INSTANCES),
        "updated_at": now_ts(),
    }

@app.put("/api/comfyui/instances")
def save_comfyui_instances(payload: ComfyInstancesPayload, request: Request):
    require_admin_user(request)
    # 宽容校验：去前后空白、去 http(s):// 前缀、去尾部斜杠；要求形如 host:port
    cleaned = []
    for item in payload.instances:
        s = str(item or "").strip()
        if not s:
            continue
        s = re.sub(r"^https?://", "", s)
        s = s.rstrip("/")
        if ":" not in s:
            raise HTTPException(status_code=400, detail=f"地址缺少端口号：{item}（应为 host:port，例如 127.0.0.1:8188）")
        host, _, port = s.rpartition(":")
        if not host or not port.isdigit():
            raise HTTPException(status_code=400, detail=f"地址不合法：{item}（应为 host:port，例如 127.0.0.1:8188）")
        if s in cleaned:
            continue
        cleaned.append(s)
    if not cleaned:
        raise HTTPException(status_code=400, detail="至少保留一个 ComfyUI 后端地址")
    # 写入 env 文件
    try:
        update_env_values({"COMFYUI_INSTANCES": ",".join(cleaned)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入 env 失败：{e}")
    # 更新进程中的全局变量
    global COMFYUI_INSTANCES, COMFYUI_ADDRESS, BACKEND_LOCAL_LOAD
    COMFYUI_INSTANCES = cleaned
    COMFYUI_ADDRESS = cleaned[0]
    new_load = {addr: 0 for addr in cleaned}
    for addr, n in (BACKEND_LOCAL_LOAD or {}).items():
        if addr in new_load:
            new_load[addr] = n
    BACKEND_LOCAL_LOAD = new_load
    with OBJECT_INFO_CACHE_LOCK:
        BACKEND_OBJECT_INFO_CACHE.clear()
    return {"instances": COMFYUI_INSTANCES}

@app.get("/api/resource-root")
def get_resource_root(request: Request):
    require_admin_user(request)
    cfg = get_resource_root_config()
    state = inspect_resource_root(cfg.get("resource_root") or "", create_missing=False)
    state["source"] = cfg.get("source") or ""
    return {
        "resource_root": cfg.get("resource_root") or "",
        "source": cfg.get("source") or "",
        "configured": bool(cfg.get("configured")),
        "detection": state,
    }

@app.put("/api/resource-root")
def save_resource_root(payload: ResourceRootPayload, request: Request):
    require_admin_user(request)
    cleaned = normalize_resource_root_path(payload.resource_root)
    try:
        update_env_values({
            RESOURCE_ROOT_PRIMARY_ENV: cleaned,
            RESOURCE_ROOT_SECONDARY_ENV: cleaned,
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存资源根目录失败：{exc}")
    cfg = get_resource_root_config()
    state = inspect_resource_root(cfg.get("resource_root") or "", create_missing=bool(payload.create_missing))
    state["source"] = cfg.get("source") or ""
    return {
        "resource_root": cfg.get("resource_root") or "",
        "source": cfg.get("source") or "",
        "configured": bool(cfg.get("configured")),
        "detection": state,
    }

@app.post("/api/resource-root/detect")
def detect_resource_root(payload: ResourceRootDetectPayload, request: Request):
    require_admin_user(request)
    cfg = get_resource_root_config()
    state = inspect_resource_root(cfg.get("resource_root") or "", create_missing=bool(payload.create_missing))
    state["source"] = cfg.get("source") or ""
    return {
        "resource_root": cfg.get("resource_root") or "",
        "source": cfg.get("source") or "",
        "configured": bool(cfg.get("configured")),
        "detection": state,
    }

@app.post("/api/resource-root/models/check")
def check_resource_root_models(payload: ResourceRootModelCheckPayload, request: Request):
    require_admin_user(request)
    cfg = get_resource_root_config()
    state = inspect_resource_root(cfg.get("resource_root") or "", create_missing=False)
    state["source"] = cfg.get("source") or ""
    detected = detect_model_dependencies_in_resource_root(payload.model_dependencies or [], state)
    return {
        "resource_root": cfg.get("resource_root") or "",
        "source": cfg.get("source") or "",
        "detection": state,
        "model_dependencies": detected.get("items") or [],
        "summary": detected.get("summary") or {},
    }

@app.post("/api/workflow-install/tasks")
def create_workflow_install_task(payload: WorkflowInstallTaskRequest, request: Request):
    require_admin_user(request)
    actions = normalize_workflow_install_task_actions(payload.actions or [])
    return start_workflow_install_task(actions)

@app.post("/api/workflow-install/model-candidates")
def workflow_install_model_candidates(payload: WorkflowModelCandidatesRequest, request: Request):
    require_admin_user(request)
    action = workflow_model_candidate_request_action(payload)
    return workflow_install_find_model_candidates_for_action(action)

@app.post("/api/workflow-install/auto-model-downloads")
def workflow_install_auto_model_downloads(payload: WorkflowAutoModelDownloadsRequest, request: Request):
    require_admin_user(request)
    return build_auto_model_downloads_response(payload.actions or [])

@app.get("/api/workflow-install/tasks/{task_id}")
def get_workflow_install_task(task_id: str, request: Request):
    require_admin_user(request)
    return workflow_install_task_snapshot(task_id)

@app.get("/api/workflows")
def list_workflows(request: Request):
    return {"workflows": workflow_list_items(public_only=not is_admin_request(request))}

@app.get("/api/workflows-public")
def list_public_workflows():
    return {"workflows": workflow_list_items(public_only=True)}

@app.get("/api/workflows-public/{name:path}")
def get_public_workflow(name: str):
    if not WORKFLOW_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid workflow name")
    workflow_path = workflow_path_from_name(name)
    if not os.path.exists(workflow_path):
        raise HTTPException(status_code=404, detail="Workflow not found")
    cfg = load_workflow_config(name)
    if not cfg.enabled:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"name": name, "config": workflow_public_config(cfg), "builtin": is_builtin_workflow(name)}

@app.get("/api/workflows/{name:path}")
def get_workflow(name: str, request: Request):
    if not WORKFLOW_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid workflow name")
    workflow_path = workflow_path_from_name(name)
    if not os.path.exists(workflow_path):
        raise HTTPException(status_code=404, detail="Workflow not found")
    cfg = load_workflow_config(name)
    if not is_admin_request(request):
        if not cfg.enabled:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"name": name, "config": workflow_public_config(cfg), "builtin": is_builtin_workflow(name)}
    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)
    return {"name": name, "workflow": workflow, "config": cfg.dict(), "builtin": is_builtin_workflow(name)}

@app.post("/api/workflows")
def upload_workflow(payload: WorkflowUploadRequest):
    if not isinstance(payload.workflow, dict) or not payload.workflow:
        raise HTTPException(status_code=400, detail="工作流 JSON 为空")
    result = save_custom_workflow_with_candidates(payload.name, payload.workflow, default_enabled=True)
    return {"name": result["name"]}

@app.post("/api/workflows/import/plan")
async def import_workflow_plan(payload: WorkflowImportPlanRequest):
    source_type = str(payload.source_type or "").strip().lower()
    if source_type not in {"workflow_json", "runninghub_ref"}:
        raise HTTPException(status_code=400, detail="source_type 仅支持 workflow_json 或 runninghub_ref")
    workflow_json: Optional[Dict[str, Any]] = None
    source_info: Dict[str, Any] = {"source_type": source_type, "source_value": str(payload.source_value or "").strip()}
    raw_runninghub_response = None

    if source_type == "workflow_json":
        workflow_json = normalize_comfy_api_workflow_payload(payload.workflow_json)
        if not workflow_json:
            raise HTTPException(status_code=400, detail="请粘贴有效的 ComfyUI API 工作流 JSON（需包含 class_type）")
    else:
        parsed = parse_runninghub_workflow_ref(payload.source_value)
        source_info["parsed"] = parsed
        if not parsed.get("ok"):
            raise HTTPException(status_code=400, detail=parsed.get("message") or "RunningHub 引用解析失败")
        if parsed.get("kind") == "post":
            post_id = str(parsed.get("post_id") or "").strip()
            return {
                "success": False,
                "status": "need_workflow_json",
                "message": f"当前 RunningHub OpenAPI 不能直接使用 postId（{post_id}）拉取 API 工作流，请改为粘贴/上传 API workflow JSON，或提供 /run/workflow/{{id}} 链接。",
                "source": source_info,
                "workflow": None,
                "compatibility": [],
                "model_dependencies": [],
                "plan_items": [
                    "无法直接通过 postId 拉取 API workflow",
                    "请在 RunningHub 导出 API workflow JSON 后粘贴/上传",
                    "或改为 /run/workflow/{id} / 纯数字 workflowId",
                ],
                "saved_workflow": None,
                "install_plan": {"actions": [], "summary": {"action_count": 0, "model_download_count": 0, "custom_node_install_count": 0}},
            }
        workflow_id = str(parsed.get("workflow_id") or "").strip()
        source_info["workflow_id"] = workflow_id
        _, workflow_json, raw_runninghub_response = await fetch_runninghub_workflow_json_by_id(workflow_id)

    if not workflow_json:
        raise HTTPException(status_code=400, detail="未获取到有效 workflow JSON")

    required_class_types = collect_required_workflow_class_types(workflow_json)
    compatibility = collect_instance_node_compatibility(required_class_types)
    model_dependencies = collect_workflow_model_dependencies(workflow_json)
    resource_root_config = get_resource_root_config()
    resource_root_state = inspect_resource_root(resource_root_config.get("resource_root") or "", create_missing=False)
    resource_root_state["source"] = resource_root_config.get("source") or ""
    model_detection_summary = None
    if model_dependencies:
        detected = detect_model_dependencies_in_resource_root(model_dependencies, resource_root_state)
        model_dependencies = detected["items"]
        model_detection_summary = detected.get("summary") or {}

    suggested_name = payload.workflow_name.strip()
    if not suggested_name:
        if source_type == "runninghub_ref" and source_info.get("workflow_id"):
            suggested_name = f"runninghub-{source_info['workflow_id']}"
        else:
            suggested_name = "imported-workflow"

    saved_workflow = None
    if payload.save_workflow:
        saved_workflow = save_custom_workflow_with_candidates(
            suggested_name,
            workflow_json,
            suggested_title=suggested_name,
            default_enabled=False,
        )

    plan_items = build_workflow_import_plan_items(
        saved_workflow["name"] if saved_workflow else "",
        compatibility,
        model_dependencies,
        resource_root_state=resource_root_state,
    )
    install_plan = build_workflow_install_plan(
        compatibility,
        model_dependencies,
        resource_root_state=resource_root_state,
    )
    compatible_count = sum(1 for item in compatibility if item.get("compatible"))
    node_count = len(list(iter_workflow_nodes(workflow_json)))
    return {
        "success": True,
        "status": "ok",
        "message": "导入预检完成",
        "source": source_info,
        "workflow": {
            "name": saved_workflow["name"] if saved_workflow else "",
            "title": saved_workflow["title"] if saved_workflow else suggested_name,
            "node_count": node_count,
            "required_class_types": required_class_types,
            "required_class_count": len(required_class_types),
        },
        "compatibility": compatibility,
        "compatibility_summary": {
            "instance_count": len(compatibility),
            "compatible_count": compatible_count,
        },
        "model_dependencies": model_dependencies,
        "model_detection_summary": model_detection_summary,
        "resource_root": resource_root_state,
        "saved_workflow": saved_workflow,
        "plan_items": plan_items,
        "install_plan": install_plan,
        "raw_runninghub": raw_runninghub_response if source_type == "runninghub_ref" else None,
    }

@app.put("/api/workflows/{name:path}/config")
def save_workflow_config(name: str, payload: WorkflowConfig):
    if not WORKFLOW_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid workflow name")
    workflow_path = workflow_path_from_name(name)
    if not os.path.exists(workflow_path):
        raise HTTPException(status_code=404, detail="Workflow not found")
    if payload.last_test is None:
        payload.last_test = load_workflow_config(name).last_test
    save_workflow_config_data(name, payload)
    return {"config": payload.dict()}

@app.delete("/api/workflows/{name:path}")
def delete_workflow(name: str):
    if not WORKFLOW_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid workflow name")
    if is_builtin_workflow(name):
        raise HTTPException(status_code=400, detail="内置工作流不可删除")
    if is_shared_workflow(name):
        raise HTTPException(status_code=400, detail="共享盘工作流为只读挂载，请直接在 60 盘目录中管理文件")
    workflow_path = workflow_path_from_name(name)
    cfg_path = workflow_config_path(name)
    if not os.path.exists(workflow_path):
        raise HTTPException(status_code=404, detail="Workflow not found")
    os.remove(workflow_path)
    if os.path.exists(cfg_path):
        os.remove(cfg_path)
    return {"ok": True}

@app.post("/api/workflows/{name:path}/run")
def run_workflow(name: str, payload: WorkflowRunRequest, request: Request):
    if not WORKFLOW_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid workflow name")
    if not os.path.exists(workflow_path_from_name(name)):
        raise HTTPException(status_code=404, detail="Workflow not found")
    user = require_current_user(request)
    cfg = payload.config if user.get("is_admin") and payload.config else load_workflow_config(name)
    if not user.get("is_admin") and not cfg.enabled:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # 普通用户只按服务端保存的可见字段映射；隐藏字段只能使用后台保存的默认值。
    params: Dict[str, Dict[str, Any]] = {}
    for field in cfg.fields:
        if not field.enabled:
            continue
        if not field.node or not field.input:
            continue
        has_client_value = field.id in payload.fields and not field.hidden
        value = payload.fields[field.id] if has_client_value else field.default
        if field.required and (value is None or value == ""):
            raise HTTPException(status_code=400, detail=f"缺少必填参数：{field.name or field.input}")
        if value is None or (value == "" and not field.required):
            continue
        # 类型转换
        if field.type in ("number", "slider"):
            try:
                value = float(value) if (field.step and field.step < 1) else int(float(value))
            except Exception:
                pass
        elif field.type == "boolean":
            if isinstance(value, str):
                value = value.strip().lower() in {"1", "true", "yes", "on", "y"}
            else:
                value = bool(value)
        elif field.type == "dropdown":
            # 下拉值如果看起来是数字（如 "1024" / "2048" / "0.8"），自动转成 int/float
            if isinstance(value, str):
                s = value.strip()
                try:
                    if s and ('.' in s or 'e' in s.lower()):
                        value = float(s)
                    elif s and (s.lstrip('-').isdigit()):
                        value = int(s)
                except (ValueError, TypeError):
                    pass
        params.setdefault(field.node, {})[field.input] = value
    apply_ltx_public_run_defaults(name, params)
    instance_override = ""
    if user.get("is_admin") and payload.instance:
        instance_override = str(payload.instance).strip()
    req = GenerateRequest(
        prompt="",
        workflow_json=name,
        params=params,
        type="workflow-test",
        client_id=payload.client_id or str(uuid.uuid4()),
    )
    result = run_comfy_generate(req, owner_key=owner_key_from_user(user), instance_override=instance_override)
    record_workflow_last_test(name, user, result, payload.fields)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
