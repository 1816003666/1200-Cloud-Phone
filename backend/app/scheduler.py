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
    # 云手机轮次运行检查：到点销毁并重建所有 redroid 设备
    _scheduler.add_job(rotation_check, "interval", seconds=60, id="rotation_check")
    _scheduler.add_job(snapshot_metrics, "interval", seconds=60, id="metrics_snapshot")
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
        for t0 in due:
            try:
                # 重新从 DB 获取，避免任务被并发删除后访问已删实例
                t = db.session.get(ScheduledTask, t0.id)
                if t is None or not t.enabled:
                    continue
                execute_task(t, actor_id=t.created_by)
                # 重排下次执行时间（先排期再跑，防重复）
                if t.schedule_type == "interval":
                    t.next_run = _now() + timedelta(seconds=t.interval_seconds)
                elif t.schedule_type == "cron":
                    from croniter import croniter
                    t.next_run = croniter(t.cron_expr or "0 * * * *",
                                          _now()).get_next(datetime)
                else:
                    t.enabled = False  # once 任务执行后禁用
                db.session.commit()
            except Exception as e:  # noqa: BLE001
                db.session.rollback()
                print(f"[tick] 任务 {t0.id} 处理异常: {e}")


def execute_task(task, actor_id: int) -> int:
    """执行一个任务，写一条 TaskExecution 记录。返回 execution id。"""
    from .extensions import db
    from .models import TaskExecution, Device, record_audit

    # 健康巡检：整机巡检一次（服务器 + 云手机），不逐设备重复执行
    if task.action == "health_check":
        return _run_health_check(task, actor_id)

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

    # 重新获取，防止任务被并发删除时级联删除了 exec_rec 导致 ObjectDeletedError
    exec_rec = db.session.get(TaskExecution, exec_rec.id)
    if exec_rec is None:
        return -1  # 执行记录已被删除，直接返回

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
        from .models import Device, raise_alert, _utcnow, get_setting
        cfg = _app.config
        def _g(key, fallback):
            try:
                v = get_setting(key)
                return int(v) if v is not None else fallback
            except Exception:  # noqa: BLE001
                return fallback
        offline_sec = _g("alert_offline_seconds", cfg.get("ALERT_OFFLINE_SECONDS", 120))
        cpu_limit = _g("alert_cpu_limit", cfg.get("ALERT_CPU_LIMIT", 90))
        mem_limit = _g("alert_mem_limit", cfg.get("ALERT_MEM_LIMIT", 90))
        now = _utcnow()

        devices = db.session.query(Device).all()
        # 先获取一次 ADB 在线列表（避免循环中重复调用）
        adb_devs = []
        has_redroid = any(d.backend == "redroid" for d in devices)
        if has_redroid:
            from . import orchestrator
            adb_devs = orchestrator.list_adb_devices()
        online_serials = {x["serial"] for x in adb_devs if x["status"] == "device"}

        for d in devices:
            # simulator 是纯内存 Mock，自动刷新心跳避免误判
            if d.backend == "simulator":
                d.last_seen = now
                d.cpu = 20.0 + (d.id * 13) % 70      # 20 ~ 89
                d.mem = 30.0 + (d.id * 11) % 60      # 30 ~ 89
                if d.status != "running":
                    d.status = "running"
            elif d.backend == "redroid":
                if d.serial in online_serials:
                    # ADB 在线：更新心跳 + 恢复状态（如果之前是 error）
                    was_offline = d.status != "running"
                    d.last_seen = now
                    if was_offline:
                        d.status = "running"
                    # 自动恢复：设备在线时幂等关闭其历史离线告警
                    #（不只在状态翻转时处理，重启后遗留的离线告警也能被清掉）
                    try:
                        from .models import resolve_alerts_for_device
                        n = resolve_alerts_for_device(d.id, "device_offline")
                        if n:
                            print(f"[alert] 设备 {d.name} 在线，自动解决 {n} 条离线告警")
                    except Exception:  # noqa: BLE001
                        pass
                    # 简易 CPU/MEM 采集（通过 /proc）
                    try:
                        from . import orchestrator
                        rc, out, _ = orchestrator._run_adb(
                            ["-s", d.serial, "shell", "cat", "/proc/stat"], timeout=5)
                        if out:
                            parts = out.decode().split()
                            if len(parts) >= 5:
                                user, nice, sys, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                                total = user + nice + sys + idle
                                if total > 0:
                                    d.cpu = round((user + nice + sys) / total * 100, 1)
                    except Exception:
                        pass
                    try:
                        from . import orchestrator
                        rc, out, _ = orchestrator._run_adb(
                            ["-s", d.serial, "shell", "cat", "/proc/meminfo"], timeout=5)
                        if out:
                            lines = out.decode().splitlines()
                            total = avail = 0
                            for line in lines:
                                if line.startswith("MemTotal:"):
                                    total = int(line.split()[1])
                                elif line.startswith("MemAvailable:"):
                                    avail = int(line.split()[1])
                            if total > 0:
                                d.mem = round((1 - avail / total) * 100, 1)
                    except Exception:
                        pass
                else:
                    # ADB 不在线，尝试重连
                    if ":" in d.serial:
                        from . import orchestrator
                        orchestrator.adb_connect(d.serial)

            # 离线判定：running 设备超过 offline_sec 无心跳 → 置 error
            if d.status == "running" and d.last_seen and (now - d.last_seen).total_seconds() > offline_sec:
                d.status = "error"
                raise_alert("device_offline", "critical",
                            f"设备 {d.name} 离线超过 {offline_sec}s（最后心跳 {d.last_seen.isoformat()}）",
                            device_id=d.id)
            elif d.status == "running" and d.cpu and d.cpu > cpu_limit:
                raise_alert("resource_limit", "warning",
                            f"设备 {d.name} CPU {d.cpu:.0f}% 超过阈值 {cpu_limit:.0f}%",
                            device_id=d.id, detail={"cpu": d.cpu, "mem": d.mem})
            elif d.status == "running" and d.mem and d.mem > mem_limit:
                raise_alert("resource_limit", "warning",
                            f"设备 {d.name} 内存 {d.mem:.0f}% 超过阈值 {mem_limit:.0f}%",
                            device_id=d.id, detail={"cpu": d.cpu, "mem": d.mem})
        db.session.commit()


