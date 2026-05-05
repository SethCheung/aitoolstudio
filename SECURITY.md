# Security Notes

本项目当前定位是公司内网 MVP，不是公网 SaaS。即便如此，AI 生成平台会处理账号、API Key、生成文件和内部素材，安全债不能装作不存在。

## 当前认证模型

- 后端使用 JWT Bearer Token
- `JWT_SECRET_KEY` 必须通过环境变量提供
- 登录接口 `/api/auth/login` 有基础限流
- 普通生成、历史、模型列表接口要求登录
- `/api/admin/*` 和 `/api/profiles` 管理接口要求管理员权限

## 必须配置的环境变量

```bash
JWT_SECRET_KEY=<至少 32 字节随机值，例如 openssl rand -hex 32>
MINIMAX_API_KEY=<可选，仅 HTTP profile 需要>
DATABASE_URL=sqlite:///./img_platform.db
```

Docker Compose 会强制要求 `JWT_SECRET_KEY`。如果没配就启动不了，这是正确行为。

## 当前已知风险

| 风险 | 严重度 | 当前状态 | 处理建议 |
|------|--------|----------|----------|
| `/minimax-output` 静态文件公开 | P1 | 未修复 | 改成 `/api/files/*` 带鉴权代理，禁止目录浏览 |
| Profile API Key 写入 JSON 文件 | P1 | 未修复 | 从 git 跟踪中移除 `profiles.json`，改为环境变量引用或加密存储 |
| Token 存在 `localStorage` | P2 | 接受为内网 MVP | 若要提升安全性，改 HttpOnly Cookie + CSRF |
| SQLite 无迁移体系 | P2 | 未修复 | 引入 Alembic，字段变更走 migration |
| 后端内联 Admin HTML | P2 | 建议废弃 | 管理入口统一到前端 `/admin` |
| 缺自动化安全回归测试 | P2 | 未修复 | 补 `test_admin_authz.py`、`test_profile_authz.py` |

## 生成文件访问策略

当前代码会把 MiniMax CLI 输出目录挂载为：

```text
/minimax-output -> ~/minimax-output
```

这方便本地调试，但不适合生产。正确方向：

1. 生成完成后只把文件相对路径或文件 ID 存入数据库
2. 前端请求 `/api/files/{file_id}`
3. 后端校验 JWT、用户归属、文件存在性
4. 后端用 `FileResponse` 返回文件
5. 不暴露真实本机目录，也不启用目录索引

## Profile Key 存储策略

当前 `backend/config/profiles.json` 适合本地假数据，不适合保存真实密钥。

推荐演进：

1. 短期：`profiles.json` 只保存 `api_key_env`，例如 `MINIMAX_API_KEY_MAIN`
2. 中期：把 Profile 存数据库，API Key 使用 Fernet 或系统 KMS 加密
3. 长期：引入审计日志，记录谁创建/修改/禁用了 Profile

不要把真实 API Key 放进 git diff。这个要求很低，低到不该再讨论。

## 管理员账号

`scripts/create_admin.py` 默认创建：

```text
admin / admin123
```

仅限本地调试。真实部署必须立刻改密码或改脚本参数。后续建议改为命令行参数或交互式输入密码，避免默认密码长期存在。

## 发布前安全清单

- [ ] `JWT_SECRET_KEY` 使用 32 字节以上随机值
- [ ] 默认管理员密码已更换
- [ ] `profiles.json` 不再被 git 跟踪，且不含真实 API Key
- [ ] `/minimax-output` 不再公开挂载
- [ ] Admin/Profile 接口匿名访问返回 403
- [ ] 普通用户访问 Admin/Profile 管理接口返回 403
- [ ] 前端生产构建通过
- [ ] 后端基础编译和权限测试通过
