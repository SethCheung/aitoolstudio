# img-platform frontend

Vue 3 + TypeScript + Vite 前端。主入口以仓库根目录 `README.md` 为准，本文件只记录前端本地命令。

## Commands

```bash
npm install
npm run dev
npm run build
```

默认开发地址：

```text
http://localhost:5173
```

如果后端不是 `http://localhost:8000`：

```bash
VITE_API_BASE_URL=http://localhost:8001 npm run dev
```

## Main Views

- `src/views/HomeView.vue`：项目首页，展示项目卡片和生成图片缩略图
- `src/views/GenerateView.vue`：生成工作台，支持 image / voice / video / music，最新生成在上，旧记录滚动到下方
- `src/views/GenerateView.vue`：底部停靠生成框支持 AI enhance、`1x / 2x / 4x`、生成中取消
- `src/views/GenerateView.vue`：图片按比例完整预览，点击图片本身或“放大”按钮同页查看原图
- `src/views/AdminView.vue`：Profile 管理页
- `src/views/LoginView.vue`：登录页

## Notes

- API 调用统一走 `src/services/api.ts`
- `/admin` 路由会根据 JWT payload 做基础 admin 判断，最终权限以后端 `require_admin` 为准
- 生成中取消目前主要中断前端请求等待；服务端任务级取消仍需要后端/模型接口支持
- 生成图原图预览只负责 UI 展示；文件访问鉴权仍需要后端改造
