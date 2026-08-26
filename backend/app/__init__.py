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

    # 注册路由蓝图
    from .routes import (auth_bp, users_bp, devices_bp, tasks_bp, dashboard_bp,
                         audit_bp, files_bp, scripts_bp, groups_bp, alerts_bp)
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

    # 确保上传目录存在（文件管理模块）
    import os
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # 启动后台调度器（APScheduler），仅当应用真正运行时拉起
    with app.app_context():
        from . import models  # noqa: F401  确保模型被导入，建表用
        db.create_all()
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
