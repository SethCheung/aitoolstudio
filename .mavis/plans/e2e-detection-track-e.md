# E2E-E Track — GPT 对话 + 画布 LLM + 会话管理 端到端

**测试目标**：192.168.1.60:3000 部署
**测试时间**：2026-06-04 16:20–16:24 (Asia/Shanghai)
**测试 Token**：`21422613-d16c-4adc-b07e-b7ae2868fceb` (user_id=`ip-192.168.1.190`)
**上游 base_url**：`https://api.minimaxi.com` (comfly provider, primary=false, has_key=true, preview `sk-c...rPLY`)

**结论**：
- 会话 CRUD = ✅ 全通
- GPT 对话（带 model）= ✅ 200，完整回复
- GPT 流式 = ✅ 真的流（4 个 SSE chunk：1 meta + 2 delta + 1 done）
- 画布 LLM = ✅ 200，text 字段 938 字符
- 测试数据 = ✅ 已清理（list 回到原始 5 条）

---

## §0 探测矩阵

| # | 端点 | 方法 | 期望 | 实际 HTTP | 实际摘要 | 判定 |
|---|---|---|---|---|---|---|
| E.4.a | `/api/config` | GET | 200 + 字段 | **200** | base_url=https://api.minimaxi.com, chat_model=MiniMax-M3, image_model=gpt-image-1, chat_models=[MiniMax-M3], image_models=[gpt-image-1,gpt-image-2-all,nano-banana], has_api_key=true | ✅ |
| E.4.b | `/api/models` | GET | 200 + 列表 | **200** | chat_models=[MiniMax-M3], image_models=[gpt-image-1,gpt-image-2-all,nano-banana] | ✅ |
| E.1.a | `/api/conversations` | GET | 200 + 列表 | **200** | 5 条历史会话 | ✅ |
| E.1.b | `/api/conversations` | POST | 200 + id | **200** | `id=261bdb3d163e46058bbbffdc15bbd02a`, title=E2E-E测试 | ✅ |
| E.1.c | `/api/conversations/{id}` | GET | 200 + 详情 | **200** | conversation 完整, messages=[] | ✅ |
| E.1.d | `/api/conversations/{id}` | DELETE | 200 | **200** | `{"ok":true}` | ✅ |
| E.1.verify | `/api/conversations/{id}` | GET | 404 | **404** | `{"detail":"对话不存在"}` | ✅ |
| E.2.a | `/api/chat` | POST (无 model) | 400 上游 | **400** | `unknown model 'gpt-4o-mini'` — 默认 model 上游不存在（**行为符合任务预期**） | ✅ |
| E.2.b | `/api/chat` | POST (model=MiniMax-M3) | 200 完整回复 | **200** | "1+1=2", 258 tokens, 3.06s | ✅ |
| E.2.c | `/api/chat/stream` | POST (model=MiniMax-M3) | 200 text/event-stream | **200** | 4 个 SSE chunk：meta(1) + delta(2) + done(1) | ✅ |
| E.3.a | `/api/canvas-llm` | POST (无 model) | 400 上游 | **400** | 同上 `gpt-4o-mini` 不存在 | ⚠️ 默认 model 不可用 |
| E.3.b | `/api/canvas-llm` | POST (message+model) | 200 + text | **200** | text=938 字符 Python hello world 教学, 463 tokens, 10.1s | ✅ |
| E.3.c | `/api/canvas-llm` | POST (prompt 字段) | 422 缺 message | **422** | `Field required: message` — 确认只接受 `message`，不接受 `prompt` | ✅(已确认任务描述) |
| 清理 | `/api/conversations?token=...` | GET | 列表回到 5 条 | **200** | count=5, 无 "E2E-E测试" 残留 | ✅ |

---

## §1 E.1 会话 CRUD 详细响应

### E.1.a GET /api/conversations
- 状态: 200, 6ms
- 响应: `{"user_id":"ip-192.168.1.190","conversations":[...5 items...]}`
- 历史包含：你好请用一句话介绍自己(test)/test/test/test(3 条同名)/新会话

### E.1.b POST /api/conversations
- 请求: `{"title":"E2E-E测试"}`
- 状态: 200, 5ms
- 响应: `{"conversation":{"id":"261bdb3d163e46058bbbffdc15bbd02a","title":"E2E-E测试","created_at":1780561256513,"updated_at":1780561256513,"messages":[]}}`

