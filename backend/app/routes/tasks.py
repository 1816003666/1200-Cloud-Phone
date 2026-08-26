"""定时任务路由：定义 / 列表 / 立即执行，调度由 scheduler.py 后台驱动。"""
import json
from datetime import datetime, timedelta
from flask import request, jsonify, g, Blueprint
tasks_bp = Blueprint("tasks", __name__)
from ..extensions import db
from ..models import ScheduledTask, TaskExecution, TASK_ACTION, SCHEDULE_TYPE, record_audit
from ..auth import login_required, require_role


@tasks_bp.get("/tasks")
@login_required
def list_tasks():
    tasks = db.session.query(ScheduledTask).order_by(ScheduledTask.id).all()
    return jsonify([_task_to_dict(t) for t in tasks])


@tasks_bp.post("/tasks")
@require_role("operator")
def create_task():
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    action = data.get("action")
    if not name:
        return jsonify(error="任务名必填"), 400
    if action not in TASK_ACTION:
        return jsonify(error="非法动作"), 400

    t = ScheduledTask(
        name=name,
        action=action,
        params=json.dumps(data.get("params", {}), ensure_ascii=False),
        device_ids=json.dumps(data.get("device_ids", []), ensure_ascii=False),
        schedule_type=data.get("schedule_type", "once"),
        interval_seconds=data.get("interval_seconds", 3600),
        next_run=_compute_next(data.get("schedule_type", "once"),
                               data.get("interval_seconds", 3600)),
        enabled=bool(data.get("enabled", True)),
        created_by=cur.id,
    )
    if t.schedule_type not in SCHEDULE_TYPE:
        return jsonify(error="非法调度类型"), 400
    db.session.add(t)
    db.session.commit()
    record_audit(cur.id, "create_task", "task", t.id, {"name": name, "action": action})
    return jsonify(_task_to_dict(t)), 201


@tasks_bp.post("/tasks/<int:tid>/run")
@require_role("operator")
def run_task(tid):
    cur = g.current_user
    t = db.session.get(ScheduledTask, tid)
    if t is None:
        return jsonify(error="任务不存在"), 404
    from ..scheduler import execute_task
    exec_id = execute_task(t, actor_id=cur.id)
    return jsonify(execution_id=exec_id)


@tasks_bp.delete("/tasks/<int:tid>")
@require_role("operator")
def delete_task(tid):
    cur = g.current_user
    t = db.session.get(ScheduledTask, tid)
    if t is None:
        return jsonify(error="任务不存在"), 404
    db.session.delete(t)
    db.session.commit()
    record_audit(cur.id, "delete_task", "task", tid, {"name": t.name})
    return jsonify(message="已删除")


def _compute_next(schedule_type, interval_seconds):
    if schedule_type == "once":
        return datetime.utcnow()
    return datetime.utcnow() + timedelta(seconds=interval_seconds)


def _task_to_dict(t: ScheduledTask) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "action": t.action,
        "params": json.loads(t.params) if t.params else {},
        "device_ids": json.loads(t.device_ids) if t.device_ids else [],
        "schedule_type": t.schedule_type,
        "interval_seconds": t.interval_seconds,
        "next_run": t.next_run.isoformat() if t.next_run else None,
        "enabled": t.enabled,
        "created_by": t.created_by,
    }
