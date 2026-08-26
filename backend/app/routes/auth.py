"""鉴权路由：登录、当前用户、登出（无状态，登出由前端清 token）。"""
from flask import request, jsonify, current_app, Blueprint
auth_bp = Blueprint("auth", __name__)
from ..extensions import db
from ..models import User, record_audit
from ..auth import (hash_password, verify_password, create_access_token,
                    _resolve_user, validate_password, ROLE_LEVELS)


@auth_bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify(error="用户名和密码必填"), 400

    user = db.session.query(User).filter_by(username=username).first()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        return jsonify(error="用户名或密码错误"), 401

    token = create_access_token(user.id)
    return jsonify(access_token=token, user=user.to_dict())


@auth_bp.get("/auth/me")
def me():
    user = _resolve_user()
    if user is None or not user.is_active:
        return jsonify(error="登录已失效，请重新登录"), 401
    return jsonify(user.to_dict())


@auth_bp.post("/auth/refresh")
def refresh():
    """用旧 token 换新的（未过期即可）。"""
    user = _resolve_user()
    if user is None or not user.is_active:
        return jsonify(error="登录已失效，请重新登录"), 401
    return jsonify(access_token=create_access_token(user.id))


@auth_bp.post("/auth/register")
def register():
    """自助注册：默认创建 viewer 角色账号，校验密码复杂度后返回 token（自动登录）。

    说明：企业内平台注册通常应仅限管理员开放；此处按任务书「登录/注册页面」
    实现自助注册，默认最低权限 viewer，并在 README 标注生产应改为邀请制。
    """
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")
    if not username:
        return jsonify(error="用户名必填"), 400
    if db.session.query(User).filter_by(username=username).first():
        return jsonify(error="用户名已存在"), 409

    ok, msg = validate_password(password)
    if not ok:
        return jsonify(error=msg), 400

    user = User(username=username, hashed_password=hash_password(password),
                role="viewer", is_active=True)
    db.session.add(user)
    db.session.commit()
    record_audit(user.id, "register_user", "user", user.id,
                {"username": username, "role": "viewer"})
    token = create_access_token(user.id)
    return jsonify(access_token=token, user=user.to_dict()), 201