### E.1.c GET /api/conversations/{id}
- 状态: 200, 4ms
- 响应: 同上（messages=[] 空数组符合预期）

### E.1.d DELETE /api/conversations/{id}
- 状态: 200, 5ms
- 响应: `{"ok":true}`

### E.1 验证清理
- 删除后 GET → **404** `{"detail":"对话不存在"}`
- 列表 count=5（与初始一致），无残留 E2E-E测试

---

## §2 E.2 GPT 对话详细响应

### E.2.a POST /api/chat（无 model 字段）
- 状态: **400**, 265ms
- 响应原文:
  ```
  {"detail":"上游接口错误：{\"type\":\"error\",\"error\":{\"type\":\"bad_request_error\",\"message\":\"invalid params, unknown model 'gpt-4o-mini' (2013)\",\"http_code\":\"400\"},\"request_id\":\"06706870303156ca637ff8ec07ab5b1f\"}"}
  ```
- **结论**: 默认 model 是 `gpt-4o-mini`，但 comfly 上游（MiniMax）没有该模型 → 业务侧预期失败，**符合任务描述**

### E.2.b POST /api/chat（model=MiniMax-M3, max_tokens=30）
- 状态: **200**, 3.06s
- 请求: `{"message":"1+1=?","model":"MiniMax-M3","max_tokens":30,"conversation_id":"261bdb3d163e46058bbbffdc15bbd02a"}`
- 响应 message.content:
  ```
  <think>
  The user is greeting me and asking a simple math question...
  </think>
  Hello! 👋 Welcome! I'm here to help you with whatever you need.
  
  As for your question: **1 + 1 = 2** 😊
  
  Is there anything else you'd like to know or discuss?
  ```
- usage: total_tokens=258, prompt=186, completion=72, cached=114
- **结论**: 完整对话工作，思考 + 答案分离

### E.2.c POST /api/chat/stream（model=MiniMax-M3, max_tokens=30）
- 状态: **200**, 3.10s, content-type=`text/event-stream; charset=utf-8`
- 请求: `{"message":"用一句话说hi","model":"MiniMax-M3","max_tokens":30,"conversation_id":"261bdb3d163e46058bbbffdc15bbd02a"}`
- **SSE chunks（共 4 个，data 行 4 个）：**

| # | type | 关键内容 |
|---|---|---|
| 1 | **meta** | `conversation.id=261bdb3d163e46058bbbffdc15bbd02a`, msgs=4（含历史 user/assistant）|
| 2 | **delta** | `delta_len=9`, `"<think>\n\n"` |
| 3 | **delta** | `delta_len=32`, `"用户要求用一句话说hi。\n</think>\n嗨～很高兴见到你！😊"` |
| 4 | **done** | conversation.msgs=5, message.content=`"嗨～很高兴见到你！😊"` |

- **chunk 类型分布**: `meta=1, delta=2, done=1` (delta 数量取决于响应长度；max_tokens=30 触发了快速收尾)
- **结论**: 流式真的流（不是一次性 dump）；标准 meta → delta*N → done 顺序；content-type 是真正的 `text/event-stream`

---

## §3 E.3 画布 LLM 详细响应

### E.3.a POST /api/canvas-llm（无 model）
- 状态: **400**, 217ms
- 响应: 同 E.2.a 的 `unknown model 'gpt-4o-mini'` 错误
- **结论**: 画布 LLM 也使用默认 model（gpt-4o-mini），comfly 不支持

### E.3.b POST /api/canvas-llm（model=MiniMax-M3, max_tokens=100）
- 状态: **200**, 10.13s
- 请求: `{"message":"写一个Python hello world","max_tokens":100,"model":"MiniMax-M3"}`
- 响应 keys: `text`, `model`, `raw_usage`
- text 长度: **938 字符**（满足 "response.text 不为空" 要求）
- text 前 200 字: 包含 `<think>...</think>` + Python hello world 教学（最简版/变量/格式化/函数/main 入口/运行方法）
- model: `MiniMax-M3`
- usage: total=463, prompt=181, completion=282
- **结论**: 画布 LLM 全功能工作，task 要求 ✓

### E.3.c POST /api/canvas-llm（用 `prompt` 字段而非 `message`）
- 状态: **422**, 4ms
- 响应: `{"detail":[{"type":"missing","loc":["body","message"],"msg":"Field required",...}]}`
- **结论**: 任务描述准确——必须用 `message` 字段，不能用 `prompt`

---

## §4 E.4 模型配置详细响应

