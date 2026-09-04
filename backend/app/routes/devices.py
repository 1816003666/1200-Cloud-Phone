"""设备生命周期：创建 / 批量建 N 台 / 启停 / 删除 / 列表 / 详情 / 单台操控 / 截图 / 导入真实设备。"""
import io
import json
import os
import uuid
from datetime import datetime
from flask import request, jsonify, g, Blueprint, send_file, current_app
from sqlalchemy import select
devices_bp = Blueprint("devices", __name__)
from ..extensions import db
from ..models import Device, DeviceLog, Group, record_audit, raise_alert
from ..auth import login_required, require_role
from .. import orchestrator


@devices_bp.get("/devices")
@login_required
def list_devices():
    group_id = request.args.get("group_id", type=int)
    status = request.args.get("status")
    q = request.args.get("q")
    stmt = select(Device)
    if group_id is not None:
        stmt = stmt.where(Device.group_id == group_id)
    if status:
        stmt = stmt.where(Device.status == status)
    if q:
        stmt = stmt.where(Device.name.ilike(f"%{q}%"))
    devices = db.session.execute(stmt.order_by(Device.id)).scalars().all()
    return jsonify([_dev_to_dict(d) for d in devices])


@devices_bp.post("/devices")
@require_role("operator")
def create_device():
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    group_id = data.get("group_id")
    backend = data.get("backend") or "simulator"
    if not name:
        return jsonify(error="设备名必填"), 400

    try:
        state = orchestrator.create_device(backend, name)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not state.get("serial"):
        return jsonify(error=state.get("error") or "设备创建失败"), 400

    d = Device(name=name, group_id=group_id, status=state["status"],
               serial=state["serial"], backend=backend, ip=state["ip"],
               fingerprint=state["fingerprint"], created_by=cur.id,
               last_seen=datetime.utcnow(), cpu=20.0, mem=30.0)
    db.session.add(d)
    db.session.commit()
    record_audit(cur.id, "create_device", "device", d.id, {"name": name, "backend": backend})
    return jsonify(_dev_to_dict(d)), 201


@devices_bp.post("/devices/batch")
@require_role("operator")
def batch_create():
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    count = data.get("count", 0)
    prefix = data.get("prefix", "phone")
    group_id = data.get("group_id")
    backend = data.get("backend") or "simulator"
    if not (1 <= count <= 200):
        return jsonify(error="count 需在 1..200"), 400

    created = []
    for i in range(count):
        state = orchestrator.create_device(backend, f"{prefix}-{i+1}")
        if not state.get("serial"):
            continue  # 该台容器创建失败（如端口已被占用），跳过不落库
        exist = db.session.query(Device).filter_by(
            backend=backend, serial=state["serial"]).first()
        if exist:
            created.append(exist)  # 已存在该 serial，复用，避免重复
            continue
        d = Device(name=f"{prefix}-{i+1}", group_id=group_id, status=state["status"],
                   serial=state["serial"], backend=backend, ip=state["ip"],
                   fingerprint=state["fingerprint"], created_by=cur.id)
        db.session.add(d)
        created.append(d)
    db.session.commit()
    record_audit(cur.id, "batch_create_device", "device", None,
                 {"count": count, "backend": backend})
    return jsonify([_dev_to_dict(d) for d in created]), 201


@devices_bp.post("/devices/batch-delete")
@require_role("operator")
def batch_delete():
    """批量删除设备（真实 redroid：断开 ADB + 删除服务器容器）。"""
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    ids = [int(i) for i in (data.get("device_ids") or [])]
    if not ids:
        return jsonify(error="请选择至少一台设备"), 400
    ok, failed_ids = 0, []
    for did in ids:
        d = db.session.get(Device, did)
        if d is None:
            failed_ids.append(did)
            continue
        try:
            orchestrator.delete_device(d.backend, d.serial)
            db.session.delete(d)
            ok += 1
        except Exception:  # noqa: BLE001
            failed_ids.append(did)
    db.session.commit()
    record_audit(cur.id, "batch_delete_device", "device", None,
                 {"count": ok, "failed": failed_ids})
    if failed_ids:
        raise_alert("operation_failure", "warning",
                    f"批量删除失败 {len(failed_ids)} 台设备",
                    detail={"failed_device_ids": failed_ids})
    return jsonify(ok=ok, failed=len(failed_ids))


