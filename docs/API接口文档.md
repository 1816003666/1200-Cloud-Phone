# 云手机平台任务看板 —— 接口文档（石文盛负责模块）

> 适用模块：用户认证与权限（JWT+RBAC）、用户管理、文件管理、脚本管理、分组管理、审计日志、告警系统、数据看板、登录/注册页面、Docker 部署。
> 项目路径：`E:\work\code\cloud-phone-board`
> 编写依据：后端 `backend/app/routes/*` 实际代码（已逐行核对，非凭记忆）。
>
> ⚠️ 设备管理 / 定时任务 / 远程控制 / ws-scrcpy / Redroid 后端 属于**彭旨豪**负责，本文档仅在第 0 章列出接口名用于上下文，不做细节展开。

---

## 0. 通用约定

### 0.1 Base URL
- 开发（前端 dev server 代理）：`/api` （Vite 代理到 `http://localhost:8000/api`）
- 直连后端：`http://localhost:8000/api`
- Docker 部署：`http://<服务器IP>/api` （nginx 反向代理）

### 0.2 认证方式
所有受保护接口需在请求头携带：
```
Authorization: Bearer <access_token>
```
- token 由 `POST /api/auth/login` 或 `POST /api/auth/register` 获取。
- 解析失败 / 过期 → `401`。前端 `client.js` 拦截器会自动清 token 并跳 `/login`。
- 权限不足（角色级别不够）→ `403`。

### 0.3 角色级别（RBAC）
| 角色 | level | 说明 |
|------|-------|------|
| `viewer` | 1 | 仅查看看板 / 列表 |
| `operator` | 2 | 在 viewer 基础上可操控设备、上传文件、执行脚本、分组批量操作 |
| `admin` | 3 | 在 operator 基础上可管理用户、分组、查看/处理告警、查看审计 |
| `superadmin` | 4 | 全部权限（含创建/分配 admin 及以上角色） |

路由保护规则：
- `@login_required`：任意**已登录且启用**的用户。
- `@require_role("X")`：角色 `level >= X.level` 才可访问。

### 0.4 统一响应格式
- 成功：`{ ...字段 }` （各接口字段见下文）
- 失败：`{ "error": "错误信息" }` + HTTP 状态码
  | 状态码 | 含义 |
  |--------|------|
  | 400 | 参数缺失 / 非法（如密码复杂度不足、action 不在枚举） |
  | 401 | 未登录 / token 失效 |
  | 403 | 权限不足 |
  | 404 | 资源不存在 |
  | 409 | 冲突（用户名/分组名已存在） |
  | 201 | 创建成功（注册、建用户、建分组、建脚本、上传文件） |

### 0.5 上下文接口（彭旨豪负责，仅列名）
`GET/POST /devices`、`POST /devices/batch`、`GET/DELETE /devices/<id>`、`POST /devices/<id>/control/<action>`、`GET/POST/DELETE /tasks`、`POST /tasks/<id>/run`。本文档不展开。

---

## 1. 认证模块（任务书 #3 用户认证与权限 / #9 登录注册页面）

### 1.1 登录
```
POST /api/auth/login
```
**请求体（JSON）：**
```json
{ "username": "admin", "password": "Admin@123456" }
```
**响应 200：**
```json
{
  "access_token": "<JWT>",
  "user": { "id": 1, "username": "admin", "role": "admin", "is_active": true, "created_at": "2026-08-26T..." }
}
```
**错误：** `400` 缺参；`401` 用户名或密码错误 / 账号被停用。

### 1.2 获取当前用户
```
GET /api/auth/me
```
**响应 200：** 同 `user` 对象（见 1.1）。`401` 失效。

### 1.3 刷新 token
```
POST /api/auth/refresh
```
用旧（未过期）token 换新 token。**响应 200：** `{ "access_token": "<JWT>" }`。

