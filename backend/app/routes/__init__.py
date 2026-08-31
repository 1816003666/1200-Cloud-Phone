"""蓝图集合。"""
from .auth import auth_bp
from .users import users_bp
from .devices import devices_bp
from .tasks import tasks_bp
from .dashboard import dashboard_bp
from .audit import audit_bp
from .files import files_bp
from .scripts import scripts_bp
from .groups import groups_bp
from .alerts import alerts_bp
from .exports import exports_bp
from .settings import settings_bp

__all__ = [
    "auth_bp",
    "users_bp",
    "devices_bp",
    "tasks_bp",
    "dashboard_bp",
    "audit_bp",
    "files_bp",
    "scripts_bp",
    "groups_bp",
    "alerts_bp",
    "exports_bp",
    "settings_bp",
]