@devices_bp.post("/devices/batch-set-group")
@require_role("operator")
def batch_set_group():
    """把选中的设备批量加入指定分组（group_id 传 null 表示移出分组/未分组）。"""
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    ids = [int(i) for i in (data.get("device_ids") or [])]
    group_id = data.get("group_id")
    if not ids:
        return jsonify(error="请选择至少一台设备"), 400
    if group_id is not None:
        g_ = db.session.get(Group, int(group_id))
        if g_ is None:
            return jsonify(error="分组不存在"), 404
        group_id = g_.id
    ok, failed_ids = 0, []
    for did in ids:
        d = db.session.get(Device, did)
        if d is None:
            failed_ids.append(did)
            continue
        d.group_id = group_id
        ok += 1
    db.session.commit()
    record_audit(cur.id, "batch_set_group", "device", None,
                 {"count": ok, "group_id": group_id})
    if failed_ids:
        raise_alert("operation_failure", "warning",
                    f"批量设置分组失败 {len(failed_ids)} 台设备",
                    detail={"failed_device_ids": failed_ids})
    return jsonify(ok=ok, failed=len(failed_ids))


@devices_bp.post("/devices/batch-power")
@require_role("operator")
def batch_power():
    """批量电源控制：start | stop | restart（真实 redroid 容器）。"""
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    ids = [int(i) for i in (data.get("device_ids") or [])]
    if action not in ("start", "stop", "restart"):
        return jsonify(error="action 必须是 start/stop/restart"), 400
    if not ids:
        return jsonify(error="请选择至少一台设备"), 400
    ok, failed_ids = 0, []
    for did in ids:
        d = db.session.get(Device, did)
        if d is None:
            failed_ids.append(did)
            continue
        try:
            if d.backend == "redroid" and ":" in d.serial:
                port = int(d.serial.split(":")[-1])
                result = orchestrator.container_power(port, action)
                if not result.get("ok"):
                    failed_ids.append(did)
                    continue
            if action == "start":
                d.status = "running"
            elif action == "stop":
                d.status = "stopped"
            # restart：状态保持 running
            d.last_seen = datetime.utcnow()
            ok += 1
        except Exception:  # noqa: BLE001
            failed_ids.append(did)
    db.session.commit()
    record_audit(cur.id, f"batch_power_{action}", "device", None,
                 {"count": ok, "failed": len(failed_ids)})
    if failed_ids:
        raise_alert("operation_failure", "warning",
                    f"批量{'重启' if action == 'restart' else '开机' if action == 'start' else '关机'}失败 {len(failed_ids)} 台",
                    detail={"failed_device_ids": failed_ids})
    return jsonify(ok=ok, failed=len(failed_ids))


@devices_bp.post("/devices/install-apk")
@require_role("operator")
def batch_install_apk():
    """上传 APK 并批量安装到所选设备（multipart: file + device_ids）。"""
    cur = g.current_user
    ids = [int(i) for i in request.form.get("device_ids", "").split(",") if i.strip()]
    if not ids:
        return jsonify(error="请选择至少一台设备"), 400
    if "file" not in request.files:
        return jsonify(error="缺少 apk 文件字段 file"), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify(error="文件名不能为空"), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext != ".apk":
        return jsonify(error="仅支持 .apk 文件"), 400

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    stored = uuid.uuid4().hex + ext
    save_path = os.path.join(upload_dir, stored)
    f.save(save_path)

    ok, failed_ids = 0, []
    try:
        for did in ids:
            d = db.session.get(Device, did)
            if d is None or d.backend != "redroid":
                failed_ids.append(did)
                continue
            result = orchestrator.install_apk(d.serial, save_path)
            if result.get("ok"):
                ok += 1
            else:
                failed_ids.append(did)
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass
    db.session.commit()
    record_audit(cur.id, "install_apk", "device", None,
                 {"filename": f.filename, "ok": ok, "failed": len(failed_ids)})
    if failed_ids:
        raise_alert("operation_failure", "warning",
                    f"APK 安装失败 {len(failed_ids)} 台设备",
                    detail={"failed_device_ids": failed_ids})
    return jsonify(ok=ok, failed=len(failed_ids))


