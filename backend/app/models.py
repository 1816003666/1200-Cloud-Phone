"""数据库架构：8 张表。

ER 关系：
    users 1──* groups            (owner)
    groups 1──* devices
    users 1──* devices           (creator)
    users 1──* scripts           (owner)
    users 1──* scheduled_tasks   (creator)
    users 1──* audit_logs        (actor)
    scheduled_tasks 1──* task_executions
    devices 1──* device_logs
"""
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

# 为避免循环依赖，这里直接复用 extensions 的 db 实例
from .extensions import db  # noqa: E402


def _utcnow():
    # 统一用 naive UTC，避免 SQLite/Postgres 时区混用导致比较报错
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# 枚举约束（用字符串列 + Python 常量，便于 SQLite/Postgres 通用，免迁移踩坑）
# ---------------------------------------------------------------------------
ROLE_LEVELS = {
    "viewer": 1,
    "operator": 2,
    "admin": 3,
    "superadmin": 4,
}
ROLE_CHOICES = list(ROLE_LEVELS.keys())

DEVICE_STATUS = ["creating", "running", "stopped", "error"]
DEVICE_BACKEND = ["simulator", "redroid"]
SCHEDULE_TYPE = ["once", "interval"]
TASK_ACTION = ["open_url", "tap", "swipe", "text", "key", "install", "sequence", "wait"]
EXEC_STATUS = ["pending", "running", "success", "failed"]


def role_level(role: str) -> int:
    return ROLE_LEVELS.get(role, 0)


def record_audit(actor_id: int, action: str, target_type: str = "",
                 target_id: int = None, detail: dict = None):
    """写入操作审计（权限系统标配）。detail 传 dict 会自动 JSON 化。"""
    import json
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=json.dumps(detail or {}, ensure_ascii=False),
    )
    db.session.add(log)
    db.session.commit()


# ---------------------------------------------------------------------------
# 用户与权限
# ---------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    hashed_password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="viewer")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    groups = db.relationship("Group", back_populates="owner",
                             foreign_keys="Group.owner_id")
    devices = db.relationship("Device", back_populates="creator",
                              foreign_keys="Device.created_by")
    scripts = db.relationship("Script", back_populates="owner")
    scheduled_tasks = db.relationship("ScheduledTask", back_populates="creator")
    audit_logs = db.relationship("AuditLog", back_populates="actor")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# 设备分组
# ---------------------------------------------------------------------------
class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), default="")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    owner = db.relationship("User", back_populates="groups",
                            foreign_keys=[owner_id])
    devices = db.relationship("Device", back_populates="group")


# ---------------------------------------------------------------------------
# 云手机设备
# ---------------------------------------------------------------------------
class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, index=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="creating")
    serial = db.Column(db.String(64), default="")        # adb serial / simulator id
    backend = db.Column(db.String(16), default="simulator")
    ip = db.Column(db.String(64), default="")            # 出口 IP（群控卖点）
    fingerprint = db.Column(db.Text, default="")         # 设备指纹 JSON
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    # 告警系统用：最近一次心跳/操控时间 + 模拟资源指标（redroid 接入后由真实采集替换）
    last_seen = db.Column(db.DateTime, nullable=True)
    cpu = db.Column(db.Float, nullable=True)             # 百分比 0-100
    mem = db.Column(db.Float, nullable=True)             # 百分比 0-100

    group = db.relationship("Group", back_populates="devices")
    creator = db.relationship("User", back_populates="devices",
                              foreign_keys=[created_by])
    logs = db.relationship("DeviceLog", back_populates="device",
                           cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 设备日志
# ---------------------------------------------------------------------------
class DeviceLog(db.Model):
    __tablename__ = "device_logs"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False)
    level = db.Column(db.String(16), default="info")
    message = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_utcnow)

    device = db.relationship("Device", back_populates="logs")


