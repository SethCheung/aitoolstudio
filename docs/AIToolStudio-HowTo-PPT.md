# AIToolStudio 平台使用与配置 How-to

适用对象：平台普通用户、项目管理员、后端运维  
文档用途：培训讲解/PPT 素材（按“可直接拆页”结构编写）  
环境示例日期：2026-05-27

---

## 第 1 页：培训目标与角色分工

**这一页讲什么**  
说明 AIToolStudio 平台里，普通用户怎么完成生成任务，管理员怎么完成后端配置与巡检。

**用户要做什么**  
1. 明确自己角色：普通用户或管理员。  
2. 普通用户聚焦“登录-创作-查看结果”。  
3. 管理员聚焦“实例配置-工作流配置-依赖预检-故障排查”。

---

## 第 2 页：当前生产环境示例（已验收）

**这一页讲什么**  
给出当前可对照的生产环境基线，便于培训时统一口径。

**用户要做什么**  
核对自己访问和操作的环境是否一致。

- Web 入口：`http://192.168.1.60:3000`
- 平台版本：`2026.05.27.6`（`GET /api/app-info`）
- ComfyUI workers：  
  - `192.168.1.195:8188`  
  - `192.168.1.197:8188`  
  - `192.168.1.249:8188`
- 当前 7 个工作流：  
  - `custom/aitool-smoke-sd15.json`  
  - `2511.json`  
  - `Flux2-Klein.json`  
  - `LTXDirectorv2-API.json`  
  - `Z-Image.json`  
  - `Z-Image-Enhance.json`  
  - `upscale.json`
- smoke 示例输出（可访问样例）：  
  - `http://192.168.1.60:3000/assets/output/workflow-test_1779891358_0481dbb124.png`

---

## 第 3 页：普通用户入口（访问与登录）

**这一页讲什么**  
普通用户从哪里进入，未登录时会发生什么。

**用户要做什么**  
1. 访问 `http://192.168.1.60:3000`。  
2. 若跳转到 `/login`，正常输入账号密码登录。  
3. 凭据请向管理员获取。

说明：未登录访问首页会重定向到登录页；登录后可进入项目与画布流程。

---

## 第 4 页：项目页（/projects）怎么用

**这一页讲什么**  
项目主页是用户进入创作的第一站，用于新建/搜索/管理项目。

**用户要做什么**  
1. 在项目页点击“新建项目”或“新建智能项目”。  
2. 使用搜索、排序快速定位已有项目。  
3. 进入项目后打开画布继续编辑。

---

## 第 5 页：工作台/画布（/canvas）基础操作

**这一页讲什么**  
画布是核心工作区：添加节点、连线、运行、查看日志和输出。

**用户要做什么**  
1. 在画布中添加需要的节点（如 ComfyUI、提示词、图片、Output）。  
2. 将输入节点连到生成节点，再连到输出节点。  
3. 点击运行，打开“日志”查看执行过程。  
4. 用输出预览面板查看图片/视频，并下载结果。

---

## 第 6 页：选择工作流并提交生成

**这一页讲什么**  
ComfyUI 节点运行前，依赖管理员已发布的工作流配置。

**用户要做什么**  
1. 在画布的 ComfyUI 节点中选择可用工作流。  
2. 填写暴露参数（例如 prompt、尺寸、步数等）。  
3. 提交运行并记录任务标识（如 `task_id` / `prompt_id`）。

---

## 第 7 页：查看进度、队列、历史与输出下载

**这一页讲什么**  
用户如何判断“任务在排队、执行中还是已完成”。

**用户要做什么**  
1. 在页面日志先看运行状态。  
2. 管理员或高级用户可查询队列接口：`GET /api/queue_status?client_id=<CLIENT_ID>`。  
3. 在历史接口查看记录：`GET /api/history`。  
4. 完成后从输出 URL 或下载接口获取文件（示例：`/api/download-output`）。

---

## 第 8 页：ComfyUI 设置页（用户视角）

**这一页讲什么**  
让普通用户知道设置页的用途，但避免误操作。

