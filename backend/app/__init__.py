"""Flask 应用工厂。

启动：
    flask --app run run   （run.py 里注册了 flask run）
或：
    python run.py
"""
from flask import Flask, jsonify
from .config import Config
from .extensions import db, cors


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 初始化扩展
    db.init_app(app)
    cors.init_app(app, origins=app.config["CORS_ORIGINS"],
                  supports_credentials=True)

    # WebSocket 实时视频流
    from .stream import sock
    sock.init_app(app)

    # 注册路由蓝图
    from .routes import (auth_bp, users_bp, devices_bp, tasks_bp, dashboard_bp,
                         audit_bp, files_bp, scripts_bp, groups_bp, alerts_bp, exports_bp, settings_bp)
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(users_bp, url_prefix="/api")
    app.register_blueprint(devices_bp, url_prefix="/api")
    app.register_blueprint(tasks_bp, url_prefix="/api")
    app.register_blueprint(dashboard_bp, url_prefix="/api")
    app.register_blueprint(audit_bp, url_prefix="/api")
    app.register_blueprint(files_bp, url_prefix="/api")
    app.register_blueprint(scripts_bp, url_prefix="/api")
    app.register_blueprint(groups_bp, url_prefix="/api")
    app.register_blueprint(alerts_bp, url_prefix="/api")
    app.register_blueprint(exports_bp, url_prefix="/api")
    app.register_blueprint(settings_bp, url_prefix="/api")

    # 确保上传目录存在（文件管理模块）
    import os
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # 启动后台调度器（APScheduler），仅当应用真正运行时拉起
    with app.app_context():
        from . import models  # noqa: F401  确保模型被导入，建表用
        db.create_all()
        # 轻量迁移：rotation_config 表补 devices_per_round 列（老库升级）
        from sqlalchemy import text, inspect as sa_inspect
        _insp = sa_inspect(db.engine)
        if "rotation_config" in _insp.get_table_names():
            _cols = {c["name"] for c in _insp.get_columns("rotation_config")}
            if "devices_per_round" not in _cols:
                with db.engine.begin() as _conn:
                    _conn.execute(text(
                        "ALTER TABLE rotation_config "
                        "ADD COLUMN devices_per_round INTEGER DEFAULT 2 NOT NULL"
                    ))
        if "scheduled_tasks" in _insp.get_table_names():
            _tcols = {c["name"] for c in _insp.get_columns("scheduled_tasks")}
            if "cron_expr" not in _tcols:
                with db.engine.begin() as _conn:
                    _conn.execute(text("ALTER TABLE scheduled_tasks ADD COLUMN cron_expr VARCHAR(64) DEFAULT ''"))
        if "users" in _insp.get_table_names():
            _ucols = {c["name"] for c in _insp.get_columns("users")}
            if "failed_attempts" not in _ucols:
                with db.engine.begin() as _conn:
                    _conn.execute(text("ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0"))
            if "locked_until" not in _ucols:
                with db.engine.begin() as _conn:
                    _conn.execute(text("ALTER TABLE users ADD COLUMN locked_until DATETIME"))
        from .seed import seed
        seed()
        from .scheduler import start_scheduler
        start_scheduler(app)

    @app.get("/")
    def root():
        return jsonify(name=app.config["APP_NAME"],
                        backend=app.config["DEVICE_BACKEND"],
                        docs="后端无 Swagger，但路由见 routes/")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", backend=app.config["DEVICE_BACKEND"])

    return app