# ---------------------------------------------------------------------------
# 定时任务定义
# ---------------------------------------------------------------------------
class ScheduledTask(db.Model):
    __tablename__ = "scheduled_tasks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    action = db.Column(db.String(32), nullable=False)     # 见 TASK_ACTION
    params = db.Column(db.Text, default="{}")             # JSON 参数
    device_ids = db.Column(db.Text, default="[]")         # JSON 数组
    schedule_type = db.Column(db.String(16), default="once")  # once/interval
    interval_seconds = db.Column(db.Integer, default=3600)
    next_run = db.Column(db.DateTime, nullable=True)
    enabled = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    creator = db.relationship("User", back_populates="scheduled_tasks")
    executions = db.relationship("TaskExecution", back_populates="task",
                                 cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# 任务执行记录
# ---------------------------------------------------------------------------
class TaskExecution(db.Model):
    __tablename__ = "task_executions"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("scheduled_tasks.id"), nullable=False)
    status = db.Column(db.String(16), default="pending")
    started_at = db.Column(db.DateTime, default=_utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    total = db.Column(db.Integer, default=0)
    ok = db.Column(db.Integer, default=0)
    failed = db.Column(db.Integer, default=0)
    detail = db.Column(db.Text, default="")               # JSON 明细

    task = db.relationship("ScheduledTask", back_populates="executions")


# ---------------------------------------------------------------------------
# 操作审计
# ---------------------------------------------------------------------------
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(64), nullable=False)     # create_user/delete_device...
    target_type = db.Column(db.String(32), default="")
    target_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, default="{}")             # JSON
    created_at = db.Column(db.DateTime, default=_utcnow)

    actor = db.relationship("User", back_populates="audit_logs")


# ---------------------------------------------------------------------------
# 脚本模板（跨设备回放）
# ---------------------------------------------------------------------------
class Script(db.Model):
    __tablename__ = "scripts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    steps = db.Column(db.Text, default="[]")              # JSON 步骤数组
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    owner = db.relationship("User", back_populates="scripts")


# ---------------------------------------------------------------------------
# 文件管理（上传/下载/浏览/推送到设备）
# ---------------------------------------------------------------------------
class FileRecord(db.Model):
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)          # 用户看到的原始文件名
    stored_name = db.Column(db.String(255), nullable=False)       # 磁盘上的实际文件名
    size = db.Column(db.Integer, default=0)
    mime = db.Column(db.String(128), default="")
    uploader_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    target_device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    uploader = db.relationship("User")


# ---------------------------------------------------------------------------
# 告警系统（任务书 #12）：设备离线 / 资源超限 / 操作失败 三类告警
# ---------------------------------------------------------------------------
ALERT_LEVELS = ["info", "warning", "critical"]
ALERT_TYPES = ["device_offline", "resource_limit", "operation_failure"]
ALERT_STATUSES = ["active", "acknowledged", "resolved"]


def raise_alert(atype: str, level: str, message: str,
                device_id: int = None, detail: dict = None,
                dedup_minutes: int = 30):
    """写入一条告警。

    - 同一 (device_id, type) 在 dedup 窗口内已有未解决告警则跳过，避免刷屏；
    - 返回新建/已有的 Alert 对象，便于调用方继续处理。
    """
    import json
    now = _utcnow()
    existing = (db.session.query(Alert)
                .filter(Alert.type == atype,
                        Alert.device_id == device_id,
                        Alert.status != "resolved",
                        Alert.created_at >= now - timedelta(minutes=dedup_minutes))
                .first())
    if existing:
        return existing
    a = Alert(level=level, type=atype, message=message,
              device_id=device_id, status="active",
              detail=json.dumps(detail or {}, ensure_ascii=False))
    db.session.add(a)
    db.session.commit()
    return a


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(16), nullable=False, default="warning")   # info/warning/critical
    type = db.Column(db.String(32), nullable=False)                       # 见 ALERT_TYPES
    message = db.Column(db.Text, default="")
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="active")   # active/acknowledged/resolved
    detail = db.Column(db.Text, default="{}")                            # JSON
    created_at = db.Column(db.DateTime, default=_utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