### E.4.a GET /api/config
- 关键字段:
  - `base_url`: `https://api.minimaxi.com`
  - `chat_model`: **MiniMax-M3**（不是 gpt-4o-mini，但 `/api/chat` 和 `/api/canvas-llm` 在缺省时硬编码使用 `gpt-4o-mini`，与 config.chat_model 不一致——见 P1 阻断原因）
  - `image_model`: `gpt-image-1`
  - `chat_models`: `["MiniMax-M3"]`（仅 1 个可选项）
  - `image_models`: `["gpt-image-1","gpt-image-2-all","nano-banana"]`
  - `has_api_key`: true（comfly）
  - `has_ms_key`: true（modelscope，preview `ms-0...58f6`）

### E.4.b GET /api/models
- 简化版本: `{"chat_models":["MiniMax-M3"],"image_models":["gpt-image-1","gpt-image-2-all","nano-banana"]}`

### 关键发现：**配置不一致**
- `/api/config` 返回的 `chat_model: MiniMax-M3` 是「系统推荐默认」
- 但 `POST /api/chat`（无 model）和 `POST /api/canvas-llm`（无 model）的代码层默认 model 实际是 `gpt-4o-mini`
- 客户端（前端）**必须**显式传 `model: MiniMax-M3` 才能跑通 chat / canvas-llm
- 这是一个 **P1 阻断**：用户从 UI 触发聊天（不传 model）就会立即 400

---

## §5 阻断原因 / 关键缺陷

### P0 — 无（核心 GPT 对话 + 画布 LLM 链路完整）

### P1 — chat / canvas-llm 默认 model 与配置不一致
- **现象**: `/api/config` 报告 `chat_model=MiniMax-M3`（comfly 上游可用），但 `/api/chat` 和 `/api/canvas-llm` 在缺省 model 字段时实际使用 `gpt-4o-mini`，comfly 不支持 → 业务 400
- **影响范围**: 任何不显式传 model 的前端调用都会失败
- **复现**:
  ```bash
  curl -X POST $BASE/api/chat?token=$TOKEN \
    -H "Content-Type: application/json" \
    -d '{"message":"hi"}'
  # → 400 unknown model 'gpt-4o-mini'
  ```
- **建议修复**:
  1. 优先让 chat/canvas-llm 默认 model 跟 `config.chat_model` 一致
  2. 或在前端 chat 入口默认加 `model=MiniMax-M3`
  3. 或在 main.py 的 chat 默认值处改为 `MiniMax-M3`（comfly 可用模型）

### P1 — 画布 LLM 与 chat 的 API 字段不一致
- **现象**: chat 接受 `message` 字段；canvas-llm 同样要求 `message`（**不**接受 `prompt`）。如果前端或其他工具把 chat 习惯套到 canvas-llm 上就会 422
- **影响**: 集成方需要明确字段约定
- **复现**:
  ```bash
  curl -X POST $BASE/api/canvas-llm?token=$TOKEN \
    -H "Content-Type: application/json" \
    -d '{"prompt":"hi"}'
  # → 422 Field required: message
  ```
- **建议**: 文档化字段名（task 已经显式提示 `message`）

### P2 — 流式 delta 数量受 max_tokens 影响
- max_tokens=30 时只产生 2 个 delta chunk（模型很快就收尾）
- 长 max_tokens 时 delta 数量会显著增加
- **建议**: 演示流式时 max_tokens ≥ 100 才能看到真实的多 chunk 效果

---

## §6 替代路径 / 绕过方法

| 阻断点 | 绕过 |
|---|---|
| 无 model 时 400 | 客户端**必须**传 `model: MiniMax-M3`（comfly 唯一支持的 chat 模型）|
| canvas-llm 接受 `prompt` 失败 | 改用 `message` 字段 |
| 流式 chunk 太少 | 把 max_tokens 调到 100+ 触发多次 delta |

---

## §7 完整性判定

| 任务 | 判定 | 证据 |
|---|---|---|
| 会话 CRUD 全 | ✅ | list(5) → create(200) → detail(200) → delete(200) → verify(404) |
| GPT 对话实际能跑通（带 model）| ✅ | E.2.b HTTP 200，"1+1=2" |
| 流式真的流 | ✅ | E.2.c HTTP 200 text/event-stream, 4 个 SSE chunk (1+2+1) |
| 画布 LLM | ✅ | E.3.b HTTP 200, text=938 字符 |
| 模型配置检查 | ✅ | E.4.a/b 都 200 |
| 测试数据清干净 | ✅ | 列表回到 5 条，无 E2E-E测试 |