def rotation_check():
    """云手机轮次运行：开启后每轮结束（24h / rounds）自动销毁并重建所有 redroid 设备。

    每 60 秒检查一次 next_round_at 是否到点；到点执行轮转并排期下一轮。
    """
    if _app is None:
        return
    with _app.app_context():
        from .extensions import db
        from . import orchestrator
        from datetime import timedelta
        from .models import RotationConfig

        cfg = db.session.get(RotationConfig, 1)
        if cfg is None or not cfg.enabled or not cfg.next_round_at:
            return
        now = _now()
        if now < cfg.next_round_at:
            return

        # 到点：销毁并重建所有 redroid 云手机
        result = orchestrator.rotate_redroid_devices()
        # 排期下一轮
        cfg.round_index = (cfg.round_index % cfg.rounds) + 1
        cfg.next_round_at = _now() + timedelta(hours=24 / cfg.rounds)
        db.session.commit()
        print(f"[rotation] round {cfg.round_index} rotated: "
              f"destroyed={result.get('destroyed')} created={result.get('created')} "
              f"failed={result.get('failed')}")


# ---------------------------------------------------------------------------
# 健康巡检任务（health_check）
# 每天巡检一次：服务器（CPU/内存/磁盘/容器）+ 云手机（ADB 在线/状态/资源）
# 结果写入 TaskExecution.detail，异常触发告警。
# ---------------------------------------------------------------------------
def _run_health_check(task, actor_id: int) -> int:
    from .extensions import db
    from .models import TaskExecution, Device, raise_alert, record_audit

    exec_rec = TaskExecution(task_id=task.id, status="running", total=0)
    db.session.add(exec_rec)
    db.session.commit()

    report = {
        "type": "health_check",
        "generated_at": _now().isoformat(),
        "server": _collect_server_health(),
        "devices": {"total": 0, "ok": 0, "failed": 0, "items": []},
    }

    # —— 云手机健康 ——
    from . import orchestrator
    try:
        adb_devs = orchestrator.list_adb_devices()
        online_serials = {x["serial"] for x in adb_devs if x["status"] == "device"}
    except Exception:
        online_serials = set()

    from .models import get_setting
    try:
        cpu_limit = int(get_setting("alert_cpu_limit") or 90)
        mem_limit = int(get_setting("alert_mem_limit") or 90)
    except Exception:  # noqa: BLE001
        cpu_limit = mem_limit = 90
    dev_rows = db.session.query(Device).filter(Device.backend == "redroid").all()
    dev_ok = dev_failed = 0
    for d in dev_rows:
        issues = []
        online = d.serial in online_serials
        if not online:
            issues.append("ADB 离线")
        if d.status != "running":
            issues.append(f"状态={d.status}")
        if d.cpu is not None and d.cpu > cpu_limit:
            issues.append(f"CPU {d.cpu:.0f}%")
        if d.mem is not None and d.mem > mem_limit:
            issues.append(f"内存 {d.mem:.0f}%")
        is_ok = len(issues) == 0
        if is_ok:
            dev_ok += 1
        else:
            dev_failed += 1
        report["devices"]["items"].append({
            "device_id": d.id, "name": d.name, "serial": d.serial,
            "status": d.status, "online": online, "cpu": d.cpu, "mem": d.mem,
            "ok": is_ok, "issues": issues,
        })
    report["devices"]["total"] = len(dev_rows)
    report["devices"]["ok"] = dev_ok
    report["devices"]["failed"] = dev_failed

    # —— 汇总 & 告警 ——
    server_ok = report["server"].get("ok", False)
    server_issues = report["server"].get("issues", [])
    total_issues = len(server_issues) + dev_failed
    if total_issues == 0:
        summary = f"健康：服务器正常，云手机 {dev_ok}/{len(dev_rows)} 在线"
    else:
        summary = f"存在 {total_issues} 项异常：服务器 {len(server_issues)} 项，云手机 {dev_failed}/{len(dev_rows)} 台"
    report["summary"] = summary

    status = "success" if total_issues == 0 else "failed"
    exec_rec = db.session.get(TaskExecution, exec_rec.id)
    if exec_rec is not None:
        exec_rec.status = status
        exec_rec.total = len(dev_rows)
        exec_rec.ok = dev_ok
        exec_rec.failed = dev_failed
        exec_rec.finished_at = _now()
        exec_rec.detail = json.dumps(report, ensure_ascii=False, default=str)
        db.session.commit()
        record_audit(actor_id, "execute_task", "task", task.id,
                     {"action": "health_check", "ok": dev_ok, "failed": dev_failed,
                      "server_ok": server_ok})

    if total_issues > 0:
        raise_alert("health_check", "critical" if (not server_ok or dev_failed) else "warning",
                    summary, detail={"server_issues": server_issues,
                                     "device_failed": dev_failed})
    return exec_rec.id if exec_rec is not None else -1