### 1.4 自助注册（任务书 #9）
```
POST /api/auth/register
```
**请求体（JSON）：**
```json
{ "username": "alice", "password": "abc123" }
```
**规则：**
- 用户名必填；重名 → `409`。
- 密码复杂度：`validate_password` 校验 **≥6 位且同时含字母和数字**，否则 `400`。
- 注册账号**默认角色 `viewer`**（最低权限），自动登录返回 token。

**响应 201：**
```json
{ "access_token": "<JWT>", "user": { "id": 3, "username": "alice", "role": "viewer", "is_active": true, "created_at": "..." } }
```
> 说明：生产环境建议改为管理员邀请制；此处按任务书「登录/注册页面」实现自助注册并在 README 标注。

---

## 2. 用户管理（任务书 #10 用户管理页面）

> 全部接口要求 `@require_role("admin")`。以下为**企业级越权防护**规则（代码 `routes/users.py` 已实现）：
> - `admin` 不能创建 / 分配 `admin` 及以上角色（仅 `superadmin` 可）。
> - 不能修改**自己**的角色、不能删除**自己**。
> - 不能删除 / 停用**最后一个 superadmin**（`_count_superadmin() <= 1` 时拒绝）。

### 2.1 用户列表
```
GET /api/users
```
**响应 200：** 数组，元素为 `user` 对象（同 1.1 的 `user`，不含 `hashed_password`）。

### 2.2 创建用户
```
POST /api/users
```
**请求体（JSON）：**
```json
{ "username": "bob", "password": "abc123", "role": "operator" }
```
**规则：** 用户名+密码必填；`role` 必须在 `viewer/operator/admin/superadmin`；越权（admin 建 admin 及以上）→ `403`。
**响应 201：** 新建 `user` 对象。

### 2.3 更新用户（改角色 / 改密码 / 启停）
```
PATCH /api/users/<uid>
```
**请求体（JSON，字段可选）：**
```json
{ "role": "operator", "password": "newpass1", "is_active": false }
```
**规则：** 改角色受 2.0 越权规则约束；改密码同样校验复杂度；停用自己 / 最后一个 superadmin → `403`。
**响应 200：** 更新后的 `user` 对象。

### 2.4 删除用户
```
DELETE /api/users/<uid>
```
**规则：** 删自己 / 删最后一个 superadmin / admin 删 admin 及以上 → `403`。
**响应 200：** `{ "message": "已删除" }`。

---

## 3. 文件管理（任务书 #8 文件管理模块）

> 上传 / 删除 / 推送：`@require_role("operator")`；浏览 / 下载：`@login_required`。
> simulator 模式下「推送到设备」为**模拟**（记设备日志 + 审计），不真正写设备。

### 3.1 上传文件
```
POST /api/files/upload
Content-Type: multipart/form-data
```
**表单字段：** `file`（二进制）。
**响应 201：**
```json
{ "id": 5, "filename": "app.apk", "size": 12345, "mime": "application/vnd.android.package-archive",
  "uploader_id": 1, "target_device_id": null, "created_at": "..." }
```

### 3.2 文件列表（分页 + 搜索）
```
GET /api/files?page=1&page_size=20&q=app&device_id=3
```
**响应 200：**
```json
{ "total": 12, "page": 1, "page_size": 20, "items": [ {同上序列化} ] }
```

### 3.3 下载文件
```
GET /api/files/<fid>/download
```
返回文件流（`Content-Disposition: attachment`，文件名取原始名）。`404` 不存在。

### 3.4 删除文件
```
DELETE /api/files/<fid>
```
物理删除磁盘文件 + 删库记录 + 写审计。返回 `{ "ok": true }`。

### 3.5 推送文件到设备（模拟）
```
POST /api/files/<fid>/push
```
**请求体（JSON）：**
```json
{ "device_ids": [2, 3] }
```
**响应 200：** `{ "ok": 2, "failed": 0 }`（`failed` = 未找到的设备数）。

