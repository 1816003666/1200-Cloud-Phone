"""后台任务调度器（APScheduler）。

- 每 5 秒扫描「enabled 且 next_run 到点」的任务，先重排排期再执行（防崩溃重复触发）；
- execute_task 既被调度器调用，也被手动「立即执行」接口调用；
- 任务动作目前以 simulator 记录日志为主，真实动作在 orchestrator 扩展。
"""
import json
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

_scheduler = None
_app = None


def start_scheduler(app):
    global _scheduler, _app
    _app = app
    if _scheduler is not None:
        return  # 避免重复启动（如 reload）
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_tick, "interval", seconds=5, id="task_tick")
    # 告警系统健康检查：设备离线 / 资源超限（任务书 #12）
    _scheduler.add_job(run_alert_checks, "interval", seconds=30, id="alert_checks")
    _scheduler.start()


def _now():
    return datetime.utcnow()


def _tick():
    if _app is None:
        return
    with _app.app_context():
        from .extensions import db
        from .models import ScheduledTask
        due = db.session.query(ScheduledTask).filter(
            ScheduledTask.enabled.is_(True),
            ScheduledTask.next_run <= _now(),
        ).all()
        for t in due:
            execute_task(t, actor_id=t.created_by)
            # 重排下次执行时间（先排期再跑，防重复）
            if t.schedule_type == "interval":
                t.next_run = _now() + timedelta(seconds=t.interval_seconds)
            else:
                t.enabled = False  # once 任务执行后禁用
            db.session.commit()


def execute_task(task, actor_id: int) -> int:
    """执行一个任务，写一条 TaskExecution 记录。返回 execution id。"""
    from .extensions import db
    from .models import TaskExecution, Device, record_audit

    device_ids = json.loads(task.device_ids) if task.device_ids else []
    exec_rec = TaskExecution(task_id=task.id, status="running",
                             total=len(device_ids))
    db.session.add(exec_rec)
    db.session.commit()

    ok = failed = 0
    details = []
    devices = db.session.query(Device).filter(Device.id.in_(device_ids)).all() \
        if device_ids else []
    for d in devices:
        try:
            from . import orchestrator
            orchestrator.control_device(d.backend, d.serial, task.action,
                                        json.loads(task.params) if task.params else {})
            ok += 1
            details.append({"device_id": d.id, "ok": True})
        except Exception as e:  # noqa: BLE001
            failed += 1
            details.append({"device_id": d.id, "ok": False, "error": str(e)})

    exec_rec.ok = ok
    exec_rec.failed = failed
    exec_rec.status = "success" if failed == 0 else "failed"
    exec_rec.finished_at = _now()
    exec_rec.detail = json.dumps(details, ensure_ascii=False)
    db.session.commit()
    record_audit(actor_id, "execute_task", "task", task.id,
                 {"ok": ok, "failed": failed})
    return exec_rec.id


def run_alert_checks():
    """告警健康检查（每 30s）。

    - device_offline：running 设备超过 ALERT_OFFLINE_SECONDS 无心跳 → 置 error + 告警；
    - resource_limit：running 设备 CPU/内存超过阈值 → 告警（阈值由 config 控制）。
    阈值可调，redroid 接入后把 cpu/mem 改为真实采集即可。
    """
    if _app is None:
        return
    with _app.app_context():
        from .extensions import db
        from .models import Device, raise_alert, _utcnow
        cfg = _app.config
        offline_sec = cfg.get("ALERT_OFFLINE_SECONDS", 120)
        cpu_limit = cfg.get("ALERT_CPU_LIMIT", 90)
        mem_limit = cfg.get("ALERT_MEM_LIMIT", 90)
        now = _utcnow()

        devices = db.session.query(Device).all()
        for d in devices:
            if d.status != "running":
                continue
            # 模拟资源采集（占位；redroid 接入后替换 real metrics）
            d.cpu = 20.0 + (d.id * 13) % 70      # 20 ~ 89
            d.mem = 30.0 + (d.id * 11) % 60      # 30 ~ 89

            if d.last_seen and (now - d.last_seen).total_seconds() > offline_sec:
                d.status = "error"
                raise_alert("device_offline", "critical",
                            f"设备 {d.name} 离线超过 {offline_sec}s（最后心跳 {d.last_seen.isoformat()}）",
                            device_id=d.id)
            elif d.cpu and d.cpu > cpu_limit:
                raise_alert("resource_limit", "warning",
                            f"设备 {d.name} CPU {d.cpu:.0f}% 超过阈值 {cpu_limit:.0f}%",
                            device_id=d.id, detail={"cpu": d.cpu, "mem": d.mem})
            elif d.mem and d.mem > mem_limit:
                raise_alert("resource_limit", "warning",
                            f"设备 {d.name} 内存 {d.mem:.0f}% 超过阈值 {mem_limit:.0f}%",
                            device_id=d.id, detail={"cpu": d.cpu, "mem": d.mem})
        db.session.commit()
