"""脚本管理模块：创建 / 编辑 / 删除 / 执行 / 模板 / 定时任务。

脚本 = 一组操作步骤（steps JSON），可回放到多台设备。
权限：查看登录即可；创建/编辑/删除/执行需 operator 及以上。
"""
import json

from flask import request, jsonify, Blueprint, g
scripts_bp = Blueprint("scripts", __name__)

from ..extensions import db
from ..models import Script, Device, DeviceLog, record_audit, raise_alert
from ..auth import login_required, require_role

# 内置脚本模板（前端“从模板新建”用）
BUILTIN_TEMPLATES = [
    {"name": "打开指定网址", "steps": [
        {"action": "open_url", "params": {"url": "https://www.example.com"}}]},
    {"name": "安装应用", "steps": [
        {"action": "install", "params": {"pkg": "com.example.app"}}]},
    {"name": "输入文本并回车", "steps": [
        {"action": "text", "params": {"value": "hello"}},
        {"action": "key", "params": {"key": "enter"}}]},
    {"name": "滑动解锁", "steps": [
        {"action": "swipe", "params": {"x1": 500, "y1": 1500, "x2": 500, "y2": 500}}]},
]


@scripts_bp.get("/scripts/templates")
@login_required
def templates():
    return jsonify(BUILTIN_TEMPLATES)


@scripts_bp.get("/scripts")
@login_required
def list_scripts():
    rows = db.session.query(Script).order_by(Script.id.desc()).all()
    return jsonify([_serialize(s) for s in rows])


@scripts_bp.post("/scripts")
@require_role("operator")
def create_script():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    steps = data.get("steps", [])
    if not name:
        return jsonify(error="脚本名必填"), 400
    if not isinstance(steps, list):
        return jsonify(error="steps 必须是数组"), 400
    s = Script(name=name, steps=json.dumps(steps, ensure_ascii=False),
               owner_id=g.current_user.id)
    db.session.add(s)
    db.session.commit()
    record_audit(g.current_user.id, "create_script", "script", s.id,
                {"name": name, "steps": len(steps)})
    return jsonify(_serialize(s)), 201


@scripts_bp.get("/scripts/<int:sid>")
@login_required
def get_script(sid):
    s = db.session.get(Script, sid)
    if s is None:
        return jsonify(error="脚本不存在"), 404
    return jsonify(_serialize(s))


@scripts_bp.patch("/scripts/<int:sid>")
@require_role("operator")
def update_script(sid):
    s = db.session.get(Script, sid)
    if s is None:
        return jsonify(error="脚本不存在"), 404
    data = request.get_json(silent=True) or {}
    if "name" in data:
        s.name = data["name"]
    if "steps" in data and isinstance(data["steps"], list):
        s.steps = json.dumps(data["steps"], ensure_ascii=False)
    db.session.commit()
    record_audit(g.current_user.id, "update_script", "script", sid,
                {"name": s.name})
    return jsonify(_serialize(s))


@scripts_bp.delete("/scripts/<int:sid>")
@require_role("operator")
def delete_script(sid):
    s = db.session.get(Script, sid)
    if s is None:
        return jsonify(error="脚本不存在"), 404
    db.session.delete(s)
    db.session.commit()
    record_audit(g.current_user.id, "delete_script", "script", sid,
                {"name": s.name})
    return jsonify(ok=True)


@scripts_bp.post("/scripts/<int:sid>/execute")
@require_role("operator")
def execute_script(sid):
    """立即在指定设备上回放脚本（simulator 模式：记设备日志 + 审计）。"""
    s = db.session.get(Script, sid)
    if s is None:
        return jsonify(error="脚本不存在"), 404
    device_ids = (request.get_json(silent=True) or {}).get("device_ids", [])
    if not device_ids:
        return jsonify(error="请选择至少一台设备"), 400

    steps = json.loads(s.steps)
    ok = 0
    failed_ids = []
    for did in device_ids:
        dev = db.session.get(Device, int(did))
        if dev is None:
            failed_ids.append(did)
            continue
        db.session.add(DeviceLog(
            device_id=dev.id, level="info",
            message=f"执行脚本[{s.name}] 共 {len(steps)} 步（模拟）"))
        ok += 1
    db.session.commit()
    failed = len(device_ids) - ok
    if failed > 0:
        raise_alert("operation_failure", "warning",
                    f"脚本[{s.name}] 执行失败 {failed} 台设备（缺失或不可用）",
                    detail={"script": s.name, "failed_device_ids": failed_ids})
    record_audit(g.current_user.id, "execute_script", "script", sid,
                {"name": s.name, "devices": device_ids})
    return jsonify(ok=ok, failed=failed)


def _serialize(s: Script):
    return {
        "id": s.id,
        "name": s.name,
        "steps": json.loads(s.steps) if s.steps else [],
        "owner_id": s.owner_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