---

## 4. 脚本管理（任务书 #5 脚本管理模块）

> 查看：`@login_required`；创建 / 编辑 / 删除 / 执行：`@require_role("operator")`。
> 脚本 = `steps` JSON 数组（操作步骤），可回放到多台设备。simulator 模式下执行为**模拟**（记日志 + 审计），失败自动产生 `operation_failure` 告警。

内置模板（`GET /scripts/templates`）：打开网址 / 安装应用 / 输入文本并回车 / 滑动解锁。

### 4.1 脚本模板列表
```
GET /api/scripts/templates
```
**响应 200：** 数组，如：
```json
[
  { "name": "打开指定网址", "steps": [ {"action": "open_url", "params": {"url": "https://www.example.com"}} ] },
  { "name": "安装应用", "steps": [ {"action": "install", "params": {"pkg": "com.example.app"}} ] }
]
```

### 4.2 脚本列表
```
GET /api/scripts
```
**响应 200：** 数组，元素：
```json
{ "id": 1, "name": "刷量脚本", "steps": [ {"action":"tap","params":{"x":100,"y":200}} ], "owner_id": 1, "created_at": "..." }
```

### 4.3 创建脚本
```
POST /api/scripts
```
**请求体（JSON）：**
```json
{ "name": "刷量脚本", "steps": [ {"action": "tap", "params": {"x": 100, "y": 200}} ] }
```
**响应 201：** 新建脚本对象。

### 4.4 获取单条脚本
```
GET /api/scripts/<sid>
```
**响应 200：** 脚本对象（`steps` 已反序列化为数组）。`404` 不存在。

### 4.5 更新脚本
```
PATCH /api/scripts/<sid>
```
**请求体（JSON，字段可选）：** `{ "name": "新名", "steps": [...] }`。
**响应 200：** 更新后对象。

### 4.6 删除脚本
```
DELETE /api/scripts/<sid>
```
**响应 200：** `{ "ok": true }`。

### 4.7 执行脚本（回放至多台设备）
```
POST /api/scripts/<sid>/execute
```
**请求体（JSON）：** `{ "device_ids": [2, 3] }`。
**响应 200：**
```json
{ "ok": 2, "failed": 0 }
```
> 若 `failed > 0`，自动调用 `raise_alert("operation_failure", "warning", ...)` 产生告警（见第 7 章）。

---

## 5. 分组管理（任务书 #6 分组管理模块）

> 查看：`@login_required`；创建 / 编辑 / 删除：`@require_role("admin")`；批量操作：`@require_role("operator")`。

### 5.1 分组列表（含设备数）
```
GET /api/groups
```
**响应 200：** 数组，元素：
```json
{ "id": 1, "name": "华东集群", "description": "上海机房", "owner_id": 1, "device_count": 8, "created_at": "..." }
```

### 5.2 创建分组
```
POST /api/groups
```
**请求体（JSON）：** `{ "name": "华东集群", "description": "上海机房" }`。重名 → `409`。
**响应 201：** `{ "id": 1, "name": "华东集群" }`。

### 5.3 更新分组
```
PATCH /api/groups/<gid>
```
**请求体（JSON，可选）：** `{ "name": "新名", "description": "..." }`。**响应 200：** `{ "ok": true }`。

### 5.4 删除分组
```
DELETE /api/groups/<gid>
```
**响应 200：** `{ "ok": true }`。（注：当前未级联删除组内设备，仅解绑概念，依业务需要可扩展。）

### 5.5 分组批量操作（开机/关机/销毁）
```
POST /api/groups/<gid>/batch-action
```
**请求体（JSON）：**
```json
{ "action": "start", "device_ids": [2, 3] }
```
- `action` 枚举：`start`（开机→`running`）/ `stop`（关机→`stopped`）/ `destroy`（销毁→`error`）。
- `device_ids` 不传 → 对该分组**全部**设备执行。
**响应 200：** `{ "ok": 2, "failed": 0 }`。

