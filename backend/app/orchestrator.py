"""设备编排抽象层。

- simulator：纯内存 Mock，免 Docker，任意平台可直接跑（开发/演示默认）。
- redroid：真 Docker Android 容器（需 Docker + adb），本脚手架留好接口，未实现真实调用，
  接入时在此补充 docker SDK / adb 命令即可，路由层无需改动。

这正是 Face-Cloud 的 DeviceBackend 抽象思想：上层路由只依赖接口，换后端只改配置。
"""
import json
import random
from datetime import datetime, timezone

# 内存态：serial -> {status, ip, fingerprint}
_SIM_STATE: dict[str, dict] = {}


def _now():
    return datetime.now(timezone.utc)


def _fake_ip():
    return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _fake_fp():
    return json.dumps({
        "imei": f"{random.randint(10**14, 10**15-1)}",
        "android_id": f"{random.randint(10**15, 10**16-1):x}",
        "model": "Pixel-Cloud",
        "sku": "iOS-skin",
    }, ensure_ascii=False)


def create_device(backend: str, name: str) -> dict:
    serial = f"sim-{random.randint(100000, 999999)}"
    if backend == "simulator":
        state = {"status": "running", "ip": _fake_ip(), "fingerprint": _fake_fp()}
        _SIM_STATE[serial] = state
        return {"serial": serial, **state}
    elif backend == "redroid":
        # TODO: 接入 docker SDK 拉起 redroid 容器 + adb connect
        return {"serial": serial, "status": "creating", "ip": "", "fingerprint": ""}
    raise ValueError(f"未知后端: {backend}")


def delete_device(backend: str, serial: str):
    _SIM_STATE.pop(serial, None)
    # redroid: docker rm + adb disconnect


def control_device(backend: str, serial: str, action: str, payload: dict) -> dict:
    """单台设备操控。simulator 仅记录日志，redroid 走真实 adb。"""
    if backend == "simulator":
        return {"serial": serial, "action": action, "ok": True,
                "result": f"[simulator] executed {action}"}
    # redroid: 映射成 adb 命令执行
    raise NotImplementedError("redroid control 未实现，请接入 adb")