**用户要做什么**  
1. 了解 `/comfyui-settings` 是管理员配置页。  
2. 普通用户只需确认：目标工作流是否“前台可用”。  
3. 若工作流不可见或参数异常，向管理员反馈工作流名称和报错截图。

---

## 第 9 页：管理员入口与部署位置

**这一页讲什么**  
管理员在哪些位置做配置，服务如何对外暴露。

**用户要做什么**  
1. 在平台代码目录部署服务：`/Users/apple/Documents/GitHub/aitoolstudio`。  
2. 通过 `docker-compose.60.yml`（生产）或 `docker-compose.yml`（通用）管理容器。  
3. 统一对外入口使用 `3000` 端口。

建议核对：  
- 路由：`/projects`、`/canvas`、`/comfyui-settings`  
- 后端配置 API：`/api/comfyui/*`、`/api/workflows*`、`/api/resource-root*`

---

## 第 10 页：版本、端口与实例状态查询（管理员）

**这一页讲什么**  
管理员的最小巡检命令集合。

**用户要做什么**  
执行以下查询并记录结果：

```bash
curl -s http://192.168.1.60:3000/api/app-info
curl -s http://192.168.1.60:3000/api/comfyui/instances -H 'Authorization: Bearer <TOKEN>' -H 'Cookie: session=<COOKIE>'
curl -s http://192.168.1.60:3000/api/comfyui/status -H 'Authorization: Bearer <TOKEN>' -H 'Cookie: session=<COOKIE>'
```

检查重点：  
1. 版本号是否符合发布计划。  
2. `instances` 是否包含三台 worker。  
3. status 中 `ok`、`queue_running`、`queue_pending` 是否正常。

---

## 第 11 页：ComfyUI 实例配置（管理员）

**这一页讲什么**  
如何维护 ComfyUI 计算池地址。

**用户要做什么**  
1. 进入 `/comfyui-settings` 配置 `host:port` 实例列表。  
2. 保存后再用状态接口验证连通性。  
3. 新增或下线 worker 后，必须复测至少 1 条生产工作流。

当前示例实例：  
`192.168.1.195:8188,192.168.1.197:8188,192.168.1.249:8188`

---

## 第 12 页：资源根目录与目录结构（管理员）

**这一页讲什么**  
模型、工作流、输入输出素材依赖统一资源根目录，避免多机分叉。

**用户要做什么**  
1. 配置资源根目录（示例）：`/vol3/@team/SJM-MediaFile`。  
2. 调用资源接口确认 `configured/available`。  
3. 确认目录结构已就绪，再导入工作流。

常用接口：

```bash
curl -s http://192.168.1.60:3000/api/resource-root -H 'Authorization: Bearer <TOKEN>' -H 'Cookie: session=<COOKIE>'
curl -s -X POST http://192.168.1.60:3000/api/resource-root/detect -H 'Authorization: Bearer <TOKEN>' -H 'Cookie: session=<COOKIE>'
```

---

## 第 13 页：工作流目录与配置文件（管理员）

**这一页讲什么**  
工作流由 JSON 本体 + config 元数据组成，决定前台是否可用与参数暴露方式。

**用户要做什么**  
1. 在 `workflows/` 管理工作流 JSON 文件。  
2. 在设置页维护工作流元信息：名称、分类、描述、是否前台可用。  
3. 通过配置接口更新参数映射与启用状态。

相关接口：

```bash
curl -s http://192.168.1.60:3000/api/workflows -H 'Authorization: Bearer <TOKEN>' -H 'Cookie: session=<COOKIE>'
curl -s -X PUT http://192.168.1.60:3000/api/workflows/<WORKFLOW_NAME>/config \
  -H 'Authorization: Bearer <TOKEN>' -H 'Cookie: session=<COOKIE>' \
  -H 'Content-Type: application/json' -d '{}'
```

---

## 第 14 页：导入工作流与依赖预检（管理员）

**这一页讲什么**  
导入前必须做“缺失节点/模型依赖”预检，先出计划再执行变更。

**用户要做什么**  
1. 在 `/comfyui-settings` 使用“导入向导”上传 JSON 或粘贴来源。  
2. 调用预检接口生成安装计划。  
3. 评审通过后再安排变更窗口执行安装动作。

