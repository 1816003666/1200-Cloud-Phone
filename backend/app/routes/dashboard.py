"""数据看板：/metrics/overview 返回前端看板所需全部聚合指标。"""
from flask import jsonify, Blueprint, request
dashboard_bp = Blueprint("dashboard", __name__)
from ..extensions import db
from ..models import Device, ScheduledTask, Group, AuditLog, TaskExecution
from ..auth import login_required


@dashboard_bp.get("/metrics/server")
@login_required
def server_metrics():
    """服务器实时监控：CPU 负载 / 内存 / 磁盘 / Docker 容器 + 云手机 ADB 在线。"""
    from ..scheduler import _collect_server_health
    from .. import orchestrator

    server = _collect_server_health()
    # 云手机在线统计
    adb_online = 0
    try:
        adb_devs = orchestrator.list_adb_devices()
        adb_online = sum(1 for x in adb_devs if x["status"] == "device")
    except Exception:  # noqa: BLE001
        pass
    total = db.session.query(Device).filter_by(backend="redroid").count()
    running = db.session.query(Device).filter(
        Device.backend == "redroid", Device.status == "running").count()
    error = db.session.query(Device).filter(
        Device.backend == "redroid", Device.status == "error").count()

    return jsonify({
        "server": server,
        "devices": {"total": total, "online": adb_online,
                    "running": running, "error": error},
        "collected_at": _utcnow_iso(),
    })


def _utcnow_iso():
    from ..models import _utcnow
    return _utcnow().isoformat()


@dashboard_bp.get("/metrics/overview")
@login_required
def overview():
    total_devices = db.session.query(Device).count()
    running = db.session.query(Device).filter_by(status="running").count()
    error = db.session.query(Device).filter_by(status="error").count()
    stopped = db.session.query(Device).filter_by(status="stopped").count()
    creating = db.session.query(Device).filter_by(status="creating").count()
    groups = db.session.query(Group).count()
    tasks = db.session.query(ScheduledTask).count()
    enabled_tasks = db.session.query(ScheduledTask).filter_by(enabled=True).count()

    # 状态分布
    status_dist = {
        "running": running, "error": error,
        "stopped": stopped, "creating": creating,
    }
    # 分组分布（按分组统计设备数）
    group_dist = []
    for g in db.session.query(Group).all():
        cnt = db.session.query(Device).filter_by(group_id=g.id).count()
        group_dist.append({"group": g.name, "count": cnt})

    recent = db.session.query(Device).order_by(Device.id.desc()).limit(5).all()
    recent_devices = [{"id": d.id, "name": d.name, "status": d.status,
                       "ip": d.ip} for d in recent]

    # 最近执行
    last_exec = db.session.query(TaskExecution).order_by(
        TaskExecution.id.desc()).first()

    return jsonify({
        "kpis": {
            "total_devices": total_devices,
            "running": running,
            "error": error,
            "groups": groups,
            "tasks": tasks,
            "enabled_tasks": enabled_tasks,
        },
        "status_distribution": status_dist,
        "group_distribution": group_dist,
        "recent_devices": recent_devices,
        "last_execution": {
            "id": last_exec.id, "ok": last_exec.ok,
            "failed": last_exec.failed
        } if last_exec else None,
    })


@dashboard_bp.get("/metrics/trend")
@login_required
def metrics_trend():
    """历史趋势数据（看板折线图）：默认最近 24h，可 ?hours= 调整。"""
    from datetime import timedelta
    from ..models import MetricsSnapshot
    hours = min(int(request.args.get("hours", 24)), 168)
    since = _utcnow_iso_dt() - timedelta(hours=hours)
    rows = db.session.query(MetricsSnapshot).filter(
        MetricsSnapshot.ts >= since).order_by(MetricsSnapshot.ts).all()
    return jsonify([{
        "ts": r.ts.isoformat(),
        "server_cpu": r.server_cpu,
        "server_mem": r.server_mem,
        "server_disk": r.server_disk,
        "containers": r.containers,
        "devices_online": r.devices_online,
        "devices_total": r.devices_total,
    } for r in rows])


def _utcnow_iso_dt():
    from ..models import _utcnow
    return _utcnow()

