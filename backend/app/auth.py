"""认证与权限核心。

- 密码：pbkdf2_hmac(sha256, 20万轮) + 随机 salt，存 pbkdf2_sha256$轮数$salt$dk
- JWT：HS256，payload={sub:用户id, exp}；从 app.config["JWT_SECRET"] 取密钥
- 依赖：login_required / require_role(min_role) 装饰器

设计要点（面试/作业加分项）：
1. 校验密码用 hmac.compare_digest 防时序攻击；
2. 角色分级 viewer<operator<admin<superadmin，require_role 做最小权限拦截；
3. 解析失败/过期一律 401，权限不足 403，绝不静默放行。
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import request, g, jsonify

from .extensions import db
from .models import User, ROLE_LEVELS


# ----------------------------- 密码哈希 -----------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, dk_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(salt_hex), int(rounds),
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def validate_password(password: str):
    """密码复杂度校验：≥6 位且含字母和数字。返回 (ok:bool, msg:str)。"""
    if not password or len(password) < 6:
        return False, "密码至少 6 位"
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return False, "密码须同时包含字母和数字"
    return True, ""


# ----------------------------- JWT -----------------------------
def create_access_token(user_id: int) -> str:
    from flask import current_app
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=current_app.config["JWT_EXPIRE_HOURS"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def _resolve_user():
    """从 Authorization: Bearer <token> 解析出当前用户，失败返回 None。"""
    from flask import current_app
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        payload = jwt.decode(
            token, current_app.config["JWT_SECRET"], algorithms=["HS256"]
        )
        return db.session.get(User, int(payload["sub"]))
    except Exception:
        return None


# ----------------------------- 装饰器 -----------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = _resolve_user()
        if user is None or not user.is_active:
            return jsonify(error="登录已失效，请重新登录"), 401
        g.current_user = user
        return f(*args, **kwargs)
    return wrapper


def require_role(min_role: str):
    """角色不低于 min_role 才可访问；admin 不能越过 superadmin。"""
    min_lv = ROLE_LEVELS[min_role]

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = _resolve_user()
            if user is None or not user.is_active:
                return jsonify(error="登录已失效，请重新登录"), 401
            if ROLE_LEVELS.get(user.role, 0) < min_lv:
                return jsonify(error="权限不足"), 403
            g.current_user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator
