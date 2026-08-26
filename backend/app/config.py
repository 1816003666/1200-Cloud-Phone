"""应用配置。

读取 .env（python-dotenv）。生产环境务必覆盖下面带 * 的默认值。
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ---- 基础 ----
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    APP_NAME = os.environ.get("APP_NAME", "CloudPhoneBoard")

    # ---- 数据库 ----
    # 默认用 SQLite，便于本地免 Docker 直接跑；生产改 Postgres 连接串
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///cloud_phone.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---- JWT *（生产必须改）----
    JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production-please")
    JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "12"))

    # ---- 设备编排后端 ----
    # simulator = 纯内存 Mock，免 Docker；redroid = 真 Docker Android 容器
    DEVICE_BACKEND = os.environ.get("DEVICE_BACKEND", "simulator")

    # ---- CORS ----
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

    # ---- 文件上传目录（文件管理模块用）----
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")

    # ---- 初始管理员（首次启动 seed 用）----
    SEED_ADMIN_USERNAME = os.environ.get("SEED_ADMIN_USERNAME", "admin")
    SEED_ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Admin@123456")
    SEED_SUPERADMIN_USERNAME = os.environ.get("SEED_SUPERADMIN_USERNAME", "root")
    SEED_SUPERADMIN_PASSWORD = os.environ.get("SEED_SUPERADMIN_PASSWORD", "Root@123456")

    # ---- 告警系统阈值（任务书 #12）----
    ALERT_OFFLINE_SECONDS = int(os.environ.get("ALERT_OFFLINE_SECONDS", "120"))
    ALERT_CPU_LIMIT = float(os.environ.get("ALERT_CPU_LIMIT", "90"))
    ALERT_MEM_LIMIT = float(os.environ.get("ALERT_MEM_LIMIT", "90"))
