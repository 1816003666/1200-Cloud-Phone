"""设备编排抽象层。

- simulator：纯内存 Mock，免 Docker，任意平台可直接跑（开发/演示默认）。
- redroid：真实 Docker Android 容器 + ADB 操控，支持截图、点按、滑动、文本、按键等。

所有设备均绑定到 CLOUD_PHONE_SERVER 指定的云手机服务器，serial 采用 ADB 风格
`server_ip:port`。

redroid 容器通过 SSH 远程管理：创建时在服务器上 docker run，删除时 docker rm -f。
"""
import json
import os
import random
import subprocess
import time
from datetime import datetime, timezone

from flask import current_app

# 内存态：serial -> {status, ip, fingerprint}（simulator 用）
_SIM_STATE: dict[str, dict] = {}
# 已分配的 ADB 端口集合（simulator 用）
_ALLOCATED_PORTS: set[int] = set()


def _now():
    return datetime.now(timezone.utc)


def _server_ip() -> str:
    try:
        return current_app.config["CLOUD_PHONE_SERVER"]
    except RuntimeError:
        import os
        return os.environ.get("CLOUD_PHONE_SERVER", "127.0.0.1")


def _adb_start_port() -> int:
    try:
        return current_app.config["CLOUD_PHONE_ADB_START_PORT"]
    except RuntimeError:
        import os
        return int(os.environ.get("CLOUD_PHONE_ADB_START_PORT", "5555"))


def _adb_path() -> str:
    """获取 adb 可执行文件路径。"""
    try:
        p = current_app.config.get("ADB_PATH", "")
    except RuntimeError:
        p = os.environ.get("ADB_PATH", "")
    if p and os.path.isfile(p):
        return p
    # 常见路径回退
    candidates = [
        r"C:\Users\熏香花朵凛然绽放\Desktop\1200台云手机部署\platform-tools\adb.exe",
        "adb",
    ]
    for c in candidates:
        if c == "adb":
            return "adb"  # 依赖 PATH
        if os.path.isfile(c):
            return c
    return "adb"


def _run_adb(args: list, timeout: int = 15) -> tuple:
    """执行 adb 命令，返回 (returncode, stdout, stderr)。"""
    cmd = [_adb_path()] + args
    try:
        # Windows: CREATE_NO_WINDOW 避免弹出控制台
        creationflags = 0x08000000 if os.name == "nt" else 0
        p = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=creationflags,
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, b"", b"timeout"
    except FileNotFoundError:
        return -1, b"", b"adb not found"


# ---------------------------------------------------------------------------
# Simulator 后端（保留）
# ---------------------------------------------------------------------------
def _alloc_port() -> int:
    port = _adb_start_port()
    while port in _ALLOCATED_PORTS:
        port += 2
    _ALLOCATED_PORTS.add(port)
    return port


def _free_port(port: int):
    _ALLOCATED_PORTS.discard(port)


