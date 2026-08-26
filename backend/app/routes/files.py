"""文件管理模块：上传 / 下载 / 浏览 / 删除 / 推送到设备。

权限：上传/删除/推送需要 operator 及以上；浏览登录即可。
推送到设备：因当前为 simulator 模式，实际只做“记录日志 + 审计”，不真正写设备。
"""
import os
import uuid

from flask import request, jsonify, Blueprint, current_app, send_from_directory, g
from werkzeug.utils import secure_filename

files_bp = Blueprint("files", __name__)

from ..extensions import db
from ..models import FileRecord, Device, DeviceLog, record_audit
from ..auth import login_required, require_role


def _upload_dir():
    d = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(d, exist_ok=True)
    return d


@files_bp.post("/files/upload")
@require_role("operator")
def upload():
    if "file" not in request.files:
        return jsonify(error="缺少文件字段 file"), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify(error="文件名不能为空"), 400
    original = f.filename
    # 磁盘名用 uuid 避免重名/中文路径问题，原文件名单独保留展示
    ext = os.path.splitext(original)[1]
    stored = uuid.uuid4().hex + ext
    f.save(os.path.join(_upload_dir(), stored))

    rec = FileRecord(
        filename=original,
        stored_name=stored,
        size=os.path.getsize(os.path.join(_upload_dir(), stored)),
        mime=f.mimetype or "",
        uploader_id=g.current_user.id,
    )
    db.session.add(rec)
    db.session.commit()
    record_audit(g.current_user.id, "upload_file", "file", rec.id,
                {"filename": original, "size": rec.size})
    return jsonify(_serialize(rec)), 201


@files_bp.get("/files")
@login_required
def list_files():
    page = int(request.args.get("page", 1))
    page_size = min(int(request.args.get("page_size", 20)), 100)
    q = (request.args.get("q") or "").strip()
    device_id = request.args.get("device_id")

    query = db.session.query(FileRecord)
    if q:
        query = query.filter(FileRecord.filename.ilike(f"%{q}%"))
    if device_id:
        query = query.filter(FileRecord.target_device_id == int(device_id))
    total = query.count()
    rows = query.order_by(FileRecord.id.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize(r) for r in rows],
    })


@files_bp.get("/files/<int:fid>/download")
@login_required
def download(fid):
    rec = db.session.get(FileRecord, fid)
    if rec is None:
        return jsonify(error="文件不存在"), 404
    return send_from_directory(_upload_dir(), rec.stored_name,
                               as_attachment=True, download_name=rec.filename)


@files_bp.delete("/files/<int:fid>")
@require_role("operator")
def delete_file(fid):
    rec = db.session.get(FileRecord, fid)
    if rec is None:
        return jsonify(error="文件不存在"), 404
    try:
        os.remove(os.path.join(_upload_dir(), rec.stored_name))
    except OSError:
        pass
    db.session.delete(rec)
    db.session.commit()
    record_audit(g.current_user.id, "delete_file", "file", fid,
                {"filename": rec.filename})
    return jsonify(ok=True)


@files_bp.post("/files/<int:fid>/push")
@require_role("operator")
def push_file(fid):
    """把文件推送到指定设备（simulator 模式下为模拟推送：记日志+审计）。"""
    rec = db.session.get(FileRecord, fid)
    if rec is None:
        return jsonify(error="文件不存在"), 404
    device_ids = request.get_json(silent=True) or {}
    ids = device_ids.get("device_ids", [])
    if not ids:
        return jsonify(error="请选择至少一台设备"), 400

    ok = 0
    for did in ids:
        dev = db.session.get(Device, int(did))
        if dev is None:
            continue
        db.session.add(DeviceLog(
            device_id=dev.id, level="info",
            message=f"推送文件 {rec.filename}（模拟）"))
        ok += 1
    rec.target_device_id = int(ids[0])
    db.session.commit()
    record_audit(g.current_user.id, "push_file", "file", fid,
                {"filename": rec.filename, "devices": ids})
    return jsonify(ok=ok, failed=len(ids) - ok)


def _serialize(r: FileRecord):
    return {
        "id": r.id,
        "filename": r.filename,
        "size": r.size,
        "mime": r.mime,
        "uploader_id": r.uploader_id,
        "target_device_id": r.target_device_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
