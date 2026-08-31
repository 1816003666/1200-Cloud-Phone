"""WebSocket 实时视频流端点。

支持两种格式：
  - H.264 裸流（默认）：screenrecord 直出，前端用 WebCodecs/Broadway 解码
  - fMP4（format=fmp4）：screenrecord → ffmpeg 转封装 → 前端 MSE 播放
"""
import os
import subprocess
import threading
import time
from flask import request
from flask_sock import Sock
from .extensions import db
from .models import Device
from . import orchestrator

sock = Sock()

# 活跃流记录：device_id -> {process, thread, clients}
_active_streams = {}
_stream_lock = threading.Lock()


def _ffmpeg_path() -> str:
    """获取 ffmpeg 可执行文件路径。"""
    # 优先使用项目自带的 bin/ffmpeg.exe
    local = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bin", "ffmpeg.exe")
    if os.path.exists(local):
        return local
    # 回退到系统 PATH
    return "ffmpeg"


def _get_serial(device_id: int) -> str | None:
    """根据设备 ID 获取 ADB serial。"""
    d = db.session.get(Device, device_id)
    if d is None or d.backend != "redroid":
        return None
    return d.serial


def _start_screenrecord(serial: str, bitrate: int = 4000000) -> subprocess.Popen:
    """启动 screenrecord H.264 直出进程。"""
    adb = orchestrator._adb_path()
    cmd = [
        adb, "-s", serial, "exec-out",
        "screenrecord",
        "--bit-rate", str(bitrate),
        "--output-format", "h264",
        "-",
    ]
    creationflags = 0x08000000 if os.name == "nt" else 0
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        bufsize=65536,
    )


def _start_fmp4_pipeline(serial: str, bitrate: int = 4000000):
    """启动 screenrecord + ffmpeg 转封装为 fMP4 的管道。

    返回 (screenrecord_proc, ffmpeg_proc)，读取 ffmpeg_proc.stdout 获取 fMP4 数据。
    """
    creationflags = 0x08000000 if os.name == "nt" else 0
    adb = orchestrator._adb_path()

    # 1. screenrecord 输出 H.264 裸流（无缓冲，尽快输出）
    sr_cmd = [
        adb, "-s", serial, "exec-out",
        "screenrecord",
        "--bit-rate", str(bitrate),
        "--output-format", "h264",
        "-",
    ]
    sr_proc = subprocess.Popen(
        sr_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        bufsize=0,
    )

    # 2. ffmpeg 从 stdin 读取 H.264，转封装为 fMP4 输出到 stdout
    ff_cmd = [
        _ffmpeg_path(),
        "-fflags", "+genpts+nobuffer",
        "-flags", "low_delay",
        "-i", "-",
        "-c:v", "copy",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-flush_packets", "1",
        "-",
    ]
    ff_proc = subprocess.Popen(
        ff_cmd,
        stdin=sr_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        bufsize=65536,
    )

    return sr_proc, ff_proc


def _stream_worker(serial: str, bitrate: int, clients: list, fmt: str = "h264"):
    """后台线程：持续启动视频流并将数据广播给所有客户端。

    screenrecord 单次最长 3 分钟，到期后自动重启实现无限流。
    """
    while clients:
        sr_proc = None
        ff_proc = None
        proc = None
        try:
            if fmt == "fmp4":
                sr_proc, ff_proc = _start_fmp4_pipeline(serial, bitrate)
                out_stream = ff_proc.stdout
            else:
                proc = _start_screenrecord(serial, bitrate)
                out_stream = proc.stdout

            # 读取数据，分块发送（使用 read1 避免阻塞）
            while clients:
                try:
                    chunk = out_stream.read1(65536)
                except Exception:
                    chunk = None
                if not chunk:
                    # 无数据时短暂等待，检查进程是否还活着
                    time.sleep(0.01)
                    if fmt == "fmp4":
                        if ff_proc.poll() is not None:
                            break
                    else:
                        if proc.poll() is not None:
                            break
                    continue
                # 广播给所有客户端
                dead = []
                for ws in clients:
                    try:
                        ws.send(chunk)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    if ws in clients:
                        clients.remove(ws)
        except Exception:
            time.sleep(0.5)
        finally:
            # 清理所有进程
            for p in [sr_proc, ff_proc, proc]:
                if p:
                    try:
                        p.kill()
                        p.wait(timeout=2)
                    except Exception:
                        pass
        # 流停止（到期/出错），短暂等待后重启
        time.sleep(0.3)

    # 没有客户端了，清理
    with _stream_lock:
        for did, info in list(_active_streams.items()):
            if info["clients"] is clients and not clients:
                del _active_streams[did]
                break


@sock.route("/ws/devices/<int:device_id>/stream")
def device_stream(ws, device_id):
    """WebSocket 端点：实时视频流。

    连接时可通过 query 参数传递：
      - token: JWT 认证令牌
      - bitrate: 码率（默认 4000000）
      - format: 输出格式，h264（默认）或 fmp4
    """
    # 简单认证：从 query 参数获取 token
    token = request.args.get("token", "")
    if not token:
        ws.close(1008, "missing token")
        return

    # 验证 token
    try:
        from flask import current_app
        import jwt as _jwt
        _jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except Exception:
        ws.close(1008, "invalid token")
        return

    serial = _get_serial(device_id)
    if serial is None:
        ws.close(1008, "device not found or not redroid")
        return

    bitrate = request.args.get("bitrate", type=int) or 4000000
    fmt = request.args.get("format", "h264")
    if fmt not in ("h264", "fmp4"):
        fmt = "h264"

    # 加入/创建流
    with _stream_lock:
        if device_id in _active_streams:
            info = _active_streams[device_id]
            # 如果格式不同，需要重启流
            if info.get("format") != fmt:
                # 标记旧流停止，等待线程退出
                old_clients = info["clients"]
                for c in old_clients:
                    try:
                        c.close()
                    except Exception:
                        pass
                # 等待旧线程退出
                time.sleep(0.5)
                # 创建新流
                clients = [ws]
                info = {"clients": clients, "thread": None, "format": fmt}
                _active_streams[device_id] = info
                t = threading.Thread(
                    target=_stream_worker,
                    args=(serial, bitrate, clients, fmt),
                    daemon=True,
                )
                t.start()
                info["thread"] = t
            else:
                info["clients"].append(ws)
        else:
            clients = [ws]
            info = {"clients": clients, "thread": None, "format": fmt}
            _active_streams[device_id] = info
            # 启动流线程
            t = threading.Thread(
                target=_stream_worker,
                args=(serial, bitrate, clients, fmt),
                daemon=True,
            )
            t.start()
            info["thread"] = t

    try:
        # 保持连接，接收客户端消息（可扩展为控制指令）
        while True:
            msg = ws.receive(timeout=30)
            if msg is None:
                break
    except Exception:
        pass
    finally:
        # 客户端断开，从列表移除
        with _stream_lock:
            if device_id in _active_streams:
                clients = _active_streams[device_id]["clients"]
                if ws in clients:
                    clients.remove(ws)
