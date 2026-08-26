"""设备生命周期：创建 / 批量建 N 台 / 启停 / 删除 / 列表 / 详情 / 单台操控。"""
import json
from datetime import datetime
from flask import request, jsonify, g, Blueprint
from sqlalchemy import select
devices_bp = Blueprint("devices", __name__)
from ..extensions import db
from ..models import Device, DeviceLog, record_audit, raise_alert
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
        d = Device(name=f"{prefix}-{i+1}", group_id=group_id, status=state["status"],
                   serial=state["serial"], backend=backend, ip=state["ip"],
                   fingerprint=state["fingerprint"], created_by=cur.id)
        db.session.add(d)
        created.append(d)
    db.session.commit()
    record_audit(cur.id, "batch_create_device", "device", None,
                 {"count": count, "backend": backend})
    return jsonify([_dev_to_dict(d) for d in created]), 201


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


def _dev_to_dict(d: Device) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "group_id": d.group_id,
        "status": d.status,
        "serial": d.serial,
        "backend": d.backend,
        "ip": d.ip,
        "fingerprint": d.fingerprint,
        "created_by": d.created_by,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "cpu": d.cpu,
        "mem": d.mem,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
