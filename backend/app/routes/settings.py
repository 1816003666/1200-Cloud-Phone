"""系统设置：告警/巡检阈值等可视化配置（key-value 持久化到 system_configs）。"""
from flask import jsonify, request, Blueprint
settings_bp = Blueprint("settings", __name__)
from ..extensions import db  # noqa: F401
from ..models import SETTING_DEFAULTS, get_setting, set_setting
from ..auth import require_role


@settings_bp.get("/settings")
@require_role("admin")
def list_settings():
    out = {}
    for k, default in SETTING_DEFAULTS.items():
        v = get_setting(k)
        out[k] = default if v is None else _cast(v, default)
    return jsonify(out)


@settings_bp.put("/settings")
@require_role("admin")
def update_settings():
    data = request.get_json(silent=True) or {}
    out = {}
    for k, v in data.items():
        if k not in SETTING_DEFAULTS:
            continue
        set_setting(k, v)
        out[k] = v
    return jsonify(out)


def _cast(v, default):
    try:
        if isinstance(default, int):
            return int(v)
        if isinstance(default, float):
            return float(v)
        if isinstance(default, bool):
            return str(v).lower() in ("1", "true", "yes", "on")
    except (TypeError, ValueError):
        return default
    return v
