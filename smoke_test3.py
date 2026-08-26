"""告警系统（任务书 #12）冒烟测试：用全新 DB 跑通告警产生 + 查询 + 确认/解决 + 权限。"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "backend"))

# 用全新 DB，确保新加的 Device 列 / alerts 表被正确建出
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(BASE, "backend", "instance", "smoke3.db")
os.environ["DEVICE_BACKEND"] = "simulator"

from app import create_app

app = create_app()
client = app.test_client()


def login(username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed {r.status_code} {r.get_data(as_text=True)[:200]}"
    return {"Authorization": "Bearer " + r.get_json()["access_token"]}


print("== 1. admin 登录 ==")
H = login("admin", "Admin@123456")

print("== 2. 创建 redroid 设备（其 control 会抛 NotImplementedError -> 应产生 operation_failure 告警）==")
r = client.post("/api/devices", json={"name": "redroid-1", "backend": "redroid"}, headers=H)
print("   create redroid:", r.status_code)
did = r.get_json().get("id")

print("== 3. 操控 redroid 设备（预期 501 + 自动告警）==")
r = client.post(f"/api/devices/{did}/control/tap", json={}, headers=H)
print("   control redroid:", r.status_code)

print("== 4. 创建并操控 simulator 设备（成功，不应产生告警）==")
r = client.post("/api/devices", json={"name": "sim-1", "backend": "simulator"}, headers=H)
sid = r.get_json().get("id")
client.post(f"/api/devices/{sid}/control/tap", json={}, headers=H)

print("== 5. 查询告警列表 ==")
r = client.get("/api/alerts", headers=H)
alerts = r.get_json()
print("   status:", r.status_code, "count:", len(alerts))
for a in alerts[:5]:
    print("   -", a["id"], a["type"], a["level"], a["status"], "|", a["message"][:46])

assert any(a["type"] == "operation_failure" for a in alerts), "未产生 operation_failure 告警！"

print("== 6. 告警汇总 ==")
r = client.get("/api/alerts/summary", headers=H)
print("   summary:", r.get_json())

print("== 7. 确认 + 解决第一条告警 ==")
if alerts:
    aid = alerts[0]["id"]
    print("   ack:", client.post(f"/api/alerts/{aid}/ack", headers=H).status_code)
    print("   resolve:", client.post(f"/api/alerts/{aid}/resolve", headers=H).status_code)
    r = client.get("/api/alerts", headers=H)
    a0 = [x for x in r.get_json() if x["id"] == aid]
    print("   解决后状态:", a0[0]["status"] if a0 else "n/a")
    assert a0 and a0[0]["status"] == "resolved", "告警未变为 resolved"

print("== 8. viewer 访问告警接口应被拒绝（403）==")
r = client.post("/api/auth/register", json={"username": "viewer1", "password": "viewer1A1"})
print("   register viewer:", r.status_code)
VH = login("viewer1", "viewer1A1")
r = client.get("/api/alerts", headers=VH)
print("   viewer GET /alerts:", r.status_code, "(预期 403)")
assert r.status_code == 403, "viewer 不应能访问告警！"

print("\nSMOKE3 ALL PASS ✅")