预检接口：

```bash
curl -s -X POST http://192.168.1.60:3000/api/workflows/import/plan \
  -H 'Authorization: Bearer <TOKEN>' -H 'Cookie: session=<COOKIE>' \
  -H 'Content-Type: application/json' \
  -d '{"source":"<WORKFLOW_NAME>"}'
```

---

## 第 15 页：安装计划边界（必须明确）

**这一页讲什么**  
哪些动作平台不会自动做，必须由管理员确认后执行。

**用户要做什么**  
确认以下高风险动作都属于“人工确认后执行”：

1. 模型下载（model download）不会自动执行。  
2. custom node 安装不会自动执行。  
3. `pip install` 不会自动执行。  
4. `git clone`/升级第三方节点不会自动执行。

结论：`/api/workflows/import/plan` 产出的是“计划”，不是“自动安装”。

---

## 第 16 页：运行、队列与历史运维视角

**这一页讲什么**  
管理员如何快速判断当前系统负载和任务健康度。

**用户要做什么**  
1. 看实例状态：`/api/comfyui/status`。  
2. 看用户队列：`/api/queue_status?client_id=<CLIENT_ID>`。  
3. 看历史记录：`/api/history`。  
4. 抽查结果文件是否可访问（HTTP 200）。

---

## 第 17 页：常用排查接口速查

**这一页讲什么**  
给培训对象一页“出问题先查什么”。

**用户要做什么**  
按顺序排查：

1. `GET /api/app-info`：版本是否正确。  
2. `GET /api/comfyui/instances`：实例列表是否完整。  
3. `GET /api/comfyui/status`：实例是否可用、队列是否堆积。  
4. `GET /api/resource-root`：资源盘是否可用。  
5. `GET /api/workflows`：目标工作流是否存在且可用。  
6. `GET /api/history`：任务是否有记录。  
7. `GET /api/queue_status?client_id=<CLIENT_ID>`：是否仍在排队。

---

## 第 18 页：安全与凭据规范

**这一页讲什么**  
培训材料中必须遵守的安全底线。

**用户要做什么**  
1. 登录凭据统一写“向管理员获取”。  
2. 文档、命令示例中只用占位符：`<TOKEN>`、`<COOKIE>`、`<CLIENT_ID>`、`<WORKFLOW_NAME>`。  
3. 不在任何文档写明文密码、密钥、Token。  
4. 共享截图前先遮挡账号、会话、路径中的敏感信息。

---

## 第 19 页：建议的 PPT 拆页方案

**这一页讲什么**  
如何把本 How-to 直接转成培训幻灯片。

**用户要做什么**  
按以下顺序拆页制作：

1. 平台目标与角色分工  
2. 生产环境基线（地址/版本/实例/工作流）  
3. 登录与入口流程  
4. 项目页操作  
5. 画布基础操作  
6. 选择工作流与提交生成  
7. 进度、队列、历史、下载  
8. ComfyUI 设置页（用户理解）  
9. 管理员部署与端口  
10. 实例配置与资源根目录  
11. 工作流配置与导入预检  
12. 安装边界与变更控制  
13. 排查接口速查  
14. 安全规范与结语

图示建议（每页至少一图）：  
- 页面截图：`/projects`、`/canvas`、`/comfyui-settings`。  
- 架构图：Web(3000) -> ComfyUI 三节点。  
- 流程图：导入预检 -> 安装审批 -> 上线。  
- 状态图：queue/history/status 三类接口的检查顺序。

---

## 附录：培训演示命令（占位符版）

```bash
# 1) 查看版本
curl -s http://192.168.1.60:3000/api/app-info

# 2) 查看 ComfyUI 状态
curl -s http://192.168.1.60:3000/api/comfyui/status \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Cookie: session=<COOKIE>'

# 3) 查看工作流清单
curl -s http://192.168.1.60:3000/api/workflows \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Cookie: session=<COOKIE>'

# 4) 触发工作流运行
curl -s -X POST http://192.168.1.60:3000/api/workflows/<WORKFLOW_NAME>/run \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Cookie: session=<COOKIE>' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

