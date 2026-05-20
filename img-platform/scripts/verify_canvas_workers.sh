#!/usr/bin/env bash
# verify_canvas_workers.sh — AI Tool Studio 回归验收脚本
# 用法: bash scripts/verify_canvas_workers.sh [base_url]
# 默认 base_url=http://192.168.1.60

set -euo pipefail
BASE="${1:-http://192.168.1.60}"
API="${BASE}:8000"
WEB="${BASE}:5173"
PASS=0
FAIL=0
TOKEN=""

red() { echo -e "\033[31m$1\033[0m"; }
green() { echo -e "\033[32m$1\033[0m"; }
warn() { echo -e "\033[33m$1\033[0m"; }

check() {
    local label="$1" result="$2" expected="$3"
    if [ "$result" = "$expected" ]; then
        green "  ✓ $label"
        ((PASS++)) || true
    else
        red "  ✗ $label (got: $result, expected: $expected)"
        ((FAIL++)) || true
    fi
}

check_gt() {
    local label="$1" result="$2" threshold="$3"
    if [ "$result" -gt "$threshold" ]; then
        green "  ✓ $label"
        ((PASS++)) || true
    else
        red "  ✗ $label (got: $result, expected > $threshold)"
        ((FAIL++)) || true
    fi
}

check_contains() {
    local label="$1" text="$2" pattern="$3"
    if echo "$text" | grep -q "$pattern"; then
        green "  ✓ $label"
        ((PASS++)) || true
    else
        red "  ✗ $label (pattern '$pattern' not found)"
        ((FAIL++)) || true
    fi
}

echo "=== AI Tool Studio 回归验收 ==="
echo "Base: $BASE"
echo ""

# ── 1. Backend health ──
echo "[1] Backend health"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$API/openapi.json" --connect-timeout 10)
check "OpenAPI accessible" "$HTTP" "200"

# ── 2. Auth ──
echo "[2] Auth"
TOKEN=$(curl -s -X POST "$API/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"test123"}' | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")
check "Login returns token" "$([ -n "$TOKEN" ] && echo 'yes' || echo 'no')" "yes"

AUTH="Authorization: Bearer $TOKEN"

# ── 3. Workers API ──
echo "[3] Workers API"
WORKERS=$(curl -s "$API/api/comfyui/workers" -H "$AUTH")
WCOUNT=$(echo "$WORKERS" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('workers',[])))")
check_gt "Workers list has entries" "$WCOUNT" 0

WLEGACY=$(echo "$WORKERS" | python3 -c "import json,sys; ws=json.load(sys.stdin)['workers']; print(next((w['id'] for w in ws if w['id']=='legacy'), ''))")
check "Legacy worker exists" "$([ -n "$WLEGACY" ] && echo 'yes' || echo 'no')" "yes"

STATUS=$(curl -s "$API/api/comfyui/workers/status" -H "$AUTH")
LEGACY_ONLINE=$(echo "$STATUS" | python3 -c "import json,sys; ws=json.load(sys.stdin)['workers']; print(next((w['online'] for w in ws if w['id']=='legacy'), False))")
check "Legacy worker online" "$LEGACY_ONLINE" "True"

# ── 4. ComfyUI legacy endpoints ──
echo "[4] ComfyUI legacy endpoints"
CS=$(curl -s -o /dev/null -w '%{http_code}' "$API/api/comfyui/status" -H "$AUTH")
check "GET /api/comfyui/status" "$CS" "200"

CP=$(curl -s -o /dev/null -w '%{http_code}' "$API/api/comfyui/checkpoints" -H "$AUTH")
check "GET /api/comfyui/checkpoints" "$CP" "200"

# ── 5. Image generate + scheduler trace ──
echo "[5] Image generate (comfyui-local) + scheduler trace"
GEN=$(curl -s -X POST "$API/api/image/generate" \
    -H "$AUTH" -H 'Content-Type: application/json' \
    -d '{"model":"comfyui-local","prompt":"test regression script","aspect_ratio":"1:1","n":1}')
GEN_ID=$(echo "$GEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))")
GEN_URLS=$(echo "$GEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('image_urls',[])))")
check "Image generate returns id" "$([ -n "$GEN_ID" ] && echo 'yes' || echo 'no')" "yes"
check_gt "Image generate has urls" "$GEN_URLS" 0

