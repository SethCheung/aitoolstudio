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
- `src/views/GenerateView.vue`：生成页，支持 image / voice / video / music，图片可同页预览原图
- `src/views/GenerateView.vue`：输入区支持 AI 优化，调用 `/api/prompt/optimize` 后回填 prompt
- `src/views/AdminView.vue`：Profile 管理页
- `src/views/LoginView.vue`：登录页

## Notes

- API 调用统一走 `src/services/api.ts`
- `/admin` 路由会根据 JWT payload 做基础 admin 判断，最终权限以后端 `require_admin` 为准
- 生成图原图预览只负责 UI 展示；文件访问鉴权仍需要后端改造
