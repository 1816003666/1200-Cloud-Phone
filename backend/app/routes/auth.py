"""鉴权路由：登录、当前用户、登出（无状态，登出由前端清 token）。

登录安全（增强）：
- 连续失败 >=5 次锁定账号 15 分钟；
- 连续失败 >=3 次起要求算术验证码，防暴力撞库。
"""
import random
import uuid
from datetime import timedelta
from flask import request, jsonify, current_app, Blueprint
auth_bp = Blueprint("auth", __name__)
from ..extensions import db
from ..models import User, record_audit, _utcnow
from ..auth import (hash_password, verify_password, create_access_token,
                    _resolve_user, validate_password, ROLE_LEVELS)

# 单进程内存验证码存储：captcha_id -> answer（简单算数题）
_captcha_store = {}
MAX_FAILS = 5
CAPTCHA_AFTER = 3
LOCK_MINUTES = 15


def _gen_captcha():
    a = random.randint(2, 9)
    b = random.randint(2, 9)
    cid = uuid.uuid4().hex[:12]
    _captcha_store[cid] = str(a + b)
    return {"captcha_id": cid, "question": f"{a} + {b} = ?"}


@auth_bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify(error="用户名和密码必填"), 400

    now = _utcnow()
    user = db.session.query(User).filter_by(username=username).first()

    # 1) 锁定检查
    if user is not None and user.locked_until and user.locked_until > now:
        remain = int((user.locked_until - now).total_seconds() // 60) + 1
        return jsonify(error=f"账号已锁定，请 {remain} 分钟后重试"), 423

    # 2) 连续失败达阈值要求验证码（验证码缺失/错误同样计失败，避免无限重试绕过锁定）
    need_captcha = user is not None and (user.failed_attempts or 0) >= CAPTCHA_AFTER
    if need_captcha:
        cid = data.get("captcha_id")
        ans = data.get("captcha")
        bad = True
        if cid and _captcha_store.get(cid) is not None:
            if str(_captcha_store.pop(cid, None)) == str(ans or "").strip():
                bad = False
        if bad:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_FAILS:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_attempts = 0
                db.session.commit()
                return jsonify(error=f"连续失败次数过多，账号已锁定 {LOCK_MINUTES} 分钟"), 423
            db.session.commit()
            return jsonify(error="验证码错误" if cid else "请填写验证码",
                           need_captcha=True, captcha=_gen_captcha()), 401

    # 3) 校验凭据
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        if user is not None:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_FAILS:
                user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                user.failed_attempts = 0
                db.session.commit()
                return jsonify(error=f"连续失败次数过多，账号已锁定 {LOCK_MINUTES} 分钟"), 423
            db.session.commit()
            again = (user.failed_attempts or 0) >= CAPTCHA_AFTER
            return jsonify(error="用户名或密码错误", need_captcha=again,
                           captcha=_gen_captcha() if again else None), 401
        return jsonify(error="用户名或密码错误"), 401

    # 4) 成功：重置计数并签发 token
    user.failed_attempts = 0
    user.locked_until = None
    db.session.commit()
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