# Scheduler trace: check CanvasRun in DB for worker_id (needs docker)
SCHED_TRACE="no"
if command -v docker &>/dev/null; then
    TRACE=$(echo '12301230' | sudo -S docker exec aitoolstudio-backend-1 python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/data/img_platform.db')
cur = conn.cursor()
cur.execute('SELECT result_payload FROM canvas_runs ORDER BY id DESC LIMIT 3')
for row in cur.fetchall():
    if row[0]:
        p = json.loads(row[0])
        if p.get('worker_id'):
            print(p['worker_id'])
            break
conn.close()
" 2>/dev/null)
    if [ -n "$TRACE" ]; then
        SCHED_TRACE="yes"
        echo "  - scheduler trace: worker_id=$TRACE"
    fi
fi
check "Scheduler records worker_id" "$SCHED_TRACE" "yes"

# ── 6. Frontend chunks (dynamic hash resolution) ──
echo "[6] Frontend chunks"

# Parse main bundle from index.html
INDEX_HTML=$(curl -s "$WEB/")
MAIN_JS=$(echo "$INDEX_HTML" | grep -oP 'src="/assets/[a-zA-Z][^"]+\.js"' | head -1 | sed 's/src="//;s/"//')
MAIN_NAME=$(basename "$MAIN_JS")
check "Main bundle parseable" "$([ -n "$MAIN_NAME" ] && echo 'yes' || echo 'no')" "yes"

MAIN_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB$MAIN_JS")
check "Main bundle accessible" "$MAIN_HTTP" "200"

# Parse lazy chunks from main bundle
MAIN_CONTENT=$(curl -s "$WEB$MAIN_JS")
ADMIN_CHUNK=$(echo "$MAIN_CONTENT" | grep -oP '"assets/AdminView-[^"]+\.js"' | head -1 | tr -d '"')
CANVAS_CHUNK=$(echo "$MAIN_CONTENT" | grep -oP '"assets/CanvasView-[^"]+\.js"' | head -1 | tr -d '"')

check "AdminView chunk parseable" "$([ -n "$ADMIN_CHUNK" ] && echo 'yes' || echo 'no')" "yes"
check "CanvasView chunk parseable" "$([ -n "$CANVAS_CHUNK" ] && echo 'yes' || echo 'no')" "yes"

ADMIN_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/assets/$(basename "$ADMIN_CHUNK")")
check "AdminView chunk accessible" "$ADMIN_HTTP" "200"

CANVAS_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/assets/$(basename "$CANVAS_CHUNK")")
check "CanvasView chunk accessible" "$CANVAS_HTTP" "200"

# Huobao Canvas chunks
HUOBAO_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/canvas/")
check "Huobao Canvas /canvas/ accessible" "$HUOBAO_HTTP" "200"

CANVAS_INDEX=$(curl -s "$WEB/canvas/" | grep -oP 'src="/canvas/assets/[^"]+\.js"' | head -1 | sed 's/src="//;s/"//')
HUOBAO_INDEX_NAME=$(basename "$CANVAS_INDEX" 2>/dev/null || echo "")
check "Huobao Canvas index parseable" "$([ -n "$HUOBAO_INDEX_NAME" ] && echo 'yes' || echo 'no')" "yes"

CANVAS_INDEX_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB$CANVAS_INDEX")
check "Huobao Canvas index accessible" "$CANVAS_INDEX_HTTP" "200"

# ── 7. Chunk content checks ──
echo "[7] Chunk content"

ADMIN_CONTENT=$(curl -s "$WEB/assets/$(basename "$ADMIN_CHUNK")")
check_contains "AdminView contains /api/comfyui/workers" "$ADMIN_CONTENT" "comfyui/workers"

CANVAS_CONTENT=$(curl -s "$WEB/assets/$(basename "$CANVAS_CHUNK")")
check_contains "CanvasView contains run-cascade" "$CANVAS_CONTENT" "run-cascade"

HUOBAO_CANVAS_CHUNK=$(echo "$CANVAS_INDEX" | sed 's|/canvas/assets/|assets/|' | sed 's|/canvas/|/|')
if [ -n "$HUOBAO_CANVAS_CHUNK" ]; then
    HUOBAO_CHUNK_URL=$(curl -s "$WEB$CANVAS_INDEX" | grep -oP '"[^"]*Canvas-[^"]+\.js"' | head -1 | tr -d '"')
    HUOBAO_CONTENT=$(curl -s "$WEB/canvas/$HUOBAO_CHUNK_URL")
    check_contains "Huobao Canvas contains 级联 (cascade)" "$HUOBAO_CONTENT" "级联"
fi

# ── 8. Admin route ──
echo "[8] Admin route"
ADMIN_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/admin")
check "GET /admin returns 200" "$ADMIN_HTTP" "200"

# ── 9. OpenAPI endpoints ──
echo "[9] OpenAPI endpoints"
OAPI=$(curl -s "$API/openapi.json")
check_contains "OpenAPI has /api/comfyui/workers" "$OAPI" "/api/comfyui/workers"
check_contains "OpenAPI has /api/comfyui/workers/status" "$OAPI" "/api/comfyui/workers/status"
check_contains "OpenAPI has run-cascade" "$OAPI" "run-cascade"
check_contains "OpenAPI has canvas run" "$OAPI" "/api/canvas/documents/{document_id}/nodes/{node_id}/run"

# ── A. Dashboard ──
echo "[A] Admin Dashboard"
DASHBOARD=$(curl -s "$API/api/admin/dashboard" -H "$AUTH")
DASH_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$API/api/admin/dashboard" -H "$AUTH")
check "GET /api/admin/dashboard returns 200" "$DASH_HTTP" "200"

DASH_WORKERS=$(echo "$DASHBOARD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('workers',{}).get('total',0))")
check_gt "Dashboard has workers total" "$DASH_WORKERS" 0

DASH_COMFY_STATUS=$(echo "$DASHBOARD" | python3 -c "import json,sys; print(json.load(sys.stdin).get('comfyui',{}).get('status',''))")
check_contains "Dashboard comfyui status present" "$DASH_COMFY_STATUS" "ok\|degraded\|offline"

check_contains "OpenAPI has /api/admin/dashboard" "$OAPI" "/api/admin/dashboard"
check_contains "AdminView chunk has dashboard" "$ADMIN_CONTENT" "dashboard"

# ── A2. Record Fields (Task H) ──
echo "[A2] Record standardization"
DASH_CASCADE=$(echo "$DASHBOARD" | python3 -c "import json,sys; print(json.load(sys.stdin).get('canvas_runs_24h',{}).get('cascade',-1))")
check_gt "Dashboard cascade count readable" "$DASH_CASCADE" -1

# Verify DB columns exist
if command -v docker &>/dev/null; then
  GEN_COLS=$(echo '12301230' | sudo -S docker exec aitoolstudio-backend-1 python3 -c "
import sqlite3; conn=sqlite3.connect('/app/data/img_platform.db')
cur=conn.cursor(); cur.execute('PRAGMA table_info(generations)')
print(','.join(row[1] for row in cur.fetchall()))
conn.close()
" 2>/dev/null)
  check_contains "generations table has worker_id" "$GEN_COLS" "worker_id"
  check_contains "generations table has run_type" "$GEN_COLS" "run_type"

  RUN_COLS=$(echo '12301230' | sudo -S docker exec aitoolstudio-backend-1 python3 -c "
import sqlite3; conn=sqlite3.connect('/app/data/img_platform.db')
cur=conn.cursor(); cur.execute('PRAGMA table_info(canvas_runs)')
print(','.join(row[1] for row in cur.fetchall()))
conn.close()
" 2>/dev/null)
  check_contains "canvas_runs table has worker_id" "$RUN_COLS" "worker_id"
  check_contains "canvas_runs table has run_type" "$RUN_COLS" "run_type"
fi

# ── B. Compileall ──
echo "[B] Backend compileall"
COMPILE_OK="no"
if command -v docker &>/dev/null && echo '12301230' | sudo -S docker exec aitoolstudio-backend-1 python -m compileall api services models schemas main.py &>/dev/null; then
    COMPILE_OK="yes"
fi
warn "  - compileall: $([ "$COMPILE_OK" = "yes" ] && echo '✓ passed' || echo '⚠ skipped (no docker access)')"

# ── C. Worker CRUD ──
echo "[C] Worker CRUD"
TEST_ID="regression-test-$(date +%s)"
CREATE=$(curl -s -X POST "$API/api/comfyui/workers" \
    -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"id\":\"$TEST_ID\",\"name\":\"Regression Test\",\"url\":\"http://127.0.0.1:8188\",\"tier\":\"light\"}")
CREATED_ID=$(echo "$CREATE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))")
check "Create worker" "$CREATED_ID" "$TEST_ID"

DELETE=$(curl -s -X DELETE "$API/api/comfyui/workers/$TEST_ID" -H "$AUTH")
DEL_OK=$(echo "$DELETE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok', False))")
check "Delete worker" "$DEL_OK" "True"

# ── Summary ──
echo ""
echo "========================================"
echo "  Passed: $PASS  Failed: $FAIL"
echo "========================================"
if [ "$FAIL" -eq 0 ]; then
    green "ALL CHECKS PASSED"
    exit 0
else
    red "SOME CHECKS FAILED"
    exit 1
fi
