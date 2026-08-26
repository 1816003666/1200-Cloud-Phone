# 云手机平台任务看板 —— 设计文档

> 对应任务书（石文盛名下）：
> - 项目初始化与技术选型（React+Flask+Docker）
> - 数据库架构设计
>
> 项目路径：`E:\work\code\cloud-phone-board`

---

## 一、项目初始化与技术选型

### 1.1 技术栈总览

| 层 | 选型 | 版本 | 选型理由 |
|----|------|------|----------|
| 前端 | React + Vite | React 18.3 / Vite 5.4 | 组件化、热更新快、生态成熟，适合中后台看板 |
| 前端路由 | React Router | 6.x | 声明式路由，配合鉴权守卫简单 |
| 前端状态 | React Context | 内置 | 仅做登录态/token 管理，无需引入 Redux |
| HTTP 客户端 | Axios | 最新 | 拦截器统一注入 `Authorization`、处理 401 跳登录 |
| 后端 | Flask | 3.0.3 | 轻量、工厂模式清晰、蓝图(Blueprint)天然分模块 |
| ORM | Flask-SQLAlchemy | 3.1.1 | 统一 SQLite/PostgreSQL，开发免迁移踩坑 |
| 跨域 | Flask-CORS | 4.0.1 | 前后端分离必备 |
| 认证 | PyJWT + pbkdf2_sha256 | PyJWT 2.9.0 | JWT 无状态登录 + 加盐哈希存密码，不存明文 |
| 调度 | APScheduler | 3.10.4 | 心跳检测/资源采集/定时任务，进程内轻量调度 |
| 关系库 | SQLite（开发）/ PostgreSQL 15（生产） | — | 本地零依赖可跑；Docker 用 PG 保证并发与类型 |
| 缓存/队列 | Redis 7 | — | 预留给设备心跳缓存、批量任务去重（compose 已挂） |
| 部署 | Docker Compose | — | 一键编排 PG+Redis+Backend+Frontend(nginx) |

### 1.2 目录结构

```
cloud-phone-board/
├── backend/
│   ├── app/
│   │   ├── __init__.py        # 应用工厂 + 蓝图注册 + lifespan
│   │   ├── config.py          # 配置（DATABASE_URL / JWT_SECRET / RBAC）
│   │   ├── extensions.py      # db / cors 单例
│   │   ├── models.py          # 10 张表 + record_audit/raise_alert 工具
│   │   ├── auth.py            # pbkdf2 哈希 + JWT 签发 + require_role 依赖
│   │   ├── orchestrator.py    # 设备后端抽象（simulator / redroid）
│   │   ├── scheduler.py       # APScheduler 心跳/资源/告警
│   │   ├── seed.py            # 初始化 admin/root 账号
│   │   └── routes/            # auth/users/devices/tasks/dashboard/
│   │                           # audit/files/scripts/groups/alerts
│   ├── requirements.txt
│   ├── Dockerfile
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── api/client.js      # axios 实例 + 拦截器
│   │   ├── store/auth.jsx     # 登录态 Context
│   │   ├── components/        # Layout / ProtectedRoute
│   │   └── views/             # Login/Register/Dashboard/Devices/Tasks/
│   │                           # Users/Files/Scripts/Groups/Audit/Alerts
│   ├── Dockerfile             # 构建后由 nginx 托管
│   ├── nginx.conf
│   └── vite.config.js
├── docker-compose.yml         # postgres + redis + backend + frontend
└── DESIGN.md
```

### 1.3 架构图

```
┌──────────────┐      HTTP /api      ┌──────────────────┐
│  React SPA   │ ─────────────────▶ │   Flask Backend  │
│ (Vite/nginx) │ ◀───────────────── │  (Blueprint 路由) │
└──────────────┘      JSON           └────────┬─────────┘
                                              │ SQLAlchemy
                                              ▼
                                      ┌───────────────┐
                                      │ SQLite / PG15 │
                                      └───────────────┘
                                              ▲
                              APScheduler 定时写入 │
                      （设备心跳 / 资源采集 / 告警产生）
```

### 1.4 本地免 Docker 运行（simulator 模式）

```bash
# 后端
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=sqlite:///app.db
set DEVICE_BACKEND=simulator
python run.py            # 默认 http://localhost:8000

# 前端
cd ../frontend
npm install
npm run dev              # http://localhost:5173
```

默认账号：`admin / Admin@123456`、`root / Root@123456`

---

## 二、数据库架构设计

### 2.1 ER 关系

```
users (1) ───< groups (owner_id)
users (1) ───< devices (created_by)
groups (1) ───< devices (group_id)
users (1) ───< scripts (owner_id)
users (1) ───< scheduled_tasks (created_by)
users (1) ───< audit_logs (actor_id)
scheduled_tasks (1) ───< task_executions (task_id)
devices (1) ───< device_logs (device_id)
devices (1) ───< files (target_device_id)
devices (1) ───< alerts (device_id)
```

### 2.2 表清单（10 张）

| 表 | 作用 | 关键字段 |
|----|------|----------|
| `users` | 用户/权限 | username, hashed_password, role(viewer/operator/admin/superadmin), is_active |
| `groups` | 设备分组 | name, description, owner_id |
| `devices` | 云手机设备 | name, group_id, status(creating/running/stopped/error), serial, backend(simulator/redroid), ip, fingerprint, last_seen, cpu, mem |
| `device_logs` | 设备操作日志 | device_id, level, message |
| `scheduled_tasks` | 定时/批量任务定义 | action, params(JSON), device_ids(JSON), schedule_type(once/interval), interval_seconds, enabled |
| `task_executions` | 任务执行记录 | task_id, status, total/ok/failed, detail(JSON) |
| `audit_logs` | 全操作审计 | actor_id, action, target_type, target_id, detail(JSON) |
| `scripts` | 脚本模板 | name, steps(JSON), owner_id |
| `files` | 文件管理 | filename, stored_name, size, mime, uploader_id, target_device_id |
| `alerts` | 告警系统 | level(info/warning/critical), type(device_offline/resource_limit/operation_failure), status(active/acknowledged/resolved), device_id, detail(JSON) |

> 设计要点：枚举统一用字符串列 + Python 常量（如 `DEVICE_STATUS`、`ROLE_LEVELS`），避免 SQLite/PostgreSQL 类型差异导致迁移踩坑；JSON 字段用 `Text` 存，业务层 `json.dumps/loads`。时间统一 naive UTC（`_utcnow()`）。

### 2.3 RBAC 模型

```
role          level
viewer        1   仅查看自己可见的设备/看板
operator      2   可操控设备、执行脚本
admin         3   管理分组/文件/脚本/用户、查看并处理告警
superadmin    4   全部权限 + 系统级配置
```

`auth.py` 提供 `require_role(min_role)` 依赖装饰器，路由按最小角色级别保护；所有写操作经 `record_audit()` 落 `audit_logs`。

### 2.4 初始化与建表

- 开发：`Flask-SQLAlchemy` 的 `db.create_all()` 在应用工厂首次启动时建表（无需 Alembic）。
- 种子：`seed.py` 写入 `admin` / `root` 两个初始账号及默认分组。
- 生产：Docker 用 PostgreSQL 15，`DATABASE_URL` 经环境变量注入，逻辑完全一致。
