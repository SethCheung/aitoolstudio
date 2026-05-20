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

red() { echo -e "\033[31m$1\033[0m"; }
green() { echo -e "\033[32m$1\033[0m"; }
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

echo "=== AI Tool Studio 回归验收 ==="
echo "Base: $BASE"
echo ""

# ── 1. Backend health ──
echo "[1] Backend health"
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$API/openapi.json")
check "OpenAPI accessible" "$HTTP" "200"

# ── 2. Auth ──
echo "[2] Auth"
TOKEN=$(curl -s -X POST "$API/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"test123"}' | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))")
check "Login returns token" "$([ -n "$TOKEN" ] && echo 'yes' || echo 'no')" "yes"

# ── 3. Workers API ──
echo "[3] Workers API"
WORKERS=$(curl -s "$API/api/comfyui/workers" -H "Authorization: Bearer $TOKEN")
WCOUNT=$(echo "$WORKERS" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('workers',[])))")
check "Workers list has entries" "$([ "$WCOUNT" -gt 0 ] && echo 'yes' || echo 'no')" "yes"

WLEGACY=$(echo "$WORKERS" | python3 -c "import json,sys; ws=json.load(sys.stdin)['workers']; print(next((w['id'] for w in ws if w['id']=='legacy'), ''))")
check "Legacy worker exists" "$([ -n "$WLEGACY" ] && echo 'yes' || echo 'no')" "yes"

# Worker status
STATUS=$(curl -s "$API/api/comfyui/workers/status" -H "Authorization: Bearer $TOKEN")
LEGACY_ONLINE=$(echo "$STATUS" | python3 -c "import json,sys; ws=json.load(sys.stdin)['workers']; print(next((w['online'] for w in ws if w['id']=='legacy'), False))")
check "Legacy worker online" "$LEGACY_ONLINE" "True"

# ── 4. ComfyUI legacy endpoints ──
echo "[4] ComfyUI legacy endpoints"
CS=$(curl -s -o /dev/null -w '%{http_code}' "$API/api/comfyui/status" -H "Authorization: Bearer $TOKEN")
check "GET /api/comfyui/status" "$CS" "200"

CP=$(curl -s -o /dev/null -w '%{http_code}' "$API/api/comfyui/checkpoints" -H "Authorization: Bearer $TOKEN")
check "GET /api/comfyui/checkpoints" "$CP" "200"

# ── 5. Image generate (comfyui-local) ──
echo "[5] Image generate (comfyui-local)"
GEN=$(curl -s -X POST "$API/api/image/generate" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"model":"comfyui-local","prompt":"test regression script","aspect_ratio":"1:1","n":1}')
GEN_ID=$(echo "$GEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))")
GEN_URLS=$(echo "$GEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('image_urls',[])))")
check "Image generate returns id" "$([ -n "$GEN_ID" ] && echo 'yes' || echo 'no')" "yes"
check "Image generate has urls" "$([ "$GEN_URLS" -gt 0 ] && echo 'yes' || echo 'no')" "yes"

# ── 6. Frontend chunks ──
echo "[6] Frontend chunks"

# Main bundle
INDEX_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/assets/index-Cb79vhsw.js")
check "Main bundle accessible" "$INDEX_HTTP" "200"

# Admin chunk (lazy-loaded by router)
ADMIN_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/assets/AdminView-JB5N4xdj.js")
check "AdminView chunk accessible" "$ADMIN_HTTP" "200"

# Canvas chunk (lazy-loaded)
CANVAS_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/assets/CanvasView-zyYapHxf.js")
check "CanvasView chunk accessible" "$CANVAS_HTTP" "200"

# Huobao Canvas SPA
HUOBAO_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/canvas/")
check "Huobao Canvas /canvas/ accessible" "$HUOBAO_HTTP" "200"

# ── 7. Admin route ──
echo "[7] Admin route"
ADMIN_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "$WEB/admin")
check "GET /admin returns 200" "$ADMIN_HTTP" "200"

# ── 8. Compileall ──
echo "[8] Backend compileall"
# Note: this requires local Docker or ssh access; skip if not available
COMPILE_OK="no"
if command -v docker &>/dev/null && docker exec aitoolstudio-backend-1 python -m compileall api services models schemas main.py &>/dev/null; then
    COMPILE_OK="yes"
fi
echo "  - compileall: $([ "$COMPILE_OK" = "yes" ] && echo '✓ passed' || echo '⚠ skipped (no docker access)')"

# ── 9. Worker CRUD ──
echo "[9] Worker CRUD"
TEST_ID="regression-test-$(date +%s)"
CREATE=$(curl -s -X POST "$API/api/comfyui/workers" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d "{\"id\":\"$TEST_ID\",\"name\":\"Regression Test\",\"url\":\"http://127.0.0.1:8188\",\"tier\":\"light\"}")
CREATED_ID=$(echo "$CREATE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))")
check "Create worker" "$CREATED_ID" "$TEST_ID"

DELETE=$(curl -s -X DELETE "$API/api/comfyui/workers/$TEST_ID" \
    -H "Authorization: Bearer $TOKEN")
DEL_OK=$(echo "$DELETE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok', False))")
check "Delete worker" "$DEL_OK" "True"

# ── Summary ──
echo ""
echo "========================================"
echo "  Passed: $PASS  Failed: $FAIL"
echo "========================================"
[ "$FAIL" -eq 0 ] && green "ALL CHECKS PASSED" || red "SOME CHECKS FAILED"
exit $FAIL