---

## §8 复现命令

```bash
export BASE="http://192.168.1.60:3000"
export TOKEN="21422613-d16c-4adc-b07e-b7ae2868fceb"

# E.4 config
curl -sS "$BASE/api/config?token=$TOKEN" | python3 -m json.tool

# E.4 models
curl -sS "$BASE/api/models?token=$TOKEN" | python3 -m json.tool

# E.1 CRUD
curl -sS "$BASE/api/conversations?token=$TOKEN" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['conversations']))"
curl -sS -X POST "$BASE/api/conversations?token=$TOKEN" -H "Content-Type: application/json" -d '{"title":"E2E-E测试"}'
CONV_ID=261bdb3d163e46058bbbffdc15bbd02a
curl -sS "$BASE/api/conversations/$CONV_ID?token=$TOKEN"
curl -sS -X DELETE "$BASE/api/conversations/$CONV_ID?token=$TOKEN"

# E.2 chat
# 无 model → 400
curl -sS -X POST "$BASE/api/chat?token=$TOKEN" -H "Content-Type: application/json" -d '{"message":"hi","conversation_id":"<id>"}'
# 带 model → 200
curl -sS -X POST "$BASE/api/chat?token=$TOKEN" -H "Content-Type: application/json" -d '{"message":"1+1=?","model":"MiniMax-M3","max_tokens":30,"conversation_id":"<id>"}'
# 流式
curl -sS -N -X POST "$BASE/api/chat/stream?token=$TOKEN" -H "Content-Type: application/json" -d '{"message":"用一句话说hi","model":"MiniMax-M3","max_tokens":30,"conversation_id":"<id>"}'

# E.3 canvas-llm
# 无 model → 400
curl -sS -X POST "$BASE/api/canvas-llm?token=$TOKEN" -H "Content-Type: application/json" -d '{"message":"hi"}'
# 带 model → 200
curl -sS -X POST "$BASE/api/canvas-llm?token=$TOKEN" -H "Content-Type: application/json" -d '{"message":"写一个Python hello world","model":"MiniMax-M3","max_tokens":100}'
# 用 prompt 字段 → 422
curl -sS -X POST "$BASE/api/canvas-llm?token=$TOKEN" -H "Content-Type: application/json" -d '{"prompt":"hi","model":"MiniMax-M3"}'
```

---

## §9 证据索引

所有原始响应保存在 `api-responses/` 和 `raw/`：

| 文件 | 内容 |
|---|---|
| `api-responses/01-config.json` | GET /api/config 完整响应 |
| `api-responses/02-models.json` | GET /api/models 完整响应 |
| `api-responses/03-conversations-list.json` | 初始 5 条会话 |
| `api-responses/04-conversation-create.json` | POST 新建 E2E-E测试 |
| `api-responses/05-conversation-detail.json` | 详情 |
| `api-responses/06-chat-no-model.json` | /api/chat 无 model → 400 |
| `api-responses/07-chat-with-model.json` | /api/chat MiniMax-M3 → 200 |
| `raw/08-chat-stream.txt` | **SSE 流式 4 个 chunk 完整内容** |
| `api-responses/09-canvas-llm.json` | /api/canvas-llm 无 model → 400 |
| `api-responses/10-canvas-llm-with-model.json` | /api/canvas-llm MiniMax-M3 → 200 |
| `api-responses/11-canvas-llm-prompt.json` | /api/canvas-llm prompt 字段 → 422 |
| `api-responses/12-conversation-delete.json` | DELETE → 200 |
| `api-responses/13-conversation-after-delete.json` | GET 已删除 → 404 |
| `api-responses/14-conversations-list-after.json` | 清理后 5 条（无残留）|

---

## §10 总结

- **全部核心端点（CRUD + chat + stream + canvas-llm）均 HTTP 200 工作正常**
- **发现 1 个 P1 阻断**：chat / canvas-llm 缺省 model 字段时使用 `gpt-4o-mini`（comfly 不支持），必须显式传 `model: MiniMax-M3`
- **流式真的流**：4 SSE chunks，标准 meta→delta*N→done 协议
- **画布 LLM 字段约定**：必须用 `message` 不能用 `prompt`（任务描述准确）
- **清理完成**：测试会话已删除，列表 count 5→5

E2E 判定：**通过**（核心链路完整，附带 1 个 P1 配置不一致问题需要后续修复）