def _fake_fp():
    return json.dumps({
        "imei": f"{random.randint(10**14, 10**15-1)}",
        "android_id": f"{random.randint(10**15, 10**16-1):x}",
        "model": "Pixel-Cloud",
        "sku": "iOS-skin",
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Redroid / 真实 ADB 后端
# ---------------------------------------------------------------------------
def list_adb_devices() -> list[dict]:
    """列出当前已连接的 ADB 设备（含离线）。"""
    rc, out, err = _run_adb(["devices", "-l"], timeout=10)
    devices = []
    if rc != 0:
        return devices
    text = out.decode("utf-8", errors="replace") if isinstance(out, bytes) else out
    for line in text.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        status = parts[1]
        info = {"serial": serial, "status": status}
        # 解析额外信息 model / device / transport_id
        for p in parts[2:]:
            if ":" in p:
                k, v = p.split(":", 1)
                info[k] = v
        devices.append(info)
    return devices


def adb_connect(serial: str) -> bool:
    """连接一个远程 ADB 设备。"""
    rc, out, err = _run_adb(["connect", serial], timeout=10)
    text = (out + err).decode("utf-8", errors="replace").lower()
    return "connected" in text or "already" in text


def _adb_ascii_dir() -> str:
    """纯 ASCII 临时目录（adb.exe 对含中文/非 ASCII 的本地路径支持不佳）。"""
    d = os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, "adb_tmp")
    os.makedirs(d, exist_ok=True)
    return d


def _adb_ascii_copy(local_path: str) -> str:
    """把本地文件复制到纯 ASCII 临时路径，返回复制后的路径（用完需清理）。"""
    import shutil
    tmp = os.path.join(_adb_ascii_dir(), os.path.basename(local_path))
    shutil.copy2(local_path, tmp)
    return tmp


def push_file_to_device(serial: str, local_path: str, remote_path: str, timeout: int = 180) -> dict:
    """把本地文件真实推送到设备（adb push），返回结果与输出。"""
    import shutil
    try:
        adb_connect(serial)  # 确保已连接（连接会断，需自动重连）
    except Exception:  # noqa: BLE001
        pass
    src = local_path
    try:
        if not _is_ascii_path(local_path):
            src = _adb_ascii_copy(local_path)
        rc, out, err = _run_adb(["-s", serial, "push", src, remote_path], timeout=timeout)
    finally:
        if src != local_path:
            try:
                os.remove(src)
            except OSError:
                pass
    text = (out + err).decode("utf-8", errors="replace").strip()
    return {"ok": rc == 0, "output": text, "remote_path": remote_path}


def pull_file_from_device(serial: str, remote_path: str, local_path: str, timeout: int = 120) -> dict:
    """从设备拉取文件到本地（adb pull）。"""
    import shutil
    try:
        adb_connect(serial)
    except Exception:  # noqa: BLE001
        pass
    dst = local_path
    try:
        if not _is_ascii_path(local_path):
            dst = os.path.join(_adb_ascii_dir(), os.path.basename(local_path) or "pulled.bin")
        rc, out, err = _run_adb(["-s", serial, "pull", remote_path, dst], timeout=timeout)
        if rc == 0 and dst != local_path and os.path.isfile(dst):
            shutil.copy2(dst, local_path)
    finally:
        if dst != local_path:
            try:
                os.remove(dst)
            except OSError:
                pass
    text = (out + err).decode("utf-8", errors="replace").strip()
    return {"ok": rc == 0 and os.path.isfile(local_path), "output": text, "local_path": local_path}


def _is_ascii_path(path: str) -> bool:
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def install_apk_to_device(serial: str, local_path: str, timeout: int = 300) -> dict:
    """把本地 APK 安装到设备（adb install -r 流式安装，路径参数为本机路径）。

    adb install 的路径参数是本地文件路径，会自动流式传输到设备安装，
    无需（也不能）先 push 到 /data/local/tmp。
    """
    import shutil
    src = local_path
    try:
        adb_connect(serial)
    except Exception:  # noqa: BLE001
        pass
    try:
        if not _is_ascii_path(local_path):
            src = _adb_ascii_copy(local_path)
        rc, out, err = _run_adb(["-s", serial, "install", "-r", src], timeout=timeout)
        text = (out + err).decode("utf-8", errors="replace").strip()
        ok = rc == 0 and "success" in text.lower()
        if not ok and not text:
            text = "install 无输出（可能失败）"
        return {"ok": ok, "output": text}
    finally:
        if src != local_path:
            try:
                os.remove(src)
            except OSError:
                pass


def adb_disconnect(serial: str):
    """断开 ADB 设备。"""
    _run_adb(["disconnect", serial], timeout=5)


def get_device_info(serial: str) -> dict:
    """通过 getprop 获取设备信息。"""
    info = {}
    props = [
        ("ro.product.model", "model"),
        ("ro.build.version.release", "android_version"),
        ("ro.build.version.sdk", "sdk"),
        ("ro.product.brand", "brand"),
        ("ro.product.manufacturer", "manufacturer"),
    ]
    for prop, key in props:
        rc, out, _ = _run_adb(["-s", serial, "shell", "getprop", prop], timeout=5)
        val = out.decode("utf-8", errors="replace").strip() if isinstance(out, bytes) else out.strip()
        info[key] = val
    return info


def get_screenshot(serial: str) -> bytes | None:
    """通过 adb exec-out screencap -p 获取设备截图（PNG 字节）。"""
    rc, out, err = _run_adb(["-s", serial, "exec-out", "screencap", "-p"], timeout=20)
    if rc != 0 or not out:
        return None
    # 确保是 PNG（有些设备会输出多余文本）
    if out[:4] != b"\x89PNG":
        # 尝试找到 PNG 起始位置
        idx = out.find(b"\x89PNG")
        if idx >= 0:
            out = out[idx:]
        else:
            return None
    return out


def get_screen_size(serial: str) -> tuple[int, int]:
    """获取设备屏幕物理分辨率 (width, height)。"""
    rc, out, _ = _run_adb(["-s", serial, "shell", "wm", "size"], timeout=5)
    if rc == 0 and out:
        text = out.decode("utf-8", errors="replace").strip()
        # "Physical size: 1080x1920"
        import re
        m = re.search(r"(\d+)x(\d+)", text)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 1080, 1920  # 默认回退


# ADBKeyboard 包探测缓存（避免每次输入都查包）
_ADBKB_CHECK = {}


def _has_adbkeyboard(serial: str) -> bool:
    """检测设备是否已安装 ADBKeyboard（包名 com.android.adbkeyboard）。"""
    if serial not in _ADBKB_CHECK:
        try:
            adb_connect(serial)  # 确保已连接
            rc, out, _ = _run_adb(
                ["-s", serial, "shell", "pm list packages | grep -i adbkeyboard"], timeout=8)
            text = (out or b"").decode("latin-1", "ignore").lower()
            _ADBKB_CHECK[serial] = rc == 0 and "com.android.adbkeyboard" in text
        except Exception:  # noqa: BLE001
            _ADBKB_CHECK[serial] = False
    return _ADBKB_CHECK[serial]


def input_text(serial: str, text: str) -> dict:
    """向设备输入文字。

    优先级：
    0. ADBKeyboard 广播（支持中文，需设备已安装并启用 ADBKeyBoard 输入法）
    1. 纯 ASCII → input text 直接注入
    2. 中文 → 剪贴板粘贴（clipper / service call）回退
    """
    adb_connect(serial)  # 确保 ADB 已连接（连接会断，需自动重连）

    # 方案0: ADBKeyboard —— 直达当前焦点输入框，中文也可靠
    if _has_adbkeyboard(serial):
        escaped = text.replace("'", "'\\''")
        rc, _, err = _run_adb([
            "-s", serial, "shell",
            "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", escaped,
        ], timeout=5)
        if rc == 0:
            return {"ok": True, "method": "adbkeyboard_broadcast", "text": text}

    # 纯 ASCII 直接 input text
    if all(ord(c) < 128 for c in text):
        safe = text.replace(" ", "%s").replace("'", r"\'").replace('"', r'\"')
        rc, out, err = _adb_shell(serial, f"input text \"{safe}\"")
        return {"ok": rc == 0, "method": "input_text", "text": text}

    # 非 ASCII（中文等）：用剪贴板粘贴方案
    # 方案1: Clipper 应用 (am broadcast -a clipper.set)
    import shlex
    escaped = text.replace("'", "'\\''")
    rc1, _, _ = _run_adb([
        "-s", serial, "shell",
        "am", "broadcast", "-a", "clipper.set", "-e", "text", escaped
    ], timeout=5)
    if rc1 == 0:
        # 发送粘贴键
        _adb_shell(serial, "input keyevent 279")  # KEYCODE_PASTE
        return {"ok": True, "method": "clipper_clipboard", "text": text}

    # 方案2: 用 service call 操作剪贴板（部分设备支持）
    # 将文字转成 UTF-16LE hex 用于 service call
    try:
        utf16 = text.encode("utf-16-le")
        hex_str = "".join(f"{b:02x}" for b in utf16)
        # service call clipboard 2 i32 1 i64 0 i64 0 s16 <hex>
        rc2, _, _ = _run_adb([
            "-s", serial, "shell",
            "service", "call", "clipboard", "2", "i32", "1", "i64", "0", "i64", "0", "s16", hex_str
        ], timeout=5)
        if rc2 == 0:
            _adb_shell(serial, "input keyevent 279")
            return {"ok": True, "method": "service_clipboard", "text": text}
    except Exception:
        pass

    # 方案3: 回退到 input text（可能只输出问号，但至少不报错）
    safe = text.replace(" ", "%s")
    _adb_shell(serial, f"input text \"{safe}\"")
    return {"ok": False, "method": "fallback", "text": text,
            "error": "设备不支持中文剪贴板输入，建议安装 Clipper 或 ADBKeyboard"}


def _adb_shell(serial: str, command: str, timeout: int = 10) -> tuple:
    """执行 adb shell 命令。"""
    return _run_adb(["-s", serial, "shell"] + command.split(), timeout=timeout)


def install_apk(serial: str, apk_path: str) -> dict:
    """通过 adb 安装 APK 到指定设备（-r 覆盖安装）。"""
    rc, out, err = _run_adb(["-s", serial, "install", "-r", apk_path], timeout=180)
    ok = rc == 0
    detail = out.decode(errors="ignore").strip() or err.decode(errors="ignore").strip()
    return {"serial": serial, "ok": ok,
            "result": detail or ("installed" if ok else "install failed")}


# ---------------------------------------------------------------------------
# 统一接口
# ---------------------------------------------------------------------------
def create_device(backend: str, name: str, serial: str = None) -> dict:
    """创建设备。

    - simulator：生成 Mock 设备
    - redroid：如果指定 serial 则连接已有设备；否则分配端口并提示需在服务器启动容器
    """
    server = _server_ip()

    if backend == "simulator":
        port = _alloc_port()
        s = f"{server}:{port}"
        state = {
            "status": "running",
            "ip": server,
            "fingerprint": _fake_fp(),
        }
        _SIM_STATE[s] = state
        return {"serial": s, **state}

    elif backend == "redroid":
        # 如果指定了 serial，连接已有设备
        if serial:
            target = serial
            if ":" in target:
                adb_connect(target)
        else:
            # 自动创建：查找可用端口，在服务器上创建 redroid 容器
            if _ssh_enabled():
                port = find_available_adb_port()
                result = create_redroid_container(port)
                if not result["ok"]:
                    return {"serial": "", "status": "error", "ip": _server_ip(),
                            "fingerprint": "", "error": result["error"]}
                target = result["serial"]
            else:
                # SSH 未配置，回退到自动发现已有设备
                devices = list_adb_devices()
                online = [d for d in devices if d["status"] == "device"]
                if online:
                    target = online[0]["serial"]
                else:
                    return {"serial": "", "status": "error", "ip": _server_ip(),
                            "fingerprint": "", "error": "无可用 ADB 设备，请先连接或配置 SSH"}

        # 获取设备信息
        info = get_device_info(target)
        fp = json.dumps({
            "model": info.get("model", "redroid"),
            "android_version": info.get("android_version", "12"),
            "brand": info.get("brand", ""),
            "manufacturer": info.get("manufacturer", ""),
        }, ensure_ascii=False)

        return {
            "serial": target,
            "status": "running",
            "ip": _server_ip(),
            "fingerprint": fp,
        }

    raise ValueError(f"未知后端: {backend}")


def delete_device(backend: str, serial: str):
    """删除设备。simulator 清理内存态，redroid 断开 ADB 并删除服务器容器。"""
    _SIM_STATE.pop(serial, None)
    try:
        port = int(serial.split(":")[-1])
        _free_port(port)
    except (ValueError, IndexError):
        pass
    if backend == "redroid" and ":" in serial:
        # 先断开 ADB
        adb_disconnect(serial)
        # 如果配置了 SSH，删除服务器上的容器
        if _ssh_enabled():
            try:
                port = int(serial.split(":")[-1])
                delete_redroid_container(port)
            except (ValueError, IndexError):
                pass


# ---------------------------------------------------------------------------
# 云手机轮次运行（24h 分 N 轮，每轮结束销毁重建）
# ---------------------------------------------------------------------------
def get_rotation_config():
    """获取轮次运行配置（单行 id=1，不存在则初始化默认值）。"""
    from .extensions import db
    from .models import RotationConfig
    cfg = db.session.get(RotationConfig, 1)
    if cfg is None:
        cfg = RotationConfig(id=1, enabled=False, rounds=4)
        db.session.add(cfg)
        db.session.commit()
        db.session.refresh(cfg)
    return cfg


def rotate_redroid_devices(target_count=None) -> dict:
    """销毁所有 redroid 容器，并按配置数量（devices_per_round）重新创建。

    用于轮次运行模式：每轮结束调用，相当于整批云手机「重置」。
    target_count 不传时使用轮次配置里的 devices_per_round。
    """
    from .extensions import db
    from .models import Device
    if target_count is None:
        cfg = get_rotation_config()
        target_count = cfg.devices_per_round or 2
    target_count = int(target_count)

    devices = db.session.query(Device).filter_by(backend="redroid").all()

    # 1) 销毁旧容器 + 删除 DB 记录
    destroyed = 0
    for d in devices:
        try:
            port = int(d.serial.split(":")[-1])
            delete_redroid_container(port)
        except Exception:
            pass
        try:
            adb_disconnect(d.serial)
        except Exception:
            pass
        db.session.delete(d)
        destroyed += 1
    db.session.commit()

    # 2) 按配置数量重新创建（redroid-1 .. redroid-N）
    created = 0
    failed = 0
    for i in range(target_count):
        name = f"redroid-{i+1}"
        try:
            state = create_device("redroid", name)
            if state.get("serial"):
                nd = Device(
                    name=name, status=state["status"], serial=state["serial"],
                    backend="redroid", ip=state.get("ip", ""),
                    fingerprint=state.get("fingerprint", ""),
                )
                db.session.add(nd)
                created += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    db.session.commit()
    return {"ok": True, "destroyed": destroyed, "created": created,
            "failed": failed, "target": target_count}


def control_device(backend: str, serial: str, action: str, payload: dict) -> dict:
    """单台设备操控。

    simulator：记录日志；
    redroid：通过 ADB 执行真实命令。
    """
    if backend == "simulator":
        return {"serial": serial, "action": action, "ok": True,
                "result": f"[simulator] executed {action} on {serial}"}

    if backend == "redroid":
        adb_connect(serial)  # 确保 ADB 已连接
        try:
            if action == "tap":
                x = payload.get("x", 500)
                y = payload.get("y", 500)
                rc, out, err = _adb_shell(serial, f"input tap {x} {y}")
                return {"serial": serial, "action": action, "ok": rc == 0,
                        "result": f"tap ({x}, {y})"}

            elif action == "swipe":
                x1, y1 = payload.get("x1", 100), payload.get("y1", 500)
                x2, y2 = payload.get("x2", 400), payload.get("y2", 500)
                duration = payload.get("duration", 300)
                _adb_shell(serial, f"input swipe {x1} {y1} {x2} {y2} {duration}")
                return {"serial": serial, "action": action, "ok": True,
                        "result": f"swipe ({x1},{y1}) -> ({x2},{y2})"}

            elif action == "text":
                text = payload.get("text", "")
                result = input_text(serial, text)
                return {"serial": serial, "action": action, **result}

            elif action == "screen_size":
                w, h = get_screen_size(serial)
                return {"serial": serial, "action": action, "ok": True,
                        "width": w, "height": h}

            elif action == "key":
                keycode = payload.get("keycode", 3)  # 默认 HOME
                _adb_shell(serial, f"input keyevent {keycode}")
                return {"serial": serial, "action": action, "ok": True,
                        "result": f"keyevent {keycode}"}

            elif action == "open_url":
                url = payload.get("url", "https://www.baidu.com")
                _adb_shell(serial, f"am start -a android.intent.action.VIEW -d {url}")
                return {"serial": serial, "action": action, "ok": True,
                        "result": f"open {url}"}

            elif action == "install":
                # 需要本地 apk 路径，暂返回提示
                return {"serial": serial, "action": action, "ok": False,
                        "result": "install 需要指定 apk 路径"}

            elif action == "wait":
                seconds = payload.get("seconds", 1)
                time.sleep(min(seconds, 10))
                return {"serial": serial, "action": action, "ok": True,
                        "result": f"waited {seconds}s"}

            elif action == "sequence":
                steps = payload.get("steps", [])
                results = []
                for step in steps:
                    a = step.get("action")
                    if a:
                        r = control_device(backend, serial, a, step)
                        results.append(r)
                return {"serial": serial, "action": action, "ok": True,
                        "result": f"executed {len(results)} steps", "details": results}

            elif action == "screenshot":
                img = get_screenshot(serial)
                return {"serial": serial, "action": action, "ok": img is not None,
                        "result": "screenshot captured" if img else "failed"}

            else:
                return {"serial": serial, "action": action, "ok": False,
                        "result": f"unknown action: {action}"}

        except Exception as e:
            return {"serial": serial, "action": action, "ok": False,
                    "result": f"error: {str(e)}"}

    raise NotImplementedError(f"backend {backend} control 未实现")


# ---------------------------------------------------------------------------
# SSH 远程管理 redroid Docker 容器
# ---------------------------------------------------------------------------
def _ssh_config() -> dict:
    """获取 SSH 配置。"""
    try:
        cfg = current_app.config
    except RuntimeError:
        cfg = os.environ
    return {
        "host": cfg.get("SSH_HOST", ""),
        "port": int(cfg.get("SSH_PORT", 22)),
        "username": cfg.get("SSH_USERNAME", ""),
        "password": cfg.get("SSH_PASSWORD", ""),
        "key_file": cfg.get("SSH_KEY_FILE", ""),
        "image": cfg.get("REDROID_IMAGE", "redroid/redroid:12.0.0_latest"),
        "prefix": cfg.get("REDROID_CONTAINER_PREFIX", "redroid"),
    }


def _ssh_enabled() -> bool:
    """检查 SSH 是否配置可用。"""
    cfg = _ssh_config()
    return bool(cfg["host"] and cfg["username"])


def _ssh_connect():
    """建立 SSH 连接，返回 paramiko.SSHClient。"""
    import paramiko
    cfg = _ssh_config()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs = {
        "hostname": cfg["host"],
        "port": cfg["port"],
        "username": cfg["username"],
        "timeout": 10,
    }
    if cfg["key_file"] and os.path.isfile(cfg["key_file"]):
        connect_kwargs["key_filename"] = cfg["key_file"]
    elif cfg["password"]:
        connect_kwargs["password"] = cfg["password"]
    client.connect(**connect_kwargs)
    return client


def _ssh_exec(client, command: str, timeout: int = 30) -> tuple:
    """执行远程命令，返回 (returncode, stdout, stderr)。"""
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def list_remote_containers() -> list[dict]:
    """列出服务器上所有 redroid 容器。"""
    if not _ssh_enabled():
        return []
    cfg = _ssh_config()
    client = None
    try:
        client = _ssh_connect()
        cmd = f"docker ps -a --filter name={cfg['prefix']} --format '{{{{.Names}}}}|{{{{.Status}}}}|{{{{.Ports}}}}'"
        rc, out, err = _ssh_exec(client, cmd)
        containers = []
        if rc == 0:
            for line in out.strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 1:
                    name = parts[0].strip()
                    # 从容器名提取端口
                    try:
                        port = int(name.split("-")[-1])
                    except (ValueError, IndexError):
                        port = 0
                    containers.append({
                        "name": name,
                        "status": parts[1].strip() if len(parts) > 1 else "",
                        "ports": parts[2].strip() if len(parts) > 2 else "",
                        "port": port,
                    })
        return containers
    except Exception as e:
        current_app.logger.warning(f"列出远程容器失败: {e}")
        return []
    finally:
        if client:
            client.close()


def find_available_adb_port() -> int:
    """查找服务器上可用的 ADB 端口（从 15555 开始递增）。"""
    used = set()
    # 收集已使用的端口
    for d in list_adb_devices():
        try:
            used.add(int(d["serial"].split(":")[-1]))
        except (ValueError, IndexError):
            pass
    for c in list_remote_containers():
        if c["port"]:
            used.add(c["port"])
    port = 15555
    while port in used:
        port += 1
    return port


def list_server_redroid_ports() -> list:
    """扫描服务器上运行中的 redroid 容器，返回其对外 ADB 端口列表。

    以 docker 容器真实运行状态为准（比易失的 adb 连接更可靠），供设备同步使用。
    """
    ports = set()
    for c in list_remote_containers():
        if not c["status"].startswith("Up"):
            continue
        for seg in c["ports"].split(","):
            seg = seg.strip()
            if "->" not in seg or "0.0.0.0:" not in seg:
                continue
            host_part = seg.split("->")[0].strip()
            if ":" in host_part:
                host_part = host_part.rsplit(":", 1)[-1]
            try:
                ports.add(int(host_part))
            except ValueError:
                pass
    return sorted(ports)


def _find_container_by_port(port: int) -> str | None:
    """在服务器上按 ADB 端口查找容器名（兼容 redroid1/redroid2 与 redroid-15555 命名）。"""
    for c in list_remote_containers():
        # ports 字段形如 "0.0.0.0:15555->5555/tcp, [::]:15555->5555/tcp"
        host_ports = set()
        for seg in c["ports"].split(","):
            seg = seg.strip()
            if "->" not in seg:
                continue
            host_part = seg.split("->")[0].strip()
            if ":" in host_part:
                host_part = host_part.rsplit(":", 1)[-1]
            try:
                host_ports.add(int(host_part))
            except ValueError:
                pass
        if port in host_ports:
            return c["name"]
    return None


def _deploy_scrcpy_server(client, port: int, retries: int = 3, delay: float = 6) -> None:
    """在服务器上为新容器部署 scrcpy server（确保 ADB 连接 + push jar + setsid 启动）。

    幂等（jar 已存在则直接启动）；带重试：ADB 未就绪时自动等待重试，
    保证新创建的云手机首次预览即有画面。部署最终失败不阻断主流程。
    """
    jar = current_app.config.get("SCRCPY_SERVER_JAR", "")
    ver = current_app.config.get("SCRCPY_SERVER_VERSION", "1.19-ws8")
    sport = int(current_app.config.get("SCRCPY_SERVER_PORT", 8886))
    if not jar:
        return
    for attempt in range(max(1, retries)):
        try:
            # 每次先确保 ADB 已连接（容器冷启动可能较慢）
            _ssh_exec(client, f"adb connect 127.0.0.1:{port}", timeout=20)
            rc, out, err = _ssh_exec(
                client,
                f"adb -s 127.0.0.1:{port} push {jar} /data/local/tmp/scrcpy-server.jar",
                timeout=60,
            )
            if rc != 0:
                time.sleep(delay)
                continue
            _ssh_exec(
                client,
                f"adb -s 127.0.0.1:{port} shell 'CLASSPATH=/data/local/tmp/scrcpy-server.jar "
                f"setsid nohup app_process / com.genymobile.scrcpy.Server {ver} web ERROR {sport} true >/dev/null 2>&1 &'",
                timeout=30,
            )
            return
        except Exception:
            time.sleep(delay)


def create_redroid_container(port: int) -> dict:
    """在服务器上创建并启动 redroid 容器。"""
    if not _ssh_enabled():
        return {"ok": False, "error": "SSH 未配置"}
    cfg = _ssh_config()
    client = None
    try:
        client = _ssh_connect()
        container_name = _find_container_by_port(port) or f"{cfg['prefix']}-{port}"

        # 检查容器是否已存在
        rc, out, _ = _ssh_exec(client, f"docker inspect {container_name} >/dev/null 2>&1 && echo EXISTS || echo NOTFOUND")
        if "EXISTS" in out:
            # 容器已存在，启动它
            _ssh_exec(client, f"docker start {container_name}")
        else:
            # 创建新容器
            docker_cmd = (
                f"docker run -itd --privileged "
                f"--name {container_name} "
                f"-p {port}:5555 "
                f"-v ~/redroid-data/{port}:/data "
                f"{cfg['image']} "
                f"androidboot.redroid_width=1080 "
                f"androidboot.redroid_height=1920 "
                f"androidboot.redroid_dpi=320"
            )
            rc, out, err = _ssh_exec(client, docker_cmd, timeout=60)
            if rc != 0:
                return {"ok": False, "error": f"docker run 失败: {err.strip() or out.strip()}"}

        # 等待 ADB 就绪（最多 30 秒）
        server = _server_ip()
        serial = f"{server}:{port}"
        # 等待 ADB 就绪（最多 60 秒，每次迭代重连，兼容容器冷启动慢的情况）
        for _ in range(60):
            adb_connect(serial)
            devices = list_adb_devices()
            if any(d["serial"] == serial and d["status"] == "device" for d in devices):
                break
            time.sleep(1)


        # 自动部署 scrcpy server（保证视频投屏可用、画面一致）
        _deploy_scrcpy_server(client, port)

        return {"ok": True, "container": container_name, "port": port, "serial": serial}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if client:
            client.close()


def delete_redroid_container(port: int) -> dict:
    """在服务器上停止并删除 redroid 容器。"""
    if not _ssh_enabled():
        return {"ok": False, "error": "SSH 未配置"}
    cfg = _ssh_config()
    client = None
    try:
        client = _ssh_connect()
        container_name = _find_container_by_port(port) or f"{cfg['prefix']}-{port}"

        # 断开 ADB
        server = _server_ip()
        serial = f"{server}:{port}"
        adb_disconnect(serial)

        # 停止并删除容器
        rc, out, err = _ssh_exec(client, f"docker rm -f {container_name}", timeout=30)
        if rc != 0 and "No such container" not in err:
            return {"ok": False, "error": f"docker rm 失败: {err.strip() or out.strip()}"}

        return {"ok": True, "container": container_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if client:
            client.close()


def container_power(port: int, action: str) -> dict:
    """控制 redroid 容器电源状态。

    action: start | stop | restart
    """
    if not _ssh_enabled():
        return {"ok": False, "error": "SSH 未配置"}
    cfg = _ssh_config()
    client = None
    try:
        client = _ssh_connect()
        container_name = _find_container_by_port(port) or f"{cfg['prefix']}-{port}"
        server = _server_ip()
        serial = f"{server}:{port}"

        if action == "start":
            rc, out, err = _ssh_exec(client, f"docker start {container_name}", timeout=30)
            if rc != 0:
                return {"ok": False, "error": f"开机失败: {err.strip() or out.strip()}"}
            # 等待 ADB 就绪
            adb_connect(serial)
            for _ in range(30):
                devices = list_adb_devices()
                if any(d["serial"] == serial and d["status"] == "device" for d in devices):
                    break
                time.sleep(1)

            # 自动部署 scrcpy server
            _deploy_scrcpy_server(client, port)
            return {"ok": True, "action": "start", "container": container_name}

        elif action == "stop":
            rc, out, err = _ssh_exec(client, f"docker stop {container_name}", timeout=30)
            if rc != 0:
                return {"ok": False, "error": f"关机失败: {err.strip() or out.strip()}"}
            adb_disconnect(serial)
            return {"ok": True, "action": "stop", "container": container_name}

        elif action == "restart":
            rc, out, err = _ssh_exec(client, f"docker restart {container_name}", timeout=60)
            if rc != 0:
                return {"ok": False, "error": f"重启失败: {err.strip() or out.strip()}"}
            # 等待 ADB 就绪
            adb_connect(serial)
            for _ in range(30):
                devices = list_adb_devices()
                if any(d["serial"] == serial and d["status"] == "device" for d in devices):
                    break
                time.sleep(1)

            # 自动部署 scrcpy server
            _deploy_scrcpy_server(client, port)
            return {"ok": True, "action": "restart", "container": container_name}

        return {"ok": False, "error": f"未知操作: {action}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if client:
            client.close()