@devices_bp.get("/devices/<int:did>")
@login_required
def get_device(did):
    d = db.session.get(Device, did)
    if d is None:
        return jsonify(error="设备不存在"), 404
    return jsonify(_dev_to_dict(d))


@devices_bp.post("/devices/<int:did>/control/<action>")
@require_role("operator")
def control(did, action):
    cur = g.current_user
    d = db.session.get(Device, did)
    if d is None:
        return jsonify(error="设备不存在"), 404
    payload = request.get_json(silent=True) or {}
    try:
        result = orchestrator.control_device(d.backend, d.serial, action, payload)
        # 操控成功 → 刷新心跳时间
        d.last_seen = datetime.utcnow()
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        # 操作失败 → 产生一条 operation_failure 告警（dedup 防刷屏）
        raise_alert("operation_failure", "critical",
                    f"设备 {d.name} 操控动作 {action} 失败：{str(e)}",
                    device_id=d.id,
                    detail={"action": action, "error": str(e)})
        return jsonify(error=str(e)), 501
    # 写一条设备日志
    log = DeviceLog(device_id=d.id, level="info",
                    message=f"control {action}: {json.dumps(payload, ensure_ascii=False)}")
    db.session.add(log)
    db.session.commit()
    record_audit(cur.id, "control_device", "device", d.id, {"action": action})
    return jsonify(result)


@devices_bp.delete("/devices/<int:did>")
@require_role("operator")
def delete_device(did):
    cur = g.current_user
    d = db.session.get(Device, did)
    if d is None:
        return jsonify(error="设备不存在"), 404
    orchestrator.delete_device(d.backend, d.serial)
    db.session.delete(d)
    db.session.commit()
    record_audit(cur.id, "delete_device", "device", did, {"name": d.name})
    return jsonify(message="已删除")


@devices_bp.post("/devices/<int:did>/power/<action>")
@require_role("operator")
def device_power(did, action):
    """redroid 容器电源控制：start | stop | restart。"""
    cur = g.current_user
    d = db.session.get(Device, did)
    if d is None:
        return jsonify(error="设备不存在"), 404
    if d.backend != "redroid" or ":" not in d.serial:
        return jsonify(error="仅支持 redroid 设备"), 400
    if action not in ("start", "stop", "restart"):
        return jsonify(error="未知电源操作"), 400

    try:
        port = int(d.serial.split(":")[-1])
        result = orchestrator.container_power(port, action)
        if not result.get("ok"):
            return jsonify(error=result.get("error", "操作失败")), 501

        # 更新设备状态
        if action == "start":
            d.status = "running"
            d.last_seen = datetime.utcnow()
        elif action == "stop":
            d.status = "stopped"
        db.session.commit()

        record_audit(cur.id, f"power_{action}", "device", did,
                     {"serial": d.serial})
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        return jsonify(error=str(e)), 501