def _collect_server_health() -> dict:
    """采集云手机服务器（SSH）的 CPU 负载 / 内存 / 磁盘 / Docker 容器。"""
    from . import orchestrator
    from .orchestrator import _ssh_enabled, _ssh_connect, _ssh_exec

    res = {"ok": False, "reachable": False, "host": orchestrator._server_ip(),
           "metrics": {}, "issues": []}
    if not _ssh_enabled():
        res["issues"].append("SSH 未配置（无法巡检服务器）")
        return res

    client = None
    try:
        client = _ssh_connect()
        res["reachable"] = True
        # 核心数
        rc, out, _ = _ssh_exec(client, "nproc")
        cores = int(out.strip() or 1) if rc == 0 else 1
        # 负载
        rc, out, _ = _ssh_exec(client, "cat /proc/loadavg")
        load = float(out.split()[0]) if rc == 0 and out.strip() else 0.0
        load_ratio = load / cores if cores else 0.0
        load_level = "ok" if load_ratio < 1.0 else ("warning" if load_ratio < 2.0 else "critical")
        # 内存
        rc, out, _ = _ssh_exec(client, "free -m")
        mem = _parse_free(out)
        mem_level = "ok" if mem and mem["used_pct"] < 85 else ("warning" if mem and mem["used_pct"] < 95 else "critical")
        # 磁盘
        rc, out, _ = _ssh_exec(client, "df -h / | tail -1")
        disk = _parse_df(out)
        disk_level = "ok" if disk and disk["used_pct"] < 85 else ("warning" if disk and disk["used_pct"] < 95 else "critical")
        # Docker 容器
        rc, total, _ = _ssh_exec(client, "docker ps -a -q | wc -l")
        rc2, running, _ = _ssh_exec(client, "docker ps -q | wc -l")
        c_total = int(total.strip() or 0) if rc == 0 else 0
        c_run = int(running.strip() or 0) if rc2 == 0 else 0
        c_level = "ok" if c_total == c_run else "warning"

        metrics = {
            "cores": cores,
            "load": {"value": round(load, 2), "ratio": round(load_ratio, 2), "level": load_level},
            "memory": {**(mem or {}), "level": mem_level},
            "disk": {**(disk or {}), "level": disk_level},
            "containers": {"total": c_total, "running": c_run, "level": c_level},
        }
        res["metrics"] = metrics

        if load_level != "ok":
            res["issues"].append(f"负载 {load:.2f} / {cores} 核")
        if mem_level != "ok":
            res["issues"].append(f"内存使用 {metrics['memory'].get('used_pct', '?')}%")
        if disk_level != "ok":
            res["issues"].append(f"磁盘使用 {metrics['disk'].get('used_pct', '?')}%")
        if c_level != "ok":
            res["issues"].append(f"容器 {c_run}/{c_total} 运行")
        res["ok"] = len(res["issues"]) == 0
    except Exception as e:  # noqa: BLE001
        res["issues"].append(f"SSH 连接失败: {e}")
    finally:
        if client:
            client.close()
    return res


