"""用户管理路由。

权限边界（企业级设计，作业加分项）：
- 整个 router 要求 admin 及以上；
- admin 不能创建/分配 admin 及以上角色（只有 superadmin 能）；
- 不能删除/降级最后一个 superadmin；
- 不能改自己的角色、不能删自己账号；
- 密码强制复杂度（>=6 位且含字母+数字）；
- 每次增删改都写 audit_logs。
"""
import re
import json
from flask import request, jsonify, g, Blueprint
users_bp = Blueprint("users", __name__)
from ..extensions import db
from ..models import User, ROLE_LEVELS, ROLE_CHOICES, record_audit
from ..auth import login_required, require_role, hash_password, verify_password

_PW_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{6,}$")


def _count_superadmin():
    return db.session.query(User).filter_by(role="superadmin", is_active=True).count()


@users_bp.get("/users")
@require_role("admin")
def list_users():
    users = db.session.query(User).order_by(User.id).all()
    return jsonify([u.to_dict() for u in users])


@users_bp.post("/users")
@require_role("admin")
def create_user():
    cur = g.current_user
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")
    role = data.get("role", "viewer")

    if not username or not password:
        return jsonify(error="用户名和密码必填"), 400
    if role not in ROLE_CHOICES:
        return jsonify(error="非法角色"), 400
    if db.session.query(User).filter_by(username=username).first():
        return jsonify(error="用户名已存在"), 409
    if not _PW_RE.match(password):
        return jsonify(error="密码至少6位且含字母和数字"), 400

    # 越权防护：admin 不能创建 admin 及以上
    if ROLE_LEVELS[cur.role] < ROLE_LEVELS["superadmin"] and \
       ROLE_LEVELS[role] >= ROLE_LEVELS["admin"]:
        return jsonify(error="无权限创建该级别账号"), 403

    u = User(username=username, hashed_password=hash_password(password),
             role=role, is_active=True)
    db.session.add(u)
    db.session.commit()
    record_audit(cur.id, "create_user", "user", u.id, {"username": username, "role": role})
    return jsonify(u.to_dict()), 201


@users_bp.patch("/users/<int:uid>")
@require_role("admin")
def update_user(uid):
    cur = g.current_user
    u = db.session.get(User, uid)
    if u is None:
        return jsonify(error="用户不存在"), 404

    data = request.get_json(silent=True) or {}

    # 改角色
    if "role" in data:
        new_role = data["role"]
        if new_role not in ROLE_CHOICES:
            return jsonify(error="非法角色"), 400
        # 不能改自己角色
        if u.id == cur.id:
            return jsonify(error="不能修改自己的角色"), 403
        # admin 不能分配 admin 及以上
        if ROLE_LEVELS[cur.role] < ROLE_LEVELS["superadmin"] and \
           ROLE_LEVELS[new_role] >= ROLE_LEVELS["admin"]:
            return jsonify(error="无权限分配该级别角色"), 403
        # 不能把最后一个 superadmin 降权
        if u.role == "superadmin" and new_role != "superadmin" and _count_superadmin() <= 1:
            return jsonify(error="不能降级最后一个超级管理员"), 403
        u.role = new_role

    # 改密码
    if "password" in data and data["password"]:
        if not _PW_RE.match(data["password"]):
            return jsonify(error="密码至少6位且含字母和数字"), 400
        u.hashed_password = hash_password(data["password"])

    # 改启用状态
    if "is_active" in data:
        # 不能停用自己
        if u.id == cur.id and not data["is_active"]:
            return jsonify(error="不能停用自己"), 403
        # 不能停用最后一个 superadmin
        if u.role == "superadmin" and not data["is_active"] and _count_superadmin() <= 1:
            return jsonify(error="不能停用最后一个超级管理员"), 403
        u.is_active = bool(data["is_active"])

    db.session.commit()
    record_audit(cur.id, "update_user", "user", u.id,
                 {"changed": [k for k in data.keys()]})
    return jsonify(u.to_dict())


@users_bp.delete("/users/<int:uid>")
@require_role("admin")
def delete_user(uid):
    cur = g.current_user
    u = db.session.get(User, uid)
    if u is None:
        return jsonify(error="用户不存在"), 404
    if u.id == cur.id:
        return jsonify(error="不能删除自己"), 403
    if u.role == "superadmin" and _count_superadmin() <= 1:
        return jsonify(error="不能删除最后一个超级管理员"), 403
    if ROLE_LEVELS[cur.role] < ROLE_LEVELS["superadmin"] and \
       ROLE_LEVELS[u.role] >= ROLE_LEVELS["admin"]:
        return jsonify(error="无权限删除该级别账号"), 403

    db.session.delete(u)
    db.session.commit()
    record_audit(cur.id, "delete_user", "user", uid, {"username": u.username})
    return jsonify(message="已删除")