# ---------- 真实设备截图 ----------
@devices_bp.get("/devices/<int:did>/screenshot")
@login_required
def device_screenshot(did):
    """获取设备实时截图（PNG）。redroid 设备走 ADB screencap，simulator 返回占位图。"""
    d = db.session.get(Device, did)
    if d is None:
        return jsonify(error="设备不存在"), 404

    if d.backend == "redroid":
        img = orchestrator.get_screenshot(d.serial)
        if img is None:
            return jsonify(error="截图失败，设备可能离线"), 502
        return send_file(io.BytesIO(img), mimetype="image/png",
                         download_name=f"device_{did}.png")

    # simulator：返回 SVG 占位图
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="360" height="640">
<rect width="360" height="640" fill="#1a1a2e"/>
<text x="180" y="320" fill="#666" font-size="16" text-anchor="middle" font-family="sans-serif">Simulator Device</text>
<text x="180" y="350" fill="#444" font-size="12" text-anchor="middle" font-family="sans-serif">{d.name}</text>
</svg>'''
    return send_file(io.BytesIO(svg.encode()), mimetype="image/svg+xml")


# ---------- 发现 / 导入真实 ADB 设备 ----------
@devices_bp.get("/devices/discover")
@require_role("operator")
def discover_devices():
    """扫描当前已连接的 ADB 设备，返回可导入列表。"""
    adb_devices = orchestrator.list_adb_devices()
    # 过滤出在线设备
    online = [d for d in adb_devices if d["status"] == "device"]
    # 检查哪些已经在数据库中
    existing_serials = {d.serial for d in db.session.query(Device).all()}
    result = []
    for d in online:
        info = orchestrator.get_device_info(d["serial"])
        result.append({
            "serial": d["serial"],
            "model": info.get("model", "unknown"),
            "android_version": info.get("android_version", "unknown"),
            "already_imported": d["serial"] in existing_serials,
        })
    return jsonify(result)


@devices_bp.post("/devices/import")
@require_role("operator")
def import_device():
    """导入一台已连接的真实 ADB 设备到数据库。"""
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    serial = (data.get("serial") or "").strip()
    name = (data.get("name") or "").strip()
    if not serial:
        return jsonify(error="serial 必填"), 400

    # 检查是否已导入
    existing = db.session.query(Device).filter_by(serial=serial).first()
    if existing:
        return jsonify(error="该设备已导入", device_id=existing.id), 409

    # 确保 ADB 已连接
    if ":" in serial:
        orchestrator.adb_connect(serial)

    info = orchestrator.get_device_info(serial)
    server = orchestrator._server_ip()
    fp = json.dumps({
        "model": info.get("model", "redroid"),
        "android_version": info.get("android_version", "12"),
        "brand": info.get("brand", ""),
    }, ensure_ascii=False)

    device_name = name or f"redroid-{serial.split(':')[-1]}"
    d = Device(
        name=device_name,
        status="running",
        serial=serial,
        backend="redroid",
        ip=server,
        fingerprint=fp,
        created_by=cur.id,
        last_seen=datetime.utcnow(),
        cpu=0.0,
        mem=0.0,
    )
    db.session.add(d)
    db.session.commit()
    record_audit(cur.id, "import_device", "device", d.id,
                 {"serial": serial, "name": device_name})
    return jsonify(_dev_to_dict(d)), 201


# ---------- 同步服务器设备 ----------
@devices_bp.post("/devices/sync")
@require_role("operator")
def sync_devices():
    """扫描服务器上实际运行的 ADB 设备，与数据库同步。

    - 服务器上有但数据库中没有的 redroid 设备 → 自动导入
    - 数据库中有但服务器上没有的 redroid 设备 → 标记为 error
    - simulator 设备不受影响
    """
    cur = g.current_user
    # 1. 扫描服务器真实运行的 redroid 容器端口（以容器状态为准，而非易失的 adb 连接）
    server = orchestrator._server_ip()
    container_ports = orchestrator.list_server_redroid_ports()
    online_serials = {f"{server}:{p}" for p in container_ports}
    # 对在线设备重新 adb_connect，确保可操控
    for _serial in online_serials:
        try:
            orchestrator.adb_connect(_serial)
        except Exception:
            pass

    # 2. 获取数据库中所有 redroid 设备
    db_devices = db.session.query(Device).filter_by(backend="redroid").all()
    db_serials = {d.serial for d in db_devices}

    # 3. 需要新增的设备（服务器有，数据库没有）
    to_add = online_serials - db_serials
    added = []
    for serial in to_add:
        # 只同步 IP:PORT 格式的 redroid 设备
        if ":" not in serial:
            continue
        orchestrator.adb_connect(serial)
        info = orchestrator.get_device_info(serial)
        server = orchestrator._server_ip()
        fp = json.dumps({
            "model": info.get("model", "redroid"),
            "android_version": info.get("android_version", "12"),
            "brand": info.get("brand", ""),
        }, ensure_ascii=False)
        port = serial.split(":")[-1]
        d = Device(
            name=f"redroid-{port}",
            status="running",
            serial=serial,
            backend="redroid",
            ip=server,
            fingerprint=fp,
            created_by=cur.id,
            last_seen=datetime.utcnow(),
            cpu=0.0,
            mem=0.0,
        )
        db.session.add(d)
        added.append(serial)

    # 4. 需要标记离线的设备（数据库有，服务器没有）
    to_offline = db_serials - online_serials
    offlined = []
    for d in db_devices:
        if d.serial in to_offline and d.status != "error":
            d.status = "error"
            offlined.append(d.serial)

    # 5. 恢复在线的设备（之前标记为 error，现在又在线了）
    restored = []
    for d in db_devices:
        if d.serial in online_serials and d.status == "error":
            d.status = "running"
            d.last_seen = datetime.utcnow()
            restored.append(d.serial)

    db.session.commit()
    record_audit(cur.id, "sync_devices", "device", None,
                 {"added": len(added), "offlined": len(offlined), "restored": len(restored)})

    return jsonify({
        "added": added,
        "offlined": offlined,
        "restored": restored,
        "online_count": len(online_serials),
        "db_count": len(db_serials),
    })


def _dev_model(d: Device) -> str:
    """从设备指纹中解析手机型号。"""
    try:
        fp = json.loads(d.fingerprint or "{}")
        return (fp.get("model") or "").strip()
    except (json.JSONDecodeError, TypeError):
        return ""


def _dev_to_dict(d: Device) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "group_id": d.group_id,
        "status": d.status,
        "serial": d.serial,
        "backend": d.backend,
        "model": _dev_model(d) or ("Pixel-Cloud" if d.backend == "simulator" else "redroid"),
        "ip": d.ip,
        "fingerprint": d.fingerprint,
        "created_by": d.created_by,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "cpu": d.cpu,
        "mem": d.mem,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


# ---------- 云手机轮次运行模式 ----------
def _rotation_dict(cfg) -> dict:
    per_hours = round(24 / max(cfg.rounds, 1), 2)
    return {
        "enabled": cfg.enabled,
        "rounds": cfg.rounds,
        "devices_per_round": cfg.devices_per_round,
        "round_index": cfg.round_index,
        "per_round_hours": per_hours,
        "started_at": cfg.started_at.isoformat() if cfg.started_at else None,
        "next_round_at": cfg.next_round_at.isoformat() if cfg.next_round_at else None,
    }


@devices_bp.get("/rotation")
@login_required
def get_rotation():
    """获取轮次运行配置。"""
    cfg = orchestrator.get_rotation_config()
    return jsonify(_rotation_dict(cfg))


@devices_bp.put("/rotation")
@require_role("operator")
def update_rotation():
    """开启/关闭轮次运行，或修改轮数 / 每轮云手机数量。

    开启时从当前时刻起算：首轮立即开始，并按 devices_per_round
    异步销毁重建一批云手机；之后每 24h/rounds 轮转一次
    （每轮结束自动销毁并重建 devices_per_round 台 redroid 云手机）。
    """
    import threading
    from datetime import timedelta
    data = request.get_json(silent=True) or {}
    cfg = orchestrator.get_rotation_config()

    if "rounds" in data:
        rounds = data.get("rounds")
        try:
            rounds = int(rounds)
        except (TypeError, ValueError):
            return jsonify(error="rounds 必须是整数"), 400
        if not (1 <= rounds <= 24):
            return jsonify(error="rounds 需在 1..24 之间"), 400
        cfg.rounds = rounds

    if "devices_per_round" in data:
        n = data.get("devices_per_round")
        try:
            n = int(n)
        except (TypeError, ValueError):
            return jsonify(error="devices_per_round 必须是整数"), 400
        if not (1 <= n <= 200):
            return jsonify(error="devices_per_round 需在 1..200 之间"), 400
        cfg.devices_per_round = n

    if "enabled" in data:
        enabled = bool(data.get("enabled"))
        cfg.enabled = enabled
        if enabled:
            # 开启：重置为第 1 轮，从当前时刻起算
            cfg.round_index = 1
            cfg.started_at = datetime.utcnow()
            cfg.next_round_at = cfg.started_at + timedelta(hours=24 / cfg.rounds)
            # 立即按 devices_per_round 销毁重建一批（异步，避免阻塞 API）
            target = cfg.devices_per_round
            threading.Thread(
                target=orchestrator.rotate_redroid_devices,
                kwargs={"target_count": target}, daemon=True,
            ).start()
        else:
            cfg.started_at = None
            cfg.next_round_at = None

    db.session.commit()
    record_audit(g.current_user.id, "update_rotation", "config", 1,
                 {"enabled": cfg.enabled, "rounds": cfg.rounds,
                  "devices_per_round": cfg.devices_per_round})
    return jsonify(_rotation_dict(cfg))
