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

    # ---- 云手机服务器 ----
    # 承载 redroid 容器 / ADB 设备的物理服务器地址，设备出口 IP 与 ADB serial 均基于此生成
    CLOUD_PHONE_SERVER = os.environ.get("CLOUD_PHONE_SERVER", "127.0.0.1")
    # ADB 起始端口，每台设备递增 1（5555, 5557, ...）
    CLOUD_PHONE_ADB_START_PORT = int(os.environ.get("CLOUD_PHONE_ADB_START_PORT", "5555"))

    # ---- ADB（真实设备操控） ----
    # adb 可执行文件路径；留空则尝试从 PATH 中查找
    ADB_PATH = os.environ.get("ADB_PATH", "")
    # 真实设备截图缓存目录
    SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", "instance/screenshots")

    # ---- SSH（远程管理 redroid Docker 容器） ----
    # 云手机服务器 SSH 连接信息，用于创建/删除 Docker 容器
    SSH_HOST = os.environ.get("SSH_HOST", "")
    SSH_PORT = int(os.environ.get("SSH_PORT", "22"))
    SSH_USERNAME = os.environ.get("SSH_USERNAME", "")
    SSH_PASSWORD = os.environ.get("SSH_PASSWORD", "")
    SSH_KEY_FILE = os.environ.get("SSH_KEY_FILE", "")
    # redroid Docker 镜像
    REDROID_IMAGE = os.environ.get("REDROID_IMAGE", "redroid/redroid:12.0.0_latest")
    # redroid 容器名前缀
    REDROID_CONTAINER_PREFIX = os.environ.get("REDROID_CONTAINER_PREFIX", "redroid")

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
    ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")
    # 告警/巡检相关阈值
    ALERT_CPU_LIMIT = float(os.environ.get("ALERT_CPU_LIMIT", "90"))
    ALERT_MEM_LIMIT = float(os.environ.get("ALERT_MEM_LIMIT", "90"))
