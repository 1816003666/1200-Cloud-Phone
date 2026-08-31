"""稳定启动入口：debug 开启但禁用自动 reloader，避免反复重启导致进程退出。

用法：python run_stable.py
"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