---

## 6. 审计日志（任务书 #7 审计日志系统）

> 全部接口 `@require_role("admin")`。所有写操作经 `record_audit()` 落 `audit_logs`（action 示例：`create_user/update_user/delete_user`、`upload_file/delete_file/push_file`、`create_script/execute_script`、`create_group/group_batch_action`、`register_user` 等）。

### 6.1 审计列表（支持多维过滤）
```
GET /api/audit?actor_id=1&action=create_user&target_type=user&start=2026-08-01T00:00:00&end=2026-08-31T23:59:59&limit=200
```
| 参数 | 说明 |
|------|------|
| `actor_id` | 操作人 id |
| `action` | 操作类型（精确匹配） |
| `target_type` | 目标类型（user/device/script/group/file...） |
| `start` / `end` | ISO 时间过滤 `created_at` |
| `limit` | 最多返回条数（默认 200，上限 500） |

**响应 200：** 数组，元素：
```json
{ "id": 42, "actor_id": 1, "action": "create_user", "target_type": "user", "target_id": 5,
  "detail": "{\"username\": \"bob\", \"role\": \"operator\"}", "created_at": "..." }
```

### 6.2 高频操作统计
```
GET /api/audit/stats
```
**响应 200：** 按 `action` 计数降序前 20：
```json
[ { "action": "create_user", "count": 12 }, { "action": "upload_file", "count": 8 } ]
```

---

## 7. 告警系统（任务书 #12 告警系统）

> 全部接口 `@require_role("admin")`。三类告警：`device_offline`（调度器心跳检测）/ `resource_limit`（CPU/内存超阈值）/ `operation_failure`（设备操控、脚本回放、任务执行失败自动产生）。`raise_alert()` 有 **30 分钟去重窗口**，避免刷屏。

### 7.1 告警列表（可筛选）
```
GET /api/alerts?status=active&level=critical&type=device_offline&device_id=3&limit=200
```
**响应 200：** 数组，元素：
```json
{ "id": 7, "level": "warning", "type": "operation_failure", "message": "脚本[刷量] 执行失败 1 台设备",
  "device_id": 3, "status": "active", "detail": "{\"script\": \"刷量\", \"failed_device_ids\": [4]}",
  "created_at": "...", "resolved_at": null }
```

### 7.2 告警汇总（看板顶部）
```
GET /api/alerts/summary
```
**响应 200：**
```json
{ "total": 30, "active": 5, "critical": 1, "warning": 4,
  "by_type": { "device_offline": 2, "resource_limit": 1, "operation_failure": 2 } }
```

### 7.3 确认告警（ack）
```
POST /api/alerts/<aid>/ack
```
状态：`active → acknowledged`，记录 `acknowledged_by`。**响应 200：** 告警对象。

### 7.4 解决告警（resolve）
```
POST /api/alerts/<aid>/resolve
```
状态 → `resolved`，记录 `resolved_at` / `resolved_by`。**响应 200：** 告警对象。

---

## 8. 数据看板（Dashboard /  metrics）

> `@login_required`。前端首页 `/` 调用。

### 8.1 总览指标
```
GET /api/metrics/overview
```
**响应 200：**
```json
{
  "kpis": { "total_devices": 12, "running": 8, "error": 1, "groups": 3, "tasks": 5, "enabled_tasks": 4 },
  "status_distribution": { "running": 8, "error": 1, "stopped": 2, "creating": 1 },
  "group_distribution": [ { "group": "华东集群", "count": 8 } ],
  "recent_devices": [ { "id": 12, "name": "dev-12", "status": "running", "ip": "10.0.0.12" } ],
  "last_execution": { "id": 9, "ok": 5, "failed": 0 }
}
```

---

## 9. 数据结构速查（相关表）

