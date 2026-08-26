"""数据看板：/metrics/overview 返回前端看板所需全部聚合指标。"""
from flask import jsonify, Blueprint
dashboard_bp = Blueprint("dashboard", __name__)
from ..extensions import db
from ..models import Device, ScheduledTask, Group, AuditLog, TaskExecution
from ..auth import login_required


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