def _parse_free(out: str) -> dict:
    """解析 free -m 输出 -> {total_mb, used_mb, used_pct}（兼容中/英文列名）"""
    for line in (out or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Mem:") or stripped.startswith("内存"):
            parts = stripped.split()
            # 兼容「内存：」冒号粘连
            total = float(parts[1])
            used = float(parts[2])
            if total > 0:
                return {"total_mb": int(total), "used_mb": int(used),
                        "used_pct": round(used / total * 100, 1)}
    return {"total_mb": 0, "used_mb": 0, "used_pct": 0.0}


def _parse_df(out: str) -> dict:
    """解析 df -h 输出 -> {size, used, used_pct}"""
    parts = (out or "").split()
    if len(parts) >= 5:
        try:
            pct = float(parts[4].replace("%", ""))
        except ValueError:
            pct = 0.0
        return {"size": parts[1], "used": parts[2], "used_pct": pct}
    return {"size": "-", "used": "-", "used_pct": 0.0}



def snapshot_metrics():
    """每 60s 采样一次服务器资源 + 设备在线数，写入 metrics_snapshots（趋势图数据源）。"""
    if _app is None:
        return
    with _app.app_context():
        from .extensions import db
        from .models import MetricsSnapshot, Device
        from . import orchestrator
        srv = _collect_server_health()
        m = srv.get("metrics", {})
        online = 0
        try:
            adb = orchestrator.list_adb_devices()
            online = sum(1 for x in adb if x["status"] == "device")
        except Exception:  # noqa: BLE001
            pass
        total = db.session.query(Device).filter_by(backend="redroid").count()
        snap = MetricsSnapshot(
            server_cpu=(m.get("load") or {}).get("ratio", 0) * 100 if (m.get("load") or {}).get("ratio") is not None else None,
            server_mem=(m.get("memory") or {}).get("used_pct"),
            server_disk=(m.get("disk") or {}).get("used_pct"),
            containers=(m.get("containers") or {}).get("running"),
            devices_online=online,
            devices_total=total,
        )
        db.session.add(snap)
        # 只保留最近 7 天数据，防止无限增长
        from datetime import timedelta
        cutoff = _now() - timedelta(days=7)
        db.session.query(MetricsSnapshot).filter(MetricsSnapshot.ts < cutoff).delete()
        db.session.commit()