| 表 | 关键字段 |
|----|----------|
| `users` | id, username, hashed_password(pbkdf2_sha256$...), role, is_active |
| `groups` | id, name, description, owner_id |
| `files` | id, filename, stored_name(uuid), size, mime, uploader_id, target_device_id |
| `scripts` | id, name, steps(JSON), owner_id |
| `audit_logs` | id, actor_id, action, target_type, target_id, detail(JSON), created_at |
| `alerts` | id, level(info/warning/critical), type(3类), status(active/acknowledged/resolved), device_id, detail(JSON), created_at, resolved_at, acknowledged_by, resolved_by |

> 完整 10 张表定义与 ER 图见 `DESIGN.md` 第二章。

---

## 10. 前端调用契约（frontend/src/api/client.js 映射）

| 前端方法 | 对应接口 |
|----------|----------|
| `api.login` | POST /auth/login |
| `api.register` | POST /auth/register |
| `api.me` | GET /auth/me |
| `api.listUsers / createUser / updateUser / deleteUser` | /users 系列 |
| `api.uploadFile / listFiles / downloadFile / deleteFile / pushFile` | /files 系列 |
| `api.scriptTemplates / listScripts / createScript / updateScript / deleteScript / executeScript` | /scripts 系列 |
| `api.listGroups / createGroup / updateGroup / deleteGroup / groupBatchAction` | /groups 系列 |
| `api.listAudit / auditStats` | /audit 系列 |
| `api.listAlerts / alertSummary / ackAlert / resolveAlert` | /alerts 系列 |
| `api.overview` | GET /metrics/overview |

前端所有请求经 `http` 拦截器自动注入 `Bearer` token；`401` 自动清登录态并跳 `/login`。

---

## 11. 调试验证示例（curl）

```bash
# 1) 登录拿 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin@123456"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2) 带 token 查看用户
curl -s http://localhost:8000/api/users \
  -H "Authorization: Bearer $TOKEN"

# 3) 创建脚本（operator 及以上）
curl -s -X POST http://localhost:8000/api/scripts \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"测试","steps":[{"action":"tap","params":{"x":100,"y":200}}]}'

# 4) 查看告警汇总
curl -s http://localhost:8000/api/alerts/summary \
  -H "Authorization: Bearer $TOKEN"
```

---

## 12. 石文盛任务 ↔ 接口 ↔ 页面 对照

| # | 任务书条目 | 后端模块 | 关键接口 | 前端页面 |
|---|-----------|----------|----------|----------|
| 1 | 项目初始化与技术选型 | 全局 | — | — |
| 2 | 数据库架构设计 | models.py / DESIGN.md | — | — |
| 3 | 用户认证与权限 | auth.py + routes/auth.py | /auth/* | Login / Register |
| 5 | 脚本管理 | routes/scripts.py | /scripts/* | Scripts |
| 6 | 分组管理 | routes/groups.py | /groups/* | Groups |
| 7 | 审计日志 | routes/audit.py | /audit, /audit/stats | Audit |
| 8 | 告警系统 | routes/alerts.py + models.Alert | /alerts, /alerts/summary | Alerts |
| 9 | 登录/注册页面 | routes/auth.py(register) | /auth/login,/auth/register | Login / Register |
| 10 | 用户管理页面 | routes/users.py | /users | Users |
| 11 | Docker 部署 | docker-compose.yml + Dockerfile | — | — |
| 12 | GitHub 推送 | git（已提交 2 commit，待远程地址） | — | — |
| 4 | 文件管理 | routes/files.py | /files/* | Files |

> 注：表中 #4 文件管理在任务书原文编号靠后，但归属石文盛，一并列出。任务书 #4 设备管理 / #5 Redroid / 远程控制 / ws-scrcpy / 全局布局 / 分轮次 / 服务器部署 / 全功能测试 / run.bat 为**彭旨豪**负责，本文档未覆盖。
